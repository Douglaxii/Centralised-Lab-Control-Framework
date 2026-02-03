"""
ec.py - Endcaps fragment for ARTIQ.

Controls endcap electrodes via Zotino DAC.
"""

from ndscan.experiment import Fragment, FloatParam
from artiq.experiment import *


class ec(Fragment):
    """
    Endcaps fragment.
    
    Device: zotino0 channels 4, 5
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_device("zotino0")
        self.first = True

    @kernel
    def device_setup(self) -> None:
        """Initialize Zotino on first run."""
        self.core.break_realtime()
        if self.first:
            self.zotino0.init()
            delay(200 * us)
            self.first = False

    @kernel 
    def set_ec(self, v1: TFloat, v2: TFloat) -> None:
        """
        Set endcap voltages directly.
        
        Args:
            v1: Voltage for channel 4 (EC1) in Volts
            v2: Voltage for channel 5 (EC2) in Volts
        """
        self.core.break_realtime()
        self.zotino0.set_dac([v1, v2], [4, 5])
        delay(100 * ms)

    @kernel
    def set_params(self, v1: TFloat, v2: TFloat) -> None:
        """Alias for set_ec for compatibility."""
        self.set_ec(v1, v2)
