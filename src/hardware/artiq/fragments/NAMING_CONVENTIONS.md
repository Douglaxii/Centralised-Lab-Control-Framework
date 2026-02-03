# ARTIQ Fragment Naming Conventions

## Quick Reference

| Full Name | Abbreviation | Purpose |
|-----------|--------------|---------|
| `Camera` | `Cam` | Camera trigger + HTTP control |
| `AutoCamera` | `AutoCam` | Camera with auto-triggering |
| `Compensation` | `Comp` | DC compensation electrodes |
| `EndCaps` | `EC` | Endcap electrodes |
| `RamanCooling` | `Raman` | Raman cooling beams |
| `SecularSweep` | `Sweep` | Secular frequency sweep |

## Usage

### Import (Abbreviated)
```python
from fragments import Cam, Comp, EC, Raman, Sweep
```

### In Experiment Code
```python
class MyExperiment(ExpFragment):
    def build_fragment(self):
        # Use abbreviated names
        self.setattr_fragment("cam", Cam)
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
        self.setattr_fragment("raman", Raman)
        self.setattr_fragment("sweep", Sweep)
```

## Naming Rules

### 1. Abbreviations Are Upper CamelCase
- `Cam` not `CAM` or `cam`
- `Comp` not `COMP` or `comp`
- `EC` not `Ec` or `ec`

### 2. Fragment Instances Are Lowercase
```python
self.setattr_fragment("comp", Comp)      # ✓ Good
self.setattr_fragment("Comp", Comp)      # ✗ Bad - instance name uppercase
```

### 3. Use Short Names in Experiments
```python
# ✓ Good
from fragments import Cam, Comp

# ✗ Bad - unnecessary verbosity
from fragments import Camera, Compensation
```

## Examples

### Basic DC Control
```python
from ndscan.experiment import ExpFragment, make_fragment_scan_exp
from fragments import Comp, EC

class DcControl(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
    
    @kernel
    def run_once(self):
        self.comp.set_compensation(10*V, 5*V)
        self.ec.set_ec(20*V, 20*V)

DcControlExp = make_fragment_scan_exp(DcControl)
```

### With Camera
```python
from fragments import Cam, Comp, EC

class Loading(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("cam", Cam)
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
    
    def run_once(self):
        self.cam.start_infinity_recording()  # HTTP call
        self.cam.trigger_frame()             # TTL trigger
```

### Full System
```python
from fragments import Cam, AutoCam, Comp, EC, Raman, Sweep

class FullControl(ExpFragment):
    def build_fragment(self):
        # DC electrodes
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
        
        # Lasers
        self.setattr_fragment("raman", Raman)
        
        # Camera
        self.setattr_fragment("cam", Cam)
        
        # Diagnostics
        self.setattr_fragment("sweep", Sweep)
```

## Backward Compatibility

Original names are still available:
```python
# These all work
from fragments import Cam          # Abbreviated
from fragments import Camera       # Original
from .cam import Camera            # Direct import
```

## Adding New Fragments

When adding a new fragment:

1. Create file with descriptive name: `shutter_control.py`
2. Define class with descriptive name: `class ShutterControl(Fragment)`
3. Add abbreviation to `__init__.py`:
   ```python
   from .shutter_control import ShutterControl as Shutter
   ```
4. Document abbreviation in this file

### Abbreviation Guidelines

| Pattern | Example |
|---------|---------|
| Keep first syllable | `Compensation` → `Comp` |
| Use initials | `EndCaps` → `EC` |
| Remove trailing words | `RamanCooling` → `Raman` |
| Shorten common words | `Camera` → `Cam` |

## Common Abbreviations Reference

| Word | Abbreviation |
|------|--------------|
| Camera | Cam |
| Compensation | Comp |
| Control | Ctrl |
| Electrode | Elec |
| Endcap | EC |
| Frequency | Freq |
| Measurement | Meas |
| Parameter | Param |
| Raman | Raman |
| Shutter | Shut |
| Sweep | Sweep |
| Temperature | Temp |
| Trigger | Trig |
| Voltage | V |
