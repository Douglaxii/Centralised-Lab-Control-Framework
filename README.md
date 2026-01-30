# Lab Control Framework

A distributed control system for ion trap experiments, coordinating ARTIQ hardware control, camera acquisition, and data analysis.

## Features

- 🔬 **ARTIQ Integration** - Full hardware control (DACs, DDS, TTL)
- 📷 **Camera Control** - Automated image capture and analysis
- 🌐 **Web Interface** - Flask-based monitoring and control
- 🔒 **Safety Systems** - Watchdog timers and automatic safe states
- ⚡ **Kill Switch Protection** - Triple-layer safety for Piezo (10s) and E-Gun (30s)
- 📊 **Experiment Tracking** - Full audit trail with unique experiment IDs
- 🔄 **ZMQ Communication** - Robust distributed messaging
- ⚙️ **Centralized Config** - YAML-based configuration management
- 🚀 **Parallel Execution** - Camera, Manager, Flask run efficiently on same PC
- 📦 **Unified Launcher** - Single command to start/stop all services

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
  output_base: "Y:/Xi/Data"         # Your network drive
  labview_tdms: "Y:/Xi/Data/PMT"    # LabVIEW TDMS files
```

### 3. Start All Services (Parallel Execution)

The easiest way - uses the unified launcher:

```bash
# Interactive mode (with command console)
python launcher.py

# Or using convenience script
start.bat              # Windows
./start.sh             # Linux/Mac
```

Or start individually:

```bash
# Terminal 1 - Manager (includes file reader for LabVIEW data)
python server/communications/manager.py

# Terminal 2 - Flask UI
python server/Flask/flask_server.py

# Terminal 3 - Camera Server
python server/cam/camera_server.py

# Terminal 4 - ARTIQ Worker (separate PC or same PC)
artiq_run artiq/experiments/artiq_worker.py
```

### 4. Access Web UI

Open browser: http://localhost:5000

### 5. Manage Services

```bash
# Check status
python launcher.py --status

# Restart all services
python launcher.py --restart

# Stop all services
python launcher.py --stop

# Interactive commands (when running interactively)
launcher> status       # Show service status
launcher> restart camera  # Restart specific service
launcher> help         # Show all commands
```

See [docs/QUICK_START_PARALLEL.md](docs/QUICK_START_PARALLEL.md) for detailed instructions.

## Architecture

### Parallel Execution (Same PC)

```
┌─────────────────────────────────────────────────────────┐
│                    Single PC                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │  Camera  │    │  Manager │    │  Flask   │          │
│  │  Server  │◄──►│ (ZMQ)    │◄──►│   UI     │          │
│  │  :5558   │    │  :5557   │    │  :5000   │          │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘          │
│       │               │               │                 │
│       └───────────────┴───────────────┘                 │
│                  Shared Memory                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Y:/Xi/Data/  -  Images & LabVIEW Telemetry    │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   ARTIQ Worker   │
                    │ (Separate PC)    │
                    └──────────────────┘
```

All three services (Camera, Manager, Flask) run efficiently in parallel on the same PC with:
- **Shared memory** for telemetry data (zero-copy)
- **Unified launcher** for process management
- **Health monitoring** with automatic restart

See [docs/PARALLEL_ARCHITECTURE.md](docs/PARALLEL_ARCHITECTURE.md) for detailed architecture documentation.

## Safety Features

### Kill Switch System

The framework implements a **triple-layer kill switch** for critical hardware outputs:

| Device | Time Limit | Protection Layers |
|--------|------------|-------------------|
| **Piezo Output** | 10 seconds max | Flask UI → Manager → LabVIEW |
| **E-Gun** | 30 seconds max | Flask UI → Manager → LabVIEW |

**Features:**
- Visual countdown timers on web interface
- Automatic shutdown when time limit exceeded
- Manual emergency stop button
- Independent hardware-level protection

See [docs/SAFETY_KILL_SWITCH.md](docs/SAFETY_KILL_SWITCH.md) for complete documentation.

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
from server.communications.lab_comms import LabComm

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
├── core/                # Shared utilities (imported by all components)
│   ├── __init__.py
│   ├── config.py        # YAML configuration management
│   ├── enums.py         # Enumeration types and constants
│   ├── exceptions.py    # Custom exception classes
│   ├── experiment.py    # Experiment tracking system
│   ├── logger.py        # Structured logging setup
│   └── zmq_utils.py     # ZMQ communication helpers
├── artiq/               # ARTIQ hardware control code
│   ├── experiments/
│   │   ├── artiq_worker.py   # Main ARTIQ worker process
│   │   └── trap_control.py   # Trap control experiments
│   ├── fragments/
│   │   ├── compensation.py   # Compensation electrode control
│   │   ├── endcaps.py        # Endcap electrode control
│   │   ├── Raman_board.py    # Raman laser control
│   │   └── secularsweep.py   # Secular frequency sweep
│   └── analyze_sweep.py      # H5 file analysis tool
├── server/              # Server-side components
│   ├── communications/  # Communication & coordination
│   │   ├── manager.py           # Central control manager
│   │   ├── labview_interface.py # LabVIEW SMILE TCP interface
│   │   ├── data_server.py       # Data ingestion server (port 5560)
│   │   └── lab_comms.py         # ZMQ communication library
│   ├── cam/            # Camera acquisition & processing
│   │   ├── camera_server.py     # Camera TCP server
│   │   ├── camera_recording.py  # DCIMG recording logic
│   │   └── image_handler.py     # Image analysis & ion detection
│   ├── Flask/          # Web dashboard
│   │   ├── flask_server.py      # Flask HTTP server
│   │   └── templates/           # HTML templates
│   └── analysis/       # Data analysis tools
│       └── secular_comparison.py  # Secular frequency comparison
├── labview/            # LabVIEW testing utilities
│   ├── mock_labview_sender.py   # Mock data sender for testing
│   ├── SMILE_Data_Sender.vi     # LabVIEW VI for SMILE
│   └── Wavemeter_Data_Sender.vi # LabVIEW VI for Wavemeter
├── tests/              # Unit and integration tests
│   ├── test_core.py
│   └── test_image_handler.py
├── docs/               # Documentation
│   ├── ARCHITECTURE.md
│   ├── COMMUNICATION_PROTOCOL.md
│   ├── DATA_INTEGRATION.md
│   ├── LABVIEW_INTEGRATION.md
│   ├── MIGRATION_GUIDE.md
│   └── SECULAR_COMPARISON.md
├── logs/               # Runtime logs (created automatically)
├── README.md           # This file
└── requirements.txt    # Python dependencies
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
