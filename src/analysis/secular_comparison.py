"""
Secular Frequency Comparison Module

Automated comparison of measured secular frequencies with theoretical predictions.

Workflow:
1. Set trap parameters (EC1, EC2, Comp_H, Comp_V, U_RF)
2. Calculate theoretical secular frequencies using trap_sim_asy
3. Identify smallest frequency (axial secular)
4. Conduct secular scan ±20V around predicted frequency
5. Analyze results:
   - No signal → return mismatch
   - Lorentzian detected → fit and compare to prediction
6. Upload results to data server
"""

import numpy as np
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import trap simulation
from analysis.eigenmodes.trap_sim_asy import (
    eigenmodes_from_masses,
    u_RF as GLOBAL_U_RF,
    EC1 as GLOBAL_EC1,
    EC2 as GLOBAL_EC2,
    OMEGA,
    RF_MHZ
)
from core import u_rf_mv_to_U_RF_V, RF_SCALE_V_PER_MV

# Setup logging
logger = logging.getLogger("secular_comparison")


@dataclass
class SecularComparisonResult:
    """Result of a secular frequency comparison."""
    # Input parameters
    ec1: float
    ec2: float
    comp_h: float
    comp_v: float
    u_rf_mV: float  # SMILE setting in mV
    u_rf_real: float  # Real RF voltage after amplification
    mass_numbers: List[int]
    
    # Theoretical prediction
    predicted_freqs_kHz: List[float]
    smallest_freq_kHz: float
    target_mode: str  # e.g., "Axial in-phase"
    
    # Scan parameters
    scan_center_kHz: float
    scan_range_kHz: float
    scan_voltages: List[float]
    scan_results: List[float]
    
    # Analysis results
    signal_detected: bool
    fit_success: bool
    fitted_center_kHz: Optional[float] = None
    fitted_fwhm_kHz: Optional[float] = None
    fitted_amplitude: Optional[float] = None
    fit_chi2: Optional[float] = None
    
    # Comparison
    frequency_difference_kHz: Optional[float] = None
    relative_difference_percent: Optional[float] = None
    match_quality: Optional[str] = None  # "excellent", "good", "poor", "mismatch"
    
    # Metadata
    timestamp: float = 0.0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class LorentzianFitter:
    """
    Lorentzian peak fitting for secular scan analysis.
    
    Model: L(x) = A * Γ² / [(x - x₀)² + Γ²] + BG
    
    Where:
    - A: amplitude
    - x₀: center (peak position)
    - Γ: half-width at half-maximum (HWHM)
    - BG: background
    - FWHM = 2Γ
    """
    
    @staticmethod
    def model(x: np.ndarray, x0: float, gamma: float, amplitude: float, 
              background: float = 0) -> np.ndarray:
        """
        Lorentzian model.
        
        Args:
            x: Frequency array
            x0: Center frequency
            gamma: Half-width at half-maximum (HWHM)
            amplitude: Peak amplitude
            background: Background level
            
        Returns:
            Model values
        """
        return amplitude * gamma**2 / ((x - x0)**2 + gamma**2) + background
    
    @staticmethod
    def guess_initial_params(x: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """
        Guess initial parameters from data.
        
        Returns:
            Dictionary with initial parameter estimates
        """
        # Background as minimum value
        bg = np.min(y)
        
        # Remove background for amplitude estimate
        y_no_bg = y - bg
        
        # Amplitude is max value above background
        amplitude = np.max(y_no_bg)
        
        # Center is at maximum
        x0 = x[np.argmax(y)]
        
        # Estimate width from FWHM
        half_max = amplitude / 2 + bg
        above_half = y > half_max
        
        if np.sum(above_half) >= 2:
            # Find indices where y crosses half-maximum
            indices = np.where(above_half)[0]
            fwhm = x[indices[-1]] - x[indices[0]]
            gamma = fwhm / 2  # HWHM
        else:
            # Default to 10% of range
            gamma = (x[-1] - x[0]) * 0.1
        
        return {
            'x0': x0,
            'gamma': max(gamma, 0.1),  # Minimum width to avoid division by zero
            'amplitude': amplitude,
            'background': bg
        }
    
    @staticmethod
    def fit(x: np.ndarray, y: np.ndarray, 
            initial_guess: Optional[Dict[str, float]] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Fit Lorentzian to data.
        
        Args:
            x: Frequency array (kHz)
            y: Signal array (counts or amplitude)
            initial_guess: Optional initial parameter dictionary
            
        Returns:
            (success, result_dict)
            result_dict contains: x0, gamma, amplitude, background, 
                                 fwhm, chi2, cov_matrix, fit_curve
        """
        try:
            from scipy.optimize import curve_fit
            
            # Guess initial parameters if not provided
            if initial_guess is None:
                initial_guess = LorentzianFitter.guess_initial_params(x, y)
            
            p0 = [
                initial_guess['x0'],
                initial_guess['gamma'],
                initial_guess['amplitude'],
                initial_guess['background']
            ]
            
            # Set bounds to keep parameters physical
            bounds = ([
                x[0],  # x0 >= min(x)
                0.01,  # gamma >= 0.01 kHz
                0,     # amplitude >= 0
                0      # background >= 0
            ], [
                x[-1],  # x0 <= max(x)
                (x[-1] - x[0]),  # gamma <= full range
                np.max(y) * 10,  # amplitude <= 10x max
                np.max(y)        # background <= max(y)
            ])
            
            # Fit
            popt, pcov = curve_fit(
                LorentzianFitter.model, x, y, p0=p0, bounds=bounds,
                maxfev=10000
            )
            
            x0, gamma, amplitude, background = popt
            
            # Calculate fit quality
            y_fit = LorentzianFitter.model(x, *popt)
            residuals = y - y_fit
            chi2 = np.sum(residuals**2) / (len(y) - 4)  # Reduced chi2
            
            # Parameter uncertainties
            perr = np.sqrt(np.diag(pcov))
            
            return True, {
                'x0': x0,
                'x0_err': perr[0],
                'gamma': gamma,
                'gamma_err': perr[1],
                'amplitude': amplitude,
                'amplitude_err': perr[2],
                'background': background,
                'background_err': perr[3],
                'fwhm': 2 * gamma,
                'fwhm_err': 2 * perr[1],
                'chi2': chi2,
                'cov_matrix': pcov,
                'fit_curve': y_fit,
                'residuals': residuals
            }
            
        except Exception as e:
            logger.error(f"Lorentzian fit failed: {e}")
            return False, {'error': str(e)}


class SecularFrequencyComparator:
    """
    Automated secular frequency comparison system.
    
    Coordinates between ARTIQ (for electrode/RF control) and
    SMILE (for RF voltage) to perform secular frequency scans.
    """
    
    # Default parameters for comparison
    DEFAULT_PARAMS = {
        'ec1': 10.0,    # V
        'ec2': 10.0,    # V
        'comp_h': 6.0,  # V
        'comp_v': 37.0, # V
        'u_rf_mV': 1400,  # mV on SMILE interface
    }
    
    # Use shared calibration constant: 700mV → 100V
    RF_VOLTAGE_SCALE = RF_SCALE_V_PER_MV  # From core.enums
    
    # Secular scan parameters
    SCAN_RANGE_KHZ = 20.0  # ±20 kHz around predicted frequency
    SCAN_POINTS = 41       # Number of points in scan
    SCAN_DWELL_MS = 100    # Dwell time per point
    
    def __init__(self):
        self.logger = logger
        self.fitter = LorentzianFitter()
        self.last_result: Optional[SecularComparisonResult] = None
    
    def calculate_theoretical_freqs(self, params: Optional[Dict[str, float]] = None,
                                    mass_numbers: List[int] = [9, 3]) -> Tuple[List[float], float, str]:
        """
        Calculate theoretical secular frequencies using trap_sim_asy.
        
        Args:
            params: Trap parameters (ec1, ec2, comp_h, comp_v, u_rf_mV)
            mass_numbers: List of ion mass numbers (default Be+ ions: 9, 3)
            
        Returns:
            (frequencies_kHz, smallest_freq_kHz, mode_name)
        """
        if params is None:
            params = self.DEFAULT_PARAMS.copy()
        
        # Calculate real RF voltage
        u_rf_mV = params.get('u_rf_mV', self.DEFAULT_PARAMS['u_rf_mV'])
        u_rf_real = u_rf_mV * self.RF_VOLTAGE_SCALE  # Convert to real voltage
        
        self.logger.info(f"Calculating secular frequencies for U_RF = {u_rf_real:.1f} V "
                        f"({u_rf_mV} mV on SMILE)")
        
        # Set global parameters for trap_sim_asy
        # Note: We need to temporarily modify the global variables
        import server.analysis.eigenmodes.trap_sim_asy as trap_sim
        
        original_u_RF = trap_sim.u_RF
        original_EC1 = trap_sim.EC1
        original_EC2 = trap_sim.EC2
        
        try:
            # Set new parameters
            trap_sim.u_RF = u_rf_real
            trap_sim.EC1 = params.get('ec1', self.DEFAULT_PARAMS['ec1'])
            trap_sim.EC2 = params.get('ec2', self.DEFAULT_PARAMS['ec2'])
            
            # Calculate eigenmodes
            freqs_hz, V, z_eq, coords = eigenmodes_from_masses(
                mass_numbers,
                theta_deg=0.0,
                z_offset=0.0,
                verbose=False
            )
            
            # Convert to kHz
            freqs_kHz = freqs_hz / 1000.0
            
            # Find smallest frequency (axial secular)
            min_idx = np.argmin(freqs_kHz)
            smallest_freq = freqs_kHz[min_idx]
            
            # Determine mode name
            if len(mass_numbers) == 2:
                # For 2 ions, use the eigenvector to determine mode
                mode_name = self._identify_mode(V[:, min_idx])
            else:
                mode_name = f"Mode {min_idx}"
            
            self.logger.info(f"Predicted frequencies: {freqs_kHz}")
            self.logger.info(f"Smallest frequency: {smallest_freq:.3f} kHz ({mode_name})")
            
            return freqs_kHz.tolist(), smallest_freq, mode_name
            
        finally:
            # Restore original parameters
            trap_sim.u_RF = original_u_RF
            trap_sim.EC1 = original_EC1
            trap_sim.EC2 = original_EC2
    
    def _identify_mode(self, eigenvector: np.ndarray) -> str:
        """Identify mode type from eigenvector."""
        # For 2 ions, eigenvector has shape (6,) for [x1,y1,z1,x2,y2,z2]
        ex = eigenvector[0]**2 + eigenvector[3]**2
        ey = eigenvector[1]**2 + eigenvector[4]**2
        ez = eigenvector[2]**2 + eigenvector[5]**2
        
        axis = int(np.argmax([ex, ey, ez]))
        
        if axis == 2:  # Z-axis (axial)
            if np.sign(eigenvector[2]) == np.sign(eigenvector[5]):
                return "Axial in-phase"
            else:
                return "Axial out-of-phase"
        elif axis == 0:
            return "Radial (x)"
        else:
            return "Radial (y)"
    
    def generate_scan_voltages(self, center_freq_kHz: float, 
                               range_kHz: float = None,
                               n_points: int = None) -> np.ndarray:
        """
        Generate voltage values for secular frequency scan.
        
        The scan is performed by varying the RF voltage slightly to 
        modulate the secular frequency.
        
        Args:
            center_freq_kHz: Center frequency in kHz
            range_kHz: Scan range in kHz (±range/2 from center)
            n_points: Number of scan points
            
        Returns:
            Array of U_RF mV values for scan
        """
        if range_kHz is None:
            range_kHz = self.SCAN_RANGE_KHZ
        if n_points is None:
            n_points = self.SCAN_POINTS
        
        # For now, scan around the default U_RF
        # In practice, you might want to scan by varying a different parameter
        base_mV = self.DEFAULT_PARAMS['u_rf_mV']
        
        # Create scan range (±10% variation)
        scan_range_mV = base_mV * 0.1
        
        voltages = np.linspace(
            base_mV - scan_range_mV,
            base_mV + scan_range_mV,
            n_points
        )
        
        return voltages
    
    def analyze_scan(self, frequencies_kHz: np.ndarray, 
                     counts: np.ndarray,
                     predicted_freq_kHz: float) -> Tuple[bool, Dict[str, Any]]:
        """
        Analyze secular scan results.
        
        Args:
            frequencies_kHz: Array of frequencies scanned
            counts: Array of PMT counts (or other signal)
            predicted_freq_kHz: Predicted frequency for comparison
            
        Returns:
            (signal_detected, analysis_results)
        """
        # Check if there's any signal (above noise)
        noise_level = np.percentile(counts, 10)
        peak_level = np.max(counts)
        snr = (peak_level - noise_level) / np.std(counts[counts < np.percentile(counts, 50)])
        
        self.logger.info(f"Scan SNR: {snr:.2f}")
        
        if snr < 2.0:  # No clear signal
            self.logger.warning("No clear signal detected in scan")
            return False, {
                'reason': 'no_signal',
                'snr': snr,
                'noise_level': noise_level,
                'peak_level': peak_level
            }
        
        # Attempt Lorentzian fit
        success, fit_result = self.fitter.fit(frequencies_kHz, counts)
        
        if not success:
            self.logger.warning(f"Lorentzian fit failed: {fit_result.get('error')}")
            return False, {
                'reason': 'fit_failed',
                'error': fit_result.get('error'),
                'snr': snr
            }
        
        # Check fit quality
        if fit_result['chi2'] > 10:  # Poor fit
            self.logger.warning(f"Poor fit quality (χ² = {fit_result['chi2']:.2f})")
            return False, {
                'reason': 'poor_fit',
                'chi2': fit_result['chi2'],
                'fit_result': fit_result
            }
        
        # Calculate frequency difference
        fitted_center = fit_result['x0']
        freq_diff = fitted_center - predicted_freq_kHz
        rel_diff = abs(freq_diff) / predicted_freq_kHz * 100
        
        self.logger.info(f"Fitted center: {fitted_center:.3f} kHz")
        self.logger.info(f"Predicted: {predicted_freq_kHz:.3f} kHz")
        self.logger.info(f"Difference: {freq_diff:.3f} kHz ({rel_diff:.2f}%)")
        
        return True, {
            'fitted_center_kHz': fitted_center,
            'fitted_fwhm_kHz': fit_result['fwhm'],
            'fitted_amplitude': fit_result['amplitude'],
            'fit_chi2': fit_result['chi2'],
            'frequency_difference_kHz': freq_diff,
            'relative_difference_percent': rel_diff,
            'fit_result': fit_result,
            'snr': snr
        }
    
    def determine_match_quality(self, rel_diff_percent: float, 
                                chi2: float) -> str:
        """
        Determine match quality based on frequency difference and fit quality.
        
        Returns:
            Quality string: "excellent", "good", "poor", or "mismatch"
        """
        if rel_diff_percent < 1.0 and chi2 < 3:
            return "excellent"
        elif rel_diff_percent < 5.0 and chi2 < 5:
            return "good"
        elif rel_diff_percent < 10.0:
            return "poor"
        else:
            return "mismatch"
    
    def run_comparison(self, params: Optional[Dict[str, float]] = None,
                       mass_numbers: List[int] = [9, 3],
                       scan_results: Optional[Tuple[List[float], List[float]]] = None
                       ) -> SecularComparisonResult:
        """
        Run complete secular frequency comparison.
        
        Args:
            params: Trap parameters (uses defaults if None)
            mass_numbers: Ion mass numbers
            scan_results: Optional (frequencies, counts) from external scan
            
        Returns:
            SecularComparisonResult with all analysis data
        """
        if params is None:
            params = self.DEFAULT_PARAMS.copy()
        
        timestamp = time.time()
        
        # Calculate theoretical frequencies
        try:
            predicted_freqs, smallest_freq, mode_name = self.calculate_theoretical_freqs(
                params, mass_numbers
            )
        except Exception as e:
            logger.error(f"Failed to calculate theoretical frequencies: {e}")
            return SecularComparisonResult(
                ec1=params.get('ec1', 0),
                ec2=params.get('ec2', 0),
                comp_h=params.get('comp_h', 0),
                comp_v=params.get('comp_v', 0),
                u_rf_mV=params.get('u_rf_mV', 0),
                u_rf_real=params.get('u_rf_mV', 0) * self.RF_VOLTAGE_SCALE,
                mass_numbers=mass_numbers,
                predicted_freqs_kHz=[],
                smallest_freq_kHz=0,
                target_mode="",
                scan_center_kHz=0,
                scan_range_kHz=self.SCAN_RANGE_KHZ,
                scan_voltages=[],
                scan_results=[],
                signal_detected=False,
                fit_success=False,
                timestamp=timestamp,
                error_message=f"Theory calculation failed: {e}"
            )
        
        # Generate scan voltages
        scan_voltages = self.generate_scan_voltages(smallest_freq).tolist()
        
        result = SecularComparisonResult(
            ec1=params.get('ec1', self.DEFAULT_PARAMS['ec1']),
            ec2=params.get('ec2', self.DEFAULT_PARAMS['ec2']),
            comp_h=params.get('comp_h', self.DEFAULT_PARAMS['comp_h']),
            comp_v=params.get('comp_v', self.DEFAULT_PARAMS['comp_v']),
            u_rf_mV=params.get('u_rf_mV', self.DEFAULT_PARAMS['u_rf_mV']),
            u_rf_real=params.get('u_rf_mV', self.DEFAULT_PARAMS['u_rf_mV']) * self.RF_VOLTAGE_SCALE,
            mass_numbers=mass_numbers,
            predicted_freqs_kHz=predicted_freqs,
            smallest_freq_kHz=smallest_freq,
            target_mode=mode_name,
            scan_center_kHz=smallest_freq,
            scan_range_kHz=self.SCAN_RANGE_KHZ,
            scan_voltages=scan_voltages,
            scan_results=[],
            signal_detected=False,
            fit_success=False,
            timestamp=timestamp
        )
        
        # If scan results provided, analyze them
        if scan_results is not None:
            frequencies, counts = scan_results
            result.scan_results = counts
            
            signal_detected, analysis = self.analyze_scan(
                np.array(frequencies),
                np.array(counts),
                smallest_freq
            )
            
            result.signal_detected = signal_detected
            
            if signal_detected:
                result.fit_success = True
                result.fitted_center_kHz = analysis.get('fitted_center_kHz')
                result.fitted_fwhm_kHz = analysis.get('fitted_fwhm_kHz')
                result.fitted_amplitude = analysis.get('fitted_amplitude')
                result.fit_chi2 = analysis.get('fit_chi2')
                result.frequency_difference_kHz = analysis.get('frequency_difference_kHz')
                result.relative_difference_percent = analysis.get('relative_difference_percent')
                result.match_quality = self.determine_match_quality(
                    result.relative_difference_percent or 0,
                    result.fit_chi2 or 999
                )
            else:
                result.error_message = analysis.get('reason', 'unknown')
        else:
            result.error_message = "No scan results provided"
        
        self.last_result = result
        return result
    
    def upload_to_data_server(self, result: SecularComparisonResult,
                              data_client=None) -> bool:
        """
        Upload comparison results to data server.
        
        Args:
            result: Comparison result to upload
            data_client: Optional DataClient instance
            
        Returns:
            True if successful
        """
        try:
            if data_client is None:
                # Try to import and create client
                from services.comms.data_server import DataClient
                data_client = DataClient()
                if not data_client.connect("secular_compare"):
                    logger.error("Failed to connect to data server")
                    return False
            
            # Upload key metrics as separate channels
            if result.fitted_center_kHz is not None:
                data_client.send_data("secular_fitted", result.fitted_center_kHz)
            
            if result.frequency_difference_kHz is not None:
                data_client.send_data("secular_diff", result.frequency_difference_kHz)
            
            data_client.send_data("secular_predicted", result.smallest_freq_kHz)
            
            # Also upload full result as JSON
            # This could be stored in a special channel or file
            logger.info("Results uploaded to data server")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload results: {e}")
            return False


# ==============================================================================
# CLI Interface for testing
# ==============================================================================

def main():
    """Test the secular comparison system."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Secular Frequency Comparison")
    parser.add_argument("--ec1", type=float, default=10.0, help="EC1 voltage")
    parser.add_argument("--ec2", type=float, default=10.0, help="EC2 voltage")
    parser.add_argument("--comp-h", type=float, default=6.0, help="Comp H voltage")
    parser.add_argument("--comp-v", type=float, default=37.0, help="Comp V voltage")
    parser.add_argument("--u-rf", type=float, default=1400, help="U_RF in mV")
    parser.add_argument("--test-fit", action="store_true", help="Test with simulated data")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO,
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    comparator = SecularFrequencyComparator()
    
    params = {
        'ec1': args.ec1,
        'ec2': args.ec2,
        'comp_h': args.comp_h,
        'comp_v': args.comp_v,
        'u_rf_mV': args.u_rf
    }
    
    print("=" * 60)
    print("Secular Frequency Comparison Test")
    print("=" * 60)
    print(f"Parameters: {params}")
    print()
    
    if args.test_fit:
        # Generate simulated scan data with a Lorentzian peak
        predicted_freqs, smallest_freq, mode_name = comparator.calculate_theoretical_freqs(params)
        
        print(f"Predicted frequencies: {predicted_freqs}")
        print(f"Target mode: {smallest_freq:.3f} kHz ({mode_name})")
        print()
        
        # Generate simulated scan
        freqs = np.linspace(smallest_freq - 20, smallest_freq + 20, 41)
        
        # Add Lorentzian peak slightly offset from prediction
        true_center = smallest_freq + 2.5  # 2.5 kHz offset
        gamma = 3.0  # HWHM
        amplitude = 1000
        background = 100
        
        counts = (LorentzianFitter.model(freqs, true_center, gamma, amplitude, background) 
                  + np.random.normal(0, 50, len(freqs)))  # Add noise
        
        print("Running analysis on simulated data...")
        print(f"True center (simulated): {true_center:.3f} kHz")
        print()
        
        result = comparator.run_comparison(params, scan_results=(freqs.tolist(), counts.tolist()))
    else:
        # Just calculate theory
        result = comparator.run_comparison(params)
    
    print("=" * 60)
    print("Results:")
    print("=" * 60)
    print(result.to_json())
    print()
    
    if result.fit_success:
        print(f"[OK] Fit successful!")
        print(f"  Predicted: {result.smallest_freq_kHz:.3f} kHz")
        print(f"  Fitted: {result.fitted_center_kHz:.3f} kHz")
        print(f"  Difference: {result.frequency_difference_kHz:.3f} kHz")
        print(f"  Quality: {result.match_quality}")
    elif result.signal_detected:
        print("⚠ Signal detected but fit failed")
    else:
        print("[FAIL] No signal detected")


if __name__ == "__main__":
    main()
