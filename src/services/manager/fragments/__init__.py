"""
Manager Fragments - Modular components for ControlManager.

This module provides a fragment-based architecture for the ControlManager,
making it easier to debug, modify, and extend functionality.

Fragment Categories:
    - Base: BaseFragment - Abstract base class for all fragments
    - Hardware: ARTIQFragment, LabVIEWFragment, CameraFragment, WavemeterFragment
    - Services: OptimizerFragment
    - Applets: AutoCompApplet, CamSweepApplet, SecularSweepApplet, PMTMeasureApplet
    - Safety: KillSwitchFragment, SafetyFragment
    - Data: TelemetryFragment

Usage:
    from fragments import (
        ARTIQFragment,
        LabVIEWFragment,
        CameraFragment,
        OptimizerFragment,
    )
    
    class ControlManager:
        def __init__(self):
            self.artiq = ARTIQFragment(self)
            self.labview = LabVIEWFragment(self)
            self.camera = CameraFragment(self)
            self.optimizer = OptimizerFragment(self)
"""

from .base import BaseFragment, FragmentPriority

# Hardware fragments
from .hardware import (
    ARTIQFragment,
    LabVIEWFragment,
    CameraFragment,
    WavemeterFragment,
)

# Service fragments
from .services import OptimizerFragment

# Applet fragments
from .applets import (
    AutoCompApplet,
    CamSweepApplet,
    SecularSweepApplet,
    PMTMeasureApplet,
)

# Safety fragments
from .safety import (
    KillSwitchFragment,
    SafetyFragment,
)

# Data fragments
from .data import TelemetryFragment

__all__ = [
    # Base
    'BaseFragment',
    'FragmentPriority',
    
    # Hardware
    'ARTIQFragment',
    'LabVIEWFragment',
    'CameraFragment',
    'WavemeterFragment',
    
    # Services
    'OptimizerFragment',
    
    # Applets
    'AutoCompApplet',
    'CamSweepApplet',
    'SecularSweepApplet',
    'PMTMeasureApplet',
    
    # Safety
    'KillSwitchFragment',
    'SafetyFragment',
    
    # Data
    'TelemetryFragment',
]
