from ndscan.experiment import Fragment, FloatParam, BoolParam
from oitg.units import MHz, dB
from artiq.experiment import *


class RamanCooling(Fragment):
    """
    Fragment for controlling Raman cooling beams.
    
    Controls two Urukul channels for 135° and 225° beams.
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("urukul1_cpld")
        self.setattr_device("urukul1_ch0")
        self.setattr_device("urukul1_ch1")

        self.u10 = self.urukul1_ch0
        self.u11 = self.urukul1_ch1

        # Parameters
        self.setattr_param("freq0", FloatParam, "frequency 135°-beam", 
                          default=212.5*MHz, unit="MHz")
        self.setattr_param("freq1", FloatParam, "frequency 225°-beam", 
                          default=212.5*MHz, unit="MHz")
        self.setattr_param("amp0", FloatParam, "amplitude 135°-beam", 
                          default=0.05)
        self.setattr_param("amp1", FloatParam, "amplitude 225°-beam", 
                          default=0.05)
        self.setattr_param("check_135", BoolParam, "135°-beam on", 
                          default=True)
        self.setattr_param("check_225", BoolParam, "225°-beam on", 
                          default=True)
        
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
    def set_cooling_params(self, f0, a0, f1, a1, sw0, sw1) -> None:
        """
        Directly set cooling parameters from ZMQ arguments.
        
        Args:
            f0: Frequency for 135° beam (Hz)
            a0: Amplitude for 135° beam (0-1)
            f1: Frequency for 225° beam (Hz)
            a1: Amplitude for 225° beam (0-1)
            sw0: Switch state for 135° beam
            sw1: Switch state for 225° beam
        """
        self.u10.set(f0, amplitude=a0)
        self.u11.set(f1, amplitude=a1)
        self.u10.cfg_sw(sw0)
        self.u11.cfg_sw(sw1)
        
    @kernel
    def activate_cooling(self) -> None:
        """Activate cooling with dashboard parameters."""
        self.u10.set(self.freq0.get(), amplitude=float(self.amp0.get()))  
        self.u11.set(self.freq1.get(), amplitude=float(self.amp1.get()))  
        self.u10.cfg_sw(self.check_135.get())
        self.u11.cfg_sw(self.check_225.get())
