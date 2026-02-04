"""
secular_sweep_exp.py - Secular Frequency Sweep Experiment

Phase 3A: Command-specific experiment for frequency sweeping with PMT detection.

Lightweight experiment that coordinates DDS sweeps with PMT counting.
Uses the decomposed fragment architecture from Phase 2.

Usage:
    # From ARTIQ dashboard: Run SecularSweepExpScan
    # From code: scheduler.submit("experiments.secular_sweep_exp.SecularSweepExpScan", params)

Parameters:
    target_freq_khz: Center frequency (kHz)
    span_khz: Sweep span (kHz)
    steps: Number of frequency steps
    att_db: DDS attenuation (dB)
    on_time_ms: RF on time per step (ms)
    off_time_ms: Delay between steps (ms)
    dds_choice: "axial" or "radial"
"""

import sys
sys.path.insert(0, "/home/artiq/Developer/artiq/artiq-master/repository")

from ndscan.experiment import (
    ExpFragment, FloatParam, IntParam, EnumParam, 
    FloatChannel, make_fragment_scan_exp
)
from artiq.experiment import *
from artiq.language.types import TFloat, TInt32
from oitg.units import kHz, ms, V

# Import Phase 2 fragments
from dds_controller import dds_controller
from pmt_counter import pmt_counter

# dB is not in oitg.units
dB = 1.0


class SecularSweepExp(ExpFragment):
    """
    Secular Frequency Sweep Experiment.
    
    Sweeps DDS frequency while counting photons with PMT.
    Results are stored in result channels for live plotting.
    """
    
    def build_fragment(self):
        """Build with DDS and PMT fragments."""
        self.setattr_device("core")
        
        # Phase 2 sub-fragments
        self.setattr_fragment("dds_axial", dds_controller, "urukul0_ch0")
        self.setattr_fragment("dds_radial", dds_controller, "urukul0_ch1")
        self.setattr_fragment("pmt", pmt_counter, "ttl0_counter")
        
        # Scan parameters
        self.setattr_param("target_freq_khz", FloatParam, "Target Frequency",
                          default=400.0, unit="kHz",
                          min=100.0, max=1000.0)
        self.setattr_param("span_khz", FloatParam, "Span",
                          default=40.0, unit="kHz",
                          min=1.0, max=200.0)
        self.setattr_param("steps", IntParam, "Steps",
                          default=41, min=2, max=1000)
        self.setattr_param("att_db", FloatParam, "Attenuation",
                          default=25.0, unit="dB",
                          min=0.0, max=31.5)
        self.setattr_param("on_time_ms", FloatParam, "On Time",
                          default=100.0, unit="ms",
                          min=1.0, max=1000.0)
        self.setattr_param("off_time_ms", FloatParam, "Off Time",
                          default=100.0, unit="ms",
                          min=0.0, max=1000.0)
        
        # DDS selection
        self.setattr_param("dds_choice", EnumParam, "DDS Select",
                          0, ("axial", "radial"))
        
        # Result channels for live plotting
        self.setattr_result("pmt_counts", FloatChannel)
        self.setattr_result("frequency_khz", FloatChannel)
        
        # Runtime state
        self.selected_dds = None
    
    def host_setup(self):
        """Select DDS before run."""
        choice = self.dds_choice.get()
        if choice == "axial":
            self.selected_dds = self.dds_axial
        else:
            self.selected_dds = self.dds_radial
    
    @kernel
    def run_once(self):
        """Execute a single sweep point."""
        self.core.break_realtime()
        
        # Calculate frequency for this point
        start_f = (self.target_freq_khz.get() - self.span_khz.get() / 2.0) * kHz
        step_size = (self.span_khz.get() * kHz) / (self.steps.get() - 1)
        
        # Initialize DDS
        self.selected_dds.device_setup()
        self.selected_dds.set_att(self.att_db.get() * dB)
        
        # Run sweep
        for i in range(self.steps.get()):
            freq = start_f + (i * step_size)
            
            # Set frequency
            self.selected_dds.set_frequency(freq)
            
            # RF on + count
            with parallel:
                self.selected_dds.cfg_sw(True)
                self.pmt.count(self.on_time_ms.get())
            
            # RF off
            self.selected_dds.cfg_sw(False)
            
            # Get count
            counts = self.pmt.pmt.fetch_count()
            
            # Push results (via RPC)
            self.push_results(freq / kHz, float(counts))
            
            # Delay between steps
            delay(self.off_time_ms.get() * ms)
    
    @rpc
    def push_results(self, freq_khz: TFloat, counts: TFloat):
        """Push results to channels (host-side)."""
        self.frequency_khz.push(freq_khz)
        self.pmt_counts.push(counts)


# Create scan-enabled version
SecularSweepExpScan = make_fragment_scan_exp(SecularSweepExp)


# Convenience function for programmatic submission
def submit_sweep(scheduler, target_freq_khz=400.0, span_khz=40.0, steps=41,
                 att_db=25.0, on_time_ms=100.0, off_time_ms=100.0,
                 dds_choice="axial", priority=0):
    """
    Submit sweep experiment to scheduler.
    
    Args:
        scheduler: ARTIQ scheduler instance
        target_freq_khz: Center frequency (kHz)
        span_khz: Sweep span (kHz)
        steps: Number of steps
        att_db: Attenuation (dB)
        on_time_ms: RF on time per step (ms)
        off_time_ms: Delay between steps (ms)
        dds_choice: "axial" or "radial"
        priority: Experiment priority
    """
    dds_idx = 0 if dds_choice == "axial" else 1
    return scheduler.submit(
        "experiments.secular_sweep_exp.SecularSweepExpScan",
        priority=priority,
        arguments={
            "target_freq_khz": target_freq_khz,
            "span_khz": span_khz,
            "steps": steps,
            "att_db": att_db,
            "on_time_ms": on_time_ms,
            "off_time_ms": off_time_ms,
            "dds_choice": dds_idx,
        }
    )
