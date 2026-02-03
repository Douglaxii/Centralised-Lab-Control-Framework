"""
Example Experiment Using Abbreviated Fragment Names

Demonstrates the short naming conventions for all fragments.
"""

from ndscan.experiment import ExpFragment, FloatParam, BoolParam, make_fragment_scan_exp
from artiq.experiment import *
from oitg.units import V, us, ms

# Import all fragments with abbreviated names
from fragments import Cam, AutoCam, Comp, EC, Raman, Sweep


class AbbreviatedExample(ExpFragment):
    """
    Example experiment showing abbreviated fragment usage.
    
    Fragment Abbreviations:
    - Cam = Camera (TTL trigger + HTTP control)
    - AutoCam = AutoCamera (Camera with auto-triggering)
    - Comp = Compensation (DC compensation electrodes)
    - EC = EndCaps (Endcap electrodes)
    - Raman = RamanCooling (Raman beam control)
    - Sweep = SecularSweep (Secular frequency sweep)
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        
        # DC Electrodes
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
        
        # Laser Control
        self.setattr_fragment("raman", Raman)
        
        # Camera
        self.setattr_fragment("cam", Cam)
        
        # Diagnostics
        self.setattr_fragment("sweep", Sweep)
        
        # Parameters
        self.setattr_param("u_hor", FloatParam, "Horizontal comp", 
                          default=0.0*V, unit="V")
        self.setattr_param("u_ver", FloatParam, "Vertical comp", 
                          default=0.0*V, unit="V")
        self.setattr_param("u_ec1", FloatParam, "EC1 voltage", 
                          default=0.0*V, unit="V")
        self.setattr_param("u_ec2", FloatParam, "EC2 voltage", 
                          default=0.0*V, unit="V")
    
    @kernel
    def run_once(self) -> None:
        """Execute one experimental sequence."""
        
        # 1. Set DC electrodes
        self.comp.set_compensation(self.u_hor.get(), self.u_ver.get())
        self.ec.set_ec(self.u_ec1.get(), self.u_ec2.get())
        
        # 2. Configure Raman beams
        self.raman.set_cooling_params(
            a0=0.05, a1=0.05,
            sw0=1, sw1=1
        )
        
        # 3. Trigger camera frame
        self.cam.trigger_frame()
        
        delay(100*ms)


# Create standalone experiment
AbbreviatedExampleExp = make_fragment_scan_exp(AbbreviatedExample)


# Alternative: Loading sequence example
class IonLoading(ExpFragment):
    """
    Simplified ion loading sequence using abbreviated names.
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        
        # Minimal setup for loading
        self.setattr_fragment("ec", EC)
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("cam", Cam)
        self.setattr_fragment("raman", Raman)
        
        self.setattr_param("loading_ec", FloatParam, "Loading EC voltage",
                          default=25.0*V, unit="V")
    
    @kernel
    def run_once(self) -> None:
        """Loading sequence."""
        # Set endcaps for loading
        self.ec.set_ec(self.loading_ec.get(), self.loading_ec.get())
        
        # Turn on cooling
        self.raman.set_cooling_params(a0=0.1, a1=0.1, sw0=1, sw1=1)
        
        # Trigger camera to check for ions
        self.cam.trigger_frame()


IonLoadingExp = make_fragment_scan_exp(IonLoading)
