"""
dds_controller.py - DDS (Direct Digital Synthesis) controller fragment for ARTIQ.

Controls a single DDS channel for frequency generation.
Lightweight fragment focused only on DDS hardware abstraction.
"""

from ndscan.experiment import Fragment, FloatParam
from artiq.experiment import *
from artiq.language.types import TFloat

# dB is not in oitg.units, define it as unitless multiplier
dB = 1.0


class dds_controller(Fragment):
    """
    DDS controller fragment.
    
    Controls a single DDS channel for frequency sweeps or fixed frequency output.
    Designed to be lightweight and focused only on DDS operations.
    
    Usage:
        # In parent fragment:
        self.setattr_fragment("dds_axial", dds_controller, "urukul0_ch0")
        self.setattr_fragment("dds_radial", dds_controller, "urukul0_ch1")
    """
    
    def build_fragment(self, device_name: str) -> None:
        """
        Build the DDS controller fragment.
        
        Args:
            device_name: Name of the DDS device in device_db.py
                        (e.g., "urukul0_ch0", "urukul0_ch1")
        """
        self.setattr_device("core")
        self.setattr_device(device_name)
        
        # Store reference to the DDS device
        self.dds = getattr(self, device_name)
        self.device_name = device_name
        
        # Track initialization state
        self.first_init = True
    
    @kernel
    def device_setup(self) -> None:
        """Initialize DDS on first run."""
        self.core.break_realtime()
        if self.first_init:
            self.dds.init()
            self.first_init = False
    
    @kernel
    def set_frequency(self, freq_hz: TFloat) -> None:
        """
        Set DDS frequency.
        
        Args:
            freq_hz: Frequency in Hz
        """
        self.core.break_realtime()
        self.dds.set(frequency=freq_hz)
    
    @kernel
    def set_amplitude(self, amplitude: TFloat) -> None:
        """
        Set DDS amplitude.
        
        Args:
            amplitude: Amplitude 0.0 to 1.0 (normalized)
        """
        self.core.break_realtime()
        self.dds.set_amplitude(amplitude)
    
    @kernel
    def set_att(self, att_db: TFloat) -> None:
        """
        Set DDS attenuation.
        
        Args:
            att_db: Attenuation in dB
        """
        self.core.break_realtime()
        self.dds.set_att(att_db * dB)
    
    @kernel
    def cfg_sw(self, enable: TBool) -> None:
        """
        Configure DDS switch (turn RF output on/off).
        
        Args:
            enable: True to enable RF output, False to disable
        """
        self.core.break_realtime()
        self.dds.cfg_sw(enable)
    
    @kernel
    def pulse(self, duration_ms: TFloat) -> None:
        """
        Output a single pulse of specified duration.
        
        Args:
            duration_ms: Pulse duration in milliseconds
        """
        self.core.break_realtime()
        self.dds.cfg_sw(True)
        delay(duration_ms * ms)
        self.dds.cfg_sw(False)
