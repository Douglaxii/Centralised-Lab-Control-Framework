# Migration Guide

This guide describes the changes made to the lab control framework and how to migrate existing code.

## Summary of Changes

### 1. New Core Module (`core/`)

Created a shared utilities module containing:

- **config.py** - Centralized YAML configuration
- **logger.py** - Structured logging with rotation
- **zmq_utils.py** - ZMQ helpers with retry logic
- **exceptions.py** - Custom exception types
- **experiment.py** - Experiment tracking system

### 2. Configuration System

**Before:** Hardcoded values scattered across files
```python
# Old way - lab_comms.py
MASTER_IP = "192.168.1.100"
CMD_PORT = 5555
```

**After:** Centralized YAML config
```python
# New way
from core import get_config

config = get_config()
ip = config.master_ip
port = config.cmd_port
```

### 3. ZMQ Pattern Fixes

**Before:** Socket pattern mismatch
- Manager used PUB for commands, SUB for data
- Worker used SUB for commands, PUB for data
- **Problem:** Data couldn't flow properly

**After:** Standardized patterns
- Manager: PUB (commands) + PULL (data)
- Worker: SUB (commands) + PUSH (data)

### 4. Experiment Tracking

New feature: Every experiment gets a unique ID that propagates through all components.

```python
from core import ExperimentContext, get_tracker

# Create experiment
tracker = get_tracker()
exp = tracker.create_experiment(parameters={"target": 307})
print(exp.exp_id)  # EXP_143022_A1B2C3D4

# Use throughout system
comm.send_command("ARTIQ", {"type": "RUN_SWEEP"}, exp_id=exp.exp_id)
```

### 5. Safety Improvements

**ARTIQ Worker:**
- Added heartbeat mechanism
- Improved watchdog with state logging
- Better error handling and recovery

**Manager:**
- Health monitoring thread
- Automatic SAFE mode on worker timeout
- Structured safety event logging

### 6. Camera Recording Fixes

**Fixed:**
- `hdcam_check` and `hrec_check` undefined variable errors
- Added proper signal handler safety
- Integrated with config system
- Added experiment ID support

### 7. Import Fixes

**Fixed:**
- `Raman_board.py` - Added missing `dB` import from `oitg.units`
- `trap_control.py` - Removed large commented code block

## Migration Steps

### Step 1: Install Dependencies

```bash
pip install pyyaml
```

### Step 2: Update Configuration

1. Copy `config/settings.yaml` to your project
2. Edit values for your setup (IP addresses, paths)

### Step 3: Update Imports

**Old:**
```python
import sys
sys.path.insert(0, "..")
```

**New:**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import get_config, setup_logging
```

### Step 4: Update LabComms Usage

**Old:**
```python
from lab_comms import LabComm

comm = LabComm("ARTIQ", role="WORKER")
comm.send_data({"counts": 100})
```

**New:**
```python
from server.communications.lab_comms import LabComm

with LabComm("ARTIQ", role="WORKER") as comm:
    comm.send_data({"counts": 100}, category="PMT")
```

### Step 5: Update Hardcoded Paths

**Old:**
```python
SETTINGS_PATH = "Y:/Stein/Server/Camera_Settings/"
```

**New:**
```python
from core import get_config
config = get_config()
settings_path = config.get_path('camera_settings')
```

## Backwards Compatibility

The `LabCommLegacy` class maintains the old interface:

```python
from server.communications.lab_comms import LabCommLegacy as LabComm

# Old code continues to work
comm = LabComm("ARTIQ", role="WORKER")
```

However, new features (experiment tracking, improved error handling) require the new interface.

## Testing

Run unit tests:

```bash
cd /path/to/MLS
python tests/test_core.py
```

Expected output:
```
.........
----------------------------------------------------------------------
Ran 9 tests in 0.XXXs
OK
```

## Configuration Reference

### Network Settings

```yaml
network:
  master_ip: "192.168.1.100"      # Master PC IP
  cmd_port: 5555                  # Commands (PUB/SUB)
  data_port: 5556                 # Data (PUSH/PULL)
  client_port: 5557               # Web UI (REQ/REP)
  watchdog_timeout: 60.0          # Safety timeout (seconds)
  heartbeat_interval: 10.0        # Heartbeat interval (seconds)
```

### Path Settings

```yaml
paths:
  artiq_data: "C:/artiq-master/results"
  output_base: "Y:/Xi/Data"
  camera_frames: "Y:/Stein/Server/Camera_Frames"
  camera_settings: "Y:/Stein/Server/Camera_Settings"
```

### Hardware Defaults

```yaml
hardware:
  worker_defaults:
    ec1: 0.0                      # Endcap 1 voltage
    ec2: 0.0                      # Endcap 2 voltage
    sweep_target: 307             # Default sweep frequency (kHz)
    sweep_span: 40.0              # Sweep span (kHz)
```

## Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'core'`

**Solution:** Add parent directory to path:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### Config Not Found

**Problem:** `FileNotFoundError: Configuration file not found`

**Solution:** Ensure `config/settings.yaml` exists at project root.

### ZMQ Connection Failed

**Problem:** `ConnectionError: Failed to connect`

**Solution:** 
1. Check IP addresses in config
2. Verify manager is running
3. Check firewall settings

## Feature Comparison

| Feature | Old Code | New Code |
|---------|----------|----------|
| Configuration | Hardcoded | YAML config |
| Logging | print() | Structured logging |
| Retries | None | Exponential backoff |
| Experiment tracking | None | Full audit trail |
| Safety logging | None | Structured events |
| Heartbeats | None | Automatic |
| Unit tests | None | Included |

## Rollback Plan

If issues occur:

1. Keep old files backed up (they were overwritten)
2. Restore from git: `git checkout -- <file>`
3. Use `LabCommLegacy` for gradual migration

## Support

For issues:
1. Check logs in `logs/` directory
2. Run unit tests: `python tests/test_core.py`
3. Verify config: `python -c "from core import get_config; print(get_config().master_ip)"`
