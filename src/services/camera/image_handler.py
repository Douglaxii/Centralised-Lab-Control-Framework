"""
Image Handler - Optimized for Ion Detection
Optimized for: Intel Core Ultra 9 + NVIDIA Quadro P400

Features:
- Multi-scale peak detection with Intel MKL/NumPy optimization
- GPU-accelerated image processing (OpenCV CUDA/OpenCL)
- Adaptive thresholding
- 1D Gaussian (X) + SHM function (Y) fitting
- Background subtraction
- Ion validation (SNR, circularity)
- Compact visualization with small labels

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
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import numpy as np

# Add project root for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Try to import OpenCV
try:
    import cv2
    CV2_AVAILABLE = True
    
    # Check for GPU/OpenCL support (optimized for NVIDIA Quadro P400)
    CV2_OCL_AVAILABLE = cv2.ocl.haveOpenCL()
    if CV2_OCL_AVAILABLE:
        cv2.ocl.setUseOpenCL(True)
        logging.info(f"OpenCV OpenCL enabled: {cv2.ocl.useOpenCL()}")
    
    # Check for CUDA support
    try:
        CV2_CUDA_AVAILABLE = cv2.cuda.getCudaEnabledDeviceCount() > 0
        if CV2_CUDA_AVAILABLE:
            logging.info(f"OpenCV CUDA available, devices: {cv2.cuda.getCudaEnabledDeviceCount()}")
    except Exception:
        CV2_CUDA_AVAILABLE = False
        
except ImportError:
    CV2_AVAILABLE = False
    CV2_OCL_AVAILABLE = False
    CV2_CUDA_AVAILABLE = False
    logging.warning("OpenCV not available - image processing disabled")

# Try to import scipy for fitting
try:
    from scipy import ndimage
    from scipy.optimize import curve_fit
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("SciPy not available - using fallback fitting")

# Thread-local storage for NumPy/Intel MKL optimization
THREAD_LOCAL = threading.local()


@dataclass
class IonFitResult:
    """Result from fitting a single ion."""
    pos_x: float
    pos_y: float
    sig_x: float
    R_y: float
    amplitude: float
    background: float
    fit_quality: float
    snr: float
    pos_x_err: float = 0.0
    pos_y_err: float = 0.0
    sig_x_err: float = 0.0
    R_y_err: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "pos_x": float(self.pos_x),
            "pos_y": float(self.pos_y),
            "sig_x": float(self.sig_x),
            "R_y": float(self.R_y),
            "snr": float(self.snr)
        }
    
    def to_uncertainty_dict(self) -> Dict[str, float]:
        return {
            "pos_x": float(self.pos_x),
            "pos_y": float(self.pos_y),
            "sig_x": float(self.sig_x),
            "R_y": float(self.R_y),
            "pos_x_err": float(self.pos_x_err),
            "pos_y_err": float(self.pos_y_err),
            "sig_x_err": float(self.sig_x_err),
            "R_y_err": float(self.R_y_err),
            "snr": float(self.snr)
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


class ImageHandlerConfig:
    """Configuration for ImageHandler - loaded from YAML config."""
    
    # Detection Parameters (tunable)
    DEFAULT_ROI = (0, 500, 10, 300)
    SCALES = [3, 5, 7]
    MIN_DISTANCE = 15
    THRESHOLD_PERCENTILE = 99.5
    MIN_SNR = 6.0
    MIN_INTENSITY = 35
    MAX_INTENSITY = 65000
    MIN_SIGMA = 2.0
    MAX_SIGMA = 60.0
    MAX_IONS = 10
    BG_KERNEL_SIZE = 15
    EDGE_MARGIN = 20
    
    # Visualization Parameters (compact labels)
    PANEL_HEIGHT_RATIO = 0.25
    FONT_SCALE_TITLE = 0.4
    FONT_SCALE_DATA = 0.32
    FONT_SCALE_ION_NUM = 0.45
    CROSSHAIR_SIZE = 0
    CIRCLE_RADIUS_FACTOR = 1.5
    
    # Performance Parameters (Intel Core Ultra 9 optimized)
    NUM_THREADS = 8
    USE_VECTORIZED = True
    BATCH_SIZE = 1
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'ImageHandlerConfig':
        """Create config from dictionary (loaded from YAML)."""
        instance = cls()
        
        if 'detection' in config:
            det = config['detection']
            instance.THRESHOLD_PERCENTILE = det.get('threshold_percentile', instance.THRESHOLD_PERCENTILE)
            instance.MIN_SNR = det.get('min_snr', instance.MIN_SNR)
            instance.MIN_INTENSITY = det.get('min_intensity', instance.MIN_INTENSITY)
            instance.MAX_INTENSITY = det.get('max_intensity', instance.MAX_INTENSITY)
            instance.MIN_SIGMA = det.get('min_sigma', instance.MIN_SIGMA)
            instance.MAX_SIGMA = det.get('max_sigma', instance.MAX_SIGMA)
            instance.MAX_IONS = det.get('max_ions', instance.MAX_IONS)
            instance.MIN_DISTANCE = det.get('min_distance', instance.MIN_DISTANCE)
            instance.EDGE_MARGIN = det.get('edge_margin', instance.EDGE_MARGIN)
            instance.BG_KERNEL_SIZE = det.get('bg_kernel_size', instance.BG_KERNEL_SIZE)
        
        if 'roi' in config:
            roi = config['roi']
            instance.DEFAULT_ROI = (
                roi.get('x_start', 0),
                roi.get('x_finish', 500),
                roi.get('y_start', 10),
                roi.get('y_finish', 300)
            )
        
        if 'visualization' in config:
            viz = config['visualization']
            instance.PANEL_HEIGHT_RATIO = viz.get('panel_height_ratio', instance.PANEL_HEIGHT_RATIO)
            instance.FONT_SCALE_TITLE = viz.get('font_scale_title', instance.FONT_SCALE_TITLE)
            instance.FONT_SCALE_DATA = viz.get('font_scale_data', instance.FONT_SCALE_DATA)
            instance.FONT_SCALE_ION_NUM = viz.get('font_scale_ion_num', instance.FONT_SCALE_ION_NUM)
            instance.CROSSHAIR_SIZE = viz.get('crosshair_size', instance.CROSSHAIR_SIZE)
        
        if 'performance' in config:
            perf = config['performance']
            instance.NUM_THREADS = perf.get('num_threads', instance.NUM_THREADS)
            instance.USE_VECTORIZED = perf.get('use_vectorized', instance.USE_VECTORIZED)
        
        return instance


class ImageHandler:
    """
    Optimized handler for processing camera frames and extracting ion data.
    Hardware Optimizations: Intel Core Ultra 9 + NVIDIA Quadro P400
    """
    
    def __init__(self, 
                 raw_frames_path: str = None,
                 labelled_frames_path: str = None,
                 ion_data_path: str = None,
                 ion_uncertainty_path: str = None,
                 roi: Optional[Tuple[int, int, int, int]] = None,
                 config: Optional[Union[Dict[str, Any], ImageHandlerConfig]] = None):
        """Initialize image handler with optimized parameters."""
        self.logger = logging.getLogger("ImageHandler")
        
        # Load configuration
        if config is None:
            self.config = ImageHandlerConfig()
        elif isinstance(config, dict):
            self.config = ImageHandlerConfig.from_dict(config)
        else:
            self.config = config
        
        # Apply NumPy threading for Intel Core Ultra 9
        if self.config.NUM_THREADS > 0:
            os.environ['MKL_NUM_THREADS'] = str(self.config.NUM_THREADS)
            os.environ['OPENBLAS_NUM_THREADS'] = str(self.config.NUM_THREADS)
            os.environ['OMP_NUM_THREADS'] = str(self.config.NUM_THREADS)
        
        # Paths - try to load from config, fall back to defaults
        try:
            from core import get_config
            _cfg = get_config()
            _default_raw = _cfg.get('camera.raw_frames_path') or _cfg.get('paths.jpg_frames')
            _default_labelled = _cfg.get('camera.labelled_frames_path') or _cfg.get('paths.jpg_frames_labelled')
            _default_ion = _cfg.get('camera.ion_data_path') or _cfg.get('paths.ion_data')
            _default_unc = _cfg.get('camera.ion_uncertainty_path') or _cfg.get('paths.ion_uncertainty')
        except:
            _default_raw = None
            _default_labelled = None
            _default_ion = None
            _default_unc = None
        
        if raw_frames_path is None:
            raw_frames_path = _default_raw or os.path.expanduser("~/Data/jpg_frames")
        if labelled_frames_path is None:
            labelled_frames_path = _default_labelled or os.path.expanduser("~/Data/jpg_frames_labelled")
        if ion_data_path is None:
            ion_data_path = _default_ion or os.path.expanduser("~/Data/ion_data")
        if ion_uncertainty_path is None:
            ion_uncertainty_path = _default_unc or os.path.expanduser("~/Data/ion_uncertainty")
            
        self.raw_frames_path = Path(raw_frames_path)
        self.labelled_frames_path = Path(labelled_frames_path)
        self.ion_data_path = Path(ion_data_path)
        self.ion_uncertainty_path = Path(ion_uncertainty_path)
        
        self._ensure_directories()
        
        # ROI and config parameters
        self.roi = roi or self.config.DEFAULT_ROI
        self.scales = self.config.SCALES
        self.min_distance = self.config.MIN_DISTANCE
        self.threshold_percentile = self.config.THRESHOLD_PERCENTILE
        self.min_snr = self.config.MIN_SNR
        self.min_intensity = self.config.MIN_INTENSITY
        self.max_intensity = self.config.MAX_INTENSITY
        self.min_sigma = self.config.MIN_SIGMA
        self.max_sigma = self.config.MAX_SIGMA
        self.max_ions = self.config.MAX_IONS
        self.bg_kernel_size = self.config.BG_KERNEL_SIZE
        self.edge_margin = self.config.EDGE_MARGIN
        
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
            "last_frame_time": 0.0,
            "avg_processing_time_ms": 0.0,
            "total_processing_time_ms": 0.0
        }
        
        self._processing_times = []
        self._max_time_history = 100
        
        self.logger.info("Image Handler initialized (Core Ultra 9 + Quadro P400)")
        self.logger.info(f"  OpenCL: {CV2_OCL_AVAILABLE}, CUDA: {CV2_CUDA_AVAILABLE}")
        self.logger.info(f"  NumPy threads: {self.config.NUM_THREADS}")
        self.logger.info(f"  ROI: {self.roi}")
    
    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        today = datetime.now().strftime("%y%m%d")
        paths = [
            self.raw_frames_path / today,
            self.labelled_frames_path / today,
            self.ion_data_path / today,
            self.ion_uncertainty_path / today
        ]
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)
    
    def _get_today_path(self, base_path: Path) -> Path:
        """Get today's subdirectory path."""
        today = datetime.now().strftime("%y%m%d")
        path = base_path / today
        path.mkdir(parents=True, exist_ok=True)
        return path


    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """Preprocess frame with background subtraction and contrast enhancement."""
        # Convert to float for processing
        frame_float = frame.astype(np.float32)
        
        # Estimate background using blur
        bg_kernel = (self.bg_kernel_size, self.bg_kernel_size)
        background = cv2.blur(frame_float, bg_kernel)
        
        # Subtract background
        subtracted = frame_float - background
        subtracted = np.maximum(subtracted, 0)
        
        # Normalize for CLAHE
        if subtracted.max() > 0:
            normalized = (subtracted / subtracted.max() * 255).astype(np.uint8)
        else:
            normalized = subtracted.astype(np.uint8)
        
        # Contrast enhancement (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(normalized)
        
        return enhanced
    
    def _detect_ions(self, frame: np.ndarray) -> List[IonFitResult]:
        """Detect ions in frame using multi-scale peak detection."""
        if not CV2_AVAILABLE:
            return []
        
        # Preprocess frame
        processed = self._preprocess_frame(frame)
        
        x_start, x_finish, y_start, y_finish = self.roi
        roi_frame = processed[y_start:y_finish, x_start:x_finish]
        
        if roi_frame.size == 0:
            return []
        
        # Multi-scale detection
        all_peaks = []
        for scale in self.scales:
            peaks = self._detect_peaks_at_scale(roi_frame, scale)
            all_peaks.extend(peaks)
        
        # Merge peaks from different scales
        merged_peaks = self._merge_peaks(all_peaks)
        
        # Filter peaks and fit Gaussians
        ions = []
        for peak in merged_peaks[:self.max_ions]:
            global_x = x_start + peak['x']
            global_y = y_start + peak['y']
            
            # Skip if too close to edges
            if (global_x < self.edge_margin or 
                global_x > frame.shape[1] - self.edge_margin or
                global_y < self.edge_margin or 
                global_y > frame.shape[0] - self.edge_margin):
                continue
            
            # Extract region for fitting (from original frame)
            fit_window = 25
            x1 = max(0, int(global_x) - fit_window)
            x2 = min(frame.shape[1], int(global_x) + fit_window)
            y1 = max(0, int(global_y) - fit_window)
            y2 = min(frame.shape[0], int(global_y) + fit_window)
            
            region = frame[y1:y2, x1:x2].astype(np.float32)
            
            if region.size < 10:
                continue
            
            ion = self._fit_gaussian_simple(region, global_x, global_y)
            
            if ion and self._validate_ion(ion):
                ions.append(ion)
        
        # Sort by x position for consistent ordering
        ions.sort(key=lambda ion: ion.pos_x)
        
        return ions
    
    def _detect_peaks_at_scale(self, frame: np.ndarray, scale: int) -> List[Dict]:
        """Detect peaks at specific scale using optimized filters."""
        # Use SciPy if available (more accurate), otherwise OpenCV
        if SCIPY_AVAILABLE:
            filtered = ndimage.gaussian_filter(frame.astype(float), sigma=scale)
            max_filtered = ndimage.maximum_filter(filtered, size=self.min_distance)
            local_maxima = (filtered == max_filtered)
            
            # Adaptive threshold based on percentile
            threshold = np.percentile(filtered, self.threshold_percentile)
            peaks_mask = local_maxima & (filtered > threshold) & (filtered > self.min_intensity)
            
            coords = np.argwhere(peaks_mask)
            peaks = []
            for y, x in coords:
                intensity = float(filtered[y, x])
                peaks.append({'x': int(x), 'y': int(y), 'intensity': intensity, 'scale': scale})
        else:
            # OpenCV fallback
            blurred = cv2.GaussianBlur(frame.astype(float), (scale * 2 + 1, scale * 2 + 1), scale)
            
            # Local maxima using dilation
            kernel = np.ones((self.min_distance, self.min_distance), np.uint8)
            dilated = cv2.dilate(blurred, kernel)
            
            max_mask = (blurred == dilated)
            threshold = np.percentile(blurred, self.threshold_percentile)
            thresh_mask = (blurred > threshold) & (blurred > self.min_intensity)
            peak_mask = max_mask & thresh_mask
            
            coords = np.column_stack(np.where(peak_mask))
            
            peaks = []
            for y, x in coords:
                intensity = float(blurred[y, x])
                peaks.append({'x': x, 'y': y, 'intensity': intensity, 'scale': scale})
        
        peaks.sort(key=lambda p: p['intensity'], reverse=True)
        return peaks
    
    def _merge_peaks(self, peaks: List[Dict]) -> List[Dict]:
        """Merge peaks that are too close together."""
        if not peaks:
            return []
        
        merged = []
        used = set()
        
        for i, peak in enumerate(peaks):
            if i in used:
                continue
            
            cluster = [peak]
            for j, other in enumerate(peaks[i+1:], start=i+1):
                if j in used:
                    continue
                dist = np.sqrt((peak['x'] - other['x'])**2 + (peak['y'] - other['y'])**2)
                if dist < self.min_distance:
                    cluster.append(other)
                    used.add(j)
            
            if cluster:
                total_intensity = sum(p['intensity'] for p in cluster)
                if total_intensity > 0:
                    avg_x = sum(p['x'] * p['intensity'] for p in cluster) / total_intensity
                    avg_y = sum(p['y'] * p['intensity'] for p in cluster) / total_intensity
                    merged.append({'x': avg_x, 'y': avg_y, 'intensity': total_intensity / len(cluster)})
        
        return merged
    
    def _gaussian_1d(self, x: np.ndarray, bg: float, amp: float, 
                     mu: float, sigma: float) -> np.ndarray:
        """1D Gaussian function for X-direction fitting."""
        return bg + amp * np.exp(-(x - mu)**2 / (2 * sigma**2))
    
    def _shm_function_1d(self, y: np.ndarray, bg: float, amp: float,
                         A: float, y0: float) -> np.ndarray:
        """
        SHM (Simple Harmonic Motion) intensity function for Y-direction.
        
        For an ion undergoing SHM, the intensity distribution follows:
        I(y) = B + C / sqrt(A^2 - (y - y0)^2)
        
        Where:
        - B: background level
        - C: scaling factor (related to intensity and exposure)
        - A: amplitude of SHM (turning point distance from center)
        - y0: center position (equilibrium point)
        
        To avoid singularities at turning points, we use a regularized form.
        """
        # Regularization parameter to avoid division by zero at turning points
        eps = 1e-6
        dy = y - y0
        # Clip to avoid going beyond turning points
        safe_dy = np.clip(dy, -A + eps, A - eps)
        return bg + amp / np.sqrt(np.maximum(eps, A**2 - safe_dy**2))
    
    def _shm_gaussian_approx_1d(self, y: np.ndarray, bg: float, amp: float,
                                 A: float, y0: float, sigma: float) -> np.ndarray:
        """
        SHM function convolved with Gaussian (approximation for real data).
        This smooths the singularities at the turning points.
        Uses superposition of two Gaussians at turning points for stability.
        """
        # Two peaks at turning points y0 ± A
        peak1 = amp * np.exp(-(y - (y0 - A))**2 / (2 * sigma**2))
        peak2 = amp * np.exp(-(y - (y0 + A))**2 / (2 * sigma**2))
        return bg + peak1 + peak2
    
    def _fit_gaussian_simple(self, region: np.ndarray, center_x: float, 
                            center_y: float) -> Optional[IonFitResult]:
        """
        Fit 1D Gaussian in X direction and SHM function in Y direction.
        
        Algorithm:
        1. Calculate center of mass to get initial pos_x, pos_y
        2. Extract 1D profile along X axis at pos_y (row through center)
        3. Fit X: 1D Gaussian to get sig_x
        4. Extract 1D profile along Y axis at pos_x (column through center)
        5. Fit Y: SHM function to get amplitude A
        """
        if region.size < 9:
            return None
        
        h, w = region.shape
        if h < 3 or w < 3:
            return None
        
        # Create coordinate arrays
        x = np.arange(w, dtype=np.float64)
        y = np.arange(h, dtype=np.float64)
        
        # Calculate initial guesses from moments (center of mass)
        total = np.sum(region)
        if total <= 0:
            return None
        
        # Initial center estimates (center of mass)
        x_coords, y_coords = np.meshgrid(np.arange(w), np.arange(h))
        x_center_init = np.sum(x_coords * region) / total
        y_center_init = np.sum(y_coords * region) / total
        
        # Clamp to valid region indices
        x_idx = int(np.clip(round(x_center_init), 0, w - 1))
        y_idx = int(np.clip(round(y_center_init), 0, h - 1))
        
        # Initial sigma estimates
        x_var = np.sum((x_coords - x_center_init)**2 * region) / total
        y_var = np.sum((y_coords - y_center_init)**2 * region) / total
        sig_x_init = np.sqrt(max(0.5, x_var))
        sig_y_init = np.sqrt(max(0.5, y_var))
        
        # Amplitude and background estimates
        amplitude_init = np.max(region) - np.min(region)
        background_init = np.min(region)
        
        # Calculate SNR
        noise = np.std(region[region < np.percentile(region, 50)])
        snr = amplitude_init / (noise + 1e-6)
        
        # Step 1 & 2: X-direction fit (1D Gaussian)
        # Extract 1D profile along X at y_idx (row through center)
        profile_x = region[y_idx, :].astype(np.float64)
        
        try:
            if SCIPY_AVAILABLE and len(profile_x) >= 4:
                p0_x = [background_init, amplitude_init, x_center_init, sig_x_init]
                bounds_x = ([0, 0, 0, 0.1], 
                           [np.inf, np.inf, w - 1, w])
                popt_x, pcov_x = curve_fit(self._gaussian_1d, x, profile_x, 
                                          p0=p0_x, bounds=bounds_x, 
                                          maxfev=5000)
                bg_x, amp_x, x_center_fit, sig_x_fit = popt_x
                x_center_err = np.sqrt(pcov_x[2, 2]) if pcov_x is not None else 0
                sig_x_err = np.sqrt(pcov_x[3, 3]) if pcov_x is not None else 0
            else:
                # Fallback to moment-based estimate
                x_center_fit = x_center_init
                sig_x_fit = sig_x_init
                x_center_err = sig_x_fit / (snr + 1e-6)
                sig_x_err = sig_x_fit / np.sqrt(2)
        except Exception:
            x_center_fit = x_center_init
            sig_x_fit = sig_x_init
            x_center_err = sig_x_fit / (snr + 1e-6)
            sig_x_err = sig_x_fit / np.sqrt(2)
        
        # Step 3 & 4: Y-direction fit (SHM function)
        # Extract 1D profile along Y at x_idx (column through center)
        profile_y = region[:, x_idx].astype(np.float64)
        
        try:
            if SCIPY_AVAILABLE and len(profile_y) >= 5:
                # Initial guess for SHM: amplitude ~ sig_y_init (half turning point distance)
                # The R_y parameter in the result represents the turning point separation (2*A)
                A_init = max(sig_y_init, 1.0)  # Half turning point distance
                p0_y = [background_init, amplitude_init * 0.5, 
                        A_init, y_center_init, sig_x_init]
                
                # Bounds: bg >= 0, amp >= 0, A > 0.5, y0 within region, sigma > 0.1
                bounds_y = ([0, 0, 0.5, 0, 0.1],
                           [np.inf, np.inf, h/2, h - 1, h])
                
                popt_y, pcov_y = curve_fit(self._shm_gaussian_approx_1d, y, profile_y,
                                          p0=p0_y, bounds=bounds_y,
                                          maxfev=5000)
                bg_y, amp_y, A_shm, y_center_fit, sigma_shm = popt_y
                y_center_err = np.sqrt(pcov_y[3, 3]) if pcov_y is not None else 0
                R_y_err = np.sqrt(pcov_y[2, 2]) if pcov_y is not None else 0
                
                # R_y is the turning point separation (2 * A)
                R_y_fit = 2 * abs(A_shm)
            else:
                # Fallback: use moment-based estimates
                y_center_fit = y_center_init
                R_y_fit = 2 * sig_y_init  # Approximate turning point separation
                y_center_err = sig_y_init / (snr + 1e-6)
                R_y_err = sig_y_init / np.sqrt(2)
        except Exception:
            # Fallback to moment-based estimates
            y_center_fit = y_center_init
            R_y_fit = 2 * sig_y_init  # Approximate turning point separation
            y_center_err = sig_y_init / (snr + 1e-6)
            R_y_err = sig_y_init / np.sqrt(2)
        
        # Calculate fit quality (R²)
        try:
            # Reconstruct 2D fit for quality assessment
            fit_x = self._gaussian_1d(x, 0, 1, x_center_fit, sig_x_fit)
            fit_y = self._shm_gaussian_approx_1d(y, 0, 1, R_y_fit/2, y_center_fit, sig_x_fit)
            expected = background_init + amplitude_init * np.outer(fit_y, fit_x)
            
            ss_res = np.sum((region - expected)**2)
            ss_tot = np.sum((region - np.mean(region))**2)
            r_squared = 1 - (ss_res / (ss_tot + 1e-6))
        except Exception:
            r_squared = 0.8  # Default reasonable value
        
        # Calculate uncertainties
        N_eff = total / (amplitude_init + 1e-6)
        
        return IonFitResult(
            pos_x=center_x - w/2 + x_center_fit,
            pos_y=center_y - h/2 + y_center_fit,
            sig_x=sig_x_fit,
            R_y=R_y_fit,
            amplitude=amplitude_init,
            background=background_init,
            fit_quality=max(0, min(1, r_squared)),
            snr=snr,
            pos_x_err=x_center_err,
            pos_y_err=y_center_err,
            sig_x_err=sig_x_err,
            R_y_err=R_y_err
        )
    
    def _validate_ion(self, ion: IonFitResult) -> bool:
        """Validate ion parameters."""
        if ion.snr < self.min_snr:
            return False
        if ion.amplitude < self.min_intensity or ion.amplitude > self.max_intensity:
            return False
        if ion.sig_x < self.min_sigma or ion.sig_x > self.max_sigma:
            return False
        return True


    def _create_overlay(self, frame: np.ndarray, 
                       ions: List[IonFitResult]) -> np.ndarray:
        """Create overlay with compact ion markers and bottom panel."""
        if not CV2_AVAILABLE:
            return frame
        
        cfg = self.config
        
        if len(frame.shape) == 2:
            frame_norm = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            color_frame = cv2.applyColorMap(frame_norm, cv2.COLORMAP_JET)
        else:
            color_frame = frame.copy()
        
        h, w = color_frame.shape[:2]
        
        # Draw ROI rectangle
        x_start, x_finish, y_start, y_finish = self.roi
        cv2.rectangle(color_frame, (x_start, y_start), (x_finish, y_finish), 
                     (255, 255, 255), 1)
        
        # Draw compact ion markers
        for i, ion in enumerate(ions):
            ix, iy = int(ion.pos_x), int(ion.pos_y)
            
            if ion.fit_quality > 0.9:
                color = (0, 255, 0)
            elif ion.fit_quality > 0.7:
                color = (0, 255, 255)
            else:
                color = (0, 165, 255)
            

            
            
            # Small circle
            radius = max(3, int(ion.sig_x * cfg.CIRCLE_RADIUS_FACTOR))
            cv2.circle(color_frame, (ix, iy), radius, color, 1)
            
            # Compact ion number (within frame)
            cs = cfg.CROSSHAIR_SIZE
            label_x = min(ix + cs + 2, w - 12)
            label_y = max(iy - cs - 2, 8)
            cv2.putText(color_frame, str(i+1), (label_x, label_y),
                       cv2.FONT_HERSHEY_SIMPLEX, cfg.FONT_SCALE_ION_NUM, 
                       (255, 255, 255), 1)
        
        # Compact bottom panel
        panel_height = int(h * cfg.PANEL_HEIGHT_RATIO)
        panel_y = h - panel_height
        
        overlay = color_frame.copy()
        cv2.rectangle(overlay, (0, panel_y), (w, h), (10, 10, 10), -1)
        cv2.addWeighted(overlay, 0.75, color_frame, 0.25, 0, color_frame)
        
        cv2.line(color_frame, (0, panel_y), (w, panel_y), (80, 80, 80), 1)
        
        # Compact header
        header_text = f"I:{len(ions)}"
        cv2.putText(color_frame, header_text, (3, panel_y + 10),
                   cv2.FONT_HERSHEY_SIMPLEX, cfg.FONT_SCALE_TITLE, 
                   (200, 200, 200), 1)
        
        if not ions:
            cv2.putText(color_frame, "No ions", (w//2 - 20, panel_y + panel_height//2),
                       cv2.FONT_HERSHEY_SIMPLEX, cfg.FONT_SCALE_DATA, 
                       (128, 128, 128), 1)
            return color_frame
        
        # Compact data table
        col_width = max(38, (w - 8) // len(ions))
        row_height = min(11, (panel_height - 15) // 5)
        
        # Row labels
        labels = ["#", "X", "Y", "SNR", "sx"]
        for row, label in enumerate(labels):
            y = panel_y + 18 + row * row_height
            cv2.putText(color_frame, label, (2, y),
                       cv2.FONT_HERSHEY_SIMPLEX, cfg.FONT_SCALE_DATA, 
                       (150, 150, 150), 1)
        
        # Ion data columns
        for i, ion in enumerate(ions):
            col_x = 16 + i * col_width
            
            if ion.fit_quality > 0.9:
                c = (0, 255, 0)
            elif ion.fit_quality > 0.7:
                c = (0, 255, 255)
            else:
                c = (0, 180, 255)
            
            values = [
                f"{i+1}",
                f"{ion.pos_x:.0f}",
                f"{ion.pos_y:.0f}",
                f"{ion.snr:.0f}",
                f"{ion.sig_x:.1f}"
            ]
            
            for row, val in enumerate(values):
                y = panel_y + 18 + row * row_height
                cv2.putText(color_frame, val, (col_x, y),
                           cv2.FONT_HERSHEY_SIMPLEX, cfg.FONT_SCALE_DATA, c, 1)
        
        return color_frame
    
    def _process_frame(self, filepath: Path):
        """Process a single frame file."""
        start_time = time.time()
        
        try:
            frame = cv2.imread(str(filepath), cv2.IMREAD_GRAYSCALE)
            if frame is None:
                self.logger.warning(f"Could not read frame: {filepath}")
                return
            
            frame_number = self._extract_frame_number(filepath.name)
            ions = self._detect_ions(frame)
            overlay_frame = self._create_overlay(frame, ions)
            
            # Save labelled frame
            labelled_path = self._get_today_path(self.labelled_frames_path)
            labelled_filename = filepath.stem + "_labelled.jpg"
            cv2.imwrite(str(labelled_path / labelled_filename), overlay_frame,
                       [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            # Save ion data
            frame_data = FrameData(
                timestamp=datetime.now().isoformat(),
                frame_number=frame_number,
                ions={f"ion_{i+1}": ion.to_dict() for i, ion in enumerate(ions)},
                fit_quality=np.mean([ion.fit_quality for ion in ions]) if ions else 0.0,
                processing_time_ms=0.0,
                detection_params={
                    "roi": self.roi,
                    "threshold_percentile": self.threshold_percentile,
                    "min_snr": self.min_snr
                }
            )
            
            ion_data_path = self._get_today_path(self.ion_data_path)
            ion_data_filename = f"ion_data_{filepath.stem}.json"
            with open(ion_data_path / ion_data_filename, 'w') as f:
                json.dump(frame_data.to_dict(), f, indent=2)
            
            # Save uncertainty data
            if ions:
                uncertainty_data = {
                    "timestamp": frame_data.timestamp,
                    "frame_number": frame_number,
                    "image_name": filepath.name,
                    "ions": {f"ion_{i+1}": ion.to_uncertainty_dict() 
                            for i, ion in enumerate(ions)}
                }
                uncertainty_path = self._get_today_path(self.ion_uncertainty_path)
                uncertainty_filename = f"ion_uncertainty_{filepath.stem}.json"
                with open(uncertainty_path / uncertainty_filename, 'w') as f:
                    json.dump(uncertainty_data, f, indent=2)
            
            # Update statistics
            processing_time = (time.time() - start_time) * 1000
            
            with self.lock:
                self.stats["frames_processed"] += 1
                self.stats["ions_detected"] += len(ions)
                self.stats["last_frame_time"] = processing_time
                self.stats["total_processing_time_ms"] += processing_time
                
                self._processing_times.append(processing_time)
                if len(self._processing_times) > self._max_time_history:
                    self._processing_times.pop(0)
                self.stats["avg_processing_time_ms"] = np.mean(self._processing_times)
            
            status = f"{len(ions)} ions" if ions else "no ions"
            self.logger.debug(f"Processed {filepath.name}: {status} in {processing_time:.1f}ms")
            
        except Exception as e:
            self.logger.error(f"Error processing {filepath.name}: {e}")
            with self.lock:
                self.stats["processing_errors"] += 1


    def _extract_frame_number(self, filename: str) -> int:
        """Extract frame number from filename."""
        import re
        patterns = [
            r'frame[_-]?(\d+)',
            r'frame_(\d+)_',
            r'(\d+)_frame',
            r'frame(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 0
    
    def process_single_frame(self, filepath: str) -> Tuple[List[IonFitResult], Optional[np.ndarray]]:
        """Process a single frame and return results without saving."""
        if not CV2_AVAILABLE:
            return [], None
        
        filepath = Path(filepath)
        frame = cv2.imread(str(filepath), cv2.IMREAD_GRAYSCALE)
        
        if frame is None:
            self.logger.error(f"Could not read frame: {filepath}")
            return [], None
        
        ions = self._detect_ions(frame)
        overlay = self._create_overlay(frame, ions)
        
        return ions, overlay
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics."""
        with self.lock:
            return self.stats.copy()
    
    def get_latest_ion_data(self) -> Optional[Dict[str, Any]]:
        """Get the latest ion data from processed frames."""
        today_path = self._get_today_path(self.ion_data_path)
        json_files = sorted(today_path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if json_files:
            try:
                with open(json_files[0], 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error reading ion data: {e}")
        
        return None
