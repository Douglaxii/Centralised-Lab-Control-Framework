# MLS Configuration

Single unified configuration file for the Multi-Species Loading System.

## Overview

All system configuration is in `config.yaml`. The file contains two profiles:

- **`development`** - For laptop/local testing
- **`production`** - For lab/manager PC

## Quick Start

### 1. Select Environment

Edit `config.yaml`:

```yaml
environment: development   # For laptop testing
# or
environment: production    # For lab
```

Or use the environment switcher:

```bash
python scripts/switch_env.py dev   # Switch to development
python scripts/switch_env.py prod  # Switch to production
```

### 2. Use in Code

```python
from src.core.config import get_config

config = get_config()

# Access via properties
ip = config.master_ip
port = config.flask_port

# Access via get()
value = config.get('hardware.defaults.ec1', 0.0)

# Access paths
log_path = config.get_path('logs')
```

## Configuration Sections

| Section | Description |
|---------|-------------|
| `network` | IP addresses, ports, timeouts |
| `services` | Flask, Manager, Camera, Optimizer, Applet settings |
| `paths` | Data directories and log locations |
| `hardware` | Default voltages, camera settings |
| `labview` | LabVIEW/SMILE integration |
| `wavemeter` | HighFinesse WS7 wavemeter TCP settings |
| `optimizer` | TuRBO and MOBO settings |
| `applet` | Applet-specific settings |
| `logging` | Log levels and file locations |
| `performance` | Threads, GPU, memory limits |

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| Flask API | 5000 | Web UI and API |
| Optimizer | 5050 | Bayesian optimization UI |
| Applet | 5051 | Experiment applets |
| Manager ZMQ | 5555-5557 | Command, data, client ports |
| Camera | 5558 | Camera TCP server |
| LabVIEW | 5559 | SMILE interface |
| Wavemeter | 1790 | HighFinesse WS7 TCP |

## Environment-Specific Notes

### Development (Laptop)
- LabVIEW disabled
- Software camera trigger
- GPU disabled
- Debug logging
- Local paths

### Production (Lab)
- LabVIEW enabled (SMILE PC)
- External camera trigger
- GPU enabled
- Info logging
- Network drives
