# MLS Directory Cleanup Plan

**Date:** 2026-02-02  
**Purpose:** Remove legacy, duplicate, and cache files to clean up the MLS directory structure

---

## 1. PYTHON CACHE FILES (Safe to Remove)

### __pycache__ Directories (11 directories, ~39 .pyc files)
These are automatically generated Python bytecode cache directories that will be regenerated as needed.

| Directory | File Count |
|-----------|------------|
| `MLS\artiq\experiments\__pycache__` | 1 .pyc file |
| `MLS\config\schemas\__pycache__` | 2 .pyc files |
| `MLS\core\__pycache__` | 6 .pyc files |
| `MLS\server\analysis\eigenmodes\__pycache__` | 1 .pyc file |
| `MLS\server\applet\__pycache__` | 5 .pyc files |
| `MLS\server\applet\experiments\__pycache__` | 6 .pyc files |
| `MLS\server\cam\__pycache__` | 5 .pyc files |
| `MLS\server\communications\__pycache__` | 2 .pyc files |
| `MLS\server\optimizer\__pycache__` | 8 .pyc files |
| `MLS\src\applet\controllers\__pycache__` | 2 .pyc files |
| `MLS\src\optimizer\flask_optimizer\__pycache__` | 1 .pyc file |

### .pytest_cache Directory
| Directory | Contents |
|-----------|----------|
| `MLS\.pytest_cache` | pytest cache files (lastfailed, nodeids, README.md, CACHEDIR.TAG, .gitignore) |

**Action:** Delete all above directories

---

## 2. ARCHIVE/BACKUP FILES

### Image Handler Archive (to be moved/removed)
Located in: `MLS\src\hardware\camera\archive\`

| File | Description | Action |
|------|-------------|--------|
| `image_handler_optimized.py` | Optimized version of image handler | Move to `MLS\archive\legacy\` or delete |
| `image_handler_original.py` | Original version of image handler | Move to `MLS\archive\legacy\` or delete |

**Note:** These appear to be superseded by `MLS\src\hardware\camera\image_handler.py`

### Backup Files (.bak) to Remove

| File | Description | Action |
|------|-------------|--------|
| `MLS\config\parallel_config.yaml.bak` | Old parallel config (migrated to services.yaml) | Delete |
| `MLS\config\settings.yaml.bak` | Old settings (migrated to base.yaml) | Delete |

---

## 3. DUPLICATE/LEGACY FILES ANALYSIS

### Camera Code Structure
The camera functionality exists in two locations:

**Primary Location (Active):** `MLS\src\hardware\camera\`
- `camera_client.py`, `camera_logic.py`, `camera_recording.py`
- `camera_server.py`, `dcam.py`, `dcamapi4.py`, `dcamcon.py`
- `dcimgnp.py`, `image_handler.py`, `__init__.py`, `README.md`

**Secondary Location (Legacy/Empty):** `MLS\server\cam\`
- Contains ONLY `__pycache__` (no Python source files)
- **Action:** Safe to remove the entire `__pycache__` directory after contents review

### Utils Files (Keep - Not Duplicates)
Located in: `MLS\src\hardware\camera\utils\`

| File | Purpose | Status |
|------|---------|--------|
| `calculate_exposure.py` | Exposure calculation utility for Hamamatsu camera | **KEEP** - Unique utility |
| `dcamcon_live_capturing.py` | Sample script for live capture | **KEEP** - Development tool |
| `dcam_live_capturing.py` | Live capture script | **KEEP** - Development tool |
| `screeninfo.py` | Monitor info utility | **KEEP** - Helper utility |
| `triggered_dcimg_capturing.py` | DCIMG capture script | **KEEP** - Specialized tool |

**Note:** These utility files provide specific camera control functionality and should be preserved.

---

## 4. OLD CONFIG FILES (Verified - Can Remove)

After confirming the new config structure is working:

**Current Config Files (New Structure):**
- `MLS\config\base.yaml` - Base network and paths configuration
- `MLS\config\hardware.yaml` - Hardware-specific settings
- `MLS\config\services.yaml` - Service orchestration configuration
- `MLS\config\README.md` - Configuration documentation

**Legacy Files to Remove:**
| File | Replacement | Status |
|------|-------------|--------|
| `settings.yaml` | `base.yaml` | Already migrated, no longer exists |
| `parallel_config.yaml` | `services.yaml` | Already migrated, no longer exists |
| `settings.yaml.bak` | N/A | Delete (backup of old config) |
| `parallel_config.yaml.bak` | N/A | Delete (backup of old config) |

**Note:** The old YAML files were already removed in a previous cleanup. Only the `.bak` files remain.

---

## 5. EMPTY DIRECTORIES AFTER CLEANUP

The following directories will be empty after file removal and can be removed:

| Directory | Reason |
|-----------|--------|
| `MLS\src\hardware\camera\archive\` | After archive files moved |
| `MLS\.pytest_cache\` | After cache cleared |

**Note:** The following data directories are intentionally empty (runtime data folders):
- `MLS\data\cam_sweep_result\`
- `MLS\data\experiments\`
- `MLS\data\telemetry\`
- `MLS\data\camera\raw_frames\`
- `MLS\artiq\fragments\`
- Various test output directories

**Action:** Keep data directories, only remove `archive\` if empty

---

## 6. CLEANUP COMMANDS

### PowerShell Commands for Cleanup

```powershell
# 1. Remove all __pycache__ directories
Get-ChildItem -Path "MLS" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# 2. Remove .pytest_cache directory
Remove-Item -Path "MLS\.pytest_cache" -Recurse -Force

# 3. Create archive directory and move legacy files
New-Item -Path "MLS\archive\legacy" -ItemType Directory -Force
Move-Item -Path "MLS\src\hardware\camera\archive\image_handler_optimized.py" -Destination "MLS\archive\legacy\" -Force
Move-Item -Path "MLS\src\hardware\camera\archive\image_handler_original.py" -Destination "MLS\archive\legacy\" -Force

# 4. Remove old backup files
Remove-Item -Path "MLS\config\parallel_config.yaml.bak" -Force
Remove-Item -Path "MLS\config\settings.yaml.bak" -Force

# 5. Remove empty archive directory
Remove-Item -Path "MLS\src\hardware\camera\archive" -Force

# 6. Verify no .pyc files remain
Get-ChildItem -Path "MLS" -Filter "*.pyc" -Recurse
```

### Alternative: Batch Commands (cmd.exe)

```batch
REM 1. Remove all __pycache__ directories
for /f "delims=" %d in ('dir /s /b /ad MLS\__pycache__ 2^>nul') do @rmdir /s /q "%d"

REM 2. Remove .pytest_cache
rmdir /s /q MLS\.pytest_cache

REM 3. Create archive and move legacy files
mkdir MLS\archive\legacy 2>nul
move MLS\src\hardware\camera\archive\*.py MLS\archive\legacy\

REM 4. Remove backup files
del /f MLS\config\*.bak

REM 5. Remove empty archive directory
rmdir /q MLS\src\hardware\camera\archive
```

---

## 7. SUMMARY OF REMOVALS

### To Be Deleted (11 directories + 4 files)

**Directories:**
1. `MLS\.pytest_cache\`
2. `MLS\artiq\experiments\__pycache__`
3. `MLS\config\schemas\__pycache__`
4. `MLS\core\__pycache__`
5. `MLS\server\analysis\eigenmodes\__pycache__`
6. `MLS\server\applet\__pycache__`
7. `MLS\server\applet\experiments\__pycache__`
8. `MLS\server\cam\__pycache__`
9. `MLS\server\communications\__pycache__`
10. `MLS\server\optimizer\__pycache__`
11. `MLS\src\applet\controllers\__pycache__`
12. `MLS\src\hardware\camera\archive\`
13. `MLS\src\optimizer\flask_optimizer\__pycache__`

**Files:**
1. `MLS\config\parallel_config.yaml.bak` (173 lines)
2. `MLS\config\settings.yaml.bak` (289 lines)

**Files to Move to Archive:**
1. `MLS\src\hardware\camera\archive\image_handler_optimized.py` → `MLS\archive\legacy\`
2. `MLS\src\hardware\camera\archive\image_handler_original.py` → `MLS\archive\legacy\`

---

## 8. POST-CLEANUP VERIFICATION

Run these commands after cleanup to verify:

```powershell
# Check for remaining __pycache__ directories
Get-ChildItem -Path "MLS" -Recurse -Directory -Filter "__pycache__"

# Check for remaining .bak files
Get-ChildItem -Path "MLS" -Recurse -Filter "*.bak"

# Check for remaining .pyc files
Get-ChildItem -Path "MLS" -Recurse -Filter "*.pyc"

# Check for remaining archive directories outside MLS\archive
Get-ChildItem -Path "MLS" -Recurse -Directory -Filter "archive" | Where-Object { $_.FullName -notlike "*MLS\archive*" }
```

---

## 9. SAFETY NOTES

⚠️ **IMPORTANT:** This plan identifies files for removal but does NOT actually delete anything.  
Before executing the cleanup:

1. **Backup** the entire MLS directory
2. **Review** this plan with the team
3. **Test** the cleanup on a copy first
4. **Verify** the system still works after cleanup
5. **Document** any issues encountered

### Files NOT to Remove (Preserved)

These files/directories should remain intact:

- `MLS\src\hardware\camera\utils\*` - Active utility scripts
- `MLS\src\hardware\camera\image_handler.py` - Current image handler (supersedes archived versions)
- `MLS\server\cam\` - Directory itself (may be used for future code)
- All `MLS\config\*.yaml` (except .bak files)
- All runtime data directories (`MLS\data\*`)

---

## 10. ESTIMATED SPACE SAVINGS

| Category | Estimated Size |
|----------|----------------|
| __pycache__ directories | ~500 KB - 1 MB |
| .pytest_cache | ~5 KB |
| Archive files (to be moved) | ~50 KB |
| Backup files | ~10 KB |
| **Total** | **~600 KB - 1.1 MB** |

---

*Generated by: MLS Cleanup Analysis*  
*Status: READY FOR REVIEW*
