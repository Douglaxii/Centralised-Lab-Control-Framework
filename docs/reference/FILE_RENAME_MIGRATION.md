# File Rename Migration Guide

**Version:** 1.0  
**Created:** 2026-02-02  
**Status:** Ready for Implementation

This document provides the complete mapping for file renames and all required import updates.

---

## Phase 1: Fragment Renames

### 1.1 Rename: `comp.py` → `compensation.py`

**Location:** `MLS/artiq/fragments/`

**Files requiring import updates:**

| File Path | Current Import | New Import |
|-----------|---------------|------------|
| `artiq/experiments/trap_controler.py` | `from comp import Compensation` | `from compensation import Compensation` |

**Usage in `trap_controler.py`:**
```python
# Line 11 - Change this:
from comp import Compensation

# To this:
from compensation import Compensation

# Line 26 - No change needed (class name stays the same):
self.setattr_fragment("comp", Compensation)
```

---

### 1.2 Rename: `ec.py` → `endcaps.py`

**Location:** `MLS/artiq/fragments/`

**Files requiring import updates:**

| File Path | Current Import | New Import |
|-----------|---------------|------------|
| `artiq/experiments/trap_controler.py` | `from ec import EndCaps` | `from endcaps import EndCaps` |

**Usage in `trap_controler.py`:**
```python
# Line 12 - Change this:
from ec import EndCaps

# To this:
from endcaps import EndCaps

# Line 27 - No change needed (class name stays the same):
self.setattr_fragment("ec", EndCaps)
```

---

### 1.3 Rename: `cam.py` → `camera.py`

**Location:** `MLS/artiq/fragments/`

**Files requiring import updates:**

| File Path | Current Import | New Import |
|-----------|---------------|------------|
| None found | - | - |

**Note:** The `cam.py` fragment appears to be imported via `setattr_fragment` only:
```python
self.setattr_fragment("camera", Camera)
```

No explicit import statements found referencing this module directly.

---

### 1.4 Rename: `Raman_board.py` → `raman_board.py`

**Location:** `MLS/artiq/fragments/`

**Files requiring import updates:**

| File Path | Current Import | New Import |
|-----------|---------------|------------|
| Search required | `from Raman_board import ...` | `from raman_board import ...` |

**Action Items:**
1. Search for any imports of `Raman_board`
2. Update to `raman_board`

---

### 1.5 Rename: `secularsweep.py` → `secular_sweep.py`

**Location:** `MLS/artiq/fragments/`

**Files requiring import updates:**

| File Path | Current Import | New Import |
|-----------|---------------|------------|
| Search required | `from secularsweep import ...` | `from secular_sweep import ...` |
| Search required | `import secularsweep` | `import secular_sweep` |

---

## Phase 2: Summary of All File Renames

| Current Path | New Path | Breaking Change | Priority |
|--------------|----------|-----------------|----------|
| `MLS/artiq/fragments/comp.py` | `MLS/artiq/fragments/compensation.py` | Yes - Import changes | High |
| `MLS/artiq/fragments/ec.py` | `MLS/artiq/fragments/endcaps.py` | Yes - Import changes | High |
| `MLS/artiq/fragments/cam.py` | `MLS/artiq/fragments/camera.py` | No - No direct imports | Medium |
| `MLS/artiq/fragments/Raman_board.py` | `MLS/artiq/fragments/raman_board.py` | Yes - Import changes | Medium |
| `MLS/artiq/fragments/secularsweep.py` | `MLS/artiq/fragments/secular_sweep.py` | Yes - Import changes | Medium |

---

## Phase 3: Pre-Rename Search Checklist

Before executing renames, search for these patterns in the codebase:

```bash
# Search for comp.py imports
grep -r "from comp import" --include="*.py" MLS/
grep -r "import comp" --include="*.py" MLS/

# Search for ec.py imports
grep -r "from ec import" --include="*.py" MLS/
grep -r "import ec" --include="*.py" MLS/

# Search for cam.py imports
grep -r "from cam import" --include="*.py" MLS/
grep -r "import cam" --include="*.py" MLS/

# Search for Raman_board.py imports
grep -r "from Raman_board import" --include="*.py" MLS/
grep -r "import Raman_board" --include="*.py" MLS/

# Search for secularsweep.py imports
grep -r "from secularsweep import" --include="*.py" MLS/
grep -r "import secularsweep" --include="*.py" MLS/
```

---

## Phase 4: Execution Steps

### Step 1: Create Backup Branch
```bash
git checkout -b naming-conventions-migration
git push -u origin naming-conventions-migration
```

### Step 2: Rename Files (with git mv)
```bash
# Rename comp.py
git mv MLS/artiq/fragments/comp.py MLS/artiq/fragments/compensation.py

# Rename ec.py
git mv MLS/artiq/fragments/ec.py MLS/artiq/fragments/endcaps.py

# Rename cam.py
git mv MLS/artiq/fragments/cam.py MLS/artiq/fragments/camera.py

# Rename Raman_board.py
git mv MLS/artiq/fragments/Raman_board.py MLS/artiq/fragments/raman_board.py

# Rename secularsweep.py
git mv MLS/artiq/fragments/secularsweep.py MLS/artiq/fragments/secular_sweep.py
```

### Step 3: Update Imports
Edit `MLS/artiq/experiments/trap_controler.py`:
```python
# OLD:
from comp import Compensation
from ec import EndCaps

# NEW:
from compensation import Compensation
from endcaps import EndCaps
```

Search and update any other files with imports to renamed modules.

### Step 4: Test
```bash
# Run Python syntax check
python -m py_compile MLS/artiq/experiments/trap_controler.py

# Run tests if available
pytest MLS/tests/ -v
```

### Step 5: Commit
```bash
git add -A
git commit -m "refactor: standardize fragment file naming conventions

- Rename comp.py -> compensation.py
- Rename ec.py -> endcaps.py  
- Rename cam.py -> camera.py
- Rename Raman_board.py -> raman_board.py
- Rename secularsweep.py -> secular_sweep.py

Update all imports in dependent files.

Refs: NAMING_CONVENTIONS.md"
```

---

## Phase 5: Post-Migration Verification

### Verification Checklist

- [ ] All renamed files exist at new paths
- [ ] No files exist at old paths
- [ ] All imports updated
- [ ] `trap_controler.py` runs without ImportError
- [ ] No broken references in documentation
- [ ] Tests pass

### Files to Verify Post-Rename

1. `MLS/artiq/fragments/compensation.py` exists
2. `MLS/artiq/fragments/comp.py` does NOT exist
3. `MLS/artiq/fragments/endcaps.py` exists
4. `MLS/artiq/fragments/ec.py` does NOT exist
5. `MLS/artiq/fragments/camera.py` exists
6. `MLS/artiq/fragments/cam.py` does NOT exist
7. `MLS/artiq/fragments/raman_board.py` exists
8. `MLS/artiq/fragments/Raman_board.py` does NOT exist
9. `MLS/artiq/fragments/secular_sweep.py` exists
10. `MLS/artiq/fragments/secularsweep.py` does NOT exist

---

## Phase 6: Rollback Plan

If issues arise post-migration:

```bash
# Revert commits
git revert HEAD

# Or reset to before migration
git checkout main
git branch -D naming-conventions-migration
```

Ensure all team members are notified before rollback to avoid conflicts.
