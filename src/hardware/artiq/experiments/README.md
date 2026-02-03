# ARTIQ Experiments

Experiment files that use the fragments for ion trap control.

## Files

| File | Description | Fragments Used |
|------|-------------|----------------|
| `trap_controler.py` | Basic DC voltage control | Comp, EC |
| `artiq_worker.py` | Main ZMQ worker | All fragments |
| `example_abbreviated.py` | Example using short names | Cam, Comp, EC, Raman, Sweep |

## Quick Example

```python
from ndscan.experiment import ExpFragment, make_fragment_scan_exp
from artiq.experiment import *
from oitg.units import V

# Import fragments with abbreviated names
from fragments import Comp, EC

class DcControl(ExpFragment):
    """Simple DC voltage control."""
    
    def build_fragment(self):
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
    
    @kernel
    def run_once(self):
        self.comp.set_compensation(10*V, 5*V)
        self.ec.set_ec(20*V, 20*V)

DcControlExp = make_fragment_scan_exp(DcControl)
```

## Running Experiments

### From ARTIQ Dashboard
1. Add repository path in ARTIQ dashboard
2. Select experiment from list
3. Run with parameter overrides

### From Command Line
```bash
cd src/hardware/artiq/experiments
artiq_run trap_controler.py
```

## Fragment Abbreviations Quick Ref

```python
from fragments import (
    Cam,      # Camera
    AutoCam,  # AutoCamera
    Comp,     # Compensation
    EC,       # EndCaps
    Raman,    # RamanCooling
    Sweep,    # SecularSweep
)
```

See [../fragments/README.md](../fragments/README.md) for fragment details.
