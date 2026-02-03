"""
Trap Control Experiment
Basic DC voltage control for endcaps and compensation electrodes.
"""

from ndscan.experiment import Fragment, ExpFragment, FloatParam, BoolParam, make_fragment_scan_exp
from artiq.experiment import *
from oitg.units import V, us, ms
import numpy as np

# Use abbreviated fragment names
from fragments import Comp, EC


class TrapControl(ExpFragment):
    """
    Trap control experiment for setting DC voltages.
    
    Controls:
    - Endcap voltages (EC1, EC2)
    - Compensation voltages (horizontal, vertical)
    
    Uses abbreviated fragment names:
    - Comp = Compensation
    - EC = EndCaps
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
        
        # Compensation parameters
        self.setattr_param("u_hor", FloatParam, "Horizontal compensation", 
                          default=10.0*V, unit="V")
        self.setattr_param("u_ver", FloatParam, "Vertical compensation", 
                          default=10.0*V, unit="V")
        self.setattr_param("monitoring", BoolParam, "Monitoring input Voltages", 
                          default=True)
        
        # Endcap parameters  
        self.setattr_param("u_ec1", FloatParam, "EC1 Voltage", 
                          default=10.0*V, unit="V")
        self.setattr_param("u_ec2", FloatParam, "EC2 Voltage", 
                          default=10.0*V, unit="V")
        self.setattr_param("monitoring_ec", BoolParam, "Monitoring input EC-Voltages", 
                          default=True)
    
    @kernel
    def run_once(self) -> None:
        """Execute one run of the experiment."""
        self.comp.set_compensation(self.u_hor.get(), self.u_ver.get())
        self.ec.set_ec(self.u_ec1.get(), self.u_ec2.get())


# Create standalone experiment class
TrapElectronics = make_fragment_scan_exp(TrapControl)
