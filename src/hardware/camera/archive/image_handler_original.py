"""
Image Handler - Process camera frames and extract ion data.

This module handles:
- Reading raw JPG frames from the camera
- Image processing and ion detection
- Saving processed/labelled frames
- Saving ion position and fit data to JSON

Directory Structure:
    E:/Data/
    ├── jpg_frames/              # Raw frames from camera
    │   └── YYMMDD/
    │       └── frame*.jpg
    ├── jpg_frames_labelled/     # Processed frames with overlays
    │   └── YYMMDD/
    │       └── frame*_labelled.jpg
    └── ion_data/                # Ion position and fit data
        └── YYMMDD/
            └── ion_data_*.json

JSON Format:
    {
        "timestamp": "2026-02-02T14:30:15.123456",
        "frame_number": 1234,
        "ions": {
            "ion_1": {"pos_x": 320.5, "pos_y": 240.3, "sig_x": 15.2, "R_y": 8.7},
            "ion_2": {"pos_x": 350.2, "pos_y": 245.1, "sig_x": 14.8, "R_y": 8.5}
        }
    }
"""

import os
import sys
import json
import time
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np

# Add project root for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Try to import OpenCV
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.warning("OpenCV not available - image processing disabled")

# Try to import scipy for fitting
try:
    from scipy import ndimage
    from scipy.optimize import curve_fit
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("SciPy not available - advanced fitting disabled")


@dataclass
class IonFitResult:
    """Result from fitting a single ion."""
    pos_x: float
    pos_y: float
    sig_x: float  # Gaussian sigma in x
    R_y: float    # SHM turning point in y (or sigma_y)
    amplitude: float
    background: float
    fit_quality: float  # R² or similar metric
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "sig_x": self.sig_x,
            "R_y": self.R_y
        }


@dataclass
class FrameData:
    """Complete data for a processed frame."""
    timestamp: str
    frame_number: int
    ions: Dict[str, Dict[str, float]]
    fit_quality: float
    processing_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "frame_number": self.frame_number,
            "ions": self.ions,
            "fit_quality": self.fit_quality,
            "processing_time_ms": self.processing_time_ms
        }


class ImageHandler:
    """
    Handler for processing camera frames and extracting ion data.
    
    Features:
    - Background subtraction
    - Ion detection via peak finding
    - 2D Gaussian fitting
    - Overlay generation
    - JSON data export
    """
    
    def __init__(self, 
                 raw_frames_path: str = None,
                 labelled_frames_path: str = None,
                 ion_data_path: str = None,
                 roi: Optional[Tuple[int, int, int, int]] = None):
        """
        Initialize image handler.
        
        Args:
            raw_frames_path: Path to raw camera frames
            labelled_frames_path: Path for processed frames with overlays
            ion_data_path: Path for ion data JSON files
            roi: Region of interest (x_start, x_finish, y_start, y_finish)
        """
        self.logger = logging.getLogger("ImageHandler")
        
        # Paths - use defaults if not provided
        if raw_frames_path is None:
            raw_frames_path = os.path.expanduser("~/Data/jpg_frames")
        if labelled_frames_path is None:
            labelled_frames_path = os.path.expanduser("~/Data/jpg_frames_labelled")
        if ion_data_path is None:
            ion_data_path = os.path.expanduser("~/Data/ion_data")
            
        self.raw_frames_path = Path(raw_frames_path)
        self.labelled_frames_path = Path(labelled_frames_path)
        self.ion_data_path = Path(ion_data_path)
        
        # Ensure directories exist
        self._ensure_directories()
        
        # ROI for processing
        self.roi = roi or (180, 220, 425, 495)  # Default ROI
        
        # Processing parameters
        self.filter_radius = 6
        self.threshold_sigma = 3.0  # Threshold for peak detection
        self.max_ions = 5  # Maximum ions to detect
        
        # State
        self.frame_counter = 0
        self.running = False
        self.process_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        
        # Statistics
        self.stats = {
            "frames_processed": 0,
            "ions_detected": 0,
            "processing_errors": 0,
            "last_frame_time": 0.0
        }
        
        self.logger.info("Image Handler initialized")
        self.logger.info(f"  Raw frames: {self.raw_frames_path}")
        self.logger.info(f"  Labelled frames: {self.labelled_frames_path}")
        self.logger.info(f"  Ion data: {self.ion_data_path}")
    
    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        today = datetime.now().strftime("%y%m%d")
        
        for base_path in [self.raw_frames_path, self.labelled_frames_path, self.ion_data_path]:
            path = base_path / today
            path.mkdir(parents=True, exist_ok=True)
    
    def _get_today_path(self, base_path: Path) -> Path:
        """Get today's subdirectory path."""
        today = datetime.now().strftime("%y%m%d")
        path = base_path / today
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def start(self):
        """Start the image processing thread."""
        if self.running:
            return
        
        if not CV2_AVAILABLE:
            self.logger.error("Cannot start: OpenCV not available")
            return
        
        self.running = True
        self.process_thread = threading.Thread(
            target=self._process_loop,
            daemon=True,
            name="ImageHandler"
        )
        self.process_thread.start()
        self.logger.info("Image Handler started")
    
    def stop(self):
        """Stop the image processing thread."""
        self.running = False
        if self.process_thread:
            self.process_thread.join(timeout=5.0)
        self.logger.info("Image Handler stopped")
    
    def _process_loop(self):
        """Main processing loop - watches for new frames."""
        known_files: set = set()
        
        while self.running:
            try:
                # Get today's raw frames directory
                raw_dir = self._get_today_path(self.raw_frames_path)
                
                if not raw_dir.exists():
                    time.sleep(0.5)
                    continue
                
                # Find new frame files
                current_files = set(p.name for p in raw_dir.glob("frame*.jpg"))
                new_files = current_files - known_files
                
                # Process new frames
                for fname in sorted(new_files):
                    filepath = raw_dir / fname
                    self._process_frame(filepath)
                    known_files.add(fname)
                
                # Cleanup old files from known set
                known_files = known_files & current_files
                
                time.sleep(0.1)  # 10 Hz check rate
                
            except Exception as e:
                self.logger.error(f"Processing loop error: {e}")
                time.sleep(1.0)
    
    def _process_frame(self, filepath: Path):
        """
        Process a single frame file.
        
        Args:
            filepath: Path to the JPG frame file
        """
        start_time = time.time()
        
        try:
            # Read image
            frame = cv2.imread(str(filepath), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                self.logger.warning(f"Could not read frame: {filepath}")
                return
            
            # Extract frame number from filename
            # Format: frame{counter}_YYYY-MM-DD_HH-MM-SS_mmmmmm.jpg
            frame_number = self._extract_frame_number(filepath.name)
            
            # Detect and fit ions
            ions = self._detect_ions(frame)
            
            # Create overlay image
            overlay_frame = self._create_overlay(frame, ions)
            
            # Save labelled frame
            labelled_path = self._get_today_path(self.labelled_frames_path)
            labelled_filename = filepath.stem + "_labelled.jpg"
            cv2.imwrite(str(labelled_path / labelled_filename), overlay_frame)
            
            # Save ion data to JSON
            frame_data = FrameData(
                timestamp=datetime.now().isoformat(),
                frame_number=frame_number,
                ions={f"ion_{i+1}": ion.to_dict() for i, ion in enumerate(ions)},
                fit_quality=np.mean([ion.fit_quality for ion in ions]) if ions else 0.0,
                processing_time_ms=(time.time() - start_time) * 1000
            )
            
            self._save_ion_data(frame_data, frame_number)
            
            # Update statistics
            with self.lock:
                self.stats["frames_processed"] += 1
                self.stats["ions_detected"] += len(ions)
                self.stats["last_frame_time"] = time.time()
            
            self.logger.debug(f"Processed frame {frame_number}: {len(ions)} ions detected")
            
        except Exception as e:
            self.logger.error(f"Frame processing error for {filepath}: {e}")
            with self.lock:
                self.stats["processing_errors"] += 1
    
    def _extract_frame_number(self, filename: str) -> int:
        """Extract frame counter from filename."""
        try:
            # Parse format: frame{counter}_YYYY-MM-DD_HH-MM-SS_mmmmmm.jpg
            if filename.startswith("frame"):
                num_str = filename[5:].split("_")[0]
                return int(num_str)
        except:
            pass
        return self.frame_counter
    
    def _detect_ions(self, frame: np.ndarray) -> List[IonFitResult]:
        """
        Detect ions in the frame using peak finding and Gaussian fitting.
        
        Args:
            frame: Grayscale image array
            
        Returns:
            List of ion fit results
        """
        ions = []
        
        try:
            # Extract ROI
            x_start, x_finish, y_start, y_finish = self.roi
            roi_frame = frame[y_start:y_finish, x_start:x_finish]
            
            if roi_frame.size == 0:
                return ions
            
            # Apply Gaussian filter for noise reduction
            if SCIPY_AVAILABLE:
                filtered = ndimage.gaussian_filter(roi_frame.astype(float), 
                                                   sigma=self.filter_radius)
            else:
                # Fallback to OpenCV
                filtered = cv2.GaussianBlur(roi_frame.astype(float), 
                                           (self.filter_radius*2+1, self.filter_radius*2+1), 
                                           self.filter_radius)
            
            # Background estimation
            background = np.median(filtered)
            noise = np.std(filtered)
            
            # Threshold for peak detection
            threshold = background + self.threshold_sigma * noise
            
            # Find local maxima
            if SCIPY_AVAILABLE:
                # Use maximum filter for peak detection
                max_filtered = ndimage.maximum_filter(filtered, size=10)
                peaks = (filtered == max_filtered) & (filtered > threshold)
                peak_coords = np.argwhere(peaks)
            else:
                # Simple threshold-based detection
                _, thresh = cv2.threshold(filtered.astype(np.uint8), 
                                         int(threshold), 255, cv2.THRESH_BINARY)
                # Find contours
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, 
                                              cv2.CHAIN_APPROX_SIMPLE)
                peak_coords = []
                for cnt in contours:
                    M = cv2.moments(cnt)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        peak_coords.append([cy, cx])
                peak_coords = np.array(peak_coords)
            
            # Fit each peak
            for i, (y, x) in enumerate(peak_coords[:self.max_ions]):
                try:
                    # Convert to global coordinates
                    global_x = x + x_start
                    global_y = y + y_start
                    
                    # Extract sub-region for fitting
                    sub_size = 20
                    sub_y_start = max(0, y - sub_size)
                    sub_y_end = min(roi_frame.shape[0], y + sub_size)
                    sub_x_start = max(0, x - sub_size)
                    sub_x_end = min(roi_frame.shape[1], x + sub_size)
                    
                    sub_region = roi_frame[sub_y_start:sub_y_end, 
                                          sub_x_start:sub_x_end]
                    
                    if sub_region.size < 10:
                        continue
                    
                    # Simple moment-based fitting (fast)
                    result = self._fit_gaussian_simple(sub_region, global_x, global_y)
                    if result:
                        ions.append(result)
                    
                except Exception as e:
                    self.logger.debug(f"Ion fit error: {e}")
                    continue
            
            # Sort by x position
            ions.sort(key=lambda ion: ion.pos_x)
            
        except Exception as e:
            self.logger.error(f"Ion detection error: {e}")
        
        return ions
    
    def _fit_gaussian_simple(self, region: np.ndarray, center_x: int, 
                            center_y: int) -> Optional[IonFitResult]:
        """
        Simple Gaussian fit using moments.
        
        Args:
            region: Sub-region around peak
            center_x, center_y: Global center coordinates
            
        Returns:
            IonFitResult or None if fit fails
        """
        try:
            # Calculate moments
            total = region.sum()
            if total <= 0:
                return None
            
            y_indices, x_indices = np.indices(region.shape)
            
            # Centroid (refined position)
            x_mean = (x_indices * region).sum() / total
            y_mean = (y_indices * region).sum() / total
            
            # Width (standard deviation)
            x_var = ((x_indices - x_mean)**2 * region).sum() / total
            y_var = ((y_indices - y_mean)**2 * region).sum() / total
            
            sig_x = np.sqrt(x_var) if x_var > 0 else 1.0
            sig_y = np.sqrt(y_var) if y_var > 0 else 1.0
            
            # Background (minimum value)
            background = region.min()
            
            # Amplitude
            amplitude = region.max() - background
            
            # Fit quality (simple metric based on SNR)
            snr = amplitude / (region.std() + 1e-6)
            fit_quality = min(1.0, snr / 10.0)  # Normalize to [0, 1]
            
            return IonFitResult(
                pos_x=center_x + (x_mean - region.shape[1] / 2),
                pos_y=center_y + (y_mean - region.shape[0] / 2),
                sig_x=sig_x,
                R_y=sig_y * 2.355,  # Convert sigma to FWHM-like R_y
                amplitude=amplitude,
                background=background,
                fit_quality=fit_quality
            )
            
        except Exception as e:
            self.logger.debug(f"Simple fit error: {e}")
            return None
    
    def _create_overlay(self, frame: np.ndarray, 
                       ions: List[IonFitResult]) -> np.ndarray:
        """
        Create overlay image with ion markers.
        
        Args:
            frame: Original grayscale frame
            ions: List of detected ions
            
        Returns:
            Color image with overlays
        """
        # Convert to color
        if len(frame.shape) == 2:
            color_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        else:
            color_frame = frame.copy()
        
        # Draw ROI rectangle
        x_start, x_finish, y_start, y_finish = self.roi
        cv2.rectangle(color_frame, (x_start, y_start), (x_finish, y_finish), 
                     (128, 128, 128), 1)
        
        # Draw ion markers
        for i, ion in enumerate(ions):
            x, y = int(ion.pos_x), int(ion.pos_y)
            
            
            # Draw circle with sigma
            radius = max(5, int(ion.sig_x * 2))
            cv2.circle(color_frame, (x, y), radius, (0, 255, 0), 0.5)
            
            # Label
            label = f"Ion {i+1}"
            cv2.putText(color_frame, label, (x + 15, y - 15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            
            # Parameters
            params_text = f"sx:{ion.sig_x:.1f} sy:{ion.R_y:.1f}"
            cv2.putText(color_frame, params_text, (x + 15, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        cv2.putText(color_frame, timestamp, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Add ion count
        cv2.putText(color_frame, f"Ions: {len(ions)}", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        return color_frame
    
    def _save_ion_data(self, frame_data: FrameData, frame_number: int):
        """
        Save ion data to JSON file.
        
        Args:
            frame_data: Processed frame data
            frame_number: Frame number for filename
        """
        try:
            ion_dir = self._get_today_path(self.ion_data_path)
            
            # Format: ion_data_YYYY-MM-DD_HH-MM-SS_mmmmmm.json
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
            filename = f"ion_data_{timestamp}.json"
            
            filepath = ion_dir / filename
            
            with open(filepath, 'w') as f:
                json.dump(frame_data.to_dict(), f, indent=2)
            
        except Exception as e:
            self.logger.error(f"Failed to save ion data: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics."""
        with self.lock:
            return self.stats.copy()
    
    def get_latest_ion_data(self) -> Optional[Dict[str, Any]]:
        """Get the most recent ion data."""
        try:
            ion_dir = self._get_today_path(self.ion_data_path)
            json_files = sorted(ion_dir.glob("ion_data_*.json"))
            
            if not json_files:
                return None
            
            latest = json_files[-1]
            with open(latest, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            self.logger.error(f"Failed to read latest ion data: {e}")
            return None


# =============================================================================
# STANDALONE PROCESSING
# =============================================================================

def run_image_handler():
    """Run the image handler as a standalone process."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )
    
    handler = ImageHandler()
    handler.start()
    
    try:
        while True:
            time.sleep(1)
            stats = handler.get_statistics()
            print(f"Processed: {stats['frames_processed']}, "
                  f"Ions: {stats['ions_detected']}, "
                  f"Errors: {stats['processing_errors']}")
    except KeyboardInterrupt:
        handler.stop()
        print("\nImage handler stopped")


if __name__ == "__main__":
    run_image_handler()
