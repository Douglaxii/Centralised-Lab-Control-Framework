# MLS Unified Configuration System

This document describes the unified configuration system for MLS that replaces the old fragmented config files.

## Quick Start

### 1. Check Current Environment
```bash
python switch_env.py
```

### 2. Switch Environment
```bash
# For development on your laptop
python switch_env.py dev

# For production on manager PC  
python switch_env.py prod
```

### 3. Start Services
```bash
python src/launcher.py
```

## Configuration File Structure

All configuration is now in a single file: **`config/config.yaml`**

```yaml
# Set which environment to use
environment: development  # or 'production'

# Define profiles for each environment
profiles:
  development:
    description: "Local development on laptop"
    network:
      master_ip: "127.0.0.1"
      ...
    paths:
      output_base: "./data"
      ...
    
  production:
    description: "Manager PC in lab"
    network:
      master_ip: "134.99.120.40"
      ...
    paths:
      output_base: "Y:/Xi/Data"
      ...
```

## Environment Comparison

| Setting | Development (Laptop) | Production (Manager PC) |
|---------|---------------------|-------------------------|
| **Master IP** | 127.0.0.1 | 134.99.120.40 |
| **Data Path** | ./data (local) | E:/data + Y:/Xi/Data |
| **LabVIEW** | Disabled | Enabled (172.17.1.217) |
| **Camera Trigger** | Software | External (hardware) |
| **GPU** | Disabled | Enabled |
| **Log Level** | DEBUG | INFO |
| **Ports** | Standard | Standard |

## Switching Environments

### Method 1: Using the Switch Script (Recommended)

```bash
# Switch to development (laptop)
python switch_env.py dev

# Switch to production (manager PC)
python switch_env.py prod

# Check current status
python switch_env.py
```

### Method 2: Editing Config File Directly

Edit `config/config.yaml` and change the first line:

```yaml
environment: development  # For laptop
# or
environment: production  # For manager PC
```

### Method 3: Using Environment Variable

Set `MLS_ENV` before running:

```bash
# Windows
set MLS_ENV=development
python src/launcher.py

# Or for production
set MLS_ENV=production
python src/launcher.py
```

The environment variable **overrides** the setting in config.yaml.

## Key Configuration Sections

### Network Settings
```yaml
network:
  master_ip: "134.99.120.40"    # Manager PC IP
  bind_host: "0.0.0.0"           # Listen on all interfaces
  cmd_port: 5555                 # ARTIQ commands
  data_port: 5556                # Data feedback
  client_port: 5557              # Flask -> Manager
  camera_port: 5558              # Camera TCP
```

### Data Paths
```yaml
paths:
  output_base: "E:/data"         # Main data directory
  camera_frames: "E:/data/camera/raw_frames"
  jpg_frames: "E:/data/jpg_frames"
  ion_data: "E:/data/ion_data"
```

### Hardware Defaults
```yaml
hardware:
  worker_defaults:
    u_rf_volts: 200.0           # Default RF voltage
    piezo: 0.0                  # Default piezo voltage
    ...
```

### Camera Settings
```yaml
camera:
  auto_start: true              # Auto-start on launch
  mode: "inf"                   # Infinite capture mode
  trigger_mode: "extern"        # external or software
```

## ARTIQ Configuration

**IMPORTANT**: ARTIQ code cannot use this configuration file. ARTIQ fragments must be hardcoded.

Example fragment configuration:
```python
class MyFragment(ExpFragment):
    # These are hardcoded - NOT from config file
    DEFAULT_RF_VOLTAGE = 200.0  # V
    DEFAULT_PIEZO = 0.0         # V
    
    def build(self):
        self.setattr_param("u_rf", FloatParam, "RF Voltage", 
                          self.DEFAULT_RF_VOLTAGE)
```

The Python control system (manager, Flask, etc.) reads from config.yaml and sends parameters to ARTIQ via ZMQ.

## Data Directory Setup

### Development (Laptop)
All data goes to `./data/` relative to project root:
```
MLS/
├── data/
│   ├── camera/
│   │   ├── raw_frames/
│   │   └── processed_frames/
│   ├── ion_data/
│   └── logs/
```

### Production (Manager PC)
Data is split between local (E:) and network (Y:) drives:
```
E:/data/                    # Local fast storage
├── jpg_frames/
├── jpg_frames_labelled/
└── ion_data/

Y:/Xi/Data/                 # Network storage
├── telemetry/
├── experiments/
└── analysis/
```

## Troubleshooting

### Config File Not Found
```
FileNotFoundError: Configuration file not found
```
**Solution**: Ensure `config/config.yaml` exists. If using old config files, they will still work but show a deprecation warning.

### Unknown Environment
```
ValueError: Unknown environment 'xyz'. Available: ['development', 'production']
```
**Solution**: Check the `environment:` line in config.yaml is either `development` or `production`.

### Path Not Found
```
KeyError: Path 'xyz' not found in configuration
```
**Solution**: Ensure the path is defined in the active profile section of config.yaml.

### Permission Denied on E:/data
**Solution**: Run the setup script to create directories:
```bash
python setup_manager_pc.py
```

## Migration from Old Config System

If you have the old config files:
- `config/base.yaml` + `config/environments/*.yaml`
- `config/settings.yaml`
- `config/settings_local.yaml`

They will continue to work, but it's recommended to migrate to `config/config.yaml`:

1. Backup your old config files
2. Create `config/config.yaml` using the template
3. Copy your custom settings into the appropriate profile
4. Test with `python switch_env.py`

## Best Practices

1. **Never commit local changes to config.yaml**: The file should work for both environments
2. **Use `switch_env.py`**: Don't manually edit the environment line when switching
3. **Keep hardcoded values in fragments minimal**: Use config for Python control system
4. **Test both environments**: Before deploying, test on both laptop and manager PC
5. **Use relative paths in development**: Makes it portable across machines

## Environment Variable Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `MLS_ENV` | Override config environment | `development`, `production` |
| `MLS_DATA_ROOT` | Override data root path | `E:/data`, `./data` |

## Need Help?

Check the environment status:
```bash
python switch_env.py
```

View loaded configuration:
```python
from core import get_config
config = get_config()
print(f"Environment: {config.environment}")
print(f"Master IP: {config.master_ip}")
```
