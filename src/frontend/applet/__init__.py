"""
Experimental scripts module for the Applet Server.

This module contains modular experimental scripts that can be
controlled via the Flask API.
"""

from .base import BaseExperiment, ExperimentStatus
from .auto_compensation import AutoCompensationExperiment
from .cam_sweep import CamSweepExperiment
from .sim_calibration import SimCalibrationExperiment

# TrapEigenmodeExperiment requires analysis module which may not be available
try:
    from .trap_eigenmode import TrapEigenmodeExperiment
    ANALYSIS_AVAILABLE = True
except ImportError:
    TrapEigenmodeExperiment = None
    ANALYSIS_AVAILABLE = False

__all__ = [
    'BaseExperiment', 'ExperimentStatus',
    'AutoCompensationExperiment', 'TrapEigenmodeExperiment',
    'CamSweepExperiment', 'SimCalibrationExperiment'
]

# Make experiments importable directly
experiments = {
    'auto_compensation': AutoCompensationExperiment,
    'cam_sweep': CamSweepExperiment,
    'sim_calibration': SimCalibrationExperiment,
}

# Only add trap_eigenmode if analysis module is available
if TrapEigenmodeExperiment is not None:
    experiments['trap_eigenmode'] = TrapEigenmodeExperiment
