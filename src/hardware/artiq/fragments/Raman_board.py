from ndscan.experiment import Fragment, FloatParam, IntParam
from oitg.units import MHz, dB
from artiq.experiment import *


# Constants - Raman laser frequencies (backend adjustable only)
RAMAN_FREQ_135_MHZ = 215.5  # 135° beam frequency in MHz
RAMAN_FREQ_225_MHZ = 215.5  # 225° beam frequency in MHz


class RamanCooling(Fragment):
    """
    Fragment for controlling Raman cooling beams.
    
    Controls two Urukul channels for 135° and 225° beams.
    Frequencies are constants (215.5 MHz) and can only be adjusted from backend.
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("urukul1_cpld")
        self.setattr_device("urukul1_ch0")
        self.setattr_device("urukul1_ch1")

        self.u10 = self.urukul1_ch0
        self.u11 = self.urukul1_ch1

        # Parameters (frequencies are now constants, not parameters)
        self.setattr_param("amp0", FloatParam, "amplitude 135°-beam", 
                          default=0.05)
        self.setattr_param("amp1", FloatParam, "amplitude 225°-beam", 
                          default=0.05)
        # Switches as integers (0=off, 1=on)
        self.setattr_param("sw0", IntParam, "135°-beam on (0=off, 1=on)", 
                          default=0, min=0, max=1)
        self.setattr_param("sw1", IntParam, "225°-beam on (0=off, 1=on)", 
                          default=0, min=0, max=1)
        
        # Attenuation settings
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
    def set_cooling_params(self, a0, a1, sw0, sw1) -> None:
        """
        Directly set cooling parameters from ZMQ arguments.
        Frequencies are fixed at 215.5 MHz.
        
        Args:
            a0: Amplitude for 135° beam (0-1)
            a1: Amplitude for 225° beam (0-1)
            sw0: Switch state for 135° beam (0=off, 1=on)
            sw1: Switch state for 225° beam (0=off, 1=on)
        """
        # Use constant frequencies (convert MHz to Hz for ARTIQ)
        self.u10.set(RAMAN_FREQ_135_MHZ * MHz, amplitude=a0)
        self.u11.set(RAMAN_FREQ_225_MHZ * MHz, amplitude=a1)
        self.u10.cfg_sw(sw0 != 0)  # Convert int to bool
        self.u11.cfg_sw(sw1 != 0)  # Convert int to bool
        
    @kernel
    def activate_cooling(self) -> None:
        """Activate cooling with dashboard parameters."""
        # Use constant frequencies (215.5 MHz)
        self.u10.set(RAMAN_FREQ_135_MHZ * MHz, amplitude=float(self.amp0.get()))  
        self.u11.set(RAMAN_FREQ_225_MHZ * MHz, amplitude=float(self.amp1.get()))  
        self.u10.cfg_sw(self.sw0.get() != 0)  # Convert int to bool
        self.u11.cfg_sw(self.sw1.get() != 0)  # Convert int to bool
