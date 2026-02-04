"""
ARTIQ Command-Specific Experiments

Phase 3A: Command-specific experiments for better ARTIQ integration.

Instead of a monolithic ZMQ worker, each command type has its own
lightweight experiment. This is the most "ARTIQ-native" approach.

Usage:
    # From Manager, submit specific experiment:
    scheduler.submit("experiments.SetDCExp", 
                     {"ec1": 5.0, "ec2": 5.0, "comp_h": 0.0, "comp_v": 0.0})

Experiments:
    SetDCExp: Set DC electrode voltages
    SecularSweepExp: Run frequency sweep with PMT detection
    PMTMeasureExp: Simple PMT photon counting
    CameraTriggerExp: Trigger camera with timing
    EmergencyZeroExp: Emergency shutdown (all outputs to safe state)
"""

# Export all experiment classes
from .set_dc_exp import SetDCExp, SetDCExpScan
from .secular_sweep_exp import SecularSweepExp, SecularSweepExpScan
from .pmt_measure_exp import PMTMeasureExp, PMTMeasureExpScan
from .emergency_zero_exp import EmergencyZeroExp, EmergencyZeroExpScan

__all__ = [
    # Individual experiments
    "SetDCExp",
    "SecularSweepExp",
    "PMTMeasureExp",
    "EmergencyZeroExp",
    # Scan-enabled experiments (for ndscan dashboard)
    "SetDCExpScan",
    "SecularSweepExpScan",
    "PMTMeasureExpScan",
    "EmergencyZeroExpScan",
]
