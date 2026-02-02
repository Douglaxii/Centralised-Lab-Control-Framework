# Variable Naming Migration Guide

**Version:** 1.0  
**Created:** 2026-02-02  
**Status:** Ready for Implementation

This document provides the complete mapping for variable name standardization across the MLS codebase.

---

## Priority 1: RF Voltage Naming (Critical)

### Issue Summary
The RF voltage variable naming is currently inconsistent and ambiguous:
- `u_rf` - sometimes means mV (SMILE interface), sometimes V (real voltage)
- `U_RF` - used inconsistently for real voltage
- `urf` - abbreviated form, unclear meaning

### Standardized Naming Convention

| Physical Quantity | Standard Variable | Unit | Range | Description |
|------------------|-------------------|------|-------|-------------|
| SMILE interface voltage | `u_rf_mv` | mV | 0-1400 | LabVIEW control output |
| Real trap RF voltage | `U_rf_v` | V | 0-200 | After amplifier |
| RF frequency | `rf_freq_mhz` | MHz | ~21.5 | Drive frequency |

### Conversion Constants (in `core/enums.py`)

```python
# Scaling constants
RF_SCALE_V_PER_MV = 100.0 / 700.0  # ~0.142857 V/mV
RF_SCALE_MV_PER_V = 700.0 / 100.0  # 7.0 mV/V

# Conversion functions
def u_rf_mv_to_U_rf_v(u_rf_mv: float) -> float:
    """Convert LabVIEW SMILE u_rf (mV) to real trap U_rf (V)."""
    return u_rf_mv * RF_SCALE_V_PER_MV

def U_rf_v_to_u_rf_mv(U_rf_v: float) -> float:
    """Convert real trap U_rf (V) to LabVIEW SMILE u_rf (mV)."""
    return U_rf_v * RF_SCALE_MV_PER_V
```

---

## Priority 2: DC Electrode Naming

### Current State vs Target State

| Current Variable | Target Variable | Context | Unit |
|-----------------|-----------------|---------|------|
| `u_ec1` | `ec1_voltage` | Endcap 1 voltage | V |
| `u_ec2` | `ec2_voltage` | Endcap 2 voltage | V |
| `u_hor` | `comp_h_voltage` | Horizontal compensation | V |
| `u_ver` | `comp_v_voltage` | Vertical compensation | V |

### Config Key Mapping

Config files use shortened keys (acceptable only in config):

| Config Key | Maps to Variable | Unit |
|-----------|-----------------|------|
| `ec1` | `ec1_voltage` | V |
| `ec2` | `ec2_voltage` | V |
| `comp_h` | `comp_h_voltage` | V |
| `comp_v` | `comp_v_voltage` | V |
| `u_rf_volts` | `U_rf_v` | V |

---

## Priority 3: Variable Migration by File

### File: `artiq/fragments/compensation.py` (to be renamed)

| Line | Current | Target | Context |
|------|---------|--------|---------|
| 34 | `u` | `target_v` | Local calculation |
| 37 | `coarse` | `coarse_v` | Calculation result |
| 41 | `fine_needed` | `fine_v_needed` | Intermediate |
| 42 | `fine` | `fine_v` | Calculation result |
| 87-88 | `u_h_target`, `u_v_target` | `target_h_v`, `target_v_v` | Parameters |
| 114 | `u_hor`, `u_ver` | `hor_v`, `ver_v` | Arguments |

**Recommended:** Variables in this file are mostly internal and well-scoped. Lower priority for renaming.

---

### File: `artiq/fragments/endcaps.py` (to be renamed from `ec.py`)

| Line | Current | Target | Context |
|------|---------|--------|---------|
| 40 | `u_out` | `output_v` | Calculation result |
| 75 | `u_in` | `input_v` | Parameter |
| 94 | `corrected_u` | `corrected_v` | Calculation result |
| 120-123 | `u_target1`, `u_target2` | `target_1_v`, `target_2_v` | Parameters |
| 139 | `u1_val`, `u2_val` | `val_1_v`, `val_2_v` | Arguments |

**Recommended:** Lower priority for renaming.

---

### File: `core/enums.py`

**Already standardized!** The conversion functions and constants use proper naming:

```python
# Already correct:
RF_SCALE_V_PER_MV = 100.0 / 700.0
RF_SCALE_MV_PER_V = 700.0 / 100.0

def u_rf_mv_to_U_rf_v(u_rf_mv: float) -> float:
def U_rf_v_to_u_rf_mv(U_rf_v: float) -> float:
```

**Note:** The docstrings correctly distinguish between `u_rf_mv` (SMILE) and `U_rf_v` (real).

---

### File: `server/communications/manager.py`

| Line | Current | Target | Context |
|------|---------|--------|---------|
| 624 | `u_rf_volts` | Keep as-is | Config key |
| 639 | `u_rf_volts` | Keep as-is | Dict key |
| 690 | `u_rf_volts` | Keep as-is | Dict key |

**Status:** Already uses `u_rf_volts` consistently as the config/manager parameter name.

---

### File: `server/applet/experiments/sim_calibration.py`

| Line | Current | Target | Context |
|------|---------|--------|---------|
| 45 | `u_rf` | `u_rf_scanned_v` | Dataclass field (V) |
| 103 | `u_rf_values` | Keep as-is | List of voltages (V) |
| 164 | `u_rf` | `u_rf_v` | Local variable (V) |
| 208 | `u_rf` | `u_rf_v` | Log message |
| 238 | `u_rf` | `u_rf_v` | List comprehension |
| 241 | `u_rf` | `u_rf_v` | Loop variable |
| 290 | `u_rf` | `u_rf_v` | Parameter |
| 309 | `u_rf` | `u_rf_v` | Reference data lookup |
| 315-324 | `u_rf` | `u_rf_v` | Interpolation |
| 350 | `u_rf` | `u_rf_v` | Parameter |
| 362 | `U_RF` | `U_rf_v` | Log message |
| 368 | `u_rf_volts` | Keep as-is | Config key |
| 388 | `u_rf` | `u_rf_v` | Parameter |
| 395 | `U_RF` | `U_rf_v` | Log message |
| 453 | `u_rf` | `u_rf_v` | Dataclass field |
| 482-508 | `u_rf` | `u_rf_v` | Loop variables |
| 558 | `u_RF` | `U_rf_v` | DataSet parameter |
| 791 | `U_RF` | `U_rf_v` | Print output |

**Note:** This file uses `u_rf` to mean volts (real RF voltage), not mV. The context is clear because it's in the experiment layer dealing with physical trap parameters.

---

### File: `server/analysis/eigenmodes/fit_Kappa_Chi_URF.py`

| Line | Current | Target | Context |
|------|---------|--------|---------|
| 26 | `u_RF` | `U_rf_v` | DataSet field (volts) |
| 67 | `u_RF` | `U_rf_v` | Context manager param |
| 142 | `u_RF` | `U_rf_v` | Math calculation |
| 293 | `U_RF` | `U_rf_v` | CLI prompt label |
| 341 | `U_RF` | `U_rf_v` | Output label |

---

### File: `server/analysis/eigenmodes/sec_urf.py`

| Line | Current | Target | Context |
|------|---------|--------|---------|
| 25 | `u_rf` | `u_rf_v` | Parameter (volts) |
| 27-28 | `u_RF`, `v_end` | `U_rf_v`, `v_end_v` | Module globals |
| 35 | `u_RF` | `U_rf_v` | Restore value |
| 57 | `u_rf` | `u_rf_v` | Loop variable |
| 114 | `u_rf` | `u_rf_v` | Script variable |
| 124 | `u_rf` | `u_rf_v` | Function argument |

---

### File: `server/analysis/eigenmodes/trap_sim.py` and `trap_sim_asy.py`

| Current | Target | Context |
|---------|--------|---------|
| `u_RF` | `U_rf_v` | Module-level parameter |
| `v_end` | `v_end_v` | Module-level parameter |

---

## Priority 4: Raman/DDS Parameter Naming

### Standardized Names

| Current | Target | Unit | Description |
|---------|--------|------|-------------|
| `amp0` | `beam_0_amplitude` | 0-1 | Beam 0 amplitude |
| `amp1` | `beam_1_amplitude` | 0-1 | Beam 1 amplitude |
| `sw0` | `beam_0_switch` | 0/1 | Beam 0 switch |
| `sw1` | `beam_1_switch` | 0/1 | Beam 1 switch |
| `freq0` | `beam_0_freq_mhz` | MHz | Beam 0 frequency (const) |
| `freq1` | `beam_1_freq_mhz` | MHz | Beam 1 frequency (const) |
| `att0` | `beam_0_att_db` | dB | Beam 0 attenuation |
| `att1` | `beam_1_att_db` | dB | Beam 1 attenuation |

**Note:** Config keys can remain as `amp0`, `amp1`, `sw0`, `sw1` for brevity, but code variables should use descriptive names.

---

## Priority 5: Variable Migration Summary

### By Priority

| Priority | Variable Pattern | Files Affected | Effort |
|----------|-----------------|----------------|--------|
| P1 | `u_rf` → `u_rf_mv` / `U_rf_v` | 8+ files | High |
| P2 | `u_ec1/2` → `ec1/2_voltage` | 3 files | Medium |
| P3 | `u_hor/ver` → `comp_h/v_voltage` | 2 files | Medium |
| P4 | `amp0/1` → `beam_0/1_amplitude` | 4 files | Medium |
| P5 | `sw0/1` → `beam_0/1_switch` | 4 files | Low |

### By File

| File | Variables to Update | Priority |
|------|---------------------|----------|
| `core/enums.py` | None (already correct) | - |
| `server/communications/manager.py` | None (already correct) | - |
| `server/applet/experiments/sim_calibration.py` | `u_rf` → `u_rf_v` | P1 |
| `server/analysis/eigenmodes/fit_Kappa_Chi_URF.py` | `u_RF` → `U_rf_v` | P1 |
| `server/analysis/eigenmodes/sec_urf.py` | `u_rf`, `u_RF` → `u_rf_v`, `U_rf_v` | P1 |
| `server/analysis/eigenmodes/trap_sim.py` | `u_RF` → `U_rf_v` | P1 |
| `server/analysis/eigenmodes/trap_sim_asy.py` | `u_RF` → `U_rf_v` | P1 |
| `artiq/fragments/Raman_board.py` | `amp0/1`, `sw0/1` → descriptive | P4/P5 |
| `artiq/fragments/comp.py` | `u_hor/ver` → `comp_h/v_voltage` | P3 |
| `artiq/fragments/ec.py` | `u_ec1/2` → `ec1/2_voltage` | P2 |

---

## Phase 5: Execution Strategy

### Approach: Gradual Migration

Rather than changing everything at once, use a phased approach:

#### Phase 5.1: New Code Only (Immediate)
- All new code must follow NAMING_CONVENTIONS.md
- Use `u_rf_mv` and `U_rf_v` in all new functions

#### Phase 5.2: Core Functions (Week 1)
- Update `core/enums.py` conversion functions (already done)
- Update `server/communications/manager.py` (already done)
- Update `server/communications/labview_interface.py`

#### Phase 5.3: Analysis Code (Week 2-3)
- Update eigenmode analysis files
- Update SIM calibration experiment

#### Phase 5.4: Fragment Code (Week 4)
- Update ARTIQ fragments after file rename

#### Phase 5.5: Documentation (Ongoing)
- Update all docstrings
- Update API documentation

---

## Phase 6: Backward Compatibility

### For Config Keys

Config keys remain stable (no change needed):
```yaml
hardware:
  worker_defaults:
    u_rf_volts: 200.0  # Keep this key
    ec1: 0.0           # Keep this key
    ec2: 0.0           # Keep this key
    comp_h: 0.0        # Keep this key
    comp_v: 0.0        # Keep this key
    amp0: 0.05         # Keep this key
    amp1: 0.05         # Keep this key
    sw0: 0             # Keep this key
    sw1: 0             # Keep this key
```

### For Function Parameters

Where backward compatibility is needed, accept both old and new:

```python
def set_rf_voltage(
    voltage_v: float = None,
    # Deprecated parameter for backward compatibility
    u_rf: float = None,
    u_rf_mv: float = None
) -> bool:
    """
    Set RF voltage.
    
    Args:
        voltage_v: Real RF voltage in volts (0-200V) [RECOMMENDED]
        u_rf: Deprecated, use voltage_v instead
        u_rf_mv: SMILE interface voltage in mV (0-1400mV)
    """
    if u_rf is not None:
        import warnings
        warnings.warn("u_rf is deprecated, use voltage_v", DeprecationWarning)
        voltage_v = u_rf
    # ... rest of implementation
```

---

## Appendix: Regex Search Patterns

Use these patterns to find variable usages:

```bash
# Find u_rf variable (excluding comments and strings)
grep -rn "\bu_rf\b" --include="*.py" MLS/ | grep -v "u_rf_mv\|u_rf_volts\|#"

# Find U_RF variable
grep -rn "\bU_RF\b" --include="*.py" MLS/

# Find urf variable
grep -rn "\burf\b" --include="*.py" MLS/

# Find u_ec1/u_ec2
grep -rn "\bu_ec[12]\b" --include="*.py" MLS/

# Find u_hor/u_ver
grep -rn "\bu_hor\b\|\bu_ver\b" --include="*.py" MLS/
```
