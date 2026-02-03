"""
comp.py - Compensation electrodes fragment for ARTIQ.

Controls compensation electrodes via Zotino DAC.
"""

from ndscan.experiment import Fragment, FloatParam
from artiq.experiment import *


class comp(Fragment):
    """
    Compensation fragment.
    
    Device: zotino0 channels 0-3
    Channel mapping:
        - Channel 0: Horizontal coarse
        - Channel 1: Horizontal fine  
        - Channel 2: Vertical coarse
        - Channel 3: Vertical fine
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
    def set_comp(self, v0: TFloat, v1: TFloat, v2: TFloat, v3: TFloat) -> None:
        """
        Set all compensation channels.
        
        Args:
            v0: Channel 0 (horizontal coarse) in Volts
            v1: Channel 1 (horizontal fine) in Volts
            v2: Channel 2 (vertical coarse) in Volts
            v3: Channel 3 (vertical fine) in Volts
        """
        self.core.break_realtime()
        self.zotino0.set_dac([v0, v1, v2, v3], [0, 1, 2, 3])
        delay(100 * ms)

    @kernel
    def set_hor_ver(self, u_hor: TFloat, u_ver: TFloat) -> None:
        """
        Set horizontal and vertical compensation.
        
        Simple version - sets coarse channels, fine channels to 0.
        
        Args:
            u_hor: Horizontal compensation in Volts
            u_ver: Vertical compensation in Volts
        """
        self.core.break_realtime()
        self.zotino0.set_dac([u_hor, 0.0, u_ver, 0.0], [0, 1, 2, 3])
        delay(100 * ms)
