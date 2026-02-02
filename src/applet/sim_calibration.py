"""
SIM Calibration (System Identification and Modeling) Experiment.

Measures secular frequencies (axial + two radial) across a range of trap parameters
to calibrate the kappa and chi parameters using the fit_Kappa_Chi_URF program.

Workflow:
1. Load reference secular frequencies from reference_eigenfrequencies.md
2. For each combination of (u_rf, ec1=ec2=v_end):
   a. Set trap voltages
   b. Measure axial secular frequency (urukul0_ch0)
   c. Measure radial X secular frequency (urukul0_ch1)
   d. Measure radial Y secular frequency (urukul0_ch1)
   e. Update reference data after each measurement
3. After all measurements, run fit_Kappa_Chi_URF
4. Calculate new kappa and chi parameters with uncertainties
5. Update config with new parameters

Reference Data Format (from reference_eigenfrequencies.md):
    U_RF (V),V_end=10V wx (2pi kHz),wy (2pi kHz),V_end=20V wx,wy,...

Usage:
    python -m applet.experiments.sim_calibration
    # or via controller API
"""

import time
import json
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import io

import numpy as np

from .base_experiment import BaseExperiment, ExperimentStatus, ExperimentResult


@dataclass
class SecularMeasurement:
    """Single secular frequency measurement."""
    u_rf: float
    v_end: float
    axis: str  # 'axial', 'radial_x', 'radial_y'
    frequency_khz: float
    uncertainty_khz: Optional[float] = None
    timestamp: Optional[str] = None
    pmt_data: Optional[List[int]] = None


@dataclass
class FitResult:
    """Result from fit_Kappa_Chi_URF."""
    chi_x: float
    chi_y: float
    kappa_x: float
    kappa_y: float
    kappa_z: float
    chi_x_err: Optional[float] = None
    chi_y_err: Optional[float] = None
    kappa_x_err: Optional[float] = None
    kappa_y_err: Optional[float] = None
    kappa_z_err: Optional[float] = None
    success: bool = False
    message: str = ""


class SimCalibrationExperiment(BaseExperiment):
    """
    SIM Calibration Experiment.
    
    Calibrates trap geometry parameters (kappa, chi) by measuring secular
    frequencies across a range of RF and endcap voltages.
    
    Parameters:
        u_rf_values: List of RF voltages to scan [V]
        v_end_values: List of endcap voltages [V] (ec1=ec2=v_end)
        ion_masses: List of ion mass numbers (default: [9] for single Be+)
        sweep_span_khz: Frequency sweep span [kHz]
        sweep_steps: Number of points per sweep
        on_time_ms: PMT gate time [ms]
        off_time_ms: Delay between points [ms]
        attenuation_db: DDS attenuation [dB]
    """
    
    def __init__(
        self,
        manager_host: str = "localhost",
        manager_port: int = 5557,
        data_dir: str = "data/sim_calibration"
    ):
        super().__init__(
            name="sim_calibration",
            manager_host=manager_host,
            manager_port=manager_port,
            data_dir=data_dir
        )
        
        # Measurement parameters
        self.u_rf_values: List[float] = [57.1, 71.4, 85.7, 100.0, 114.3, 128.6, 142.9, 157.1, 171.4, 200.0]
        self.v_end_values: List[float] = [10.0, 20.0, 30.0]
        self.ion_masses: List[int] = [9]  # Single Be+ for simplicity
        
        # Sweep parameters
        self.sweep_span_khz: float = 40.0
        self.sweep_steps: int = 41
        self.on_time_ms: float = 100.0
        self.off_time_ms: float = 100.0
        self.attenuation_db: float = 25.0
        
        # Axial vs radial frequency ranges (for intelligent sweep centering)
        self.axial_freq_range: Tuple[float, float] = (200.0, 1000.0)  # kHz
        self.radial_freq_range: Tuple[float, float] = (400.0, 1800.0)  # kHz
        
        # Results storage
        self.measurements: List[SecularMeasurement] = []
        self.reference_data: Dict[str, Any] = {}
        self.fit_result: Optional[FitResult] = None
        
        # Paths
        self.reference_file = Path(__file__).parent.parent.parent / "analysis" / "eigenmodes" / "reference eigenfrequencies.md"
        self.fit_module_path = Path(__file__).parent.parent.parent / "analysis" / "eigenmodes"
        
        # Measurement tracking
        self.current_measurement_index: int = 0
        self.total_measurements: int = 0
    
    def load_reference_data(self) -> Dict[str, Any]:
        """
        Load reference secular frequencies from CSV file.
        
        Returns:
            Dictionary with reference data structure
        """
        self.logger.info(f"Loading reference data from: {self.reference_file}")
        
        if not self.reference_file.exists():
            self.logger.warning("Reference file not found, creating empty structure")
            return self._create_empty_reference()
        
        try:
            # Parse the markdown/CSV file
            with open(self.reference_file, 'r') as f:
                content = f.read()
            
            # Parse CSV content (skip header line if it starts with #)
            lines = content.strip().split('\n')
            csv_lines = [line for line in lines if not line.startswith('#')]
            
            if not csv_lines:
                return self._create_empty_reference()
            
            # Parse header
            header = csv_lines[0].split(',')
            
            # Parse data rows
            data = {}
            for line in csv_lines[1:]:
                parts = line.split(',')
                if len(parts) >= 2:
                    u_rf = float(parts[0])
                    data[u_rf] = {}
                    
                    # Parse each V_end column
                    for i, col in enumerate(header[1:], 1):
                        if i < len(parts) and parts[i] and parts[i] != '-':
                            # Parse frequency and uncertainty
                            freq_str = parts[i].strip()
                            # Format: "value(uncertainty)" e.g., "420.0(5)"
                            if '(' in freq_str:
                                freq_val = float(freq_str.split('(')[0])
                                unc_str = freq_str.split('(')[1].rstrip(')')
                                uncertainty = float(unc_str) if unc_str else 0.5
                            else:
                                freq_val = float(freq_str)
                                uncertainty = 0.5
                            
                            # Determine axis from column name
                            if 'wx' in col.lower():
                                axis = 'radial_x'
                            elif 'wy' in col.lower():
                                axis = 'radial_y'
                            else:
                                axis = 'unknown'
                            
                            # Extract V_end from column name
                            v_end = None
                            if 'v_end=' in col.lower():
                                v_str = col.lower().split('v_end=')[1].split()[0]
                                v_end = float(v_str.rstrip('v'))
                            
                            if v_end is not None:
                                key = f"v{v_end}_{axis}"
                                data[u_rf][key] = {
                                    'frequency_khz': freq_val,
                                    'uncertainty_khz': uncertainty
                                }
            
            self.reference_data = {
                'header': header,
                'data': data,
                'source': str(self.reference_file)
            }
            
            self.logger.info(f"Loaded reference data for {len(data)} U_RF values")
            return self.reference_data
            
        except Exception as e:
            self.logger.error(f"Error loading reference data: {e}")
            return self._create_empty_reference()
    
    def _create_empty_reference(self) -> Dict[str, Any]:
        """Create empty reference data structure."""
        return {
            'header': ['U_RF (V)'],
            'data': {},
            'source': str(self.reference_file)
        }
    
    def save_reference_data(self):
        """Save updated reference data back to CSV file."""
        try:
            # Build CSV content
            lines = []
            
            # Build header based on v_end values and axes
            header = ['U_RF (V)']
            for v_end in sorted(self.v_end_values):
                header.append(f'V_end={v_end}V wx (2pi kHz)')
                header.append(f'V_end={v_end}V wy (2pi kHz)')
            lines.append(','.join(header))
            
            # Build data rows
            all_u_rf = sorted(set(list(self.reference_data.get('data', {}).keys()) + 
                                   [m.u_rf for m in self.measurements]))
            
            for u_rf in all_u_rf:
                row = [str(u_rf)]
                
                for v_end in sorted(self.v_end_values):
                    # Find measurements for this u_rf, v_end
                    wx_meas = self._find_measurement(u_rf, v_end, 'radial_x')
                    wy_meas = self._find_measurement(u_rf, v_end, 'radial_y')
                    
                    # Format: value(uncertainty) or just value
                    if wx_meas:
                        unc = wx_meas.uncertainty_khz or 0.5
                        row.append(f"{wx_meas.frequency_khz:.1f}({unc:.1f})")
                    else:
                        # Check reference data
                        ref = self.reference_data.get('data', {}).get(u_rf, {})
                        wx_key = f'v{v_end}_radial_x'
                        if wx_key in ref:
                            f = ref[wx_key]['frequency_khz']
                            u = ref[wx_key]['uncertainty_khz']
                            row.append(f"{f:.1f}({u:.1f})")
                        else:
                            row.append('-')
                    
                    if wy_meas:
                        unc = wy_meas.uncertainty_khz or 0.5
                        row.append(f"{wy_meas.frequency_khz:.1f}({unc:.1f})")
                    else:
                        ref = self.reference_data.get('data', {}).get(u_rf, {})
                        wy_key = f'v{v_end}_radial_y'
                        if wy_key in ref:
                            f = ref[wy_key]['frequency_khz']
                            u = ref[wy_key]['uncertainty_khz']
                            row.append(f"{f:.1f}({u:.1f})")
                        else:
                            row.append('-')
                
                lines.append(','.join(row))
            
            # Write to file
            with open(self.reference_file, 'w') as f:
                f.write('\n'.join(lines))
            
            self.logger.info(f"Reference data saved to: {self.reference_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving reference data: {e}")
    
    def _find_measurement(self, u_rf: float, v_end: float, axis: str) -> Optional[SecularMeasurement]:
        """Find a measurement by parameters."""
        for m in self.measurements:
            if (abs(m.u_rf - u_rf) < 0.1 and 
                abs(m.v_end - v_end) < 0.1 and 
                m.axis == axis):
                return m
        return None
    
    def estimate_sweep_center(self, u_rf: float, v_end: float, axis: str) -> float:
        """
        Estimate sweep center frequency based on reference data or physics model.
        
        Args:
            u_rf: RF voltage [V]
            v_end: Endcap voltage [V]
            axis: 'axial', 'radial_x', or 'radial_y'
            
        Returns:
            Estimated center frequency [kHz]
        """
        # First try to find in reference data
        key = f'v{v_end}_{axis}'
        ref = self.reference_data.get('data', {}).get(u_rf, {}).get(key)
        if ref:
            return ref['frequency_khz']
        
        # Interpolate from nearby U_RF values
        u_rf_values = sorted(self.reference_data.get('data', {}).keys())
        if len(u_rf_values) >= 2:
            # Find bracketing U_RF values
            lower_u = None
            upper_u = None
            for u in u_rf_values:
                if u <= u_rf:
                    lower_u = u
                if u >= u_rf and upper_u is None:
                    upper_u = u
                    break
            
            if lower_u is not None and upper_u is not None and lower_u != upper_u:
                lower_ref = self.reference_data['data'][lower_u].get(key)
                upper_ref = self.reference_data['data'][upper_u].get(key)
                if lower_ref and upper_ref:
                    # Linear interpolation
                    frac = (u_rf - lower_u) / (upper_u - lower_u)
                    freq = lower_ref['frequency_khz'] + frac * (
                        upper_ref['frequency_khz'] - lower_ref['frequency_khz']
                    )
                    return freq
        
        # Fallback to physics estimates
        if 'axial' in axis:
            # Axial frequency scales as sqrt(V_end)
            # Estimate based on typical values
            base_freq = 400.0  # kHz at 10V
            return base_freq * np.sqrt(v_end / 10.0)
        else:
            # Radial frequency depends on both U_RF and V_end
            # Roughly linear with U_RF
            base_freq = 450.0  # kHz at 57.1V, 10V
            return base_freq * (u_rf / 57.1)
    
    def set_trap_voltages(self, u_rf: float, v_end: float) -> bool:
        """
        Set trap voltages via manager.
        
        Args:
            u_rf: RF voltage [V]
            v_end: DC endcap voltage [V] (ec1=ec2=v_end)
            
        Returns:
            True if successful
        """
        self.logger.info(f"Setting trap voltages: U_RF={u_rf}V, V_end={v_end}V")
        
        # Set RF voltage via LabVIEW (through manager)
        response = self.send_to_manager({
            "action": "SET",
            "source": "EXPERIMENT_SIM_CALIB",
            "params": {
                "u_rf_volts": u_rf,
                "ec1": v_end,
                "ec2": v_end
            }
        })
        
        if response.get("status") == "success":
            self.logger.info("Trap voltages set successfully")
            # Wait for voltages to settle
            time.sleep(0.5)
            return True
        else:
            self.logger.error(f"Failed to set trap voltages: {response.get('message')}")
            return False
    
    def measure_secular_frequency(self, u_rf: float, v_end: float, axis: str) -> Optional[SecularMeasurement]:
        """
        Measure secular frequency for given trap parameters and axis.
        
        Args:
            u_rf: RF voltage [V]
            v_end: Endcap voltage [V]
            axis: 'axial', 'radial_x', or 'radial_y'
            
        Returns:
            SecularMeasurement with results
        """
        self.logger.info(f"Measuring {axis} secular frequency at U_RF={u_rf}V, V_end={v_end}V")
        
        # Estimate sweep center
        center_freq = self.estimate_sweep_center(u_rf, v_end, axis)
        
        # Determine DDS choice based on axis
        if axis == 'axial':
            dds_choice = 'axial'  # urukul0_ch0
        else:
            dds_choice = 'radial'  # urukul0_ch1
        
        # Adjust span based on axis
        if axis == 'axial':
            span = min(self.sweep_span_khz, 60.0)  # Narrower span for axial
        else:
            span = self.sweep_span_khz
        
        # Run secular sweep via manager/ARTIQ
        sweep_params = {
            "target_frequency_khz": center_freq,
            "span_khz": span,
            "steps": self.sweep_steps,
            "on_time_ms": self.on_time_ms,
            "off_time_ms": self.off_time_ms,
            "attenuation_db": self.attenuation_db,
            "dds_choice": dds_choice,
            "axis": axis  # Pass axis info for any axis-specific handling
        }
        
        response = self.send_to_manager({
            "action": "SECULAR_SWEEP",
            "source": "EXPERIMENT_SIM_CALIB",
            "params": sweep_params,
            "timeout_ms": int((self.on_time_ms + self.off_time_ms) * self.sweep_steps + 30000)
        })
        
        if response.get("status") != "success":
            self.logger.error(f"Secular sweep failed: {response.get('message')}")
            return None
        
        # Extract sweep data
        sweep_data = response.get("sweep_data", {})
        frequencies = sweep_data.get("frequencies_khz", [])
        pmt_counts = sweep_data.get("pmt_counts", [])
        
        if not frequencies or not pmt_counts:
            self.logger.error("No sweep data returned")
            return None
        
        # Find peak (secular frequency)
        peak_idx = np.argmax(pmt_counts)
        peak_freq = frequencies[peak_idx]
        
        # Estimate uncertainty based on sweep step size
        step_size = span / (self.sweep_steps - 1)
        uncertainty = step_size / 2
        
        measurement = SecularMeasurement(
            u_rf=u_rf,
            v_end=v_end,
            axis=axis,
            frequency_khz=peak_freq,
            uncertainty_khz=uncertainty,
            timestamp=datetime.now().isoformat(),
            pmt_data=pmt_counts
        )
        
        self.logger.info(f"{axis} frequency: {peak_freq:.1f} ± {uncertainty:.1f} kHz")
        
        return measurement
    
    def run_all_measurements(self) -> List[SecularMeasurement]:
        """
        Run all secular frequency measurements.
        
        Returns:
            List of all measurements
        """
        self.measurements = []
        
        # Calculate total number of measurements
        axes = ['radial_x', 'radial_y']  # Based on reference data format
        self.total_measurements = len(self.u_rf_values) * len(self.v_end_values) * len(axes)
        self.current_measurement_index = 0
        
        self.logger.info(f"Starting {self.total_measurements} measurements")
        
        for u_rf in self.u_rf_values:
            for v_end in self.v_end_values:
                # Set trap voltages
                if not self.set_trap_voltages(u_rf, v_end):
                    self.logger.warning(f"Skipping U_RF={u_rf}, V_end={v_end} due to voltage setting failure")
                    continue
                
                # Measure each axis
                for axis in axes:
                    if self.check_stop():
                        return self.measurements
                    
                    self.pause_point()
                    
                    # Measure
                    measurement = self.measure_secular_frequency(u_rf, v_end, axis)
                    
                    if measurement:
                        self.measurements.append(measurement)
                        # Save reference data after each measurement
                        self.save_reference_data()
                    else:
                        self.logger.warning(f"Failed to measure {axis} at U_RF={u_rf}, V_end={v_end}")
                    
                    self.current_measurement_index += 1
                    progress = 10 + (self.current_measurement_index / self.total_measurements) * 70
                    self.set_progress(progress)
        
        return self.measurements
    
    def run_fit(self) -> Optional[FitResult]:
        """
        Run fit_Kappa_Chi_URF on collected data.
        
        Returns:
            FitResult with fitted parameters
        """
        self.logger.info("Running kappa/chi fit...")
        
        try:
            # Add fit module to path
            import sys
            if str(self.fit_module_path) not in sys.path:
                sys.path.insert(0, str(self.fit_module_path))
            
            from fit_Kappa_Chi_URF import DataSet, fit_chi_kappa_multi
            
            # Build datasets from measurements
            datasets = []
            
            # Group measurements by (u_rf, v_end)
            grouped = {}
            for m in self.measurements:
                key = (m.u_rf, m.v_end)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(m)
            
            # Create DataSet for each (u_rf, v_end) combination
            for (u_rf, v_end), meas_list in grouped.items():
                # Separate by axis
                radial_x = [m for m in meas_list if m.axis == 'radial_x']
                radial_y = [m for m in meas_list if m.axis == 'radial_y']
                axial = [m for m in meas_list if m.axis == 'axial']
                
                # Create radial dataset (wx, wy)
                if radial_x and radial_y:
                    freqs = [radial_x[0].frequency_khz, radial_y[0].frequency_khz]
                    sigmas = [radial_x[0].uncertainty_khz or 0.5, 
                             radial_y[0].uncertainty_khz or 0.5]
                    
                    ds = DataSet(
                        masses_A=self.ion_masses,
                        measured_kHz=freqs,
                        which_modes='radial',
                        sigma_kHz=sigmas,
                        u_RF=u_rf,
                        v_end=v_end,
                        name=f"U{u_rf:.1f}V_V{v_end:.1f}V"
                    )
                    datasets.append(ds)
            
            if len(datasets) < 2:
                self.logger.error(f"Need at least 2 datasets for fitting, have {len(datasets)}")
                return None
            
            self.logger.info(f"Fitting with {len(datasets)} datasets")
            
            # Run fit
            result = fit_chi_kappa_multi(datasets)
            
            fit_result = FitResult(
                chi_x=result.chi[0],
                chi_y=result.chi[1],
                kappa_x=result.kappa[0],
                kappa_y=result.kappa[1],
                kappa_z=result.kappa[2],
                chi_x_err=result.chi_err[0] if result.chi_err else None,
                chi_y_err=result.chi_err[1] if result.chi_err else None,
                kappa_x_err=result.kappa_err[0] if result.kappa_err else None,
                kappa_y_err=result.kappa_err[1] if result.kappa_err else None,
                kappa_z_err=result.kappa_err[2] if result.kappa_err else None,
                success=result.success,
                message=result.message
            )
            
            self.logger.info(f"Fit result: chi=[{fit_result.chi_x:.6f}, {fit_result.chi_y:.6f}]")
            self.logger.info(f"            kappa=[{fit_result.kappa_x:.6f}, {fit_result.kappa_y:.6f}, {fit_result.kappa_z:.6f}]")
            
            return fit_result
            
        except Exception as e:
            self.logger.exception("Fit failed")
            return None
    
    def update_config(self, fit_result: FitResult) -> bool:
        """
        Update config with new kappa and chi parameters.
        
        Args:
            fit_result: Fit result with new parameters
            
        Returns:
            True if successful
        """
        self.logger.info("Updating config with new parameters...")
        
        try:
            from core import get_config
            
            config = get_config()
            
            # Update trap geometry parameters
            config_data = {
                'trap': {
                    'chi': [fit_result.chi_x, fit_result.chi_y],
                    'kappa': [fit_result.kappa_x, fit_result.kappa_y, fit_result.kappa_z],
                    'chi_uncertainty': [fit_result.chi_x_err, fit_result.chi_y_err],
                    'kappa_uncertainty': [fit_result.kappa_x_err, fit_result.kappa_y_err, fit_result.kappa_z_err],
                    'calibration_timestamp': datetime.now().isoformat()
                }
            }
            
            # Save to config (this depends on how config is implemented)
            # For now, save to a JSON file
            config_file = Path(self.data_dir) / "sim_calibration_config.json"
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.logger.info(f"Config saved to: {config_file}")
            
            # Record in experiment data
            self.record_data("calibrated_chi", [fit_result.chi_x, fit_result.chi_y])
            self.record_data("calibrated_kappa", [fit_result.kappa_x, fit_result.kappa_y, fit_result.kappa_z])
            self.record_data("chi_uncertainty", [fit_result.chi_x_err, fit_result.chi_y_err])
            self.record_data("kappa_uncertainty", [fit_result.kappa_x_err, fit_result.kappa_y_err, fit_result.kappa_z_err])
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update config: {e}")
            return False
    
    def save_measurement_data(self):
        """Save all measurement data to JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sim_calibration_{timestamp}.json"
        filepath = self.data_dir / filename
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            "timestamp": timestamp,
            "experiment": "sim_calibration",
            "parameters": {
                "u_rf_values": self.u_rf_values,
                "v_end_values": self.v_end_values,
                "ion_masses": self.ion_masses,
                "sweep_span_khz": self.sweep_span_khz,
                "sweep_steps": self.sweep_steps
            },
            "measurements": [
                {
                    "u_rf": m.u_rf,
                    "v_end": m.v_end,
                    "axis": m.axis,
                    "frequency_khz": m.frequency_khz,
                    "uncertainty_khz": m.uncertainty_khz,
                    "timestamp": m.timestamp
                }
                for m in self.measurements
            ],
            "fit_result": asdict(self.fit_result) if self.fit_result else None
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        self.logger.info(f"Measurement data saved to: {filepath}")
        return str(filepath)
    
    def run(self) -> ExperimentResult:
        """
        Execute SIM calibration experiment.
        
        Returns:
            ExperimentResult with success status and data
        """
        self.logger.info("="*60)
        self.logger.info("SIM CALIBRATION EXPERIMENT START")
        self.logger.info("="*60)
        
        try:
            self.set_status(ExperimentStatus.RUNNING)
            
            # Phase 1: Load reference data
            self.set_progress(5)
            self.load_reference_data()
            
            if self.check_stop():
                return ExperimentResult(success=False, error="Experiment stopped")
            
            # Phase 2: Run all measurements
            self.set_progress(10)
            self.run_all_measurements()
            
            if not self.measurements:
                return ExperimentResult(
                    success=False,
                    error="No measurements completed"
                )
            
            if self.check_stop():
                return ExperimentResult(success=False, error="Experiment stopped")
            
            # Phase 3: Save measurement data
            self.set_progress(80)
            data_file = self.save_measurement_data()
            
            # Phase 4: Run fit
            self.set_progress(85)
            self.fit_result = self.run_fit()
            
            if self.fit_result and self.fit_result.success:
                # Phase 5: Update config
                self.set_progress(95)
                self.update_config(self.fit_result)
                
                self.set_progress(100)
                
                msg = (f"SIM calibration complete. "
                       f"chi=[{self.fit_result.chi_x:.4f}, {self.fit_result.chi_y:.4f}], "
                       f"kappa=[{self.fit_result.kappa_x:.4f}, {self.fit_result.kappa_y:.4f}, {self.fit_result.kappa_z:.4f}]")
                
                return ExperimentResult(
                    success=True,
                    data=self.data,
                    message=msg
                )
            else:
                self.set_progress(100)
                return ExperimentResult(
                    success=False,
                    error="Fit failed",
                    data=self.data,
                    message="Measurements complete but fit failed"
                )
            
        except Exception as e:
            self.logger.exception("SIM calibration experiment failed")
            return ExperimentResult(
                success=False,
                error=str(e),
                message="Experiment crashed"
            )


# Command-line entry point
def main():
    """Run SIM calibration experiment from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SIM Calibration Experiment")
    parser.add_argument("--host", default="localhost", help="Manager host")
    parser.add_argument("--port", type=int, default=5557, help="Manager port")
    parser.add_argument("--data-dir", default="data/sim_calibration", help="Data directory")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and run experiment
    exp = SimCalibrationExperiment(
        manager_host=args.host,
        manager_port=args.port,
        data_dir=args.data_dir
    )
    
    print("="*60)
    print("SIM CALIBRATION EXPERIMENT")
    print("="*60)
    print(f"Manager: {args.host}:{args.port}")
    print(f"Data dir: {args.data_dir}")
    print(f"U_RF values: {exp.u_rf_values}")
    print(f"V_end values: {exp.v_end_values}")
    print("="*60)
    
    # Run experiment
    result = exp.run()
    
    print("\n" + "="*60)
    if result.success:
        print("RESULT: SUCCESS")
        print(f"Message: {result.message}")
        if result.data.get('calibrated_chi'):
            print(f"\nCalibrated chi: {result.data['calibrated_chi']}")
            print(f"Calibrated kappa: {result.data['calibrated_kappa']}")
    else:
        print("RESULT: FAILED")
        print(f"Error: {result.error}")
    print("="*60)
    
    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())
