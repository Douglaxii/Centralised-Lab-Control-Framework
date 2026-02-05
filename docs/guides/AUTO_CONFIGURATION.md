# Automatic Configuration Guide

**Date:** 2026-02-05  
**Purpose:** Guide for automatic environment detection and path configuration

---

## Overview

MLS now supports **automatic environment detection** and **path configuration**. The system can automatically:

1. Detect if running on development (laptop) or production (manager PC)
2. Configure appropriate paths based on detected drives
3. Create necessary directories on startup
4. Support environment variable substitution in paths

---

## Quick Start

### Automatic Setup (Recommended)

```bash
# Auto-detect environment and configure
python scripts/setup/auto_config.py

# Or use the batch file (Windows)
scripts\windows\setup_environment.bat
```

### Force Specific Environment

```bash
# Force development mode
python scripts/setup/auto_config.py --dev

# Force production mode
python scripts/setup/auto_config.py --prod

# Or using batch files
scripts\windows\setup_environment.bat --dev
scripts\windows\setup_environment.bat --prod
```

### Check Current Setup

```bash
# Validate current configuration
python scripts/setup/auto_config.py --check
```

---

## Environment Detection

The system automatically detects the environment using the following priority:

| Priority | Method | Detection |
|----------|--------|-----------|
| 1 | `MLS_ENV` environment variable | Explicit setting |
| 2 | Hostname | `manager`, `lab-pc`, `server` = production |
| 3 | Network drives | `Y:` and `E:` exist = production |
| 4 | IP address | `134.99.x.x` = production |
| 5 | Default | Development |

### Setting Environment Variable

**Windows:**
```cmd
set MLS_ENV=development
python -m src.launcher

set MLS_ENV=production
python -m src.launcher
```

**PowerShell:**
```powershell
$env:MLS_ENV="production"
python -m src.launcher
```

**Linux/Mac:**
```bash
export MLS_ENV=production
python -m src.launcher
```

---

## Path Configuration

### Auto-Generated Paths

Based on detected environment, paths are automatically configured:

**Development (Laptop):**
```yaml
paths:
  output_base: "./data"
  jpg_frames: "./data/jpg_frames"
  ion_data: "./data/ion_data"
  # ... all relative to project root
```

**Production (Manager PC):**
```yaml
paths:
  output_base: "Y:/Xi/Data"      # Network share
  jpg_frames: "E:/data/jpg_frames"  # Local fast storage
  ion_data: "E:/data/ion_data"
  # ... split between network and local
```

### Environment Variable Substitution

You can use environment variables in `config.yaml`:

```yaml
paths:
  # Windows style
  output_base: "%MLS_DATA_PATH%/data"
  
  # Unix style
  jpg_frames: "$TEMP/frames"
  
  # Brace style
  ion_data: "${HOME}/mls/data"
```

**Setting custom data path:**
```cmd
set MLS_DATA_PATH=D:/mls_data
python -m src.launcher
```

---

## Directory Auto-Creation

On startup, the launcher automatically creates these directories if they don't exist:

```
./data/
./data/jpg_frames
./data/jpg_frames_labelled
./data/ion_data
./data/ion_uncertainty
./data/camera/settings
./data/camera/dcimg
./data/camera/live_frames
./data/experiments
./data/analysis/results
./data/debug
./logs
./logs/server
```

### Disabling Auto-Creation

To disable auto-creation, set the environment variable:
```cmd
set MLS_NO_AUTO_CREATE=1
```

---

## Drive Detection

The system automatically detects available drives:

```bash
python -c "from core.config.auto_setup import get_drive_options; print(get_drive_options())"
```

Example output:
```python
{
    'data': ['Y:/Xi/Data', 'E:/data'],
    'network': ['Y:/'],
    'local_fast': ['E:/', 'C:/']
}
```

### Custom Drive Configuration

If your network drives use different letters, set environment variables:

```cmd
set MLS_NETWORK_DRIVE=Z:
set MLS_LOCAL_DRIVE=D:
```

Then in `config.yaml`:
```yaml
paths:
  output_base: "%MLS_NETWORK_DRIVE%/Xi/Data"
  jpg_frames: "%MLS_LOCAL_DRIVE%/data/jpg_frames"
```

---

## Manual Configuration

If automatic detection doesn't work for your setup, manually edit `config/config.yaml`:

```yaml
environment: production  # Force production mode

profiles:
  production:
    paths:
      output_base: "Z:/Custom/Path"  # Your custom path
      jpg_frames: "D:/frames"
      # ... etc
```

---

## Troubleshooting

### Environment Not Detected Correctly

Check what the system detects:
```bash
python scripts/setup/auto_config.py --check
```

Override with environment variable:
```cmd
set MLS_ENV=production
```

### Paths Not Created

Check directory permissions:
```python
python -c "
from pathlib import Path
from core.config.auto_setup import ensure_directories
created = ensure_directories()
print(f'Created: {created}')
"
```

### Network Drive Not Found

Verify drive is mapped:
```cmd
net use
```

Map drive if needed:
```cmd
net use Y: \\server\share
```

### Environment Variables Not Substituting

Check variable is set:
```cmd
echo %MLS_DATA_PATH%
```

Test substitution:
```python
python -c "
import os
from core.config.auto_setup import substitute_env_vars
config = {'path': '%MLS_DATA_PATH%/data'}
result = substitute_env_vars(config)
print(result)
"
```

---

## Configuration Precedence

Configuration is loaded in this order (later overrides earlier):

1. **Default config** (`config/config.yaml`)
2. **Environment substitution** (replace `$VAR` with values)
3. **Environment variable `MLS_ENV`** (select profile)
4. **Profile selection** (development/production)
5. **Auto-path generation** (if paths not set)
6. **Directory creation** (ensure paths exist)

---

## API Reference

### Python Functions

```python
from core.config.auto_setup import (
    setup_environment,      # Full setup
    detect_environment,     # Just detect
    ensure_directories,     # Just create dirs
    validate_setup,         # Check setup
    get_auto_paths,         # Get path dict
    substitute_env_vars,    # Replace env vars
)

# One-call setup
from core.config.auto_setup import auto_configure
auto_configure()
```

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `MLS_ENV` | Force environment | `development` or `production` |
| `MLS_DATA_PATH` | Custom data root | `D:/mls_data` |
| `MLS_NETWORK_DRIVE` | Network drive letter | `Y:` |
| `MLS_LOCAL_DRIVE` | Local fast drive | `E:` |
| `MLS_NO_AUTO_CREATE` | Disable dir creation | `1` |

---

## Examples

### Example 1: Laptop Development

```bash
# No setup needed - auto-detected as development
python -m src.launcher

# Or explicitly
set MLS_ENV=development
python -m src.launcher
```

### Example 2: Manager PC with Standard Drives

```bash
# Auto-detected as production (Y: and E: exist)
python -m src.launcher

# Or explicitly
set MLS_ENV=production
python -m src.launcher
```

### Example 3: Custom Data Location

```bash
# Use D drive for all data
set MLS_DATA_PATH=D:/mls_experiment
python scripts/setup/auto_config.py
python -m src.launcher
```

### Example 4: Temporary Frames Location

```yaml
# config.yaml
paths:
  jpg_frames: "$TEMP/mls_frames"
```

```bash
set TEMP=C:/Temp
python -m src.launcher
```

---

**Last Updated:** 2026-02-05
