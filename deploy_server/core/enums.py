"""
Shared Enumerations for Lab Control Framework

This module contains all enums used across the system to ensure
consistency in serialization and state management.
"""

from enum import Enum


class SystemMode(Enum):
    """System operating modes."""
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    SAFE = "SAFE"


class AlgorithmState(Enum):
    """Turbo algorithm execution states."""
    IDLE = "idle"
    RUNNING = "running"
    OPTIMIZING = "optimizing"
    CONVERGED = "converged"
    DIVERGING = "diverging"
    ERROR = "error"
    STOPPED = "stopped"


class ExperimentStatus(Enum):
    """Experiment lifecycle states."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ExperimentPhase(Enum):
    """Experiment execution phases."""
    INIT = "init"
    DC_SETUP = "dc_setup"
    COOLING = "cooling"
    SWEEP = "sweep"
    SECULAR_COMPARE = "secular_compare"
    CAMERA = "camera"
    ANALYSIS = "analysis"
    COMPLETE = "complete"


class DataSource(Enum):
    """Canonical data source identifiers."""
    WAVEMETER = "wavemeter"
    SMILE = "smile"
    CAMERA = "camera"
    ARTIQ = "artiq"
    TURBO = "turbo"
    SECULAR_COMPARE = "secular_compare"


class CommandType(Enum):
    """ZMQ Command types between Manager and Workers."""
    SET_DC = "SET_DC"
    SET_COOLING = "SET_COOLING"
    SET_RF = "SET_RF"
    SET_PIEZO = "SET_PIEZO"
    SET_TOGGLE = "SET_TOGGLE"
    SET_DDS = "SET_DDS"
    RUN_SWEEP = "RUN_SWEEP"
    COMPARE = "COMPARE"
    STOP = "STOP"
    STATUS = "STATUS"


class MatchQuality(Enum):
    """Secular frequency comparison match quality."""
    EXCELLENT = "excellent"  # < 1% diff, chi2 < 3
    GOOD = "good"            # < 5% diff, chi2 < 5
    POOR = "poor"            # < 10% diff
    MISMATCH = "mismatch"    # >= 10% diff


# Physical Constants for RF Voltage Scaling
# Based on calibration: 700mV on SMILE interface = 100V real RF
RF_SCALE_V_PER_MV = 100.0 / 700.0  # ~0.142857 V/mV
RF_SCALE_MV_PER_V = 700.0 / 100.0  # 7.0 mV/V


def smile_mv_to_real_volts(smile_mv: float) -> float:
    """
    Convert SMILE interface mV to real RF voltage.
    
    Args:
        smile_mv: Voltage in millivolts on SMILE interface
        
    Returns:
        Real RF voltage in volts
    """
    return smile_mv * RF_SCALE_V_PER_MV


def real_volts_to_smile_mv(real_v: float) -> float:
    """
    Convert real RF voltage to SMILE interface mV.
    
    Args:
        real_v: Real RF voltage in volts
        
    Returns:
        SMILE interface voltage in millivolts
    """
    return real_v * RF_SCALE_MV_PER_V
