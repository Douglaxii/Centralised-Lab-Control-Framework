# ARTIQ Fragments

Modular ARTIQ fragments for ion trap control.

## Quick Reference

```python
from fragments import Cam, Comp, EC, Raman, Sweep
```

| Abbreviation | Description | Devices |
|-------------|-------------|---------|
| `Cam` | Camera control | TTL trigger, HTTP API |
| `AutoCam` | Auto-triggering camera | TTL + HTTP |
| `Comp` | Compensation electrodes | Zotino DAC (ch 0-3) |
| `EC` | Endcap electrodes | Zotino DAC (ch 4-5) |
| `Raman` | Raman cooling beams | Urukul DDS |
| `Sweep` | Secular frequency sweep | DDS + PMT + Camera |

## Usage Example

```python
from ndscan.experiment import ExpFragment, make_fragment_scan_exp
from fragments import Cam, Comp, EC

class MyExperiment(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("cam", Cam)
        self.setattr_fragment("comp", Comp)
        self.setattr_fragment("ec", EC)
    
    @kernel
    def run_once(self):
        # Set DC voltages
        self.comp.set_compensation(10*V, 5*V)
        self.ec.set_ec(20*V, 20*V)
        
        # Trigger camera
        self.cam.trigger_frame()

MyExperimentExp = make_fragment_scan_exp(MyExperiment)
```

## Fragment Details

### Cam (Camera)
- **File**: `cam.py`
- **Purpose**: Hardware TTL triggering + HTTP control
- **Key Methods**:
  - `trigger_frame()` - TTL pulse for single frame
  - `start_infinity_recording()` - HTTP start
  - `stop_infinity_recording()` - HTTP stop

### Comp (Compensation)
- **File**: `comp.py`
- **Purpose**: DC compensation electrodes (horizontal + vertical)
- **Hardware**: Zotino DAC channels 0-3
- **Key Methods**:
  - `set_compensation(u_hor, u_ver)` - Set voltages

### EC (EndCaps)
- **File**: `ec.py`
- **Purpose**: Endcap electrodes (EC1, EC2)
- **Hardware**: Zotino DAC channels 4-5
- **Key Methods**:
  - `set_ec(u1, u2)` - Set endcap voltages

### Raman (RamanCooling)
- **File**: `Raman_board.py`
- **Purpose**: 135° and 225° Raman beams
- **Hardware**: Urukul DDS channels 0-1
- **Key Methods**:
  - `set_cooling_params(a0, a1, sw0, sw1)` - Set amplitudes and switches
  - `activate_cooling()` - Use dashboard parameters

### Sweep (SecularSweep)
- **File**: `secularsweep.py`
- **Purpose**: Sweep secular frequency with PMT readout
- **Hardware**: DDS + PMT counter + Camera trigger
- **Key Methods**:
  - `run_point()` - Executed for each scan point

## Naming Conventions

See [NAMING_CONVENTIONS.md](NAMING_CONVENTIONS.md) for detailed naming guidelines.

### Rules
1. Use abbreviated imports: `from fragments import Cam`
2. Instance names are lowercase: `self.setattr_fragment("cam", Cam)`
3. Both old and new names work (backward compatible)

## Adding New Fragments

1. Create file: `my_fragment.py`
2. Define class: `class MyFragment(Fragment)`
3. Add to `__init__.py`:
   ```python
   from .my_fragment import MyFragment as MF
   ```
4. Document in this README

## Backward Compatibility

Original names still work:
```python
from fragments import Camera, Compensation, EndCaps  # etc.
```

But abbreviated names are preferred:
```python
from fragments import Cam, Comp, EC  # cleaner!
```
