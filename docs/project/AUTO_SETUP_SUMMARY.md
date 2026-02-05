# Automatic Path Setup - Implementation Summary

**Date:** 2026-02-05  
**Status:** ✅ Implemented

---

## What Was Implemented

### 1. **Auto-Detection System** (`src/core/config/auto_setup.py`)

Automatically detects whether running on **development** (laptop) or **production** (manager PC):

| Detection Method | Development | Production |
|-----------------|-------------|------------|
| `MLS_ENV` env var | `development` | `production` |
| Hostname | Anything else | `manager`, `lab-pc`, `server` |
| Network drives | Not checked | `Y:` and `E:` exist |
| IP address | Not 134.99.x.x | `134.99.x.x` |

### 2. **Auto-Generated Paths**

**Development:**
```yaml
paths:
  output_base: "./data"              # Local project folder
  jpg_frames: "./data/jpg_frames"
  ion_data: "./data/ion_data"
  # All paths relative to project root
```

**Production:**
```yaml
paths:
  output_base: "Y:/Xi/Data"          # Network share
  jpg_frames: "E:/data/jpg_frames"   # Local fast storage
  ion_data: "E:/data/ion_data"
  # Split between network and local for performance
```

### 3. **Directory Auto-Creation**

On startup, automatically creates:
- `./data/` and all subdirectories
- `./logs/` and subdirectories
- Camera frame directories
- Analysis output directories

### 4. **Environment Variable Support**

Supports substitution in config.yaml:
```yaml
paths:
  output_base: "${MLS_DATA_PATH}/data"
  jpg_frames: "$TEMP/frames"
  ion_data: "%LOCALAPPDATA%/mls/ion_data"
```

---

## Files Created/Modified

### New Files

| File | Purpose |
|------|---------|
| `src/core/config/auto_setup.py` | Core auto-setup functionality |
| `scripts/setup/auto_config.py` | Setup/validation script |
| `scripts/windows/setup_environment.bat` | Windows batch wrapper |
| `docs/guides/AUTO_CONFIGURATION.md` | User documentation |

### Modified Files

| File | Changes |
|------|---------|
| `src/core/config/config.py` | Added `_auto_setup_paths()` method |
| `src/launcher.py` | Integrated auto-setup on startup |
| `config/config.yaml` | Added documentation headers |
| `README.md` | Updated quick start instructions |

---

## Usage

### For Users

```bash
# First time setup
python scripts/setup/auto_config.py

# Start the system (auto-setup runs automatically)
python -m src.launcher
```

### For Developers

```python
from core.config.auto_setup import auto_configure

# One-call setup
info, created_dirs = auto_configure()

# Individual functions
env = detect_environment()           # 'development' or 'production'
paths = get_auto_paths(env)          # Get path dict
ensure_directories()                 # Create all dirs
```

---

## Key Features

### ✅ Automatic Environment Detection
No need to manually edit config files when switching between laptop and lab PC.

### ✅ Smart Path Configuration
- **Development:** All paths local to project
- **Production:** Network paths for shared data, local paths for fast I/O

### ✅ Directory Auto-Creation
Directories are created on startup - no manual setup needed.

### ✅ Environment Variable Substitution
Use `$VAR`, `${VAR}`, or `%VAR%` in config.yaml paths.

### ✅ Drive Detection
Automatically finds available network and local drives.

### ✅ Backward Compatible
Existing manual configuration still works. Auto-setup only fills in missing pieces.

---

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `MLS_ENV` | Force environment mode | `development` or `production` |
| `MLS_DATA_PATH` | Custom data root | `D:/mls_data` |
| `MLS_NETWORK_DRIVE` | Network drive letter | `Y:` |
| `MLS_LOCAL_DRIVE` | Local fast drive | `E:` |
| `MLS_NO_AUTO_CREATE` | Disable auto-creation | `1` |

---

## Testing

Run the setup script to test:

```bash
# Check current setup
python scripts/setup/auto_config.py --check

# Force development mode
python scripts/setup/auto_config.py --dev

# Force production mode
python scripts/setup/auto_config.py --prod
```

Expected output on development (laptop):
```
Environment: development
Hostname: YOUR_LAPTOP
IP Address: 192.168.x.x or 10.x.x.x
Created directories: ./data, ./logs, ...
```

Expected output on production (manager PC):
```
Environment: production
Hostname: manager or lab-pc
IP Address: 134.99.x.x
Created directories: Y:/Xi/Data/..., E:/data/...
```

---

## Migration Guide

### From Old Manual Setup

**Before:**
1. Edit `config.yaml` to set environment
2. Edit paths for your machine
3. Manually create directories
4. Start launcher

**After:**
1. Run `python scripts/setup/auto_config.py` (once)
2. Start launcher

That's it! Environment and paths are auto-detected.

### Override Auto-Detection

If auto-detection doesn't work for your setup:

```bash
# Force specific environment
set MLS_ENV=production

# Or edit config.yaml
environment: production  # Force this profile
```

---

**Last Updated:** 2026-02-05
