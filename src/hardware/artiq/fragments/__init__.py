"""
ARTIQ Fragments - Short naming conventions module.

This module provides ARTIQ fragments with abbreviated naming conventions
for cleaner experiment code.

╔═════════════╦════════════════════╦════════════════════════════════════╗
║ Abbreviated ║ Full Name          ║ Purpose                            ║
╠═════════════╬════════════════════╬════════════════════════════════════╣
║ Cam         ║ Camera             ║ TTL trigger + HTTP control         ║
║ AutoCam     ║ AutoCamera         ║ Camera with automatic triggering   ║
║ Comp        ║ Compensation       ║ DC compensation electrodes         ║
║ EC          ║ EndCaps            ║ Endcap electrodes                  ║
║ Raman       ║ RamanCooling       ║ Raman beam control                 ║
║ Sweep       ║ SecularSweep       ║ Secular frequency sweep            ║
╚═════════════╩════════════════════╩════════════════════════════════════╝

Quick Start:
    from fragments import Cam, Comp, EC, Raman
    
    class MyExp(ExpFragment):
        def build_fragment(self):
            self.setattr_fragment("cam", Cam)
            self.setattr_fragment("comp", Comp)
            self.setattr_fragment("ec", EC)

See NAMING_CONVENTIONS.md for full documentation.
"""

# Import with short abbreviations
from .cam import Camera as Cam
from .cam import AutoCamera as AutoCam
from .comp import Compensation as Comp
from .ec import EndCaps as EC
from .Raman_board import RamanCooling as Raman
from .secularsweep import SecularSweep as Sweep

# Also export original names for backward compatibility
from .cam import Camera, AutoCamera
from .comp import Compensation
from .ec import EndCaps
from .Raman_board import RamanCooling
from .secularsweep import SecularSweep

__all__ = [
    # Abbreviated names (recommended)
    'Cam',
    'AutoCam', 
    'Comp',
    'EC',
    'Raman',
    'Sweep',
    # Original names (backward compatibility)
    'Camera',
    'AutoCamera',
    'Compensation',
    'EndCaps',
    'RamanCooling',
    'SecularSweep',
]
