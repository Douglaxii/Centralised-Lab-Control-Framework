"""
pmt_measure_exp.py - PMT Measurement Experiment

Phase 3A: Command-specific experiment for simple photon counting.

Lightweight experiment that measures PMT counts for a specified duration.

Usage:
    # From ARTIQ dashboard: Run PMTMeasureExpScan
    # From code: scheduler.submit("experiments.pmt_measure_exp.PMTMeasureExpScan", params)

Parameters:
    duration_ms: Measurement duration in milliseconds
    num_samples: Number of repeated measurements (for averaging)
"""

import sys
sys.path.insert(0, "/home/artiq/Developer/artiq/artiq-master/repository")

from ndscan.experiment import (
    ExpFragment, FloatParam, IntParam,
    FloatChannel, make_fragment_scan_exp
)
from artiq.experiment import *
from artiq.language.types import TFloat, TInt32

# Import Phase 2 fragment
from pmt_counter import pmt_counter


class PMTMeasureExp(ExpFragment):
    """
    PMT Measurement Experiment.
    
    Simple photon counting for a specified duration.
    Can average multiple samples for better statistics.
    """
    
    def build_fragment(self):
        """Build with PMT fragment only."""
        self.setattr_device("core")
        
        # Only PMT fragment (minimal!)
        self.setattr_fragment("pmt", pmt_counter, "ttl0_counter")
        
        # Parameters
        self.setattr_param("duration_ms", FloatParam, "Duration",
                          default=100.0, unit="ms",
                          min=1.0, max=10000.0)
        self.setattr_param("num_samples", IntParam, "Samples",
                          default=1, min=1, max=1000)
        
        # Result channels
        self.setattr_result("counts", FloatChannel)
        self.setattr_result("counts_std", FloatChannel)  # Standard deviation
    
    @kernel
    def run_once(self):
        """Execute PMT measurement."""
        self.core.break_realtime()
        
        total_counts = 0
        sum_squares = 0
        
        for i in range(self.num_samples.get()):
            # Single measurement
            counts = self.pmt.count(self.duration_ms.get())
            
            total_counts += counts
            sum_squares += counts * counts
            
            # Small delay between samples
            if i < self.num_samples.get() - 1:
                delay(10 * ms)
        
        # Calculate statistics
        mean = total_counts / self.num_samples.get()
        
        # Variance = E[x^2] - E[x]^2
        if self.num_samples.get() > 1:
            mean_squares = sum_squares / self.num_samples.get()
            variance = mean_squares - (mean * mean)
            std = variance ** 0.5 if variance > 0 else 0.0
        else:
            std = 0.0
        
        # Push results
        self.push_results(float(mean), float(std))
    
    @rpc
    def push_results(self, mean: TFloat, std: TFloat):
        """Push results to channels."""
        self.counts.push(mean)
        self.counts_std.push(std)


# Create scan-enabled version
PMTMeasureExpScan = make_fragment_scan_exp(PMTMeasureExp)


# Convenience function for programmatic submission
def submit_pmt_measure(scheduler, duration_ms=100.0, num_samples=1, priority=0):
    """
    Submit PMT measurement experiment to scheduler.
    
    Args:
        scheduler: ARTIQ scheduler instance
        duration_ms: Measurement duration (ms)
        num_samples: Number of samples to average
        priority: Experiment priority
    """
    return scheduler.submit(
        "experiments.pmt_measure_exp.PMTMeasureExpScan",
        priority=priority,
        arguments={
            "duration_ms": duration_ms,
            "num_samples": num_samples,
        }
    )
