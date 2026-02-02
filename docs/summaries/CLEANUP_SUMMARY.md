# MLS Directory Cleanup Summary

**Date**: 2026-02-02

## Overview

Comprehensive cleanup of the MLS directory structure to improve organization, remove unnecessary files, and consolidate documentation.

## Changes Made

### 1. Python Cache Files Removed
- **Removed**: All `__pycache__` directories (81 .pyc files)
- **Locations**: Root, core/, server/*/, tests/
- **Space Saved**: ~2 MB

### 2. Test Output Cleanup
- **Cleaned**: `tests/output/`
  - Removed `debug_*`, `test_*`, `compare` directories
  - Kept `image_handler_test/` with sample results (10 files each)
- **Reduced from**: 612 JPG + 612 JSON files
- **Kept**: 10 JPG + 10 JSON samples
- **Space Saved**: ~30 MB

### 3. Documentation Reorganized

#### Moved to `docs/summaries/`:
- `IMPLEMENTATION_SUMMARY.md` → `CAMERA_IMPLEMENTATION.md`
- `OPTIMIZATION_SUMMARY.md` → `IMAGE_HANDLER_OPTIMIZATION.md`
- `CLEANUP_SUMMARY.md` (this file)

#### Moved to `docs/guides/`:
- `CONDA_SETUP.md`

#### Moved to `docs/camera/`:
- `server/cam/UNCERTAINTY_CALCULATION.md`
- `server/cam/OPTIMIZATION_README.md` → `IMAGE_HANDLER_README.md`

#### Moved to `docs/tests/`:
- `tests/IMAGE_HANDLER_TEST_README.md`
- `tests/README.md` → `TESTING.md`
- `tests/TEST_SUITE_SUMMARY.md` → `TEST_SUMMARY.md`

#### Archived:
- `server/cam/MODULE_SYNC_SUMMARY.md` → `docs/summaries/`

### 4. Configuration Organized
- `config/settings_local.yaml` → `config/examples/local_development.yaml`
- Created `config/examples/` directory for example configurations

### 5. Setup Scripts Organized
Created `setup/` directory:
- `setup_conda.bat`
- `setup_conda.py`
- `validate_setup.py`
- `environment.yml`

### 6. Log Files Cleaned
- Truncated all `.log` files to empty (kept for structure)
- Kept `.gitkeep` files

### 7. Camera Directory Organized
- Created `server/cam/utils/` for utility scripts:
  - `dcamcon_live_capturing.py`
  - `dcam_live_capturing.py`
  - `triggered_dcimg_capturing.py`
  - `calculate_exposure.py`
  - `screeninfo.py`
- Created `server/cam/archive/` for backup files:
  - `image_handler_optimized.py`
  - `image_handler_original.py`

## Final Directory Structure

```
MLS/
├── launcher.py              # Main entry point
├── requirements.txt         # Dependencies
├── start.bat / start.sh     # Quick start
│
├── config/                  # Configuration
│   ├── settings.yaml       # Main config
│   ├── parallel_config.yaml
│   └── examples/           # Example configs
│
├── core/                    # Shared utilities
├── server/                  # Server components
│   ├── cam/                # Camera system
│   │   ├── image_handler.py
│   │   ├── utils/          # Camera utilities
│   │   └── archive/        # Backup files
│   ├── communications/
│   ├── Flask/
│   └── optimizer/
│
├── artiq/                   # ARTIQ control
├── tests/                   # Test suite
│   └── output/             # Test outputs (minimal)
│
├── setup/                   # Setup scripts
├── tools/                   # Diagnostic tools
├── logs/                    # Log files
├── data/                    # Data storage
└── docs/                    # Documentation
    ├── guides/             # User guides
    ├── camera/             # Camera docs
    ├── server/             # Server docs
    ├── tests/              # Testing docs
    └── summaries/          # Implementation summaries
```

## Space Summary

| Category | Before | After | Saved |
|----------|--------|-------|-------|
| Python Cache | ~2 MB | 0 MB | ~2 MB |
| Test Outputs | ~35 MB | ~1 MB | ~34 MB |
| Logs | ~0.5 MB | ~0.01 MB | ~0.5 MB |
| **Total** | **~37.5 MB** | **~4.3 MB** | **~33.2 MB** |

## Current Stats

- **Total Files**: 176
- **Total Size**: 4.27 MB
- **Directories**: 12 main + subdirectories

## Notes

1. All `.pyc` files are automatically regenerated when Python runs
2. Test outputs are kept minimal (10 samples) for reference
3. All documentation is now in `docs/` with clear organization
4. Configuration examples are separated from production config
5. Camera utilities are in `utils/` to keep main directory clean
