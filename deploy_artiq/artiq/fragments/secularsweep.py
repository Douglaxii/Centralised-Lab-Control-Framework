from ndscan.experiment import Fragment, FloatParam, EnumParam
from oitg.units import kHz, ms, dB
from artiq.experiment import *

class SecularSweep(Fragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("ttl0_counter")
        self.setattr_device("urukul0_ch0") # Axial
        self.setattr_device("urukul0_ch1") # Radial
        self.setattr_device("ttl4")        # Camera Trigger
        
        self.pmt = self.ttl0_counter
        self.cam = self.ttl4

        # --- Parameters ---
        # Note: 'freq' is what we SCAN. The others are static settings for this run.
        self.setattr_param("freq", FloatParam, "Frequency", default=400.0*kHz, unit="kHz")
        
        # New requested arguments:
        self.setattr_param("att", FloatParam, "Attenuation", default=25.0, unit="dB")
        self.setattr_param("on_time", FloatParam, "ON time", default=100.0*ms, unit="ms")
        self.setattr_param("off_time", FloatParam, "OFF time", default=100.0*ms, unit="ms")
        
        # DDS Selection
        self.setattr_param("dds_choice", EnumParam, "DDS Select", 
                           options={"axial": "axial", "radial": "radial"}, 
                           default="axial")

    def host_setup(self):
        # Select the correct DDS device object based on enum
        if self.dds_choice.get() == "axial":
            self.dds = self.urukul0_ch0
        else:
            self.dds = self.urukul0_ch1

    @kernel
    def device_setup(self):
        self.core.break_realtime()
        self.dds.init()
        # Set attenuation once at start of scan
        self.dds.set_att(self.att.get() * dB)

    @kernel
    def run_point(self):
        """
        Executed for each point in the scan.
        """
        # Set Frequency for this point
        self.dds.set(frequency=self.freq.get())
        
        with parallel:
            self.dds.cfg_sw(True)
            self.pmt.gate_rising(self.on_time.get())
            self.cam.pulse(10*us) # Short trigger for cam

        self.dds.cfg_sw(False)
        
        # Readout
        counts = self.pmt.fetch_count()
        
        # Delay (Off Time)
        delay(self.off_time.get())
        
        return counts