"""
sweeping.py - Secular frequency sweep fragment for ARTIQ.

Controls DDS sweeps (axial or radial) with PMT readout.
"""

from ndscan.experiment import Fragment, FloatParam, EnumParam
from artiq.experiment import *


class sweeping(Fragment):
    """
    Sweeping fragment for secular frequency sweeps.
    
    Devices:
        - urukul0_ch0 (axial)
        - urukul0_ch1 (radial)
        - ttl0_counter (PMT)
        - ttl4 (camera trigger)
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("ttl0_counter")
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("ttl4")
        
        self.pmt = self.ttl0_counter
        self.dds_axial = self.urukul0_ch0
        self.dds_radial = self.urukul0_ch1
        self.cam = self.ttl4

        # Frequency parameter (scannable)
        self.setattr_param("freq", FloatParam, "Frequency", 
                          default=400.0 * kHz, unit="kHz")
        
        # Static parameters
        self.setattr_param("att", FloatParam, "Attenuation", 
                          default=25.0, unit="dB")
        self.setattr_param("on_time", FloatParam, "ON time", 
                          default=100.0 * ms, unit="ms")
        self.setattr_param("off_time", FloatParam, "OFF time", 
                          default=100.0 * ms, unit="ms")
        
        # DDS selection
        self.setattr_param("dds_choice", EnumParam, "DDS Select", 
                          options={"axial": "axial", "radial": "radial"}, 
                          default="axial")
        
        self.first = True

    def host_setup(self):
        """Select DDS device based on parameter."""
        if self.dds_choice.get() == "axial":
            self.dds = self.dds_axial
        else:
            self.dds = self.dds_radial

    @kernel
    def device_setup(self):
        """Initialize DDS hardware."""
        self.core.break_realtime()
        if self.first:
            self.dds.init()
            self.first = False
        self.dds.set_att(self.att.get() * dB)

    @kernel
    def sweep_point(self, freq_hz: TFloat, on_ms: TFloat, off_ms: TFloat) -> TInt:
        """
        Execute a single sweep point.
        
        Args:
            freq_hz: Frequency in Hz for this point
            on_ms: Gate/measurement time in milliseconds
            off_ms: Delay after measurement in milliseconds
            
        Returns:
            PMT count for this point
        """
        self.core.break_realtime()
        
        # Set frequency
        self.dds.set(frequency=freq_hz)
        
        # Enable DDS and gate PMT
        with parallel:
            self.dds.cfg_sw(True)
            self.pmt.gate_rising(on_ms * ms)
        
        # Disable DDS
        self.dds.cfg_sw(False)
        
        # Read PMT count
        counts = self.pmt.fetch_count()
        
        # Delay before next point
        delay(off_ms * ms)
        
        return counts

    @kernel
    def sweep_point_with_cam(self, freq_hz: TFloat, on_ms: TFloat, off_ms: TFloat) -> TInt:
        """
        Execute a single sweep point with camera trigger.
        
        Args:
            freq_hz: Frequency in Hz for this point
            on_ms: Gate/measurement time in milliseconds
            off_ms: Delay after measurement in milliseconds
            
        Returns:
            PMT count for this point
        """
        self.core.break_realtime()
        
        # Set frequency
        self.dds.set(frequency=freq_hz)
        
        # Enable DDS, gate PMT, and trigger camera
        with parallel:
            self.dds.cfg_sw(True)
            self.pmt.gate_rising(on_ms * ms)
            self.cam.pulse(on_ms * ms)
        
        # Disable DDS
        self.dds.cfg_sw(False)
        
        # Read PMT count
        counts = self.pmt.fetch_count()
        
        # Delay before next point
        delay(off_ms * ms)
        
        return counts
    
    @kernel
    def pmt_measure(self, duration_ms: TFloat) -> TInt:
        """
        Simple PMT measurement without DDS.
        
        Args:
            duration_ms: Gate duration in milliseconds
            
        Returns:
            PMT count
        """
        self.core.break_realtime()
        self.pmt.gate_rising(duration_ms * ms)
        delay(duration_ms * ms)
        return self.pmt.fetch_count()
