# Lab Control Framework

A distributed control system for ion trap experiments, coordinating ARTIQ hardware control, camera acquisition, and data analysis.

## Features

- 🔬 **ARTIQ Integration** - Full hardware control (DACs, DDS, TTL)
- 📷 **Camera Control** - Automated image capture and analysis
- 🌐 **Web Interface** - Flask-based monitoring and control
- 🔒 **Safety Systems** - Watchdog timers and automatic safe states
- 📊 **Experiment Tracking** - Full audit trail with unique experiment IDs
- 🔄 **ZMQ Communication** - Robust distributed messaging
- ⚙️ **Centralized Config** - YAML-based configuration management

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure System

Edit `config/settings.yaml`:

```yaml
network:
  master_ip: "192.168.1.100"  # Your Master PC IP

paths:
  output_base: "Y:/Xi/Data"    # Your network drive
```

### 3. Start Components

Terminal 1 - Manager:
```bash
cd server/communications
python manager.py
```

Terminal 2 - ARTIQ Worker:
```bash
# In ARTIQ environment
artiq_run artiq/experiments/artiq_worker.py
```

Terminal 3 - Flask UI:
```bash
cd server/Flask
python flask_server.py
```

Terminal 4 - Camera Server:
```bash
cd server/cam
python camera_server.py
```

### 4. Access Web UI

Open browser: http://localhost:5000

## Architecture

```
┌─────────┐     ┌──────────┐     ┌─────────┐
│  Flask  │────▶│ Manager  │────▶│  ARTIQ  │
│   UI    │◄────│ (ZMQ)    │◄────│ Worker  │
└─────────┘     └────┬─────┘     └─────────┘
                     │
                     ▼
              ┌──────────┐
              │  Camera  │
              │  Server  │
              └──────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed documentation.

## Key Components

| Component | File | Purpose |
|-----------|------|---------|
| Manager | `server/communications/manager.py` | Central coordinator |
| ARTIQ Worker | `artiq/experiments/artiq_worker.py` | Hardware control |
| Camera | `server/cam/camera_recording.py` | Image acquisition |
| Image Analysis | `server/cam/image_handler.py` | Ion detection |
| Sweep Analysis | `artiq/analyze_sweep.py` | H5 file processing |
| Web UI | `server/Flask/flask_server.py` | User interface |

## Usage Examples

### Manual Control via Python

```python
from lab_comms import LabComm

# Connect as master
with LabComm("MASTER", role="MASTER") as comm:
    # Set DC voltages
    comm.send_command("ARTIQ", {
        "type": "SET_DC",
        "values": {"ec1": 5.0, "ec2": 5.0}
    })
    
    # Trigger sweep
    comm.send_command("ARTIQ", {
        "type": "RUN_SWEEP",
        "values": {"target_frequency_khz": 307}
    })
```

### Starting an Experiment

```python
from core import ExperimentContext, get_tracker

# Create experiment
tracker = get_tracker()
exp = tracker.create_experiment(parameters={"target": 307})
exp.start()

# Use exp.exp_id when sending commands
# All data will be tagged with this ID
```

### Analyzing Sweep Data

```bash
# Analyze latest sweep
python artiq/analyze_sweep.py --latest

# Watch for new files
python artiq/analyze_sweep.py --watch

# Specific file
python artiq/analyze_sweep.py /path/to/file.h5 --exp-id EXP_143022_A1B2C3D4
```

## Safety Features

- **Watchdog Timer** - Hardware resets to safe state if communication lost
- **Heartbeat Monitoring** - Health checks between all components
- **Safe Mode** - Automatic transition to safe state on errors
- **Connection Retry** - Exponential backoff for network issues
- **Structured Logging** - Full audit trail of all operations

## Configuration

All configuration is in `config/settings.yaml`:

| Section | Description |
|---------|-------------|
| `network` | IP addresses and ports |
| `paths` | Data storage locations |
| `hardware` | Default parameter values |
| `logging` | Log levels and rotation |

## Troubleshooting

### Worker Timeout
Check worker logs: `logs/artiq_worker.log`

### Camera Not Responding
```bash
# Check camera server
python server/cam/test_local_net.py
```

### ZMQ Connection Issues
```bash
# Check ports
netstat -an | findstr 5555
```

## Project Structure

```
MLS/
├── config/              # Configuration files
│   └── settings.yaml
├── core/                # Shared utilities
│   ├── config.py       # Config management
│   ├── logger.py       # Logging setup
│   ├── zmq_utils.py    # ZMQ helpers
│   ├── experiment.py   # Experiment tracking
│   └── exceptions.py   # Custom exceptions
├── artiq/              # ARTIQ code
│   ├── experiments/    # Main experiments
│   └── fragments/      # Hardware fragments
├── server/             # Server components
│   ├── communications/ # Manager
│   ├── cam/           # Camera control
│   └── Flask/         # Web UI
├── tests/             # Unit tests
└── docs/              # Documentation
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black artiq/ server/ core/
```

## License

Proprietary - For internal lab use only.

## Contributing

1. Create feature branch
2. Make changes with tests
3. Update documentation
4. Submit merge request

## Support

For issues or questions, check:
1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Detailed architecture
2. Logs in `logs/` directory
3. Experiment metadata in `Y:/Xi/Data/[date]/metadata/`
