"""
Parameter space definitions for ion loading optimization.

Defines the parameter bounds, constraints, and decoupled parameterization
using Absolute Time Windows (start_time, duration) instead of sequential delays.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("optimizer.parameters")


class ParameterType(Enum):
    """Types of parameters."""
    CONTINUOUS = "continuous"
    DISCRETE = "discrete"
    BINARY = "binary"
    TIME_START = "time_start"      # Absolute start time
    TIME_DURATION = "time_duration"  # Duration


@dataclass
class ParameterConfig:
    """Configuration for a single parameter."""
    name: str
    param_type: ParameterType
    bounds: Tuple[float, float]  # (min, max)
    default: float = 0.0
    unit: str = ""
    description: str = ""
    group: str = ""  # Parameter group (e.g., "be_loading", "hd_loading")
    
    def validate(self, value: float) -> bool:
        """Check if value is within bounds."""
        return self.bounds[0] <= value <= self.bounds[1]


@dataclass
class TimeWindow:
    """
    Absolute time window for a device.
    
    Replaces sequential delays to prevent the "Domino Effect" where
    changing one delay shifts all subsequent events.
    """
    device: str
    start: float  # Absolute start time (ms)
    duration: float  # Active duration (ms)
    
    @property
    def end(self) -> float:
        """Calculate end time."""
        return self.start + self.duration
    
    def overlaps_with(self, other: 'TimeWindow', tolerance_ms: float = 0.1) -> bool:
        """Check if this window overlaps with another."""
        return not (self.end + tolerance_ms < other.start or 
                    other.end + tolerance_ms < self.start)


class ParameterSpace:
    """
    Defines the complete parameter space for mixed-species ion loading.
    
    Uses decoupled parameterization with Absolute Time Windows to prevent
    the "Domino Effect" where changing one delay shifts all subsequent events.
    """
    
    # =========================================================================
    # HARDWARE LIMITS (from settings.yaml)
    # =========================================================================
    
    # RF Voltage: 0-200V (real voltage after amplifier)
    U_RF_VOLTS_BOUNDS = (0.0, 200.0)
    
    # Electrodes: -1V to 50V
    ELECTRODE_BOUNDS = (-1.0, 50.0)
    
    # Piezo: 0-4V
    PIEZO_BOUNDS = (0.0, 4.0)
    
    # DDS Frequency: 0-200 MHz
    DDS_BOUNDS = (0.0, 200.0)
    
    # Raman amplitudes: 0-1
    AMPLITUDE_BOUNDS = (0.0, 1.0)
    
    # Binary toggles: 0 or 1
    BINARY_BOUNDS = (0, 1)
    
    # Time parameters (milliseconds)
    TIME_BOUNDS_MS = (0.0, 10000.0)  # 0 to 10 seconds
    
    # Laser power
    LASER_POWER_BOUNDS = (0.0, 10.0)  # mW
    LASER_DETUNING_BOUNDS = (-50.0, 50.0)  # MHz
    
    # =========================================================================
    # DEFAULT PARAMETERS
    # =========================================================================
    
    DEFAULTS = {
        # RF
        "u_rf_volts": 200.0,
        
        # Electrodes
        "ec1": 0.0,
        "ec2": 0.0,
        "comp_h": 0.0,
        "comp_v": 0.0,
        
        # Raman
        "amp0": 0.05,
        "amp1": 0.05,
        "sw0": 0,
        "sw1": 0,
        
        # Toggles
        "bephi": 0,
        "b_field": 1,
        "be_oven": 0,
        "uv3": 0,
        "e_gun": 0,
        "hd_valve": 0,
        
        # Laser & Piezo
        "piezo": 0.0,
        "dds_freq_mhz": 0.0,
        
        # Cooling laser
        "cooling_power_mw": 0.8,
        "cooling_detuning_mhz": -10.0,
        
        # Be+ Loading timing (absolute windows)
        "be_oven_start_ms": 0.0,
        "be_oven_duration_ms": 4500.0,
        "be_pi_laser_start_ms": 3000.0,
        "be_pi_laser_duration_ms": 500.0,
        
        # HD+ Loading timing
        "hd_valve_start_ms": 0.0,
        "hd_valve_duration_ms": 50.0,
        "hd_egun_start_ms": 500.0,
        "hd_egun_duration_ms": 1200.0,
        
        # Tickle pulse (for ejection)
        "tickle_amplitude": 0.5,
        "tickle_duration_ms": 100.0,
        "tickle_freq_khz": 307.0,
    }
    
    def __init__(self, phase: str = "be_loading"):
        """
        Initialize parameter space for a specific optimization phase.
        
        Args:
            phase: One of "be_loading", "be_ejection", "hd_loading"
        """
        self.phase = phase
        self.parameters: Dict[str, ParameterConfig] = {}
        self.time_windows: Dict[str, TimeWindow] = {}
        
        self._setup_parameters()
        self._setup_time_windows()
        self._setup_constraints()
        
        logger.info(f"Parameter space initialized for phase: {phase}")
    
    def _setup_parameters(self):
        """Set up parameter definitions based on phase."""
        
        # =========================================================================
        # COMMON PARAMETERS (all phases)
        # =========================================================================
        
        common_params = [
            # RF Voltage
            ParameterConfig(
                name="u_rf_volts",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.U_RF_VOLTS_BOUNDS,
                default=self.DEFAULTS["u_rf_volts"],
                unit="V",
                description="RF voltage after amplifier",
                group="common"
            ),
            
            # Electrodes
            ParameterConfig(
                name="ec1",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.ELECTRODE_BOUNDS,
                default=self.DEFAULTS["ec1"],
                unit="V",
                description="Endcap electrode 1",
                group="common"
            ),
            ParameterConfig(
                name="ec2",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.ELECTRODE_BOUNDS,
                default=self.DEFAULTS["ec2"],
                unit="V",
                description="Endcap electrode 2",
                group="common"
            ),
            ParameterConfig(
                name="comp_h",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.ELECTRODE_BOUNDS,
                default=self.DEFAULTS["comp_h"],
                unit="V",
                description="Horizontal compensation",
                group="common"
            ),
            ParameterConfig(
                name="comp_v",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.ELECTRODE_BOUNDS,
                default=self.DEFAULTS["comp_v"],
                unit="V",
                description="Vertical compensation",
                group="common"
            ),
        ]
        
        for p in common_params:
            self.parameters[p.name] = p
        
        # =========================================================================
        # PHASE-SPECIFIC PARAMETERS
        # =========================================================================
        
        if self.phase == "be_loading":
            self._setup_be_loading_params()
        elif self.phase == "be_ejection":
            self._setup_be_ejection_params()
        elif self.phase == "hd_loading":
            self._setup_hd_loading_params()
    
    def _setup_be_loading_params(self):
        """Set up parameters for Be+ loading phase."""
        be_params = [
            # B-field (usually constant but can be optimized)
            ParameterConfig(
                name="b_field",
                param_type=ParameterType.BINARY,
                bounds=self.BINARY_BOUNDS,
                default=self.DEFAULTS["b_field"],
                unit="",
                description="B-field on/off",
                group="be_loading"
            ),
            
            # Piezo for laser frequency tuning
            ParameterConfig(
                name="piezo",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.PIEZO_BOUNDS,
                default=self.DEFAULTS["piezo"],
                unit="V",
                description="Piezo voltage for laser frequency",
                group="be_loading"
            ),
            
            # Cooling laser parameters
            ParameterConfig(
                name="cooling_power_mw",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.LASER_POWER_BOUNDS,
                default=self.DEFAULTS["cooling_power_mw"],
                unit="mW",
                description="397nm cooling laser power",
                group="be_loading"
            ),
            ParameterConfig(
                name="cooling_detuning_mhz",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.LASER_DETUNING_BOUNDS,
                default=self.DEFAULTS["cooling_detuning_mhz"],
                unit="MHz",
                description="397nm laser detuning",
                group="be_loading"
            ),
            
            # Timing parameters (absolute windows)
            ParameterConfig(
                name="be_oven_start_ms",
                param_type=ParameterType.TIME_START,
                bounds=(0.0, 1000.0),
                default=self.DEFAULTS["be_oven_start_ms"],
                unit="ms",
                description="Be oven absolute start time",
                group="be_loading"
            ),
            ParameterConfig(
                name="be_oven_duration_ms",
                param_type=ParameterType.TIME_DURATION,
                bounds=(100.0, 8000.0),
                default=self.DEFAULTS["be_oven_duration_ms"],
                unit="ms",
                description="Be oven duration",
                group="be_loading"
            ),
            
            # PI (photoionization) laser - KEY PARAMETER
            ParameterConfig(
                name="be_pi_laser_start_ms",
                param_type=ParameterType.TIME_START,
                bounds=(0.0, 8000.0),
                default=self.DEFAULTS["be_pi_laser_start_ms"],
                unit="ms",
                description="235nm PI laser start time",
                group="be_loading"
            ),
            ParameterConfig(
                name="be_pi_laser_duration_ms",
                param_type=ParameterType.TIME_DURATION,
                bounds=(10.0, 2000.0),
                default=self.DEFAULTS["be_pi_laser_duration_ms"],
                unit="ms",
                description="235nm PI laser duration (KEY: minimize this)",
                group="be_loading"
            ),
        ]
        
        for p in be_params:
            self.parameters[p.name] = p
    
    def _setup_be_ejection_params(self):
        """Set up parameters for Be+ ejection phase."""
        ejection_params = [
            # Tickle pulse parameters
            ParameterConfig(
                name="tickle_amplitude",
                param_type=ParameterType.CONTINUOUS,
                bounds=(0.01, 2.0),
                default=self.DEFAULTS["tickle_amplitude"],
                unit="V",
                description="Tickle pulse amplitude",
                group="be_ejection"
            ),
            ParameterConfig(
                name="tickle_duration_ms",
                param_type=ParameterType.CONTINUOUS,
                bounds=(1.0, 500.0),
                default=self.DEFAULTS["tickle_duration_ms"],
                unit="ms",
                description="Tickle pulse duration",
                group="be_ejection"
            ),
            ParameterConfig(
                name="tickle_freq_khz",
                param_type=ParameterType.CONTINUOUS,
                bounds=(250.0, 400.0),
                default=self.DEFAULTS["tickle_freq_khz"],
                unit="kHz",
                description="Tickle frequency (secular resonance)",
                group="be_ejection"
            ),
            
            # RF voltage during ejection
            ParameterConfig(
                name="u_rf_volts",
                param_type=ParameterType.CONTINUOUS,
                bounds=(50.0, 200.0),
                default=self.DEFAULTS["u_rf_volts"],
                unit="V",
                description="RF voltage during ejection",
                group="be_ejection"
            ),
        ]
        
        for p in ejection_params:
            self.parameters[p.name] = p
    
    def _setup_hd_loading_params(self):
        """Set up parameters for HD+ loading phase."""
        hd_params = [
            # Piezo (must overlap with HD flux)
            ParameterConfig(
                name="piezo",
                param_type=ParameterType.CONTINUOUS,
                bounds=self.PIEZO_BOUNDS,
                default=self.DEFAULTS["piezo"],
                unit="V",
                description="Piezo voltage (must overlap with HD flux)",
                group="hd_loading"
            ),
            
            # E-gun parameters
            ParameterConfig(
                name="e_gun",
                param_type=ParameterType.BINARY,
                bounds=self.BINARY_BOUNDS,
                default=self.DEFAULTS["e_gun"],
                unit="",
                description="Electron gun on/off",
                group="hd_loading"
            ),
            
            # HD valve timing
            ParameterConfig(
                name="hd_valve_start_ms",
                param_type=ParameterType.TIME_START,
                bounds=(0.0, 1000.0),
                default=self.DEFAULTS["hd_valve_start_ms"],
                unit="ms",
                description="HD valve start time",
                group="hd_loading"
            ),
            ParameterConfig(
                name="hd_valve_duration_ms",
                param_type=ParameterType.TIME_DURATION,
                bounds=(10.0, 200.0),
                default=self.DEFAULTS["hd_valve_duration_ms"],
                unit="ms",
                description="HD valve duration (gas load)",
                group="hd_loading"
            ),
            
            # E-gun timing
            ParameterConfig(
                name="hd_egun_start_ms",
                param_type=ParameterType.TIME_START,
                bounds=(0.0, 5000.0),
                default=self.DEFAULTS["hd_egun_start_ms"],
                unit="ms",
                description="E-gun start time",
                group="hd_loading"
            ),
            ParameterConfig(
                name="hd_egun_duration_ms",
                param_type=ParameterType.TIME_DURATION,
                bounds=(100.0, 5000.0),
                default=self.DEFAULTS["hd_egun_duration_ms"],
                unit="ms",
                description="E-gun duration (thermal load)",
                group="hd_loading"
            ),
            
            # RF voltage during HD loading
            ParameterConfig(
                name="u_rf_volts",
                param_type=ParameterType.CONTINUOUS,
                bounds=(100.0, 200.0),
                default=150.0,
                unit="V",
                description="RF voltage during HD loading",
                group="hd_loading"
            ),
        ]
        
        for p in hd_params:
            self.parameters[p.name] = p
    
    def _setup_time_windows(self):
        """Set up time windows for devices."""
        if self.phase == "be_loading":
            self.time_windows["be_oven"] = TimeWindow(
                device="be_oven",
                start=self.DEFAULTS["be_oven_start_ms"],
                duration=self.DEFAULTS["be_oven_duration_ms"]
            )
            self.time_windows["be_pi_laser"] = TimeWindow(
                device="be_pi_laser",
                start=self.DEFAULTS["be_pi_laser_start_ms"],
                duration=self.DEFAULTS["be_pi_laser_duration_ms"]
            )
            
        elif self.phase == "hd_loading":
            self.time_windows["hd_valve"] = TimeWindow(
                device="hd_valve",
                start=self.DEFAULTS["hd_valve_start_ms"],
                duration=self.DEFAULTS["hd_valve_duration_ms"]
            )
            self.time_windows["hd_egun"] = TimeWindow(
                device="hd_egun",
                start=self.DEFAULTS["hd_egun_start_ms"],
                duration=self.DEFAULTS["hd_egun_duration_ms"]
            )
    
    def _setup_constraints(self):
        """Set up linear constraints for causality and physical validity."""
        self.constraints: List[Dict[str, Any]] = []
        
        if self.phase == "be_loading":
            # PI laser must overlap with oven flux
            self.constraints.append({
                "type": "overlap",
                "devices": ["be_oven", "be_pi_laser"],
                "description": "PI laser must overlap with oven flux"
            })
            
            # Oven duration > PI duration
            self.constraints.append({
                "type": "inequality",
                "expression": "be_oven_duration_ms > be_pi_laser_duration_ms + 100",
                "description": "Oven must run longer than PI laser + buffer"
            })
            
        elif self.phase == "hd_loading":
            # Piezo must overlap with HD flux
            self.constraints.append({
                "type": "overlap",
                "devices": ["hd_valve", "piezo_active"],
                "description": "Piezo must overlap with HD valve"
            })
    
    def get_bounds_list(self) -> List[Tuple[float, float]]:
        """
        Get list of (min, max) bounds for all parameters.
        
        Returns:
            List of bounds in parameter order
        """
        return [p.bounds for p in self.parameters.values()]
    
    def get_parameter_names(self) -> List[str]:
        """Get list of parameter names."""
        return list(self.parameters.keys())
    
    def get_defaults_array(self) -> np.ndarray:
        """Get default values as numpy array."""
        return np.array([p.default for p in self.parameters.values()])
    
    def dict_to_array(self, param_dict: Dict[str, float]) -> np.ndarray:
        """Convert parameter dictionary to array."""
        return np.array([
            param_dict.get(name, self.parameters[name].default)
            for name in self.get_parameter_names()
        ])
    
    def array_to_dict(self, param_array: np.ndarray) -> Dict[str, float]:
        """Convert parameter array to dictionary."""
        names = self.get_parameter_names()
        return {
            name: float(param_array[i])
            for i, name in enumerate(names)
        }
    
    def validate(self, param_dict: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        Validate parameters against bounds and constraints.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check bounds
        for name, value in param_dict.items():
            if name in self.parameters:
                param = self.parameters[name]
                if not param.validate(value):
                    errors.append(
                        f"{name}={value} outside bounds {param.bounds}"
                    )
        
        # Check time window constraints
        if self.phase == "be_loading":
            oven_start = param_dict.get("be_oven_start_ms", self.DEFAULTS["be_oven_start_ms"])
            oven_dur = param_dict.get("be_oven_duration_ms", self.DEFAULTS["be_oven_duration_ms"])
            pi_start = param_dict.get("be_pi_laser_start_ms", self.DEFAULTS["be_pi_laser_start_ms"])
            pi_dur = param_dict.get("be_pi_laser_duration_ms", self.DEFAULTS["be_pi_laser_duration_ms"])
            
            oven_window = TimeWindow("be_oven", oven_start, oven_dur)
            pi_window = TimeWindow("be_pi_laser", pi_start, pi_dur)
            
            if not oven_window.overlaps_with(pi_window):
                errors.append("PI laser does not overlap with oven flux")
        
        return len(errors) == 0, errors
    
    def get_time_windows_from_params(self, param_dict: Dict[str, float]) -> Dict[str, TimeWindow]:
        """Extract time windows from parameter dictionary."""
        windows = {}
        
        if self.phase == "be_loading":
            windows["be_oven"] = TimeWindow(
                device="be_oven",
                start=param_dict.get("be_oven_start_ms", self.DEFAULTS["be_oven_start_ms"]),
                duration=param_dict.get("be_oven_duration_ms", self.DEFAULTS["be_oven_duration_ms"])
            )
            windows["be_pi_laser"] = TimeWindow(
                device="be_pi_laser",
                start=param_dict.get("be_pi_laser_start_ms", self.DEFAULTS["be_pi_laser_start_ms"]),
                duration=param_dict.get("be_pi_laser_duration_ms", self.DEFAULTS["be_pi_laser_duration_ms"])
            )
            
        elif self.phase == "hd_loading":
            windows["hd_valve"] = TimeWindow(
                device="hd_valve",
                start=param_dict.get("hd_valve_start_ms", self.DEFAULTS["hd_valve_start_ms"]),
                duration=param_dict.get("hd_valve_duration_ms", self.DEFAULTS["hd_valve_duration_ms"])
            )
            windows["hd_egun"] = TimeWindow(
                device="hd_egun",
                start=param_dict.get("hd_egun_start_ms", self.DEFAULTS["hd_egun_start_ms"]),
                duration=param_dict.get("hd_egun_duration_ms", self.DEFAULTS["hd_egun_duration_ms"])
            )
        
        return windows
    
    def get_n_dims(self) -> int:
        """Get number of dimensions."""
        return len(self.parameters)


# Convenience functions for creating parameter spaces
def create_be_loading_space() -> ParameterSpace:
    """Create parameter space for Be+ loading optimization."""
    return ParameterSpace(phase="be_loading")


def create_be_ejection_space() -> ParameterSpace:
    """Create parameter space for Be+ ejection optimization."""
    return ParameterSpace(phase="be_ejection")


def create_hd_loading_space() -> ParameterSpace:
    """Create parameter space for HD+ loading optimization."""
    return ParameterSpace(phase="hd_loading")
