# MLS Naming Conventions

**Version:** 1.0  
**Last Updated:** 2026-02-02  
**Status:** Active

This document defines the naming conventions for the Mixed Species Ion Trap (MLS) codebase. All contributors must follow these conventions to ensure consistency across the project.

---

## 1. File Naming Conventions

### 1.1 Python Files

**Rule:** Use `lowercase_with_underscores.py`

| Pattern | Example | Notes |
|---------|---------|-------|
| ✓ Correct | `compensation.py`, `secular_sweep.py` | Descriptive, all lowercase, underscores |
| ✗ Incorrect | `comp.py`, `secularsweep.py`, `Raman_board.py` | Avoid abbreviations, run-on words, CamelCase |

**Examples:**
- `compensation.py` (not `comp.py`)
- `endcaps.py` (not `ec.py`)
- `camera.py` (not `cam.py`)
- `raman_board.py` (not `Raman_board.py`)
- `secular_sweep.py` (not `secularsweep.py`)

### 1.2 Configuration Files

**Rule:** Use `lowercase_with_underscores.yaml`

Examples:
- `settings.yaml`
- `parallel_config.yaml`
- `local_development.yaml`

### 1.3 Documentation Files

**Rule:** Use `UPPERCASE_WITH_UNDERSCORES.md` for main docs, `lowercase.md` for guides

| Type | Pattern | Example |
|------|---------|---------|
| Architecture docs | `UPPERCASE.md` | `ARCHITECTURE.md`, `API_REFERENCE.md` |
| Guides | `lowercase.md` | `conda_setup.md`, `camera_activation.md` |
| Summaries | `UPPERCASE_SUMMARY.md` | `CAMERA_IMPLEMENTATION.md` |

---

## 2. Class Naming Conventions

### 2.1 Python Classes

**Rule:** Use `PascalCase` for all class names

| Pattern | Example | Notes |
|---------|---------|-------|
| ✓ Correct | `Compensation`, `SecularSweep`, `RamanCooling` | Nouns or noun phrases |
| ✗ Incorrect | `compensation`, `secular_sweep` | Avoid snake_case |

**Special Cases:**
- Fragment classes: `PascalCase` ending with descriptive noun
  - `Compensation` (fragment for compensation electrodes)
  - `EndCaps` (fragment for endcap electrodes)
  - `Camera` (fragment for camera control)
  - `RamanCooling` (fragment for Raman cooling beams)
  - `SecularSweep` (fragment for secular frequency sweeps)

- Experiment classes: `PascalCase` ending with `Experiment` or descriptive name
  - `TrapControl`
  - `SimCalibrationExperiment`
  - `AutoCompensationExperiment`

- Manager/Controller classes: `PascalCase` ending with `Manager`, `Controller`, or `Interface`
  - `ControlManager`
  - `LabVIEWInterface`
  - `CameraInterface`
  - `OptimizerController`

- Data classes: `PascalCase` with descriptive names
  - `SecularMeasurement`
  - `FitResult`
  - `ExperimentContext`

### 2.2 Exception Classes

**Rule:** Use `PascalCase` ending with `Error`

Examples:
- `LabFrameworkError`
- `ConnectionError`
- `SafetyError`
- `ConfigurationError`

---

## 3. Variable Naming Conventions

### 3.1 General Variables

**Rule:** Use `snake_case` for all variables

| Pattern | Example | Notes |
|---------|---------|-------|
| ✓ Correct | `rf_voltage`, `dc_offset`, `sweep_range` | Descriptive, lowercase, underscores |
| ✗ Incorrect | `rfVoltage`, `DC_Offset`, `sweepRange` | Avoid camelCase, UPPER_SNAKE_CASE for vars |

### 3.2 Hardware Device Naming

#### DC Electrodes
| Device | Variable Name | Unit | Range |
|--------|--------------|------|-------|
| Endcap 1 | `ec1_voltage` | V | -1 to 50 |
| Endcap 2 | `ec2_voltage` | V | -1 to 50 |
| Horizontal Compensation | `comp_h_voltage` | V | -1 to 50 |
| Vertical Compensation | `comp_v_voltage` | V | -1 to 50 |

**Config keys:** `ec1`, `ec2`, `comp_h`, `comp_v` (shortened for config files only)

#### RF Voltage
**CRITICAL:** Use consistent naming for RF voltage to distinguish between:

| Physical Quantity | Variable Name | Unit | Range | Notes |
|------------------|---------------|------|-------|-------|
| SMILE interface voltage | `u_rf_mv` | mV | 0-1400 | LabVIEW SMILE output |
| Real trap RF voltage | `U_rf_v` | V | 0-200 | After 700:100 amplification |
| Config parameter | `u_rf_volts` | V | 0-200 | Manager parameter name |

**Conversion functions:**
```python
from core.enums import u_rf_mv_to_U_rf_v, U_rf_v_to_u_rf_mv

# Convert SMILE mV to real V
U_rf_v = u_rf_mv_to_U_rf_v(u_rf_mv)

# Convert real V to SMILE mV  
u_rf_mv = U_rf_v_to_u_rf_v(U_rf_v)
```

**Deprecated names (DO NOT USE):**
- `u_rf` - ambiguous (could be mV or V)
- `U_RF` - ambiguous without units
- `urf` - too abbreviated

#### DDS/Raman Parameters
| Parameter | Variable Name | Unit | Notes |
|-----------|--------------|------|-------|
| Beam 0 Amplitude | `beam_0_amplitude` | - | 0-1 range |
| Beam 1 Amplitude | `beam_1_amplitude` | - | 0-1 range |
| Beam 0 Switch | `beam_0_switch` | - | 0=off, 1=on |
| Beam 1 Switch | `beam_1_switch` | - | 0=off, 1=on |
| Attenuation | `attenuation_db` | dB | e.g., 25.0 |

**Config keys:** `amp0`, `amp1`, `sw0`, `sw1` (shortened for config files only)

#### Camera Parameters
| Parameter | Variable Name | Unit | Notes |
|-----------|--------------|------|-------|
| Exposure time | `exposure_ms` | ms | e.g., 300.0 |
| Frame count | `frame_count` | - | Number of frames |
| Trigger mode | `trigger_mode` | - | "extern" or "software" |
| ROI X start | `roi_x_start` | pixels | |
| ROI X end | `roi_x_end` | pixels | |
| ROI Y start | `roi_y_start` | pixels | |
| ROI Y end | `roi_y_end` | pixels | |

### 3.3 Constants

**Rule:** Use `UPPER_SNAKE_CASE` for module-level constants

Examples:
```python
# Physics constants
RF_SCALE_V_PER_MV = 100.0 / 700.0  # ~0.142857 V/mV
RF_SCALE_MV_PER_V = 700.0 / 100.0  # 7.0 mV/V

# Hardware limits
DAC_LIMIT = 10.0  # Volts
MAX_RF_VOLTAGE = 200.0  # Volts

# Frequency constants
RAMAN_FREQ_135_MHZ = 215.5
RAMAN_FREQ_225_MHZ = 215.5
```

### 3.4 Private Variables

**Rule:** Use `_leading_underscore` for private/internal variables

Examples:
```python
class MyClass:
    def __init__(self):
        self._internal_state = None  # Private instance variable
        self._lock = threading.RLock()  # Private lock
```

---

## 4. Function and Method Naming

### 4.1 Functions

**Rule:** Use `snake_case` for all functions. Use verbs or verb phrases.

| Pattern | Example | Notes |
|---------|---------|-------|
| ✓ Correct | `set_compensation()`, `calculate_voltage()` | Verb + object |
| ✗ Incorrect | `setCompensation()`, `CalculateVoltage()` | Avoid camelCase |

### 4.2 Private Methods

**Rule:** Use `_leading_underscore` for private methods

Examples:
```python
def _internal_helper(self):  # Private method
    pass

def _calculate_intermediate(self):  # Private calculation
    pass
```

---

## 5. Configuration Key Naming

### 5.1 Top-Level Sections

**Rule:** Use `lowercase` single words for top-level sections

```yaml
network:
paths:
hardware:
camera:
labview:
logging:
analysis:
experiment:
telemetry:
```

### 5.2 Nested Keys

**Rule:** Use `snake_case` for nested configuration keys

```yaml
hardware:
  worker_defaults:
    u_rf_volts: 200.0
    ec1: 0.0
    ec2: 0.0
    comp_h: 0.0
    comp_v: 0.0
    
network:
  master_ip: "192.168.1.100"
  cmd_port: 5555
  data_port: 5556
```

### 5.3 Hardware Parameter Keys (Config Only)

These shortened keys are acceptable **only in configuration files**:

| Full Name | Config Key | Unit |
|-----------|-----------|------|
| RF Voltage | `u_rf_volts` | V |
| Endcap 1 | `ec1` | V |
| Endcap 2 | `ec2` | V |
| Compensation Horizontal | `comp_h` | V |
| Compensation Vertical | `comp_v` | V |
| Beam 0 Amplitude | `amp0` | - |
| Beam 1 Amplitude | `amp1` | - |
| Beam 0 Switch | `sw0` | - |
| Beam 1 Switch | `sw1` | - |

---

## 6. Import Conventions

### 6.1 Absolute Imports

**Rule:** Prefer absolute imports for cross-module dependencies

```python
# Correct
from server.communications.manager import ControlManager
from core.enums import SystemMode
from artiq.fragments.compensation import Compensation

# Incorrect (relative)
from ..communications.manager import ControlManager
```

### 6.2 Import Ordering

Order imports as follows:
1. Standard library imports
2. Third-party imports
3. Local application imports

```python
# 1. Standard library
import os
import json
from pathlib import Path

# 2. Third-party
import numpy as np
import zmq

# 3. Local application
from core import get_config
from artiq.fragments.camera import Camera
```

---

## 7. Type Hint Conventions

### 7.1 Function Signatures

**Rule:** Use type hints for function parameters and return types

```python
def calculate_voltage(
    u_rf_mv: float, 
    v_end: float
) -> tuple[float, float]:
    """Calculate DAC voltages."""
    pass

def set_rf_voltage(self, voltage_v: float) -> bool:
    """Set RF voltage."""
    pass
```

---

## 8. Migration Checklist

When renaming files or variables:

- [ ] Update all imports in dependent files
- [ ] Update class references in type hints
- [ ] Update documentation references
- [ ] Update string references (if any)
- [ ] Run tests to verify no breakage
- [ ] Update architecture docs if module structure changes
- [ ] Notify team members of breaking changes

---

## 9. Enforcement

### 9.1 Code Review Checklist

- [ ] File names use `lowercase_with_underscores.py`
- [ ] Class names use `PascalCase`
- [ ] Variable names use `snake_case`
- [ ] Constants use `UPPER_SNAKE_CASE`
- [ ] RF voltage variables use `u_rf_mv` / `U_rf_v` convention
- [ ] No ambiguous abbreviations (e.g., `comp`, `ec`, `cam`)

### 9.2 IDE Configuration

Configure your IDE/editor to:
1. Highlight naming convention violations
2. Auto-format imports according to conventions
3. Suggest type hints for function signatures

---

## Appendix A: Quick Reference

| Element | Convention | Example |
|---------|-----------|---------|
| Python files | `lowercase_with_underscores.py` | `camera_control.py` |
| Classes | `PascalCase` | `CameraController` |
| Functions | `snake_case` | `set_camera_params()` |
| Variables | `snake_case` | `exposure_time_ms` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_EXPOSURE_MS` |
| Private | `_leading_underscore` | `_internal_buffer` |
| RF SMILE mV | `u_rf_mv` | Interface value |
| RF Real V | `U_rf_v` | Trap voltage |
| Config sections | `lowercase` | `hardware:` |
| Config keys | `snake_case` | `u_rf_volts:` |
