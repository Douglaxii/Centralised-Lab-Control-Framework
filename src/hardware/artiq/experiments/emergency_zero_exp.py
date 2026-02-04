"""
emergency_zero_exp.py - Emergency Shutdown Experiment

Phase 3A: Command-specific experiment for emergency safety shutdown.

Immediately sets all outputs to safe state:
  - Endcaps: 0V
  - Compensation: 0V
  - Raman beams: Minimum amplitude, switches off
  - DDS outputs: Switches off

Usage:
    # From ARTIQ dashboard: Run EmergencyZeroExpScan
    # From code: scheduler.submit("experiments.emergency_zero_exp.EmergencyZeroExpScan")
    
    # Or use convenience function:
    submit_emergency_zero(scheduler, priority=100)  # High priority!
"""

import sys
sys.path.insert(0, "/home/artiq/Developer/artiq/artiq-master/repository")

from ndscan.experiment import ExpFragment, make_fragment_scan_exp
from artiq.experiment import *
from oitg.units import V

# Import all fragments for safety shutdown
from ec import ec
from comp import comp
from raman_control import raman_control
from dds_controller import dds_controller


class EmergencyZeroExp(ExpFragment):
    """
    Emergency Zero/Shutdown Experiment.
    
    CRITICAL SAFETY: This experiment immediately sets all hardware
to safe state. It has high priority and runs immediately.
    
    Safe state:
      - All DC electrodes: 0V
      - All DDS switches: OFF
      - Raman beams: Minimum amplitude, switches off
    """
    
    def build_fragment(self):
        """Build with all fragments that need safety shutdown."""
        self.setattr_device("core")
        
        # All fragments that can affect hardware
        self.setattr_fragment("ec", ec)
        self.setattr_fragment("comp", comp)
        self.setattr_fragment("raman", raman_control)
        
        # Both DDS channels for direct switch control
        self.setattr_fragment("dds_axial", dds_controller, "urukul0_ch0")
        self.setattr_fragment("dds_radial", dds_controller, "urukul0_ch1")
    
    @kernel
    def run_once(self):
        """Execute emergency shutdown."""
        self.core.break_realtime()
        
        # 1. Turn off all DDS switches immediately
        self.dds_axial.cfg_sw(False)
        self.dds_radial.cfg_sw(False)
        
        # 2. Set Raman beams to safe state (minimum amplitude, switches off)
        self.raman.set_beams(0.05, 0.05, 0, 0)
        
        # 3. Set all DC electrodes to 0V
        self.ec.set_ec(0.0 * V, 0.0 * V)
        self.comp.set_hor_ver(0.0 * V, 0.0 * V)
        
        # Allow time for hardware to settle
        delay(200 * ms)


# Create scan-enabled version
EmergencyZeroExpScan = make_fragment_scan_exp(EmergencyZeroExp)


# Convenience function for programmatic submission
def submit_emergency_zero(scheduler, priority=100):
    """
    Submit emergency shutdown experiment with high priority.
    
    Args:
        scheduler: ARTIQ scheduler instance
        priority: Experiment priority (default: 100 = highest)
    
    Returns:
        Experiment RID (Run ID)
    
    Example:
        # Emergency shutdown
        rid = submit_emergency_zero(scheduler)
        
        # Or manually with highest priority
        scheduler.submit(
            "experiments.emergency_zero_exp.EmergencyZeroExpScan",
            priority=100  # Higher than any normal experiment
        )
    """
    return scheduler.submit(
        "experiments.emergency_zero_exp.EmergencyZeroExpScan",
        priority=priority,
        # No arguments needed - always does the same thing
    )


# Alias for convenience
emergency_shutdown = submit_emergency_zero
