# MLS Reorganization Migration Guide

**Version:** 1.0  
**Last Updated:** 2026-02-02  
**Status:** Complete

---

## Table of Contents

1. [Overview](#1-overview)
2. [Directory Structure Changes](#2-directory-structure-changes)
3. [Configuration Migration](#3-configuration-migration)
4. [Import Path Changes](#4-import-path-changes)
5. [File Renames](#5-file-renames)
6. [Script Updates](#6-script-updates)
7. [Step-by-Step Migration](#7-step-by-step-migration)
8. [Troubleshooting](#8-troubleshooting)
9. [Quick Reference](#9-quick-reference)

---

## 1. Overview

### What Changed and Why

The MLS codebase has undergone a major reorganization to improve maintainability, modularity, and clarity:

| Aspect | Before | After |
|--------|--------|-------|
| **Structure** | Flat, mixed-purpose directories | Clean modular architecture (`src/`, `docs/`, `config/`)
| **Configuration** | Single `settings.yaml` | Split into `base.yaml` + `hardware.yaml` + environments |
| **Code Organization** | Mixed in root and subdirectories | All code organized under `src/` |
| **Documentation** | Scattered README files | Structured under `docs/` with clear hierarchy |
| **File Naming** | Inconsistent (`comp.py`, `ec.py`, `Raman_board.py`) | Standardized (`compensation.py`, `endcaps.py`, `raman_board.py`) |

### Benefits of the New Structure

- **Clear Separation of Concerns**: Core, hardware, server, and analysis code are now isolated
- **Easier Configuration Management**: Environment-specific configs can override base settings
- **Better Documentation**: All docs organized by purpose (guides, API, architecture)
- **Consistent Naming**: All files follow `lowercase_with_underscores.py` convention
- **Simplified Imports**: Clear package structure makes imports more intuitive

### Breaking vs Non-Breaking Changes

| Change Type | Breaking | Description |
|-------------|----------|-------------|
| **Directory Structure** | ❌ No | Old imports still work during transition |
| **Configuration Format** | ⚠️ Partial | Old `settings.yaml` still works but deprecated |
| **File Renames** | ✅ Yes | Import statements must be updated |
| **Import Paths** | ✅ Yes | Some modules moved to `src/` subpackages |
| **Data Paths** | ⚠️ Partial | New `E:/Data` standard; old paths still supported |

---

## 2. Directory Structure Changes

### Old → New Path Mapping

```
MLS/                              MLS/
├── artiq/                        ├── artiq/                    # ARTIQ-specific (unchanged)
│   ├── experiments/              │   └── experiments/
│   └── fragments/                │
├── server/                       ├── src/                      # NEW: All source code
│   ├── communications/           │   ├── core/                 # NEW: Core utilities
│   ├── Flask/                    │   │   ├── config/
│   └── cam/                      │   │   ├── exceptions/
│                                 │   │   ├── logging/
│                                 │   │   └── utils/
├── core/                         │   ├── hardware/             # NEW: Hardware interfaces
│   ├── config.py                 │   │   ├── artiq/
│   ├── enums.py                  │   │   ├── camera/
│   ├── exceptions.py             │   │   └── labview/
│   ├── experiment.py             │   │
│   ├── logger.py                 │   ├── server/               # MOVED: From server/
│   └── zmq_utils.py              │   │   ├── api/              # Was: server/Flask/
│                                 │   │   ├── comms/            # Was: server/communications/
│                                 │   │   └── manager/          # Was: server/communications/
├── optimizer/                    │   │
│   └── ...                       │   ├── optimizer/            # MOVED: From optimizer/
│                                 │   │   └── flask_optimizer/
├── tests/                        │   │
│   └── ...                       │   ├── analysis/             # NEW: Analysis code
│                                 │   └── applet/               # NEW: Applet controllers
├── logs/                         │
│   ├── camera.log                ├── config/                   # NEW: Configuration
│   ├── manager.log               │   ├── base.yaml             # Core settings
│   └── ...                       │   ├── hardware.yaml         # Hardware config
│                                 │   ├── services.yaml         # Service definitions
│                                 │   ├── environments/         # Environment overrides
│                                 │   ├── examples/             # Example configs
│                                 │   └── schemas/              # Config schemas
├── config/                       │
│   ├── settings.yaml             ├── docs/                     # NEW: Documentation
│   └── parallel_config.yaml      │   ├── api/
│                                 │   ├── architecture/
│                                 │   ├── camera/
│                                 │   ├── development/
│                                 │   ├── guides/
│                                 │   ├── hardware/
│                                 │   ├── reference/
│                                 │   ├── server/
│                                 │   ├── summaries/
│                                 │   └── tests/
│                                 │
├── README.md                     ├── data/                     # NEW: Data directory
├── CONDA_SETUP.md                │   ├── camera/
├── CAMERA_IMPLEMENTATION.md      │   ├── experiments/
│                                 │   └── telemetry/
└── ...                           │
                                  ├── logs/                     # Streamlined
                                  │   └── server/
                                  │
                                  ├── scripts/                  # NEW: Platform scripts
                                  │   ├── linux/
                                  │   └── windows/
                                  │
                                  ├── setup/                    # MOVED: Setup files
                                  │   ├── environment.yml
                                  │   ├── setup_conda.bat
                                  │   └── validate_setup.py
                                  │
                                  ├── tests/                    # Preserved
                                  ├── tools/                    # NEW: Admin tools
                                  ├── requirements.txt
                                  ├── pyproject.toml            # NEW: Modern Python packaging
                                  └── README.md
```

### What Moved Where

| Old Location | New Location | Notes |
|--------------|--------------|-------|
| `MLS/server/communications/manager.py` | `MLS/src/server/manager/manager.py` | Communication layer reorganized |
| `MLS/server/communications/labview_interface.py` | `MLS/src/server/comms/labview_interface.py` | Shortened module name |
| `MLS/server/communications/data_server.py` | `MLS/src/server/comms/data_server.py` | Shortened module name |
| `MLS/server/Flask/flask_server.py` | `MLS/src/server/api/flask_server.py` | Clearer API naming |
| `MLS/server/cam/` | `MLS/src/hardware/camera/` | Camera is hardware layer |
| `MLS/optimizer/` | `MLS/src/optimizer/` | Moved under src |
| `MLS/core/` | `MLS/src/core/` | Core utilities moved |
| `MLS/config/settings.yaml` | `MLS/config/base.yaml` | Renamed for clarity |
| `MLS/environment.yml` | `MLS/setup/environment.yml` | Setup files organized |
| `MLS/CONDA_SETUP.md` | `MLS/docs/guides/CONDA_SETUP.md` | Docs organized by type |
| `MLS/CAMERA_IMPLEMENTATION.md` | `MLS/docs/summaries/CAMERA_IMPLEMENTATION.md` | Summaries folder |

---

## 3. Configuration Migration

### Old `settings.yaml` → New `base.yaml`

The monolithic `settings.yaml` has been split into focused configuration files:

#### Migration Mapping

| Old File | New File | Purpose |
|----------|----------|---------|
| `config/settings.yaml` | `config/base.yaml` | Core network, paths, defaults |
| (hardware section) | `config/hardware.yaml` | Hardware-specific settings |
| (was parallel_config.yaml) | `config/services.yaml` | Service definitions |
| N/A | `config/environments/*.yaml` | Environment-specific overrides |

#### Key Configuration Changes

**1. Network Configuration** (unchanged structure):
```yaml
# OLD (settings.yaml)          # NEW (base.yaml)
network:                        network:
  master_ip: "134.99.120.40"      master_ip: "134.99.120.40"
  cmd_port: 5555                  cmd_port: 5555
  # ...                          # ...
```

**2. Paths Configuration** (mostly unchanged):
```yaml
# OLD (settings.yaml)          # NEW (base.yaml)
paths:                          paths:
  output_base: "E:/Data"          output_base: "E:/Data"
  camera_frames: "..."            camera_frames: "..."
  # ...                          # ...
```

**3. Hardware Settings** (moved to separate file):
```yaml
# OLD (settings.yaml - hardware section)
hardware:
  worker_defaults:
    ec1: 0.0
    ec2: 0.0
    # ...

# NEW (hardware.yaml - complete hardware config)
system:
  lab_name: "Ion Trap Lab"
  safety:
    max_rf_voltage: 250.0
    # ...

rf_system:
  frequency_mhz: 20.0
  voltage_scale:
    # ...
```

### How to Migrate Custom Configs

#### Step 1: Backup Current Config
```powershell
# Create backup of your current settings
copy D:\MLS\config\settings.yaml D:\MLS\config\settings.yaml.backup
```

#### Step 2: Create Environment-Specific Config
Instead of modifying `base.yaml`, create an environment override:

```powershell
# Create your environment config
New-Item D:\MLS\config\environments\local_development.yaml -Force
```

**Example: `config/environments/local_development.yaml`**
```yaml
# Override base settings for local development
network:
  master_ip: "127.0.0.1"  # Use localhost for testing

paths:
  output_base: "D:/TestData"  # Use local test directory

logging:
  level: "DEBUG"  # More verbose logging for development
```

#### Step 3: Update Config Loading Code

**OLD approach:**
```python
from core.config import load_config
config = load_config("config/settings.yaml")
```

**NEW approach:**
```python
from src.core.config.config import ConfigManager

# Loads base.yaml + hardware.yaml + environment override
config = ConfigManager()
config.load_environment("local_development")

# Access configuration
network_config = config.get_network()
paths_config = config.get_paths()
```

### Environment Variable Changes

| Old Variable | New Variable | Description |
|--------------|--------------|-------------|
| `MLS_CONFIG_PATH` | `MLS_CONFIG_DIR` | Directory containing configs |
| `MLS_SETTINGS_FILE` | `MLS_ENVIRONMENT` | Environment name to load |
| `MLS_LOG_LEVEL` | `MLS_LOG_LEVEL` | (unchanged) Logging level |
| N/A | `MLS_DATA_DIR` | Override data directory |

**Example: Setting environment variables (PowerShell)**
```powershell
# Set environment for current session
$env:MLS_CONFIG_DIR = "D:\MLS\config"
$env:MLS_ENVIRONMENT = "local_development"
$env:MLS_DATA_DIR = "D:\TestData"

# Or make them persistent (User scope)
[Environment]::SetEnvironmentVariable("MLS_ENVIRONMENT", "local_development", "User")
```

---

## 4. Import Path Changes

### Old Imports → New Imports

#### Core Module Imports

| Old Import | New Import | Status |
|------------|------------|--------|
| `from core.config import ...` | `from src.core.config import ...` | Update required |
| `from core.enums import ...` | `from src.core.utils.enums import ...` | Path changed |
| `from core.exceptions import ...` | `from src.core.exceptions import ...` | Update required |
| `from core.experiment import ...` | `from src.core.utils.experiment import ...` | Path changed |
| `from core.logger import ...` | `from src.core.logging import ...` | Path changed |
| `from core.zmq_utils import ...` | `from src.core.utils.zmq_utils import ...` | Path changed |

#### Server Module Imports

| Old Import | New Import | Status |
|------------|------------|--------|
| `from server.communications.manager import ...` | `from src.server.manager import ...` | Path changed |
| `from server.communications.labview_interface import ...` | `from src.server.comms import ...` | Module renamed |
| `from server.communications.data_server import ...` | `from src.server.comms import ...` | Module renamed |
| `from server.Flask.flask_server import ...` | `from src.server.api import ...` | Module renamed |

#### Hardware Module Imports

| Old Import | New Import | Status |
|------------|------------|--------|
| `from server.cam.camera_server import ...` | `from src.hardware.camera import ...` | Path changed |
| `from server.cam.image_handler import ...` | `from src.hardware.camera.image_handler import ...` | Path changed |

#### Optimizer Imports

| Old Import | New Import | Status |
|------------|------------|--------|
| `from optimizer.mobo import ...` | `from src.optimizer import ...` | (unchanged path under src) |
| `from optimizer.turbo import ...` | `from src.optimizer import ...` | (unchanged path under src) |

### Common Import Patterns

#### Pattern 1: Core Configuration
```python
# OLD
import sys
sys.path.insert(0, 'D:/MLS')
from core.config import load_config
from core.logger import setup_logger

# NEW
# Add src to path or use proper package installation
import sys
sys.path.insert(0, 'D:/MLS/src')
from core.config.config import ConfigManager
from core.logging.logger import setup_logger
```

#### Pattern 2: Manager Components
```python
# OLD
from server.communications.manager import ControlManager
from server.communications.labview_interface import LabVIEWInterface

# NEW
from server.manager.manager import ControlManager
from server.comms.labview_interface import LabVIEWInterface
```

#### Pattern 3: Camera Hardware
```python
# OLD
from server.cam.camera_server import CameraServer
from server.cam.image_handler import ImageHandler

# NEW
from hardware.camera.camera_server import CameraServer
from hardware.camera.image_handler import ImageHandler
```

#### Pattern 4: Utilities
```python
# OLD
from core.enums import u_rf_mv_to_U_rf_v
from core.zmq_utils import ZMQClient

# NEW
from core.utils.enums import u_rf_mv_to_U_rf_v
from core.utils.zmq_utils import ZMQClient
```

---

## 5. File Renames

### ARTIQ Fragment Renames

| Old Filename | New Filename | Import Update Required |
|--------------|--------------|------------------------|
| `comp.py` | `compensation.py` | ✅ Yes |
| `ec.py` | `endcaps.py` | ✅ Yes |
| `cam.py` | `camera.py` | ❌ No (no direct imports) |
| `Raman_board.py` | `raman_board.py` | ✅ Yes |
| `secularsweep.py` | `secular_sweep.py` | ✅ Yes |

### Detailed Migration for Each File

#### `comp.py` → `compensation.py`

**File location**: `artiq/fragments/` → `src/hardware/artiq/fragments/`

**Import changes**:
```python
# OLD (in artiq/experiments/trap_controler.py)
from comp import Compensation

# NEW
from compensation import Compensation
# Or if using full path:
from src.hardware.artiq.fragments.compensation import Compensation
```

**Fragment usage** (unchanged):
```python
# This stays the same
self.setattr_fragment("comp", Compensation)
```

#### `ec.py` → `endcaps.py`

**File location**: `artiq/fragments/` → `src/hardware/artiq/fragments/`

**Import changes**:
```python
# OLD
from ec import EndCaps

# NEW
from endcaps import EndCaps
```

**Fragment usage** (unchanged):
```python
# This stays the same
self.setattr_fragment("ec", EndCaps)
```

#### `cam.py` → `camera.py`

**File location**: `artiq/fragments/` → `src/hardware/artiq/fragments/`

**Note**: No direct import changes needed. The fragment is only used via `setattr_fragment`:
```python
# This usage pattern stays the same
self.setattr_fragment("camera", Camera)
```

#### `Raman_board.py` → `raman_board.py`

**File location**: `artiq/fragments/` → `src/hardware/artiq/fragments/`

**Import changes**:
```python
# OLD
from Raman_board import RamanCooling

# NEW
from raman_board import RamanCooling
```

#### `secularsweep.py` → `secular_sweep.py`

**File location**: `artiq/fragments/` → `src/hardware/artiq/fragments/`

**Import changes**:
```python
# OLD
from secularsweep import SecularSweep

# NEW
from secular_sweep import SecularSweep
```

### Batch Rename Commands

If you need to perform the renames manually (before git migration):

```powershell
# Navigate to fragments directory
cd D:\MLS\src\hardware\artiq\fragments

# Rename files (if they haven't been renamed yet)
Rename-Item comp.py compensation.py
Rename-Item ec.py endcaps.py
Rename-Item cam.py camera.py
Rename-Item Raman_board.py raman_board.py
Rename-Item secularsweep.py secular_sweep.py

# Using git mv (preferred for version control)
cd D:\MLS
git mv artiq/fragments/comp.py src/hardware/artiq/fragments/compensation.py
git mv artiq/fragments/ec.py src/hardware/artiq/fragments/endcaps.py
git mv artiq/fragments/cam.py src/hardware/artiq/fragments/camera.py
git mv artiq/fragments/Raman_board.py src/hardware/artiq/fragments/raman_board.py
git mv artiq/fragments/secularsweep.py src/hardware/artiq/fragments/secular_sweep.py
```

---

## 6. Script Updates

### Old Script Locations → New Locations

| Old Script | New Script | Change |
|------------|------------|--------|
| `start_servers.bat` | `scripts/windows/start_servers.bat` | Moved to platform folder |
| `setup_conda.bat` | `setup/setup_conda.bat` | Setup scripts organized |
| `validate_setup.py` | `setup/validate_setup.py` | Setup scripts organized |
| `launcher.py` | `src/launcher.py` | Main launcher moved |
| N/A | `scripts/windows/Start-LabControl.ps1` | NEW: PowerShell launcher |

### How to Update Batch/PowerShell Scripts

#### Environment Variable Setup (NEW)

Add to your PowerShell profile or scripts:

```powershell
# MLS Environment Setup
$env:MLS_ROOT = "D:\MLS"
$env:MLS_CONFIG_DIR = "$env:MLS_ROOT\config"
$env:MLS_DATA_DIR = "E:\Data"
$env:MLS_LOG_LEVEL = "INFO"
$env:MLS_ENVIRONMENT = "production"  # or "local_development"

# Python Path
$env:PYTHONPATH = "$env:MLS_ROOT\src;$env:PYTHONPATH"
```

#### Old Batch Script Pattern

```batch
@echo off
set MLS_ROOT=D:\MLS
set PYTHONPATH=%MLS_ROOT%;%PYTHONPATH%
cd %MLS_ROOT%
python server/communications/manager.py
```

#### New PowerShell Script Pattern

```powershell
#Requires -Version 5.1

# Setup environment
$env:MLS_ROOT = "D:\MLS"
$env:MLS_CONFIG_DIR = "$env:MLS_ROOT\config"
$env:MLS_ENVIRONMENT = "production"
$env:PYTHONPATH = "$env:MLS_ROOT\src"

# Import MLS module (NEW)
Import-Module "$env:MLS_ROOT\tools\ControlManager.psm1" -Force

# Start services using module functions
Start-ControlManager
Start-CameraServer
```

### Launching Components

#### OLD Way
```python
# From repository root
python server/communications/manager.py
python server/cam/camera_server.py
python server/Flask/flask_server.py
```

#### NEW Way
```python
# From repository root with src in PYTHONPATH
set PYTHONPATH=D:\MLS\src

python -m server.manager.manager
python -m hardware.camera.camera_server
python -m server.api.flask_server

# Or use the new launcher
python src/launcher.py --component manager
python src/launcher.py --component camera
python src/launcher.py --component flask
```

---

## 7. Step-by-Step Migration

### Pre-Migration Checklist

Before starting the migration, ensure you have:

- [ ] Full backup of your current MLS installation
- [ ] Backup of your `config/settings.yaml`
- [ ] Backup of any custom scripts or modifications
- [ ] Git access (to view diffs and revert if needed)
- [ ] Test environment to verify migration
- [ ] List of custom import statements in your code

#### Create Full Backup

```powershell
# Create backup directory
New-Item -ItemType Directory -Force -Path "D:\MLS_Backup_$(Get-Date -Format 'yyyyMMdd')"

# Copy entire MLS directory
robocopy D:\MLS "D:\MLS_Backup_$(Get-Date -Format 'yyyyMMdd')" /E /Z /R:3 /W:5 /XD .git __pycache__ .pytest_cache

# Or use git to create a checkpoint
cd D:\MLS
git add -A
git commit -m "PRE-MIGRATION: checkpoint before reorganization"
```

### Migration Steps (In Order)

#### Step 1: Update Repository

```powershell
cd D:\MLS
git fetch origin
git pull origin main
```

#### Step 2: Migrate Configuration

```powershell
# 1. Backup old config
copy D:\MLS\config\settings.yaml D:\MLS\config\settings.yaml.pre-migration

# 2. Review new config structure
Get-ChildItem D:\MLS\config

# 3. Create environment-specific config from your settings
# Copy example and customize
copy D:\MLS\config\examples\local_development_example.yaml D:\MLS\config\environments\my_lab.yaml

# 4. Edit my_lab.yaml with your specific settings
notepad D:\MLS\config\environments\my_lab.yaml
```

#### Step 3: Update Environment Variables

```powershell
# Set persistent environment variables
[Environment]::SetEnvironmentVariable("MLS_ROOT", "D:\MLS", "User")
[Environment]::SetEnvironmentVariable("MLS_CONFIG_DIR", "D:\MLS\config", "User")
[Environment]::SetEnvironmentVariable("MLS_ENVIRONMENT", "my_lab", "User")
[Environment]::SetEnvironmentVariable("MLS_DATA_DIR", "E:\Data", "User")

# Add to PYTHONPATH (prepend src)
$currentPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "User")
$newPythonPath = "D:\MLS\src;$currentPythonPath"
[Environment]::SetEnvironmentVariable("PYTHONPATH", $newPythonPath, "User")
```

#### Step 4: Update Import Statements

Search for files that need import updates:

```powershell
# Find files with old imports
grep -r "from core\." --include="*.py" D:\MLS\src\hardware\artiq\experiments
grep -r "from server\." --include="*.py" D:\MLS\src\hardware\artiq\experiments

# Update imports (example: trap_controler.py)
# OLD:
from comp import Compensation
from ec import EndCaps

# NEW:
from compensation import Compensation
from endcaps import EndCaps
```

#### Step 5: Verify File Renames

Ensure all fragment files have been renamed:

```powershell
# Check new files exist
Test-Path D:\MLS\src\hardware\artiq\fragments\compensation.py
Test-Path D:\MLS\src\hardware\artiq\fragments\endcaps.py
Test-Path D:\MLS\src\hardware\artiq\fragments\camera.py
Test-Path D:\MLS\src\hardware\artiq\fragments\raman_board.py
Test-Path D:\MLS\src\hardware\artiq\fragments\secular_sweep.py

# Check old files don't exist (should fail)
Test-Path D:\MLS\src\hardware\artiq\fragments\comp.py  # Should be False
Test-Path D:\MLS\src\hardware\artiq\fragments\ec.py     # Should be False
```

#### Step 6: Test Import Structure

```powershell
cd D:\MLS

# Test Python imports
python -c "
import sys
sys.path.insert(0, 'D:/MLS/src')
from core.config.config import ConfigManager
from core.utils.enums import u_rf_mv_to_U_rf_v
print('Core imports: OK')

from hardware.artiq.fragments.compensation import Compensation
from hardware.artiq.fragments.endcaps import EndCaps
print('Fragment imports: OK')

print('All imports successful!')
"
```

#### Step 7: Test Data Directory Setup

```powershell
# Run data directory setup
D:\setup_data_directory.bat

# Verify structure exists
Get-ChildItem E:\Data
```

#### Step 8: Start Services (Test Mode)

```powershell
# Import the MLS PowerShell module
Import-Module D:\MLS\tools\ControlManager.psm1 -Force

# Test configuration loading
Test-MLSConfig

# Start individual components in test mode
python D:\MLS\src\launcher.py --component manager --dry-run
```

### Post-Migration Verification

#### Verification Checklist

- [ ] Configuration loads without errors
- [ ] All import statements work
- [ ] Manager starts successfully
- [ ] Camera server starts successfully
- [ ] Flask server starts successfully
- [ ] LabVIEW interface connects
- [ ] Telemetry data flows correctly
- [ ] Experiment files can be loaded
- [ ] Custom scripts run without modification (or with documented changes)

#### Automated Verification Script

```powershell
# Save as: D:\MLS\verify_migration.ps1

$ErrorActionPreference = "Stop"
Write-Host "MLS Migration Verification" -ForegroundColor Green

# Test 1: Python path and imports
Write-Host "`n[1/5] Testing Python imports..." -ForegroundColor Yellow
try {
    $result = python -c "
import sys
sys.path.insert(0, 'D:/MLS/src')
from core.config.config import ConfigManager
from core.utils.enums import u_rf_mv_to_U_rf_v
print('SUCCESS: Core imports work')
" 2>&1
    Write-Host $result -ForegroundColor Green
} catch {
    Write-Host "FAILED: Core imports" -ForegroundColor Red
    exit 1
}

# Test 2: Configuration files exist
Write-Host "`n[2/5] Testing configuration files..." -ForegroundColor Yellow
$configs = @(
    "D:\MLS\config\base.yaml",
    "D:\MLS\config\hardware.yaml",
    "D:\MLS\config\services.yaml"
)
foreach ($config in $configs) {
    if (Test-Path $config) {
        Write-Host "  ✓ $config" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Missing: $config" -ForegroundColor Red
        exit 1
    }
}

# Test 3: Fragment files renamed
Write-Host "`n[3/5] Testing fragment file renames..." -ForegroundColor Yellow
$fragments = @(
    "compensation.py",
    "endcaps.py",
    "camera.py",
    "raman_board.py",
    "secular_sweep.py"
)
foreach ($fragment in $fragments) {
    $path = "D:\MLS\src\hardware\artiq\fragments\$fragment"
    if (Test-Path $path) {
        Write-Host "  ✓ $fragment" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Missing: $fragment" -ForegroundColor Red
        exit 1
    }
}

# Test 4: Data directory structure
Write-Host "`n[4/5] Testing data directory..." -ForegroundColor Yellow
$dataDirs = @(
    "E:\Data\telemetry",
    "E:\Data\camera\raw_frames",
    "E:\Data\logs"
)
foreach ($dir in $dataDirs) {
    if (Test-Path $dir) {
        Write-Host "  ✓ $dir" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Missing: $dir" -ForegroundColor Yellow
    }
}

# Test 5: Documentation structure
Write-Host "`n[5/5] Testing documentation..." -ForegroundColor Yellow
$docs = @(
    "D:\MLS\docs\guides",
    "D:\MLS\docs\reference",
    "D:\MLS\MIGRATION_GUIDE.md"
)
foreach ($doc in $docs) {
    if (Test-Path $doc) {
        Write-Host "  ✓ $doc" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Missing: $doc" -ForegroundColor Yellow
    }
}

Write-Host "`n=================================" -ForegroundColor Green
Write-Host "Migration verification COMPLETE!" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green
```

Run the verification:
```powershell
D:\MLS\verify_migration.ps1
```

---

## 8. Troubleshooting

### Common Issues and Solutions

#### Issue 1: "ModuleNotFoundError: No module named 'core'"

**Symptom:**
```
ModuleNotFoundError: No module named 'core'
```

**Cause**: PYTHONPATH doesn't include `src/` directory

**Solution:**
```powershell
# Add to your script or environment
$env:PYTHONPATH = "D:\MLS\src;$env:PYTHONPATH"

# Or modify your Python invocation
python -c "import sys; sys.path.insert(0, 'D:/MLS/src'); from core.config.config import ConfigManager"
```

#### Issue 2: "ImportError: cannot import name 'Compensation' from 'comp'"

**Symptom:**
```
ImportError: cannot import name 'Compensation' from 'comp'
```

**Cause**: Import statement still using old filename

**Solution:**
```python
# OLD (broken)
from comp import Compensation

# NEW (correct)
from compensation import Compensation
```

#### Issue 3: Configuration file not found

**Symptom:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'config/settings.yaml'
```

**Cause**: Code still looking for old `settings.yaml`

**Solution:**
```python
# OLD
config = load_config("config/settings.yaml")

# NEW
from core.config.config import ConfigManager
config = ConfigManager()  # Automatically finds base.yaml
```

#### Issue 4: "AttributeError: module 'core' has no attribute 'enums'"

**Symptom:**
```
AttributeError: module 'core' has no attribute 'enums'
```

**Cause**: Module moved to `core.utils`

**Solution:**
```python
# OLD
from core.enums import u_rf_mv_to_U_rf_v

# NEW
from core.utils.enums import u_rf_mv_to_U_rf_v
```

#### Issue 5: Old pycache conflicts

**Symptom:**
Strange import errors or old code being executed

**Solution:**
```powershell
# Clear all __pycache__ directories
Get-ChildItem D:\MLS -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# Clear .pyc files
Get-ChildItem D:\MLS -Recurse -File -Filter "*.pyc" | Remove-Item -Force
```

#### Issue 6: Camera server not finding image_handler

**Symptom:**
```
ModuleNotFoundError: No module named 'server.cam'
```

**Solution:**
```python
# OLD
from server.cam.image_handler import ImageHandler

# NEW
from hardware.camera.image_handler import ImageHandler
```

### How to Rollback if Needed

#### Option 1: Git Revert (If you committed the migration)

```powershell
cd D:\MLS

# See recent commits
git log --oneline -5

# Revert the migration commit
git revert <migration-commit-hash>

# Or reset to pre-migration (DANGEROUS - loses changes)
git reset --hard <pre-migration-commit-hash>
```

#### Option 2: Restore from Backup

```powershell
# Remove current MLS
Rename-Item D:\MLS D:\MLS_failed_migration

# Restore from backup
robocopy "D:\MLS_Backup_20260202" D:\MLS /E /Z /R:3

# Restore your settings
copy D:\MLS\config\settings.yaml.pre-migration D:\MLS\config\settings.yaml
```

#### Option 3: Selective Rollback (Keep some changes)

```powershell
# Just revert specific files
git checkout HEAD -- config/settings.yaml
git checkout HEAD -- artiq/experiments/trap_controler.py

# Or restore old fragment files temporarily
git checkout HEAD -- artiq/fragments/comp.py
git checkout HEAD -- artiq/fragments/ec.py
```

---

## 9. Quick Reference

### Cheat Sheet for Common Tasks

#### Start the System

```powershell
# Quick start (all services)
D:\start_servers.bat

# Or using PowerShell module
Import-Module D:\MLS\tools\ControlManager.psm1
Start-ControlManager
Start-CameraServer
```

#### Check Configuration

```powershell
# Validate config files
python D:\MLS\setup\validate_setup.py

# Or manually check
python -c "
import sys; sys.path.insert(0, 'D:/MLS/src')
from core.config.config import ConfigManager
cm = ConfigManager()
print('Config loaded successfully!')
print(f'Environment: {cm.environment}')
"
```

#### Update Imports (Find and Replace)

```powershell
# Find files needing updates
grep -r "from comp import" --include="*.py" D:\MLS
grep -r "from ec import" --include="*.py" D:\MLS
grep -r "from core\." --include="*.py" D:\MLS

# PowerShell replace (example)
(Get-Content D:\MLS\my_script.py) -replace 'from comp import', 'from compensation import' | Set-Content D:\MLS\my_script.py
```

#### Environment Setup

```powershell
# Set up for current session
$env:MLS_ROOT = "D:\MLS"
$env:MLS_CONFIG_DIR = "D:\MLS\config"
$env:MLS_ENVIRONMENT = "production"
$env:MLS_DATA_DIR = "E:\Data"
$env:PYTHONPATH = "D:\MLS\src"

# Make permanent (User scope)
foreach ($var in @('MLS_ROOT', 'MLS_CONFIG_DIR', 'MLS_ENVIRONMENT', 'MLS_DATA_DIR')) {
    [Environment]::SetEnvironmentVariable($var, (Get-Item "env:$var").Value, "User")
}
```

### FAQ

**Q: Do I need to update all my experiment files at once?**  
A: No. The old imports will continue to work during the transition. You can update files incrementally as you work on them.

**Q: Can I still use `settings.yaml`?**  
A: It's deprecated but still supported. Create an environment config in `config/environments/` instead for better organization.

**Q: What if I have custom modifications to the old files?**  
A: You'll need to port your changes to the new file locations. Use `git diff` to see what changed:
```powershell
git diff HEAD~10 -- artiq/fragments/comp.py
```

**Q: How do I add a new configuration environment?**  
A: Create a new file in `config/environments/`:
```yaml
# config/environments/my_setup.yaml
network:
  master_ip: "192.168.1.100"
paths:
  output_base: "D:/MyData"
```
Then set `$env:MLS_ENVIRONMENT = "my_setup"`

**Q: Where did the server logs go?**  
A: Logs are now organized under `logs/server/`:
- `logs/server/manager.log`
- `logs/server/camera.log`
- `logs/server/flask.log`

**Q: Can I use both old and new import styles during transition?**  
A: Yes, as long as your PYTHONPATH includes both the old locations and `src/`. However, migrate to the new style as soon as possible.

**Q: What Python version is required?**  
A: Python 3.11 or higher is recommended. Check with `python --version`.

**Q: How do I update my LabVIEW VIs?**  
A: Update the file paths in your LabVIEW code to use the new data directory structure:
- Old: `Y:\Xi\Data\...`
- New: `E:\Data\...`

See `D:\DATA_DIRECTORY_STANDARD.md` for complete path mappings.

---

## Additional Resources

- **Architecture Overview**: `D:\MLS\docs\ARCHITECTURE.md`
- **Naming Conventions**: `D:\MLS\docs\reference\NAMING_CONVENTIONS.md`
- **File Rename Migration**: `D:\MLS\docs\reference\FILE_RENAME_MIGRATION.md`
- **API Reference**: `D:\MLS\docs\API_REFERENCE.md`
- **Server Startup Guide**: `D:\SERVER_STARTUP_GUIDE.md`
- **Data Directory Standard**: `D:\DATA_DIRECTORY_STANDARD.md`

---

## Support

For migration issues:

1. Check this guide's Troubleshooting section
2. Review the relevant documentation in `docs/`
3. Run the verification script: `D:\MLS\verify_migration.ps1`
4. Check logs: `D:\MLS\logs\server\`

---

*End of Migration Guide*
