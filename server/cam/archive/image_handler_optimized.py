"""
Image Handler - Optimized for Ion Detection

This module handles image processing and ion detection with optimized algorithms:
- Multi-scale peak detection
- Adaptive thresholding
- 2D Gaussian fitting
- Background subtraction
- Ion validation

Directory Structure:
    E:/Data/
    ├── jpg_frames/              # Raw frames from camera
    ├── jpg_frames_labelled/     # Processed frames with overlays
    └── ion_data/                # Ion position and fit data (JSON)
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
    logging.warning("SciPy not available - using fallback fitting")


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
    snr: float  # Signal-to-noise ratio
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "sig_x": self.sig_x,
            "R_y": self.R_y,
            "snr": self.snr
        }


@dataclass
class FrameData:
    """Complete data for a processed frame."""
    timestamp: str
    frame_number: int
    ions: Dict[str, Dict[str, float]]
    fit_quality: float
    processing_time_ms: float
    detection_params: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "frame_number": self.frame_number,
            "ions": self.ions,
            "fit_quality": self.fit_quality,
            "processing_time_ms": self.processing_time_ms,
            "detection_params": self.detection_params
        }


class OptimizedImageHandler:
    """
    Optimized handler for processing camera frames and extracting ion data.
    
    Features:
    - Multi-scale peak detection
    - Adaptive thresholding
    - 2D Gaussian fitting
    - Background subtraction
    - Ion validation (SNR, circularity)
    """
    
    def __init__(self, 
                 raw_frames_path: str = None,
                 labelled_frames_path: str = None,
                 ion_data_path: str = None,
                 roi: Optional[Tuple[int, int, int, int]] = None):
        """
        Initialize image handler with optimized parameters.
        
        Args:
            raw_frames_path: Path to raw camera frames
            labelled_frames_path: Path for processed frames with overlays
            ion_data_path: Path for ion data JSON files
            roi: Region of interest (x_start, x_finish, y_start, y_finish)
        """
        self.logger = logging.getLogger("OptimizedImageHandler")
        
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
        
        # ROI for processing - FULL IMAGE to catch ions anywhere
        # Ions can appear from x=0 to x=500, y=15 to y=298
        self.roi = roi or (0, 500, 10, 300)  # (x_start, x_end, y_start, y_end)
        
        # OPTIMIZED PARAMETERS for better ion detection
        # Multi-scale detection parameters
        self.scales = [3, 5, 7]  # Multiple filter sizes
        self.min_distance = 15  # Minimum pixels between ions
        
        # Adaptive thresholding parameters
        self.threshold_percentile = 99.5  # Detect top 0.5% brightest spots
        self.min_snr = 6.0  # Minimum signal-to-noise ratio
        
        # Ion validation parameters
        self.min_intensity = 35   # Minimum peak intensity
        self.max_intensity = 65000  # Maximum (saturated)
        self.min_sigma = 2.0  # Minimum Gaussian width
        self.max_sigma = 30.0  # Maximum Gaussian width
        self.max_ions = 10  # Maximum ions to detect
        
        # Background subtraction
        self.bg_kernel_size = 15  # Large kernel for background estimation
        
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
        
        self.logger.info("Optimized Image Handler initialized")
        self.logger.info(f"  Raw frames: {self.raw_frames_path}")
        self.logger.info(f"  Labelled frames: {self.labelled_frames_path}")
        self.logger.info(f"  Ion data: {self.ion_data_path}")
        self.logger.info(f"  ROI: {self.roi}")
    
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
            name="OptimizedImageHandler"
        )
        self.process_thread.start()
        self.logger.info("Optimized Image Handler started")
    
    def stop(self):
        """Stop the image processing thread."""
        self.running = False
        if self.process_thread:
            self.process_thread.join(timeout=5.0)
        self.logger.info("Optimized Image Handler stopped")
    
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
    
    def _preprocess_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Preprocess frame with background subtraction and contrast enhancement.
        
        Args:
            frame: Input grayscale frame
            
        Returns:
            Tuple of (processed_frame, background)
        """
        # Convert to grayscale if needed
        if len(frame.shape) == 3:
            if frame.shape[2] == 3:
                frame_gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            else:
                frame_gray = frame[:,:,0]
        else:
            frame_gray = frame
        
        # Convert to float for processing
        frame_float = frame_gray.astype(np.float32)
        
        # Estimate background using blur (faster than median filter)
        bg_kernel = (self.bg_kernel_size, self.bg_kernel_size)
        background = cv2.blur(frame_float, bg_kernel)
        
        # Subtract background
        subtracted = frame_float - background
        
        # Remove negative values
        subtracted = np.maximum(subtracted, 0)
        
        # Normalize for CLAHE
        if subtracted.max() > 0:
            normalized = (subtracted / subtracted.max() * 255).astype(np.uint8)
        else:
            normalized = subtracted.astype(np.uint8)
        
        # Contrast enhancement (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(normalized)
        
        return enhanced, background
    
    def _detect_peaks_multi_scale(self, frame: np.ndarray) -> List[Tuple[int, int, float]]:
        """
        Detect peaks using multi-scale approach.
        
        Args:
            frame: Preprocessed frame
            
        Returns:
            List of (x, y, intensity) peak candidates
        """
        peaks_all = []
        
        for scale in self.scales:
            # Apply Gaussian filter at this scale
            if SCIPY_AVAILABLE:
                filtered = ndimage.gaussian_filter(frame.astype(float), sigma=scale)
            else:
                filtered = cv2.GaussianBlur(frame.astype(float), (scale*2+1, scale*2+1), scale)
            
            # Find local maxima
            if SCIPY_AVAILABLE:
                max_filtered = ndimage.maximum_filter(filtered, size=self.min_distance)
                local_maxima = (filtered == max_filtered)
                
                # Adaptive threshold based on percentile
                threshold = np.percentile(filtered, self.threshold_percentile)
                peaks = local_maxima & (filtered > threshold) & (filtered > self.min_intensity)
                
                # Get coordinates
                coords = np.argwhere(peaks)
                for y, x in coords:
                    peaks_all.append((int(x), int(y), float(filtered[y, x])))
            else:
                # Fallback: simple threshold
                threshold = np.percentile(filtered, self.threshold_percentile)
                _, thresh = cv2.threshold(filtered.astype(np.uint8), 
                                         int(threshold), 255, cv2.THRESH_BINARY)
                
                # Find contours
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, 
                                              cv2.CHAIN_APPROX_SIMPLE)
                for cnt in contours:
                    M = cv2.moments(cnt)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        intensity = float(filtered[cy, cx])
                        if intensity > self.min_intensity:
                            peaks_all.append((cx, cy, intensity))
        
        # Remove duplicates (peaks detected at multiple scales)
        peaks_unique = []
        for x, y, intensity in peaks_all:
            # Check if too close to existing peak
            too_close = False
            for x2, y2, _ in peaks_unique:
                dist = np.sqrt((x - x2)**2 + (y - y2)**2)
                if dist < self.min_distance:
                    too_close = True
                    break
            if not too_close:
                peaks_unique.append((x, y, intensity))
        
        # Sort by intensity (brightest first)
        peaks_unique.sort(key=lambda p: p[2], reverse=True)
        
        # Check for minima between peaks to avoid splitting wide ions
        # If two peaks are close horizontally and there's no minimum between them,
        # it's likely a single wide ion - keep only the brightest
        peaks_final = []
        for x, y, intensity in peaks_unique:
            is_wide_ion = False
            for x2, y2, intensity2 in peaks_final:
                # Check if peaks are close horizontally (within 2x min_distance)
                x_dist = abs(x - x2)
                y_dist = abs(y - y2)
                
                if x_dist < self.min_distance * 2 and y_dist < self.min_distance:
                    # Peaks are close - check for minimum in between along horizontal
                    x_min, x_max = min(x, x2), max(x, x2)
                    y_avg = (y + y2) // 2
                    
                    # Extract horizontal profile at average y
                    if 0 <= y_avg < frame.shape[0] and x_min < x_max:
                        profile = frame[y_avg, x_min:x_max+1]
                        
                        # Check if there's a clear minimum in the middle
                        if len(profile) > 2:
                            mid_idx = len(profile) // 2
                            left_max = np.max(profile[:mid_idx])
                            right_max = np.max(profile[mid_idx:])
                            mid_min = np.min(profile[mid_idx-1:mid_idx+2]) if mid_idx > 0 else profile[mid_idx]
                            
                            # If no clear minimum (mid_min is close to maxima), 
                            # it's likely one wide ion
                            if mid_min > 0.7 * min(left_max, right_max):
                                is_wide_ion = True
                                break
            
            if not is_wide_ion:
                peaks_final.append((x, y, intensity))
        
        return peaks_final[:self.max_ions]
    
    def _fit_2d_gaussian(self, region: np.ndarray, 
                         global_x: int, global_y: int) -> Optional[IonFitResult]:
        """
        Fit 2D Gaussian to region.
        
        Args:
            region: Sub-region around peak
            global_x, global_y: Global center coordinates
            
        Returns:
            IonFitResult or None if fit fails
        """
        try:
            if region.size < 25:  # Need at least 5x5
                return None
            
            # Create coordinate grids
            y_indices, x_indices = np.indices(region.shape)
            
            # Initial guess
            amplitude = region.max() - region.min()
            background = region.min()
            x_center = region.shape[1] / 2
            y_center = region.shape[0] / 2
            sigma_x = 5.0
            sigma_y = 5.0
            
            # 2D Gaussian function
            def gaussian_2d(coords, A, x0, y0, sx, sy, bg):
                x, y = coords
                return A * np.exp(-((x - x0)**2 / (2 * sx**2) + (y - y0)**2 / (2 * sy**2))) + bg
            
            if SCIPY_AVAILABLE:
                try:
                    # Fit Gaussian
                    p0 = [amplitude, x_center, y_center, sigma_x, sigma_y, background]
                    popt, _ = curve_fit(
                        gaussian_2d, 
                        (x_indices, y_indices), 
                        region.ravel(),
                        p0=p0,
                        maxfev=5000
                    )
                    
                    A_fit, x0_fit, y0_fit, sx_fit, sy_fit, bg_fit = popt
                    
                    # Validate fit
                    if not (self.min_sigma <= sx_fit <= self.max_sigma and 
                            self.min_sigma <= sy_fit <= self.max_sigma):
                        return None
                    
                    if A_fit < self.min_intensity:
                        return None
                    
                    # Calculate fit quality (R²)
                    fitted = gaussian_2d((x_indices, y_indices), *popt).reshape(region.shape)
                    ss_res = np.sum((region - fitted) ** 2)
                    ss_tot = np.sum((region - region.mean()) ** 2)
                    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
                    
                    # Calculate SNR
                    noise = np.std(region[region < np.percentile(region, 50)])
                    snr = A_fit / (noise + 1e-6)
                    
                    if snr < self.min_snr:
                        return None
                    
                    # Convert to global coordinates
                    global_pos_x = global_x + (x0_fit - region.shape[1] / 2)
                    global_pos_y = global_y + (y0_fit - region.shape[0] / 2)
                    
                    return IonFitResult(
                        pos_x=global_pos_x,
                        pos_y=global_pos_y,
                        sig_x=sx_fit,
                        R_y=sy_fit * 2.355,  # FWHM
                        amplitude=A_fit,
                        background=bg_fit,
                        fit_quality=max(0.0, min(1.0, r_squared)),
                        snr=snr
                    )
                    
                except Exception as e:
                    self.logger.debug(f"Gaussian fit failed: {e}")
                    return None
            else:
                # Fallback to simple moments
                return self._fit_gaussian_simple(region, global_x, global_y)
                
        except Exception as e:
            self.logger.debug(f"2D fit error: {e}")
            return None
    
    def _fit_gaussian_simple(self, region: np.ndarray, center_x: int, 
                            center_y: int) -> Optional[IonFitResult]:
        """Simple Gaussian fit using moments (fallback)."""
        try:
            total = region.sum()
            if total <= 0:
                return None
            
            y_indices, x_indices = np.indices(region.shape)
            
            # Centroid
            x_mean = (x_indices * region).sum() / total
            y_mean = (y_indices * region).sum() / total
            
            # Width
            x_var = ((x_indices - x_mean)**2 * region).sum() / total
            y_var = ((y_indices - y_mean)**2 * region).sum() / total
            
            sig_x = np.sqrt(x_var) if x_var > 0 else 1.0
            sig_y = np.sqrt(y_var) if y_var > 0 else 1.0
            
            # Validate
            if not (self.min_sigma <= sig_x <= self.max_sigma and 
                    self.min_sigma <= sig_y <= self.max_sigma):
                return None
            
            background = region.min()
            amplitude = region.max() - background
            
            if amplitude < self.min_intensity:
                return None
            
            noise = np.std(region[region < np.percentile(region, 50)])
            snr = amplitude / (noise + 1e-6)
            
            if snr < self.min_snr:
                return None
            
            fit_quality = min(1.0, snr / 20.0)
            
            return IonFitResult(
                pos_x=center_x + (x_mean - region.shape[1] / 2),
                pos_y=center_y + (y_mean - region.shape[0] / 2),
                sig_x=sig_x,
                R_y=sig_y * 2.355,
                amplitude=amplitude,
                background=background,
                fit_quality=fit_quality,
                snr=snr
            )
            
        except Exception as e:
            self.logger.debug(f"Simple fit error: {e}")
            return None
    
    def _detect_ions(self, frame: np.ndarray) -> List[IonFitResult]:
        """
        Detect ions with optimized multi-scale approach.
        
        Args:
            frame: Grayscale image array
            
        Returns:
            List of ion fit results
        """
        ions = []
        
        try:
            # Preprocess frame
            processed, background = self._preprocess_frame(frame)
            
            # Extract ROI
            x_start, x_finish, y_start, y_finish = self.roi
            roi_frame = processed[y_start:y_finish, x_start:x_finish]
            
            if roi_frame.size == 0:
                return ions
            
            # Detect peaks at multiple scales
            peak_candidates = self._detect_peaks_multi_scale(roi_frame)
            
            # Fit each candidate
            for x, y, intensity in peak_candidates:
                # Convert to global coordinates
                global_x = x + x_start
                global_y = y + y_start
                
                # Extract sub-region for fitting
                sub_size = 25
                sub_y_start = max(0, y - sub_size)
                sub_y_end = min(roi_frame.shape[0], y + sub_size)
                sub_x_start = max(0, x - sub_size)
                sub_x_end = min(roi_frame.shape[1], x + sub_size)
                
                sub_region = roi_frame[sub_y_start:sub_y_end, 
                                      sub_x_start:sub_x_end]
                
                if sub_region.size < 25:
                    continue
                
                # Try simple moments-based fit first (faster)
                result = self._fit_gaussian_simple(sub_region, global_x, global_y)
                if result:
                    # Reject ions too close to image edges (likely artifacts)
                    h, w = frame.shape[:2]
                    edge_margin = 20
                    if (edge_margin <= result.pos_x < w - edge_margin and 
                        edge_margin <= result.pos_y < h - edge_margin):
                        ions.append(result)
            
            # Sort by x position for consistent ordering
            ions.sort(key=lambda ion: ion.pos_x)
            
        except Exception as e:
            self.logger.error(f"Ion detection error: {e}")
        
        return ions
    
    def _create_overlay(self, frame: np.ndarray, 
                       ions: List[IonFitResult]) -> np.ndarray:
        """Create overlay image with ion markers and bottom information table (inside frame bottom 30%)."""
        # Normalize frame for color mapping
        if len(frame.shape) == 2:
            # Normalize to 0-255 range for better color mapping
            frame_norm = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            # Apply color map (JET for good contrast)
            color_frame = cv2.applyColorMap(frame_norm, cv2.COLORMAP_JET)
        else:
            color_frame = frame.copy()
        
        h, w = color_frame.shape[:2]
        
        # Draw ROI rectangle
        x_start, x_finish, y_start, y_finish = self.roi
        cv2.rectangle(color_frame, (x_start, y_start), (x_finish, y_finish), 
                     (255, 255, 255), 2)
        
        # Draw ion markers (without text labels)
        for i, ion in enumerate(ions):
            x, y = int(ion.pos_x), int(ion.pos_y)
            
            # Color based on fit quality (brighter colors for better visibility)
            if ion.fit_quality > 0.9:
                color = (0, 255, 0)  # Green - excellent
            elif ion.fit_quality > 0.7:
                color = (0, 255, 255)  # Yellow - good
            else:
                color = (0, 165, 255)  # Orange - fair
            
            # Draw crosshair with thicker lines
            cv2.line(color_frame, (x - 20, y), (x + 20, y), (255, 255, 255), 3)
            cv2.line(color_frame, (x, y - 20), (x, y + 20), (255, 255, 255), 3)
            cv2.line(color_frame, (x - 20, y), (x + 20, y), color, 2)
            cv2.line(color_frame, (x, y - 20), (x, y + 20), color, 2)
            
            # Draw circle with sigma
            radius = max(5, int(ion.sig_x * 2))
            cv2.circle(color_frame, (x, y), radius, (255, 255, 255), 3)
            cv2.circle(color_frame, (x, y), radius, color, 2)
            
            # Small ion number near the crosshair (not the full label)
            cv2.putText(color_frame, str(i+1), (x + 25, y - 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3)
            cv2.putText(color_frame, str(i+1), (x + 25, y - 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Bottom 30% table - inside image
        table_height = int(h * 0.30)
        y_start_table = h - table_height
        
        # Create semi-transparent overlay for bottom panel
        overlay = color_frame.copy()
        cv2.rectangle(overlay, (0, y_start_table), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(color_frame, 0.3, overlay, 0.7, 0, color_frame)
        
        # Draw header line
        cv2.line(color_frame, (10, y_start_table + 25), (w - 10, y_start_table + 25), (100, 100, 100), 1)
        
        # Header text
        header_text = f"Ions: {len(ions)} | ROI: {self.roi}"
        cv2.putText(color_frame, header_text, (10, y_start_table + 18),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        if not ions:
            cv2.putText(color_frame, "No ions detected", (w//2 - 80, y_start_table + table_height//2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)
            return color_frame
        
        # Layout: 6 rows x N columns (one column per ion)
        # Row labels on the left, then one column per ion
        row_labels = ["#", "X (px)", "Y (px)", "SNR", "sig_x", "FQ"]
        label_width = 60
        ion_col_width = max(70, (w - label_width - 20) // max(1, len(ions)))
        
        row_height = min(22, (table_height - 40) // len(row_labels))
        
        # Draw row labels and values
        for row_idx, label in enumerate(row_labels):
            y_pos = y_start_table + 45 + row_idx * row_height
            
            # Row label (left side)
            cv2.putText(color_frame, label, (10, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            
            # Draw values for each ion
            for ion_idx, ion in enumerate(ions):
                x_pos = label_width + 10 + ion_idx * ion_col_width
                
                # Color based on fit quality
                if ion.fit_quality > 0.9:
                    val_color = (0, 255, 0)
                elif ion.fit_quality > 0.7:
                    val_color = (0, 255, 255)
                else:
                    val_color = (0, 165, 255)
                
                # Get value for this row
                if row_idx == 0:
                    value = f"{ion_idx + 1}"
                elif row_idx == 1:
                    value = f"{ion.pos_x:.1f}"
                elif row_idx == 2:
                    value = f"{ion.pos_y:.1f}"
                elif row_idx == 3:
                    value = f"{ion.snr:.0f}"
                elif row_idx == 4:
                    value = f"{ion.sig_x:.2f}"
                else:
                    value = f"{ion.fit_quality:.2f}"
                
                # Center align in column
                cv2.putText(color_frame, value, (x_pos, y_pos),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.45, val_color, 1)
        
        return color_frame
    
    def _process_frame(self, filepath: Path):
        """Process a single frame file."""
        start_time = time.time()
        
        try:
            # Read image
            frame = cv2.imread(str(filepath), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                self.logger.warning(f"Could not read frame: {filepath}")
                return
            
            # Extract frame number
            frame_number = self._extract_frame_number(filepath.name)
            
            # Detect and fit ions
            ions = self._detect_ions(frame)
            
            # Create overlay
            overlay_frame = self._create_overlay(frame, ions)
            
            # Save labelled frame
            labelled_path = self._get_today_path(self.labelled_frames_path)
            labelled_filename = filepath.stem + "_labelled.jpg"
            cv2.imwrite(str(labelled_path / labelled_filename), overlay_frame)
            
            # Save ion data
            frame_data = FrameData(
                timestamp=datetime.now().isoformat(),
                frame_number=frame_number,
                ions={f"ion_{i+1}": ion.to_dict() for i, ion in enumerate(ions)},
                fit_quality=np.mean([ion.fit_quality for ion in ions]) if ions else 0.0,
                processing_time_ms=(time.time() - start_time) * 1000,
                detection_params={
                    "roi": self.roi,
                    "threshold_percentile": self.threshold_percentile,
                    "min_snr": self.min_snr,
                    "scales": self.scales
                }
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
            if filename.startswith("frame"):
                num_str = filename[5:].split("_")[0]
                return int(num_str)
        except:
            pass
        return self.frame_counter
    
    def _save_ion_data(self, frame_data: FrameData, frame_number: int):
        """Save ion data to JSON file."""
        try:
            ion_dir = self._get_today_path(self.ion_data_path)
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


# For backward compatibility, alias to original name
ImageHandler = OptimizedImageHandler


def run_image_handler():
    """Run the optimized image handler as a standalone process."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )
    
    handler = OptimizedImageHandler()
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
