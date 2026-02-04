"""
set_dc_exp.py - DC Voltage Setting Experiment

Phase 3A: Command-specific experiment for setting DC electrode voltages.

This is a lightweight, single-purpose experiment that sets endcap and
compensation electrode voltages via Zotino DAC.

Usage:
    # From ARTIQ dashboard: Just run SetDCExpScan
    # From code: scheduler.submit("experiments.set_dc_exp.SetDCExpScan", params)

Parameters:
    ec1: Endcap 1 voltage (V)
    ec2: Endcap 2 voltage (V)
    comp_h: Horizontal compensation (V)
    comp_v: Vertical compensation (V)
"""

import sys
sys.path.insert(0, "/home/artiq/Developer/artiq/artiq-master/repository")

from ndscan.experiment import ExpFragment, FloatParam, make_fragment_scan_exp
from artiq.experiment import *
from artiq.language.types import TFloat
from oitg.units import V

# Import fragments
from ec import ec
from comp import comp


class SetDCExp(ExpFragment):
    """
    DC Voltage Setting Experiment.
    
    Sets endcap and compensation voltages in a single kernel call.
    Minimal, fast, and focused only on DC control.
    """
    
    def build_fragment(self):
        """Build with minimal fragment dependencies."""
        self.setattr_device("core")
        
        # Only the fragments we need
        self.setattr_fragment("ec", ec)
        self.setattr_fragment("comp", comp)
        
        # Parameters with safe defaults
        self.setattr_param("ec1", FloatParam, "Endcap 1",
                          default=0.0, unit="V",
                          min=-1.0, max=50.0)
        self.setattr_param("ec2", FloatParam, "Endcap 2",
                          default=0.0, unit="V",
                          min=-1.0, max=50.0)
        self.setattr_param("comp_h", FloatParam, "Comp H",
                          default=0.0, unit="V",
                          min=-10.0, max=10.0)
        self.setattr_param("comp_v", FloatParam, "Comp V",
                          default=0.0, unit="V",
                          min=-10.0, max=10.0)
    
    @kernel
    def run_once(self):
        """Execute DC setting in a single kernel call."""
        self.core.break_realtime()
        
        # Apply voltages
        self.ec.set_ec(self.ec1.get() * V, self.ec2.get() * V)
        self.comp.set_hor_ver(self.comp_h.get() * V, self.comp_v.get() * V)
        
        # Small delay for DAC settling
        delay(100 * ms)
    
    def get_default_analyses(self):
        """No analysis needed for DC setting."""
        return []


# Create scan-enabled version for ARTIQ dashboard
SetDCExpScan = make_fragment_scan_exp(SetDCExp)


# Convenience function for programmatic submission
def submit_set_dc(scheduler, ec1=0.0, ec2=0.0, comp_h=0.0, comp_v=0.0, priority=0):
    """
    Submit DC setting experiment to scheduler.
    
    Args:
        scheduler: ARTIQ scheduler instance
        ec1, ec2: Endcap voltages (V)
        comp_h, comp_v: Compensation voltages (V)
        priority: Experiment priority
    """
    return scheduler.submit(
        "experiments.set_dc_exp.SetDCExpScan",
        priority=priority,
        arguments={
            "ec1": ec1,
            "ec2": ec2,
            "comp_h": comp_h,
            "comp_v": comp_v,
        }
    )
