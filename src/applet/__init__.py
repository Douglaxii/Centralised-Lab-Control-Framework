"""
Experimental scripts module for the Applet Server.

This module contains modular experimental scripts that can be
controlled via the Flask API.
"""

from .base import BaseExperiment, ExperimentStatus
from .auto_compensation import AutoCompensationExperiment
from .trap_eigenmode import TrapEigenmodeExperiment
from .cam_sweep import CamSweepExperiment
from .sim_calibration import SimCalibrationExperiment

__all__ = [
    'BaseExperiment', 'ExperimentStatus',
    'AutoCompensationExperiment', 'TrapEigenmodeExperiment',
    'CamSweepExperiment', 'SimCalibrationExperiment'
]

# Make experiments importable directly
experiments = {
    'auto_compensation': AutoCompensationExperiment,
    'trap_eigenmode': TrapEigenmodeExperiment,
    'cam_sweep': CamSweepExperiment,
    'sim_calibration': SimCalibrationExperiment,
}
