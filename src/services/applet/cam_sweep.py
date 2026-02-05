"""
Camera Sweep Experiment.

This script performs a secular frequency sweep with synchronized camera capture:
1. Reads ion position from the last frame of infinity mode
2. Pauses camera infinity mode
3. Configures camera for N frames with ROI centered on ion position
4. Starts camera recording
5. Runs ARTIQ secular sweep with TTL camera triggers
6. Collects PMT counts and ion position data (sig_x, r_y) for each frequency point
7. Fits Lorentzian to PMT, sig_x, and R_y data
8. Saves sweep data and fit results to JSON in cam_sweep_result folder
9. Restarts camera infinity mode

ROI Selection:
    - Reads ion position from last frame before stopping infinity mode
    - Sets analysis ROI centered on detected ion position
    - Forces single-ion detection regardless of ion size/brightness

Fitting:
    - Fits Lorentzian to PMT vs frequency
    - Fits Lorentzian to sig_x vs frequency  
    - Fits Lorentzian to R_y vs frequency
    - Detects if no clear Lorentzian shape (poor fit quality)
    - Saves fit parameters with uncertainties

Usage:
    python -m applet.experiments.cam_sweep
    # or via controller API
"""

import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

import numpy as np
from scipy.optimize import curve_fit

from .base import BaseExperiment, ExperimentStatus, ExperimentResult


@dataclass
class SweepDataPoint:
    """Single data point from camera sweep."""
    frequency_khz: float
    pmt_counts: int
    sig_x: Optional[float] = None
    r_y: Optional[float] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    frame_number: Optional[int] = None
    timestamp: Optional[str] = None


@dataclass
class LorentzianFitResult:
    """Result of Lorentzian fit."""
    L0: float = 0.0  # Background
    A: float = 0.0   # Amplitude
    f0: float = 0.0  # Center frequency
    FWHM: float = 0.0  # Full width at half maximum
    L0_err: Optional[float] = None
    A_err: Optional[float] = None
    f0_err: Optional[float] = None
    FWHM_err: Optional[float] = None
    r_squared: float = 0.0
    fit_quality: str = "unknown"  # "good", "poor", "failed"
    success: bool = False


@dataclass
class CamSweepResult:
    """Result of camera sweep experiment."""
    frequencies_khz: List[float]
    pmt_counts: List[int]
    sig_x_values: List[Optional[float]]
    r_y_values: List[Optional[float]]
    data_points: List[SweepDataPoint]
    sweep_params: Dict[str, Any]
    pmt_fit: Optional[LorentzianFitResult] = None
    sig_x_fit: Optional[LorentzianFitResult] = None
    r_y_fit: Optional[LorentzianFitResult] = None
    ion_position: Optional[Tuple[float, float]] = None
    data_file: Optional[str] = None


class CamSweepExperiment(BaseExperiment):
    """
    Camera Sweep Experiment.
    
    Performs secular frequency sweep with synchronized camera capture,
    collecting PMT counts and ion position data.
    
    Features:
    - Auto-detects ion position from live view before sweep
    - Sets ROI centered on ion for consistent tracking
    - Fits Lorentzian to PMT, sig_x, and R_y data
    - Detects poor fit quality
    
    Parameters:
        target_frequency_khz: Center frequency for sweep [kHz]
        span_khz: Sweep span [kHz] (±span/2 around target)
        steps: Number of frequency points
        on_time_ms: PMT gate time per point [ms]
        off_time_ms: Delay between points [ms]
        attenuation_db: DDS attenuation [dB]
        exposure_ms: Camera exposure time [ms]
        roi_size: ROI size around ion position [pixels]
    """
    
    def __init__(
        self,
        manager_host: str = "localhost",
        manager_port: int = 5557,
        data_dir: str = "data/cam_sweep_result"
    ):
        super().__init__(
            name="cam_sweep",
            manager_host=manager_host,
            manager_port=manager_port,
            data_dir=data_dir
        )
        
        # Sweep parameters
        self.target_frequency_khz: float = 400.0
        self.span_khz: float = 40.0
        self.steps: int = 41
        self.on_time_ms: float = 100.0
        self.off_time_ms: float = 100.0
        self.attenuation_db: float = 25.0
        
        # Camera parameters
        self.exposure_ms: float = 300.0
        self.roi_size: int = 60  # ROI half-size (total ROI = 2*roi_size)
        
        # Analysis parameters
        self.analysis_roi: Dict[str, int] = {
            "xstart": 180,
            "xfinish": 220,
            "ystart": 425,
            "yfinish": 495,
            "radius": 6
        }
        
        # Ion position (detected before sweep)
        self.ion_position: Optional[Tuple[float, float]] = None
        
        # Results
        self.sweep_result: Optional[CamSweepResult] = None
        
        # Paths for ion data (where ImageHandler saves results)
        self.ion_data_path = Path("E:/Data/ion_data")
        self.camera_frames_path = Path("E:/Data/jpg_frames")
        
        # Fit quality threshold
        self.fit_quality_threshold: float = 0.7  # R² threshold for "good" fit
    
    def configure_sweep(
        self,
        target_frequency_khz: float,
        span_khz: float = 40.0,
        steps: int = 41,
        on_time_ms: float = 100.0,
        off_time_ms: float = 100.0,
        attenuation_db: float = 25.0,
        exposure_ms: float = 300.0,
        roi_size: int = 60
    ):
        """Configure sweep parameters."""
        self.target_frequency_khz = target_frequency_khz
        self.span_khz = span_khz
        self.steps = steps
        self.on_time_ms = on_time_ms
        self.off_time_ms = off_time_ms
        self.attenuation_db = attenuation_db
        self.exposure_ms = exposure_ms
        self.roi_size = roi_size
        
        self.logger.info(f"Sweep configured: {target_frequency_khz}kHz ± {span_khz/2}kHz, "
                        f"{steps} steps, {on_time_ms}ms on/{off_time_ms}ms off, "
                        f"ROI size: {roi_size}px")
    
    def read_last_frame_position(self) -> Optional[Tuple[float, float]]:
        """
        Read ion position from the last frame of infinity mode.
        
        Returns:
            (pos_x, pos_y) or None if unavailable
        """
        self.logger.info("Reading ion position from last frame...")
        
        try:
            # Get today's ion data folder
            today = datetime.now().strftime("%y%m%d")
            ion_data_folder = self.ion_data_path / today
            
            if not ion_data_folder.exists():
                self.logger.warning(f"Ion data folder not found: {ion_data_folder}")
                return None
            
            # Find most recent ion data file
            json_files = sorted(
                ion_data_folder.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not json_files:
                self.logger.warning("No ion data files found")
                return None
            
            # Read the most recent file
            latest_file = json_files[0]
            with open(latest_file, 'r') as f:
                data = json.load(f)
            
            ions = data.get("ions", {})
            if not ions:
                self.logger.warning("No ions detected in last frame")
                return None
            
            # Get the first (and should be only) ion
            first_ion_key = sorted(ions.keys())[0]
            first_ion = ions[first_ion_key]
            
            pos_x = first_ion.get("pos_x")
            pos_y = first_ion.get("pos_y")
            
            if pos_x is not None and pos_y is not None:
                self.logger.info(f"Detected ion position: ({pos_x:.1f}, {pos_y:.1f})")
                return (float(pos_x), float(pos_y))
            else:
                self.logger.warning("No position data in ion data")
                return None
                
        except Exception as e:
            self.logger.error(f"Error reading ion position: {e}")
            return None
    
    def calculate_roi_from_position(self, pos_x: float, pos_y: float) -> Dict[str, int]:
        """
        Calculate analysis ROI centered on ion position.
        
        Args:
            pos_x: Ion X position [pixels]
            pos_y: Ion Y position [pixels]
            
        Returns:
            ROI dictionary for ImageHandler
        """
        # Calculate ROI boundaries
        x_start = max(0, int(pos_x - self.roi_size))
        x_finish = min(1024, int(pos_x + self.roi_size))  # Assuming 1024x1024 sensor
        y_start = max(0, int(pos_y - self.roi_size))
        y_finish = min(1024, int(pos_y + self.roi_size))
        
        # Ensure minimum ROI size
        if x_finish - x_start < 20:
            x_start = max(0, int(pos_x - 30))
            x_finish = min(1024, int(pos_x + 30))
        if y_finish - y_start < 20:
            y_start = max(0, int(pos_y - 30))
            y_finish = min(1024, int(pos_y + 30))
        
        roi = {
            "xstart": x_start,
            "xfinish": x_finish,
            "ystart": y_start,
            "yfinish": y_finish,
            "radius": 6,  # Keep default radius for filtering
            "force_single_ion": True  # Flag to force single-ion detection
        }
        
        self.logger.info(f"Calculated ROI: x=[{x_start}, {x_finish}], y=[{y_start}, {y_finish}]")
        return roi
    
    def stop_camera_inf(self) -> bool:
        """Stop camera infinity mode."""
        self.logger.info("Stopping camera infinity mode...")
        
        response = self.send_to_manager({
            "action": "CAMERA_STOP",
            "source": "EXPERIMENT_CAM_SWEEP"
        })
        
        if response.get("status") == "success":
            self.logger.info("Camera infinity mode stopped")
            time.sleep(1.0)
            return True
        else:
            self.logger.warning(f"Failed to stop camera infinity: {response.get('message')}")
            return False
    
    def start_camera_recording(self, n_frames: int, roi: Dict[str, int]) -> bool:
        """
        Start camera in recording mode with specified ROI.
        
        Args:
            n_frames: Number of frames to capture
            roi: ROI dictionary with xstart, xfinish, ystart, yfinish, radius
            
        Returns:
            True if successful
        """
        self.logger.info(f"Starting camera recording: {n_frames} frames")
        
        # Configure camera settings with ROI
        config_response = self.send_to_manager({
            "action": "CAMERA_SETTINGS",
            "source": "EXPERIMENT_CAM_SWEEP",
            "params": {
                "n_frames": n_frames,
                "exposure_ms": self.exposure_ms,
                "trigger_mode": "extern",
                "analysis_roi": roi,
                "force_single_ion": True  # Ensure single-ion detection
            }
        })
        
        if config_response.get("status") != "success":
            self.logger.error("Failed to configure camera settings")
            return False
        
        time.sleep(0.5)
        
        # Start camera recording
        response = self.send_to_manager({
            "action": "CAMERA_START",
            "source": "EXPERIMENT_CAM_SWEEP",
            "mode": "single",
            "n_frames": n_frames,
            "trigger": False
        })
        
        if response.get("status") == "success":
            self.logger.info("Camera recording started")
            time.sleep(1.0)
            return True
        else:
            self.logger.error(f"Failed to start camera recording: {response.get('message')}")
            return False
    
    def start_camera_inf(self) -> bool:
        """Restart camera infinity mode after sweep."""
        self.logger.info("Restarting camera infinity mode...")
        
        response = self.send_to_manager({
            "action": "CAMERA_START",
            "source": "EXPERIMENT_CAM_SWEEP",
            "mode": "inf",
            "trigger": True
        })
        
        if response.get("status") == "success":
            self.logger.info("Camera infinity mode restarted")
            return True
        else:
            self.logger.error(f"Failed to restart camera infinity: {response.get('message')}")
            return False
    
    def execute_sweep(self) -> Optional[CamSweepResult]:
        """Execute the camera sweep via manager/ARTIQ."""
        self.logger.info("="*60)
        self.logger.info("EXECUTING CAMERA SWEEP")
        self.logger.info("="*60)
        
        sweep_params = {
            "target_frequency_khz": self.target_frequency_khz,
            "span_khz": self.span_khz,
            "steps": self.steps,
            "on_time_ms": self.on_time_ms,
            "off_time_ms": self.off_time_ms,
            "attenuation_db": self.attenuation_db
        }
        
        self.logger.info(f"Sweep parameters: {sweep_params}")
        
        response = self.send_to_manager({
            "action": "CAM_SWEEP",
            "source": "EXPERIMENT_CAM_SWEEP",
            "params": sweep_params,
            "timeout_ms": int((self.on_time_ms + self.off_time_ms) * self.steps + 30000)
        })
        
        if response.get("status") != "success":
            self.logger.error(f"Sweep failed: {response.get('message')}")
            return None
        
        sweep_data = response.get("sweep_data", {})
        frequencies = sweep_data.get("frequencies_khz", [])
        pmt_counts = sweep_data.get("pmt_counts", [])
        
        self.logger.info(f"Sweep completed: {len(frequencies)} points")
        
        time.sleep(2.0)
        
        # Read ion position data from ion_data files
        sig_x_values, r_y_values, pos_x_values, pos_y_values = self._read_ion_data(len(frequencies))
        
        # Build data points
        data_points = []
        for i, freq in enumerate(frequencies):
            point = SweepDataPoint(
                frequency_khz=freq,
                pmt_counts=pmt_counts[i] if i < len(pmt_counts) else 0,
                sig_x=sig_x_values[i] if i < len(sig_x_values) else None,
                r_y=r_y_values[i] if i < len(r_y_values) else None,
                pos_x=pos_x_values[i] if i < len(pos_x_values) else None,
                pos_y=pos_y_values[i] if i < len(pos_y_values) else None,
                frame_number=i
            )
            data_points.append(point)
        
        result = CamSweepResult(
            frequencies_khz=frequencies,
            pmt_counts=pmt_counts,
            sig_x_values=sig_x_values,
            r_y_values=r_y_values,
            data_points=data_points,
            sweep_params=sweep_params,
            ion_position=self.ion_position
        )
        
        return result
    
    def _read_ion_data(self, expected_frames: int) -> tuple:
        """Read ion position data from ImageHandler output."""
        sig_x_values = []
        r_y_values = []
        pos_x_values = []
        pos_y_values = []
        
        try:
            today = datetime.now().strftime("%y%m%d")
            ion_data_folder = self.ion_data_path / today
            
            if not ion_data_folder.exists():
                self.logger.warning(f"Ion data folder not found: {ion_data_folder}")
                return ([None] * expected_frames,) * 4
            
            # Find recent ion data files
            json_files = sorted(
                ion_data_folder.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # Take the most recent files up to expected_frames
            recent_files = json_files[:expected_frames]
            recent_files.reverse()  # Chronological order
            
            self.logger.info(f"Found {len(recent_files)} ion data files")
            
            for filepath in recent_files:
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    ions = data.get("ions", {})
                    if ions:
                        # Get first ion data (should be only one due to ROI)
                        first_ion_key = sorted(ions.keys())[0]
                        first_ion = ions[first_ion_key]
                        
                        sig_x_values.append(first_ion.get("sig_x"))
                        r_y_values.append(first_ion.get("R_y"))
                        pos_x_values.append(first_ion.get("pos_x"))
                        pos_y_values.append(first_ion.get("pos_y"))
                    else:
                        sig_x_values.append(None)
                        r_y_values.append(None)
                        pos_x_values.append(None)
                        pos_y_values.append(None)
                        
                except Exception as e:
                    self.logger.debug(f"Error reading {filepath}: {e}")
                    sig_x_values.append(None)
                    r_y_values.append(None)
                    pos_x_values.append(None)
                    pos_y_values.append(None)
            
            # Pad with None if we didn't get enough frames
            while len(sig_x_values) < expected_frames:
                sig_x_values.append(None)
                r_y_values.append(None)
                pos_x_values.append(None)
                pos_y_values.append(None)
                
        except Exception as e:
            self.logger.error(f"Error reading ion data: {e}")
            return ([None] * expected_frames,) * 4
        
        return (
            sig_x_values[:expected_frames],
            r_y_values[:expected_frames],
            pos_x_values[:expected_frames],
            pos_y_values[:expected_frames]
        )
    
    def lorentzian(self, f: np.ndarray, L0: float, A: float, f0: float, FWHM: float) -> np.ndarray:
        """
        Lorentzian function for fitting.
        
        L(f) = L0 + A/π * ((0.5*FWHM)^2 / ((f-f0)^2 + (0.5*FWHM)^2))
        """
        return L0 + A / np.pi * ((0.5 * FWHM)**2 / ((f - f0)**2 + (0.5 * FWHM)**2))
    
    def fit_lorentzian(self, frequencies: List[float], values: List[float], 
                       label: str = "data") -> LorentzianFitResult:
        """
        Fit Lorentzian to data.
        
        Args:
            frequencies: Frequency array [kHz]
            values: Data values to fit
            label: Label for logging
            
        Returns:
            LorentzianFitResult with fit parameters
        """
        # Filter out None values
        valid_pairs = [(f, v) for f, v in zip(frequencies, values) if v is not None]
        if len(valid_pairs) < 10:
            self.logger.warning(f"Not enough valid data points for {label} fit")
            return LorentzianFitResult(fit_quality="failed", success=False)
        
        f_arr = np.array([p[0] for p in valid_pairs])
        v_arr = np.array([p[1] for p in valid_pairs])
        
        # Initial guesses
        L0_guess = np.min(v_arr)
        A_guess = np.max(v_arr) - L0_guess
        f0_guess = f_arr[np.argmax(v_arr)]
        FWHM_guess = self.span_khz / 4
        
        try:
            # Fit with bounds
            popt, pcov = curve_fit(
                self.lorentzian,
                f_arr, v_arr,
                p0=[L0_guess, A_guess, f0_guess, FWHM_guess],
                bounds=([
                    np.min(v_arr) - abs(A_guess),  # L0
                    0,  # A >= 0
                    f_arr[0],  # f0 within range
                    1.0  # FWHM > 0
                ], [
                    np.max(v_arr) + abs(A_guess),
                    3 * abs(A_guess),
                    f_arr[-1],
                    self.span_khz
                ]),
                maxfev=10000
            )
            
            L0, A, f0, FWHM = popt
            
            # Calculate uncertainties
            perr = np.sqrt(np.diag(pcov))
            L0_err, A_err, f0_err, FWHM_err = perr
            
            # Calculate R²
            v_pred = self.lorentzian(f_arr, *popt)
            ss_res = np.sum((v_arr - v_pred)**2)
            ss_tot = np.sum((v_arr - np.mean(v_arr))**2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            # Determine fit quality
            if r_squared > self.fit_quality_threshold and A > 0:
                fit_quality = "good"
            elif r_squared > 0.3:
                fit_quality = "poor"
            else:
                fit_quality = "failed"
            
            self.logger.info(f"{label} fit: f0={f0:.2f}±{f0_err:.2f} kHz, "
                           f"FWHM={FWHM:.2f}±{FWHM_err:.2f} kHz, R²={r_squared:.3f}, "
                           f"quality={fit_quality}")
            
            return LorentzianFitResult(
                L0=L0, A=A, f0=f0, FWHM=FWHM,
                L0_err=L0_err, A_err=A_err, f0_err=f0_err, FWHM_err=FWHM_err,
                r_squared=r_squared,
                fit_quality=fit_quality,
                success=True
            )
            
        except Exception as e:
            self.logger.error(f"{label} fit failed: {e}")
            return LorentzianFitResult(fit_quality="failed", success=False)
    
    def perform_fits(self, result: CamSweepResult) -> CamSweepResult:
        """
        Perform Lorentzian fits to all three datasets.
        
        Args:
            result: CamSweepResult with sweep data
            
        Returns:
            Updated CamSweepResult with fit results
        """
        self.logger.info("="*60)
        self.logger.info("PERFORMING LORENTZIAN FITS")
        self.logger.info("="*60)
        
        freqs = result.frequencies_khz
        
        # Fit PMT data
        self.logger.info("Fitting PMT data...")
        result.pmt_fit = self.fit_lorentzian(freqs, result.pmt_counts, "PMT")
        
        # Fit sig_x data
        self.logger.info("Fitting sig_x data...")
        result.sig_x_fit = self.fit_lorentzian(freqs, result.sig_x_values, "sig_x")
        
        # Fit R_y data
        self.logger.info("Fitting R_y data...")
        result.r_y_fit = self.fit_lorentzian(freqs, result.r_y_values, "R_y")
        
        return result
    
    def save_results(self, result: CamSweepResult) -> str:
        """
        Save sweep data and fit results to JSON.
        
        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cam_sweep_{self.target_frequency_khz:.0f}kHz_{timestamp}.json"
        filepath = self.data_dir / filename
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        def fit_to_dict(fit: Optional[LorentzianFitResult]) -> Optional[Dict]:
            if fit is None:
                return None
            return {
                "L0": fit.L0,
                "A": fit.A,
                "f0_kHz": fit.f0,
                "FWHM_kHz": fit.FWHM,
                "L0_err": fit.L0_err,
                "A_err": fit.A_err,
                "f0_err_kHz": fit.f0_err,
                "FWHM_err_kHz": fit.FWHM_err,
                "r_squared": fit.r_squared,
                "fit_quality": fit.fit_quality,
                "success": fit.success
            }
        
        data = {
            "timestamp": timestamp,
            "experiment": "cam_sweep",
            "ion_position": self.ion_position,
            "sweep_params": result.sweep_params,
            "data_points": [
                {
                    "frequency_khz": dp.frequency_khz,
                    "pmt_counts": dp.pmt_counts,
                    "sig_x": dp.sig_x,
                    "r_y": dp.r_y,
                    "pos_x": dp.pos_x,
                    "pos_y": dp.pos_y,
                    "frame_number": dp.frame_number
                }
                for dp in result.data_points
            ],
            "fits": {
                "pmt_fit": fit_to_dict(result.pmt_fit),
                "sig_x_fit": fit_to_dict(result.sig_x_fit),
                "r_y_fit": fit_to_dict(result.r_y_fit)
            },
            "summary": {
                "total_points": len(result.data_points),
                "freq_start_khz": result.frequencies_khz[0] if result.frequencies_khz else None,
                "freq_end_khz": result.frequencies_khz[-1] if result.frequencies_khz else None,
                "pmt_max": max(result.pmt_counts) if result.pmt_counts else 0,
                "pmt_min": min(result.pmt_counts) if result.pmt_counts else 0,
                "best_fit_quality": min([
                    result.pmt_fit.fit_quality if result.pmt_fit else "failed",
                    result.sig_x_fit.fit_quality if result.sig_x_fit else "failed",
                    result.r_y_fit.fit_quality if result.r_y_fit else "failed"
                ], key=lambda x: {"good": 0, "poor": 1, "failed": 2}.get(x, 3))
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        self.logger.info(f"Results saved to: {filepath}")
        return str(filepath)
    
    def run(self) -> ExperimentResult:
        """Execute camera sweep experiment."""
        self.logger.info("="*60)
        self.logger.info("CAMERA SWEEP EXPERIMENT START")
        self.logger.info("="*60)
        
        try:
            self.set_status(ExperimentStatus.RUNNING)
            
            # Phase 0: Read ion position from last frame
            self.set_progress(2)
            self.ion_position = self.read_last_frame_position()
            
            if self.ion_position is None:
                self.logger.warning("Could not detect ion position, using default ROI")
                # Use default ROI
                self.analysis_roi = {
                    "xstart": 180, "xfinish": 220,
                    "ystart": 425, "yfinish": 495,
                    "radius": 6
                }
            else:
                # Calculate ROI centered on ion
                self.analysis_roi = self.calculate_roi_from_position(
                    self.ion_position[0], self.ion_position[1]
                )
            
            if self.check_stop():
                return ExperimentResult(success=False, error="Experiment stopped")
            
            # Phase 1: Stop camera infinity mode
            self.set_progress(5)
            if not self.stop_camera_inf():
                self.logger.warning("Could not stop camera infinity mode, continuing...")
            
            if self.check_stop():
                return ExperimentResult(success=False, error="Experiment stopped")
            
            # Phase 2: Configure and start camera recording
            self.set_progress(15)
            if not self.start_camera_recording(self.steps, self.analysis_roi):
                self.start_camera_inf()
                return ExperimentResult(
                    success=False,
                    error="Failed to start camera recording"
                )
            
            if self.check_stop():
                self.start_camera_inf()
                return ExperimentResult(success=False, error="Experiment stopped")
            
            # Phase 3: Execute sweep
            self.set_progress(30)
            self.sweep_result = self.execute_sweep()
            
            if self.sweep_result is None:
                self.start_camera_inf()
                return ExperimentResult(
                    success=False,
                    error="Sweep execution failed"
                )
            
            if self.check_stop():
                self.start_camera_inf()
                return ExperimentResult(success=False, error="Experiment stopped")
            
            # Phase 4: Perform Lorentzian fits
            self.set_progress(70)
            self.sweep_result = self.perform_fits(self.sweep_result)
            
            # Phase 5: Save data
            self.set_progress(85)
            data_file = self.save_results(self.sweep_result)
            self.sweep_result.data_file = data_file
            
            # Record data
            self.record_data("frequencies_khz", self.sweep_result.frequencies_khz)
            self.record_data("pmt_counts", self.sweep_result.pmt_counts)
            self.record_data("sig_x_values", self.sweep_result.sig_x_values)
            self.record_data("r_y_values", self.sweep_result.r_y_values)
            self.record_data("ion_position", self.ion_position)
            self.record_data("sweep_params", self.sweep_result.sweep_params)
            self.record_data("fits", {
                "pmt_fit": asdict(self.sweep_result.pmt_fit) if self.sweep_result.pmt_fit else None,
                "sig_x_fit": asdict(self.sweep_result.sig_x_fit) if self.sweep_result.sig_x_fit else None,
                "r_y_fit": asdict(self.sweep_result.r_y_fit) if self.sweep_result.r_y_fit else None
            })
            self.record_data("data_file", data_file)
            
            # Phase 6: Restart camera infinity mode
            self.set_progress(95)
            if not self.start_camera_inf():
                self.logger.warning("Failed to restart camera infinity mode")
            
            self.set_progress(100)
            
            # Summary
            fit_status = []
            if self.sweep_result.pmt_fit and self.sweep_result.pmt_fit.success:
                fit_status.append(f"PMT: {self.sweep_result.pmt_fit.f0:.1f}kHz ({self.sweep_result.pmt_fit.fit_quality})")
            if self.sweep_result.sig_x_fit and self.sweep_result.sig_x_fit.success:
                fit_status.append(f"sig_x: {self.sweep_result.sig_x_fit.f0:.1f}kHz ({self.sweep_result.sig_x_fit.fit_quality})")
            if self.sweep_result.r_y_fit and self.sweep_result.r_y_fit.success:
                fit_status.append(f"R_y: {self.sweep_result.r_y_fit.f0:.1f}kHz ({self.sweep_result.r_y_fit.fit_quality})")
            
            fit_summary = ", ".join(fit_status) if fit_status else "No successful fits"
            msg = (f"Camera sweep complete: {len(self.sweep_result.data_points)} points. "
                   f"Fits: {fit_summary}. Data: {data_file}")
            
            self.logger.info(msg)
            
            return ExperimentResult(
                success=True,
                data=self.data,
                message=msg
            )
            
        except Exception as e:
            self.logger.exception("Camera sweep experiment failed")
            try:
                self.start_camera_inf()
            except:
                pass
            return ExperimentResult(
                success=False,
                error=str(e),
                message="Experiment crashed"
            )


# Command-line entry point
def main():
    """Run camera sweep experiment from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Camera Sweep Experiment")
    parser.add_argument("--host", default="localhost", help="Manager host")
    parser.add_argument("--port", type=int, default=5557, help="Manager port")
    parser.add_argument("--data-dir", default="data/cam_sweep_result", help="Data directory")
    
    # Sweep parameters
    parser.add_argument("-f", "--frequency", type=float, default=400.0,
                       help="Target frequency [kHz] (default: 400)")
    parser.add_argument("-s", "--span", type=float, default=40.0,
                       help="Sweep span [kHz] (default: 40)")
    parser.add_argument("-n", "--steps", type=int, default=41,
                       help="Number of steps (default: 41)")
    parser.add_argument("--on-time", type=float, default=100.0,
                       help="PMT on time [ms] (default: 100)")
    parser.add_argument("--off-time", type=float, default=100.0,
                       help="PMT off time [ms] (default: 100)")
    parser.add_argument("--att", type=float, default=25.0,
                       help="Attenuation [dB] (default: 25)")
    parser.add_argument("--exposure", type=float, default=300.0,
                       help="Camera exposure [ms] (default: 300)")
    parser.add_argument("--roi-size", type=int, default=60,
                       help="ROI half-size around ion [pixels] (default: 60)")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and configure experiment
    exp = CamSweepExperiment(
        manager_host=args.host,
        manager_port=args.port,
        data_dir=args.data_dir
    )
    
    exp.configure_sweep(
        target_frequency_khz=args.frequency,
        span_khz=args.span,
        steps=args.steps,
        on_time_ms=args.on_time,
        off_time_ms=args.off_time,
        attenuation_db=args.att,
        exposure_ms=args.exposure,
        roi_size=args.roi_size
    )
    
    print("="*60)
    print("CAMERA SWEEP EXPERIMENT")
    print("="*60)
    print(f"Frequency: {args.frequency} kHz ± {args.span/2} kHz")
    print(f"Steps: {args.steps}")
    print(f"On/Off time: {args.on_time}/{args.off_time} ms")
    print(f"ROI size: {args.roi_size} pixels")
    print(f"Data dir: {args.data_dir}")
    print("="*60)
    
    # Run experiment
    result = exp.run()
    
    print("\n" + "="*60)
    if result.success:
        print("RESULT: SUCCESS")
        print(f"Message: {result.message}")
        if result.data.get('fits'):
            fits = result.data['fits']
            print("\nFit Results:")
            for key, fit in fits.items():
                if fit and fit.get('success'):
                    print(f"  {key}: f0={fit['f0_kHz']:.2f}±{fit['f0_err_kHz']:.2f} kHz, "
                          f"quality={fit['fit_quality']}, R²={fit['r_squared']:.3f}")
    else:
        print("RESULT: FAILED")
        print(f"Error: {result.error}")
    print("="*60)
    
    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())
