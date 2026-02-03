"""
raman_control.py - Raman cooling control fragment for ARTIQ.

Controls Raman cooling beams via Urukul DDS.
"""

from ndscan.experiment import Fragment, FloatParam, IntParam
from artiq.experiment import *

# Constants - Raman laser frequencies (hardware-fixed)
RAMAN_FREQ_135_MHZ = 215.5
RAMAN_FREQ_225_MHZ = 215.5


class raman_control(Fragment):
    """
    Raman control fragment.
    
    Devices:
        - urukul1_cpld, urukul1_ch0 (135° beam)
        - urukul1_ch1 (225° beam)
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("urukul1_cpld")
        self.setattr_device("urukul1_ch0")
        self.setattr_device("urukul1_ch1")

        self.u10 = self.urukul1_ch0
        self.u11 = self.urukul1_ch1

        # Amplitude parameters
        self.setattr_param("amp0", FloatParam, "amplitude 135 beam", 
                          default=0.05, min=0.0, max=1.0)
        self.setattr_param("amp1", FloatParam, "amplitude 225 beam", 
                          default=0.05, min=0.0, max=1.0)
        
        # Switch parameters (0=off, 1=on)
        self.setattr_param("sw0", IntParam, "135 beam switch", 
                          default=0, min=0, max=1)
        self.setattr_param("sw1", IntParam, "225 beam switch", 
                          default=0, min=0, max=1)
        
        # Attenuation (fixed at 20 dB)
        self.att0 = 20 * dB
        self.att1 = 20 * dB

        self.first_run = True

    @kernel    
    def device_setup(self) -> None:
        """Initialize hardware on first run."""
        if self.first_run:
            self.core.reset()
            self.core.break_realtime()
            self.u10.cpld.init()
            self.u10.init()
            self.u11.init()
            self.u10.set_att(self.att0)
            self.u11.set_att(self.att1)
            self.first_run = False

    @kernel
    def set_beams(self, amp0: TFloat, amp1: TFloat, sw0: TInt, sw1: TInt) -> None:
        """
        Set beam parameters.
        
        Args:
            amp0: Amplitude for 135° beam (0-1)
            amp1: Amplitude for 225° beam (0-1)
            sw0: Switch state for 135° beam (0=off, 1=on)
            sw1: Switch state for 225° beam (0=off, 1=on)
        """
        self.u10.set(RAMAN_FREQ_135_MHZ * MHz, amplitude=amp0)
        self.u11.set(RAMAN_FREQ_225_MHZ * MHz, amplitude=amp1)
        self.u10.cfg_sw(sw0 != 0)
        self.u11.cfg_sw(sw1 != 0)
        
    @kernel
    def set_params(self) -> None:
        """Set beams using current parameter values."""
        self.set_beams(
            float(self.amp0.get()),
            float(self.amp1.get()),
            self.sw0.get(),
            self.sw1.get()
        )
