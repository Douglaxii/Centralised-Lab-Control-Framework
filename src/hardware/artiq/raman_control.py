"""
raman_control.py - Raman cooling beam control fragment for ARTIQ.

Controls two DDS channels for Raman cooling beams via Urukul.
"""

from ndscan.experiment import Fragment, FloatParam
from artiq.experiment import *
from artiq.language.types import TInt32, TFloat
from oitg.units import MHz, dB


class raman_control(Fragment):
    """
    Raman cooling control fragment.
    
    Controls two DDS channels for Raman beams:
    - Channel 0: Raman beam 0 (urukul0_ch2)
    - Channel 1: Raman beam 1 (urukul0_ch3)
    
    Amplitudes are 0.0 to 1.0 (normalized).
    Switches are 0 (off) or 1 (on).
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("urukul0_ch2")
        self.setattr_device("urukul0_ch3")
        
        self.dds0 = self.urukul0_ch2
        self.dds1 = self.urukul0_ch3
        
        # Track first init for device_setup
        self.first = True
    
    @kernel
    def device_setup(self) -> None:
        """Initialize Urukul DDS channels on first run."""
        self.core.break_realtime()
        if self.first:
            self.dds0.init()
            self.dds1.init()
            self.first = False
    
    @kernel 
    def set_beams(self, amp0: TFloat, amp1: TFloat, sw0: TInt32, sw1: TInt32) -> None:
        """
        Set Raman beam amplitudes and switch states.
        
        Args:
            amp0: Amplitude for beam 0 (0.0 to 1.0)
            amp1: Amplitude for beam 1 (0.0 to 1.0)
            sw0: Switch state for beam 0 (0=off, 1=on)
            sw1: Switch state for beam 1 (0=off, 1=on)
        """
        self.core.break_realtime()
        
        # Set amplitudes
        self.dds0.set_amplitude(amp0)
        self.dds1.set_amplitude(amp1)
        
        # Set switches (cfg_sw takes boolean)
        self.dds0.cfg_sw(sw0 != 0)
        self.dds1.cfg_sw(sw1 != 0)
        
        delay(10 * ms)
    
    @kernel
    def set_frequency(self, freq0_mhz: TFloat, freq1_mhz: TFloat) -> None:
        """
        Set Raman beam frequencies.
        
        Args:
            freq0_mhz: Frequency for beam 0 in MHz
            freq1_mhz: Frequency for beam 1 in MHz
        """
        self.core.break_realtime()
        self.dds0.set(freq0_mhz * MHz)
        self.dds1.set(freq1_mhz * MHz)
    
    @kernel
    def set_att(self, att0_db: TFloat, att1_db: TFloat) -> None:
        """
        Set Raman beam attenuations.
        
        Args:
            att0_db: Attenuation for beam 0 in dB
            att1_db: Attenuation for beam 1 in dB
        """
        self.core.break_realtime()
        self.dds0.set_att(att0_db * dB)
        self.dds1.set_att(att1_db * dB)
