"""
Auto Compensation Experiment.

This script performs automatic compensation voltage calibration:
1. Set u_rf to 200V, record pos_y (reference position)
2. Set u_rf to 100V, calibrate comp_h until pos_y matches reference
3. Scan comp_v from 30V to 50V in 1V steps (random sequence)
4. For each comp_v, record PMT data
5. Fit cubic: ax³ + bx² + cx + d
6. Find f'(comp_v) = 0 (3 extremas)
7. Choose middle extrema if in [0V, 50V]
8. Set optimal comp_v

PMT Data Collection:
    Uses hardware-gated PMT measurement via ARTIQ ttl0_counter, following the
    approach from PMT_beam_finder.py:
    - Sends PMT_MEASURE command to ARTIQ worker via manager
    - ARTIQ opens ttl0_counter gate for specified duration
    - Returns accumulated photon count
    - More accurate than polling telemetry data

Usage:
    python -m applet.experiments.auto_compensation
    # or via controller API
"""

import time
import random
import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np
from scipy.optimize import fsolve
import matplotlib.pyplot as plt
from pathlib import Path

from .base_experiment import BaseExperiment, ExperimentStatus, ExperimentResult


@dataclass
class CubicFitResult:
    """Result of cubic polynomial fit."""
    a: float
    b: float
    c: float
    d: float
    r_squared: float
    extremas: List[float]
    selected_extrema: Optional[float]


class AutoCompensationExperiment(BaseExperiment):
    """
    Auto compensation experiment.
    
    Automatically finds optimal compensation voltages by:
    1. Calibrating horizontal compensation (comp_h) at reduced RF
    2. Finding optimal vertical compensation (comp_v) via PMT signal
    """
    
    def __init__(
        self,
        manager_host: str = "localhost",
        manager_port: int = 5557,
        data_dir: str = "data/experiments"
    ):
        super().__init__(
            name="auto_compensation",
            manager_host=manager_host,
            manager_port=manager_port,
            data_dir=data_dir
        )
        
        # Experiment parameters (can be overridden)
        self.u_rf_high = 200.0  # V
        self.u_rf_low = 100.0   # V
        self.comp_v_range = (30.0, 50.0)  # V
        self.comp_v_step = 1.0  # V
        self.comp_h_tolerance = 0.5  # pixels
        self.comp_h_max_iter = 20
        self.pmt_integration_time = 0.1  # seconds (100ms - matches PMT_beam_finder default)
        self.settling_time = 0.5  # seconds after voltage change
        
        # Results storage
        self.scan_data: List[Dict[str, float]] = []
        self.fit_result: Optional[CubicFitResult] = None
    
    def get_position(self) -> Optional[Tuple[float, float]]:
        """
        Get current ion position from manager.
        
        Returns:
            (pos_x, pos_y) or None if unavailable
        """
        response = self.send_to_manager({
            "action": "GET",
            "source": "EXPERIMENT_AUTO_COMP"
        })
        
        if response.get("status") == "success":
            params = response.get("params", {})
            pos_x = params.get("pos_x")
            pos_y = params.get("pos_y")
            if pos_x is not None and pos_y is not None:
                return (float(pos_x), float(pos_y))
        
        return None
    
    def get_pmt_signal(self, integration_time: float = 1.0) -> Optional[float]:
        """
        Get PMT signal using hardware-gated measurement via ARTIQ.
        
        This method uses the PMT_beam_finder approach:
        - Sends PMT_MEASURE command to ARTIQ via manager
        - ARTIQ opens ttl0_counter gate for specified duration
        - Returns accumulated count
        
        Args:
            integration_time: Gate duration in seconds (default: 1.0s)
        
        Returns:
            PMT counts or None if measurement failed
        """
        if self.check_stop():
            return None
        
        # Convert integration time to milliseconds
        duration_ms = integration_time * 1000.0
        
        # Use the base class measure_pmt method for hardware-gated measurement
        counts = self.measure_pmt(duration_ms=duration_ms)
        
        if counts is not None:
            return float(counts)
        return None
    
    def calibrate_comp_h(self, target_y: float) -> bool:
        """
        Calibrate comp_h to match target_y position.
        
        Uses simple proportional feedback control.
        
        Args:
            target_y: Target y position (pixels)
        
        Returns:
            True if calibration successful
        """
        self.logger.info(f"Starting comp_h calibration (target_y={target_y:.2f})")
        
        # Get initial comp_h
        current_comp_h = self.get_voltage("comp_h") or 0.0
        
        for iteration in range(self.comp_h_max_iter):
            if self.check_stop():
                return False
            self.pause_point()
            
            pos = self.get_position()
            if pos is None:
                self.logger.warning("Cannot get position for comp_h calibration")
                time.sleep(0.5)
                continue
            
            _, current_y = pos
            error = target_y - current_y
            
            self.logger.debug(f"comp_h iter {iteration}: y={current_y:.2f}, error={error:.2f}")
            
            # Check convergence
            if abs(error) < self.comp_h_tolerance:
                self.logger.info(f"comp_h calibration converged at {current_comp_h:.3f}V")
                return True
            
            # Proportional control with gain
            gain = 0.01  # V per pixel error
            adjustment = error * gain
            current_comp_h += adjustment
            
            # Clamp to valid range [-50, 50]
            current_comp_h = max(-50.0, min(50.0, current_comp_h))
            
            if not self.set_voltage("comp_h", current_comp_h):
                self.logger.error("Failed to set comp_h")
                return False
            
            time.sleep(self.settling_time)
        
        self.logger.warning(f"comp_h calibration did not converge after {self.comp_h_max_iter} iterations")
        return False
    
    def scan_comp_v(self) -> List[Dict[str, float]]:
        """
        Scan comp_v and record PMT signal.
        
        Returns:
            List of {comp_v, pmt_signal} dictionaries
        """
        # Generate random sequence of comp_v values
        num_steps = int((self.comp_v_range[1] - self.comp_v_range[0]) / self.comp_v_step) + 1
        comp_v_values = [
            self.comp_v_range[0] + i * self.comp_v_step 
            for i in range(num_steps)
        ]
        random.shuffle(comp_v_values)
        
        self.logger.info(f"Scanning comp_v: {len(comp_v_values)} points in random order")
        
        scan_data = []
        total_points = len(comp_v_values)
        
        for idx, comp_v in enumerate(comp_v_values):
            if self.check_stop():
                break
            self.pause_point()
            
            self.logger.info(f"Scanning {idx+1}/{total_points}: comp_v={comp_v:.1f}V")
            
            # Set comp_v
            if not self.set_voltage("comp_v", comp_v):
                self.logger.error(f"Failed to set comp_v={comp_v}")
                continue
            
            # Wait for settling
            time.sleep(self.settling_time)
            
            # Measure PMT
            pmt_signal = self.get_pmt_signal(self.pmt_integration_time)
            
            if pmt_signal is not None:
                point = {
                    "comp_v": comp_v,
                    "pmt_signal": pmt_signal,
                    "index": idx
                }
                scan_data.append(point)
                self.logger.debug(f"  PMT signal: {pmt_signal:.1f}")
            else:
                self.logger.warning(f"  Failed to get PMT signal at comp_v={comp_v}")
            
            # Update progress (phase 2 is 30-80%)
            progress = 30 + (idx / total_points) * 50
            self.set_progress(progress)
        
        return scan_data
    
    def fit_cubic(self, data: List[Dict[str, float]]) -> Optional[CubicFitResult]:
        """
        Fit cubic polynomial to PMT vs comp_v data.
        
        PMT = a*comp_v³ + b*comp_v² + c*comp_v + d
        
        Args:
            data: List of {comp_v, pmt_signal} points
        
        Returns:
            CubicFitResult with coefficients and extremas
        """
        if len(data) < 4:
            self.logger.error(f"Not enough data points for cubic fit (need 4, have {len(data)})")
            return None
        
        # Extract arrays
        x = np.array([d["comp_v"] for d in data])
        y = np.array([d["pmt_signal"] for d in data])
        
        # Fit cubic: ax³ + bx² + cx + d
        coeffs = np.polyfit(x, y, 3)
        a, b, c, d = coeffs
        
        self.logger.info(f"Cubic fit: a={a:.6f}, b={b:.6f}, c={c:.6f}, d={d:.6f}")
        
        # Calculate R²
        y_pred = a * x**3 + b * x**2 + c * x + d
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        self.logger.info(f"R² = {r_squared:.4f}")
        
        # Find extremas: f'(x) = 3ax² + 2bx + c = 0
        # Quadratic formula: x = (-2b ± sqrt(4b² - 12ac)) / (6a)
        discriminant = (2*b)**2 - 4*(3*a)*c
        
        extremas = []
        if discriminant >= 0:
            sqrt_disc = np.sqrt(discriminant)
            x1 = (-2*b + sqrt_disc) / (6*a)
            x2 = (-2*b - sqrt_disc) / (6*a)
            extremas = sorted([x1, x2])
            self.logger.info(f"Found extremas at comp_v = {extremas[0]:.2f}, {extremas[1]:.2f}")
        else:
            self.logger.warning("No real extremas found (discriminant < 0)")
        
        # Select middle extrema if in valid range [0, 50]
        selected = None
        if len(extremas) >= 2:
            # For 2 extremas, the "middle" one depends on curvature
            # Actually for cubic with a<0, max then min, we want the one between
            # Let's just pick the one in the middle of the scan range if both are valid
            valid_extremas = [e for e in extremas if 0 <= e <= 50]
            if valid_extremas:
                if len(valid_extremas) == 1:
                    selected = valid_extremas[0]
                else:
                    # Pick the one closer to middle of scan range
                    mid_range = (self.comp_v_range[0] + self.comp_v_range[1]) / 2
                    selected = min(valid_extremas, key=lambda e: abs(e - mid_range))
                
                self.logger.info(f"Selected optimal comp_v = {selected:.2f}V")
        
        return CubicFitResult(
            a=a, b=b, c=c, d=d,
            r_squared=r_squared,
            extremas=extremas,
            selected_extrema=selected
        )
    
    def plot_results(self, data: List[Dict[str, float]], fit: CubicFitResult) -> str:
        """
        Create and save plot of PMT vs comp_v with fit.
        
        Args:
            data: Scan data
            fit: Fit result
        
        Returns:
            Path to saved plot
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Sort data by comp_v for plotting
        sorted_data = sorted(data, key=lambda d: d["comp_v"])
        x_data = [d["comp_v"] for d in sorted_data]
        y_data = [d["pmt_signal"] for d in sorted_data]
        
        # Plot data points
        ax.scatter(x_data, y_data, c='blue', s=50, alpha=0.6, label='Data')
        
        # Plot fit
        x_fit = np.linspace(self.comp_v_range[0], self.comp_v_range[1], 200)
        y_fit = fit.a * x_fit**3 + fit.b * x_fit**2 + fit.c * x_fit + fit.d
        ax.plot(x_fit, y_fit, 'r-', linewidth=2, label=f'Fit (R²={fit.r_squared:.3f})')
        
        # Mark extremas
        for ext in fit.extremas:
            if self.comp_v_range[0] <= ext <= self.comp_v_range[1]:
                y_ext = fit.a * ext**3 + fit.b * ext**2 + fit.c * ext + fit.d
                color = 'green' if ext == fit.selected_extrema else 'orange'
                label = 'Optimal' if ext == fit.selected_extrema else 'Extrema'
                ax.axvline(x=ext, color=color, linestyle='--', alpha=0.7, label=f'{label}: {ext:.2f}V')
        
        ax.set_xlabel('Compensation Voltage (V)', fontsize=12)
        ax.set_ylabel('PMT Signal (counts)', fontsize=12)
        ax.set_title('Auto Compensation: PMT vs Comp_V', fontsize=14)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Save plot
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        plot_path = self.data_dir / f"auto_compensation_{timestamp}.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"Plot saved to {plot_path}")
        return str(plot_path)
    
    def run(self) -> ExperimentResult:
        """
        Execute auto compensation experiment.
        
        Returns:
            ExperimentResult with success status and data
        """
        self.logger.info("="*50)
        self.logger.info("AUTO COMPENSATION EXPERIMENT START")
        self.logger.info("="*50)
        
        try:
            # Phase 1: Record reference position at u_rf = 200V
            self.set_status(ExperimentStatus.RUNNING)
            self.set_progress(5)
            self.logger.info("PHASE 1: Setting u_rf = 200V")
            
            if not self.set_voltage("u_rf", self.u_rf_high):
                return ExperimentResult(
                    success=False,
                    error="Failed to set u_rf to 200V"
                )
            
            time.sleep(self.settling_time * 2)  # Extra settling for RF change
            
            pos = self.get_position()
            if pos is None:
                return ExperimentResult(
                    success=False,
                    error="Failed to get position at u_rf=200V"
                )
            
            _, ref_y = pos
            self.record_data("reference_y", ref_y)
            self.record_data("u_rf_high", self.u_rf_high)
            self.logger.info(f"Reference position y = {ref_y:.2f} pixels")
            
            # Phase 2: Set u_rf = 100V and calibrate comp_h
            self.set_progress(10)
            self.logger.info("PHASE 2: Setting u_rf = 100V and calibrating comp_h")
            
            if not self.set_voltage("u_rf", self.u_rf_low):
                return ExperimentResult(
                    success=False,
                    error="Failed to set u_rf to 100V"
                )
            
            time.sleep(self.settling_time * 2)
            
            if not self.calibrate_comp_h(ref_y):
                self.logger.warning("comp_h calibration did not converge, continuing anyway")
            
            # Record final comp_h
            final_comp_h = self.get_voltage("comp_h") or 0.0
            self.record_data("comp_h_final", final_comp_h)
            self.logger.info(f"comp_h = {final_comp_h:.3f}V")
            
            # Phase 3: Scan comp_v and record PMT
            self.set_progress(30)
            self.logger.info("PHASE 3: Scanning comp_v")
            
            self.scan_data = self.scan_comp_v()
            self.record_data("scan_data", self.scan_data)
            
            if len(self.scan_data) < 4:
                return ExperimentResult(
                    success=False,
                    error=f"Insufficient scan data ({len(self.scan_data)} points, need >= 4)"
                )
            
            # Phase 4: Fit cubic and find optimum
            self.set_progress(80)
            self.logger.info("PHASE 4: Fitting cubic and finding optimum")
            
            self.fit_result = self.fit_cubic(self.scan_data)
            
            if self.fit_result is None:
                return ExperimentResult(
                    success=False,
                    error="Cubic fit failed"
                )
            
            self.record_data("fit_coefficients", {
                "a": self.fit_result.a,
                "b": self.fit_result.b,
                "c": self.fit_result.c,
                "d": self.fit_result.d
            })
            self.record_data("r_squared", self.fit_result.r_squared)
            self.record_data("extremas", self.fit_result.extremas)
            self.record_data("selected_extrema", self.fit_result.selected_extrema)
            
            # Create plot
            plot_path = self.plot_results(self.scan_data, self.fit_result)
            self.record_data("plot_path", plot_path)
            
            # Phase 5: Set optimal comp_v
            self.set_progress(95)
            
            if self.fit_result.selected_extrema is not None:
                optimal_v = self.fit_result.selected_extrema
                
                if 0 <= optimal_v <= 50:
                    self.logger.info(f"Setting optimal comp_v = {optimal_v:.3f}V")
                    
                    if not self.set_voltage("comp_v", optimal_v):
                        return ExperimentResult(
                            success=False,
                            error=f"Failed to set optimal comp_v={optimal_v}"
                        )
                    
                    self.record_data("optimal_comp_v", optimal_v)
                    self.record_data("optimization_success", True)
                    
                    # Wait and verify
                    time.sleep(self.settling_time)
                    final_pmt = self.get_pmt_signal(self.pmt_integration_time)
                    self.record_data("final_pmt_signal", final_pmt)
                    
                    self.set_progress(100)
                    
                    return ExperimentResult(
                        success=True,
                        data=self.data,
                        message=f"Auto compensation complete. Optimal comp_v = {optimal_v:.3f}V, comp_h = {final_comp_h:.3f}V"
                    )
                else:
                    return ExperimentResult(
                        success=False,
                        error=f"Optimal comp_v ({optimal_v:.2f}V) outside valid range [0, 50]"
                    )
            else:
                return ExperimentResult(
                    success=False,
                    error="No valid extrema found for optimization"
                )
            
        except Exception as e:
            self.logger.exception("Experiment failed with exception")
            return ExperimentResult(
                success=False,
                error=str(e),
                message="Experiment crashed"
            )


# Command-line entry point
def main():
    """Run auto compensation experiment from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto Compensation Experiment")
    parser.add_argument("--host", default="localhost", help="Manager host")
    parser.add_argument("--port", type=int, default=5557, help="Manager port")
    parser.add_argument("--data-dir", default="data/experiments", help="Data directory")
    parser.add_argument("--blocking", action="store_true", help="Run blocking (not threaded)")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and run experiment
    exp = AutoCompensationExperiment(
        manager_host=args.host,
        manager_port=args.port,
        data_dir=args.data_dir
    )
    
    print("="*60)
    print("AUTO COMPENSATION EXPERIMENT")
    print("="*60)
    print(f"Manager: {args.host}:{args.port}")
    print(f"Data dir: {args.data_dir}")
    print("="*60)
    
    # Start experiment
    success = exp.start(blocking=args.blocking)
    
    if not args.blocking:
        print("\nExperiment started in background thread.")
        print("Waiting for completion...")
        
        # Wait with progress updates
        while exp.status == ExperimentStatus.RUNNING:
            time.sleep(1)
            progress = exp.progress
            print(f"\rProgress: {progress:.1f}%", end="", flush=True)
        
        print()  # New line after progress
        result = exp.wait()
    else:
        result = exp.result
    
    # Print results
    print("\n" + "="*60)
    if result and result.success:
        print("RESULT: SUCCESS")
        print(f"Message: {result.message}")
        print(f"\nOptimal voltages:")
        print(f"  comp_v = {result.data.get('optimal_comp_v', 'N/A')}")
        print(f"  comp_h = {result.data.get('comp_h_final', 'N/A')}")
        print(f"\nData saved to: {args.data_dir}")
    else:
        print("RESULT: FAILED")
        print(f"Error: {result.error if result else 'Unknown error'}")
    print("="*60)
    
    return 0 if (result and result.success) else 1


if __name__ == "__main__":
    exit(main())
