"""
sweeping.py - Secular frequency sweep fragment for ARTIQ (ndscan 0.5.x COMPATIBLE)

CRITICAL FIXES:
1. Choices = TUPLE ("axial", "radial") NOT list ["axial", "radial"]
2. Default = INTEGER INDEX (0) NOT string
3. build_fragment() contains ONLY attribute declarations (no hardware access)
"""
from ndscan.experiment import Fragment, FloatParam, EnumParam
from artiq.experiment import *

class sweeping(Fragment):
    def build_fragment(self) -> None:
        # ONLY attribute declarations here - NO hardware access during scan!
        self.setattr_device("core")
        self.setattr_device("ttl0_counter")
        self.setattr_device("urukul0_ch0")
        self.setattr_device("urukul0_ch1")
        self.setattr_device("ttl4")
        
        self.pmt = self.ttl0_counter
        self.dds_axial = self.urukul0_ch0
        self.dds_radial = self.urukul0_ch1
        self.cam = self.ttl4

        # Parameters (scannable)
        self.setattr_param("freq", FloatParam, "Frequency", 
                          default=400.0 * kHz, unit="kHz")
        self.setattr_param("att", FloatParam, "Attenuation", 
                          default=25.0, unit="dB")
        self.setattr_param("on_time", FloatParam, "ON time", 
                          default=100.0 * ms, unit="ms")
        self.setattr_param("off_time", FloatParam, "OFF time", 
                          default=100.0 * ms, unit="ms")
        
        # FIXED FOR ndscan 0.5.x:
        #   - default = INTEGER INDEX (0 = first choice)
        #   - choices = HASHABLE TUPLE (NOT list!)
        self.setattr_param("dds_choice", EnumParam, "DDS Select",
                          0,                          # Integer index default
                          ("axial", "radial"))        # ← TUPLE required!
        
        self.first_init = True  # Track first hardware init

    def host_setup(self):
        """Select DDS device - SAFE during scan (no hardware access)."""
        # .get() returns string "axial" or "radial" based on integer index
        if self.dds_choice.get() == "axial":
            self.dds = self.dds_axial
        else:
            self.dds = self.dds_radial

    @kernel
    def device_setup(self):
        """Hardware initialization - ONLY called during run(), NOT during scan."""
        self.core.break_realtime()
        if self.first_init:
            self.dds.init()
            self.first_init = False
        self.dds.set_att(self.att.get() * dB)

    @kernel
    def sweep_point(self, freq_hz: TFloat, on_ms: TFloat, off_ms: TFloat) -> TInt32:
        """Execute a single sweep point."""
        self.core.break_realtime()
        self.dds.set(frequency=freq_hz)
        with parallel:
            self.dds.cfg_sw(True)
            self.pmt.gate_rising(on_ms * ms)
        self.dds.cfg_sw(False)
        counts = self.pmt.fetch_count()
        delay(off_ms * ms)
        return counts

    @kernel
    def sweep_point_with_cam(self, freq_hz: TFloat, on_ms: TFloat, off_ms: TFloat) -> TInt32:
        """Execute a single sweep point with camera trigger."""
        self.core.break_realtime()
        self.dds.set(frequency=freq_hz)
        with parallel:
            self.dds.cfg_sw(True)
            self.pmt.gate_rising(on_ms * ms)
            self.cam.pulse(on_ms * ms)
        self.dds.cfg_sw(False)
        counts = self.pmt.fetch_count()
        delay(off_ms * ms)
        return counts
    
    @kernel
    def pmt_measure(self, duration_ms: TFloat) -> TInt32:
        """Simple PMT measurement without DDS."""
        self.core.break_realtime()
        self.pmt.gate_rising(duration_ms * ms)
        delay(duration_ms * ms)
        return self.pmt.fetch_count()