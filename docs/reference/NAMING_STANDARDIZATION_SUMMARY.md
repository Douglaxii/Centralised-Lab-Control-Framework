# Naming Standardization Summary

**Version:** 1.0  
**Created:** 2026-02-02  
**Status:** Complete - Ready for Review

---

## Overview

This document summarizes the naming convention standardization effort for the MLS codebase. Three reference documents have been created to guide the migration.

---

## Documents Created

### 1. NAMING_CONVENTIONS.md
**Path:** `MLS/docs/reference/NAMING_CONVENTIONS.md`

**Purpose:** Definitive reference for all naming conventions in the project.

**Contents:**
- File naming conventions (lowercase_with_underscores.py)
- Class naming conventions (PascalCase)
- Variable naming conventions (snake_case)
- Constants naming (UPPER_SNAKE_CASE)
- Hardware device naming conventions
- Config key naming conventions
- Import conventions
- Type hint conventions
- Quick reference table

**Key Decisions:**
| Element | Convention | Example |
|---------|-----------|---------|
| Python files | `lowercase_with_underscores.py` | `camera_control.py` |
| Classes | `PascalCase` | `CameraController` |
| Functions | `snake_case` | `set_camera_params()` |
| Variables | `snake_case` | `exposure_time_ms` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_EXPOSURE_MS` |
| RF SMILE mV | `u_rf_mv` | Interface value |
| RF Real V | `U_rf_v` | Trap voltage |

---

### 2. FILE_RENAME_MIGRATION.md
**Path:** `MLS/docs/reference/FILE_RENAME_MIGRATION.md`

**Purpose:** Complete guide for renaming files with step-by-step instructions.

**Files to Rename:**

| Current Path | New Path | Breaking Change |
|--------------|----------|-----------------|
| `MLS/artiq/fragments/comp.py` | `MLS/artiq/fragments/compensation.py` | Yes - Import changes |
| `MLS/artiq/fragments/ec.py` | `MLS/artiq/fragments/endcaps.py` | Yes - Import changes |
| `MLS/artiq/fragments/cam.py` | `MLS/artiq/fragments/camera.py` | No - No direct imports |
| `MLS/artiq/fragments/Raman_board.py` | `MLS/artiq/fragments/raman_board.py` | Yes - Import changes |
| `MLS/artiq/fragments/secularsweep.py` | `MLS/artiq/fragments/secular_sweep.py` | Yes - Import changes |

**Import Updates Required:**
- `artiq/experiments/trap_controler.py` - Update imports for `comp` and `ec`

---

### 3. VARIABLE_NAMING_MIGRATION.md
**Path:** `MLS/docs/reference/VARIABLE_NAMING_MIGRATION.md`

**Purpose:** Complete mapping for variable name standardization.

**Critical Variable Mappings:**

| Current (Inconsistent) | Standard | Meaning |
|------------------------|----------|---------|
| `u_rf` (ambiguous) | `u_rf_mv` | SMILE interface (mV) |
| `u_rf` (ambiguous) | `U_rf_v` | Real trap voltage (V) |
| `U_RF` | `U_rf_v` | Real trap voltage (V) |
| `urf` | `u_rf_mv` | SMILE interface (mV) |

**Files Requiring Variable Updates:**
1. `server/applet/experiments/sim_calibration.py` - `u_rf` → `u_rf_v`
2. `server/analysis/eigenmodes/fit_Kappa_Chi_URF.py` - `u_RF` → `U_rf_v`
3. `server/analysis/eigenmodes/sec_urf.py` - Both `u_rf` and `u_RF`
4. `server/analysis/eigenmodes/trap_sim.py` - `u_RF` → `U_rf_v`
5. `server/analysis/eigenmodes/trap_sim_asy.py` - `u_RF` → `U_rf_v`

---

## Current State Analysis

### Files Already Following Conventions

| File | Status | Notes |
|------|--------|-------|
| `core/enums.py` | ✓ Compliant | RF voltage functions already correct |
| `core/config.py` | ✓ Compliant | Follows all conventions |
| `core/hardware_interface.py` | ✓ Compliant | Clean naming |
| `server/communications/manager.py` | ✓ Compliant | Uses `u_rf_volts` correctly |

### Files Needing File Rename Only

| File | New Name | Import Updates |
|------|----------|----------------|
| `artiq/fragments/cam.py` | `camera.py` | None |

### Files Needing File Rename + Import Updates

| File | New Name | Import Updates Required |
|------|----------|------------------------|
| `artiq/fragments/comp.py` | `compensation.py` | `trap_controler.py` |
| `artiq/fragments/ec.py` | `endcaps.py` | `trap_controler.py` |
| `artiq/fragments/Raman_board.py` | `raman_board.py` | Search required |
| `artiq/fragments/secularsweep.py` | `secular_sweep.py` | Search required |

### Files Needing Variable Renames (No File Rename)

| File | Variables to Update |
|------|---------------------|
| `server/applet/experiments/sim_calibration.py` | `u_rf` → `u_rf_v` |
| `server/analysis/eigenmodes/fit_Kappa_Chi_URF.py` | `u_RF` → `U_rf_v` |
| `server/analysis/eigenmodes/sec_urf.py` | `u_rf` → `u_rf_v`, `u_RF` → `U_rf_v` |
| `server/analysis/eigenmodes/trap_sim.py` | `u_RF` → `U_rf_v` |
| `server/analysis/eigenmodes/trap_sim_asy.py` | `u_RF` → `U_rf_v` |

---

## Public API Surface

The following classes/functions form the public API and should be prioritized:

### Fragment Classes (ARTIQ)
- `Compensation` (in `comp.py` → `compensation.py`)
- `EndCaps` (in `ec.py` → `endcaps.py`)
- `Camera` (in `cam.py` → `camera.py`)
- `RamanCooling` (in `Raman_board.py` → `raman_board.py`)
- `SecularSweep` (in `secularsweep.py` → `secular_sweep.py`)

### Manager Commands
- `u_rf_volts` - Config parameter name (keep stable)
- `ec1`, `ec2`, `comp_h`, `comp_v` - Config parameter names (keep stable)

### Conversion Functions (core/enums.py)
- `u_rf_mv_to_U_rf_v(u_rf_mv: float) -> float`
- `U_rf_v_to_u_rf_mv(U_rf_v: float) -> float`

---

## Recommended Implementation Order

### Phase 1: Documentation (Complete ✓)
1. ✓ Create NAMING_CONVENTIONS.md
2. ✓ Create FILE_RENAME_MIGRATION.md
3. ✓ Create VARIABLE_NAMING_MIGRATION.md

### Phase 2: File Renames (Next Step)
1. Rename fragment files with `git mv`
2. Update imports in `trap_controler.py`
3. Search for any other import references
4. Test that experiments still run

### Phase 3: Variable Renames (Gradual)
1. Update analysis code variables (`u_rf` → `u_rf_v`)
2. Update docstrings to use consistent naming
3. Add deprecation warnings if backward compatibility needed

### Phase 4: Verification
1. Run all tests
2. Verify no broken imports
3. Update ARCHITECTURE.md if needed
4. Notify team of changes

---

## Migration Commands Quick Reference

### File Rename Commands
```bash
# Create branch
git checkout -b naming-conventions-migration

# Rename files
git mv MLS/artiq/fragments/comp.py MLS/artiq/fragments/compensation.py
git mv MLS/artiq/fragments/ec.py MLS/artiq/fragments/endcaps.py
git mv MLS/artiq/fragments/cam.py MLS/artiq/fragments/camera.py
git mv MLS/artiq/fragments/Raman_board.py MLS/artiq/fragments/raman_board.py
git mv MLS/artiq/fragments/secularsweep.py MLS/artiq/fragments/secular_sweep.py
```

### Import Update (trap_controler.py)
```python
# OLD:
from comp import Compensation
from ec import EndCaps

# NEW:
from compensation import Compensation
from endcaps import EndCaps
```

---

## Verification Checklist

Before marking migration complete:

- [ ] All 5 fragment files renamed
- [ ] All imports updated in dependent files
- [ ] `trap_controler.py` runs without ImportError
- [ ] Tests pass (if available)
- [ ] Documentation updated
- [ ] Team notified of changes

---

## Contact

For questions about naming conventions, refer to:
- Primary: `MLS/docs/reference/NAMING_CONVENTIONS.md`
- File renames: `MLS/docs/reference/FILE_RENAME_MIGRATION.md`
- Variable updates: `MLS/docs/reference/VARIABLE_NAMING_MIGRATION.md`
