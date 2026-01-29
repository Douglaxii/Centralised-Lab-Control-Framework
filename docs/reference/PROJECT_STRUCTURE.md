# Project Directory Structure

This document describes the organization of the Lab Control Framework codebase.

## Quick Overview

```
MLS/
├── artiq/              # ARTIQ hardware control
├── config/             # Configuration files
├── core/               # Shared utilities
├── docs/               # Documentation
│   ├── guides/         # User guides
│   ├── reference/      # Technical reference
│   └── server/         # Server-specific docs
├── labview/            # LabVIEW utilities
├── logs/               # Runtime logs
│   └── server/         # Service logs
├── scripts/            # Utility scripts
│   ├── service/        # Windows service setup
│   └── setup/          # Installation scripts
├── server/             # Server components
│   ├── cam/            # Camera acquisition
│   ├── communications/ # ZMQ communication
│   └── Flask/          # Web dashboard
├── tests/              # Unit tests
└── tools/              # Diagnostic tools
```

## Directory Details

### Root Files

| File | Purpose |
|------|---------|
| `launcher.py` | Main entry point - starts all services |
| `requirements.txt` | Python dependencies |
| `start.bat` / `start.sh` | Quick start scripts |
| `README.md` | Project overview |

### `artiq/` - Hardware Control

ARTIQ (Advanced Real-Time Infrastructure for Quantum physics) control code.

```
artiq/
├── experiments/        # Main ARTIQ experiments
│   ├── artiq_worker.py
│   └── trap_control.py
├── fragments/          # Reusable components
│   ├── compensation.py
│   ├── endcaps.py
│   ├── Raman_board.py
│   └── secularsweep.py
└── analyze_sweep.py    # Data analysis tool
```

### `config/` - Configuration

```
config/
├── settings.yaml           # Main configuration
└── parallel_config.yaml    # Parallel execution config
```

**Important:** Only edit `settings.yaml` - all components read from this single source.

### `core/` - Shared Utilities

Core utilities imported by all components:
- `config.py` - Singleton configuration management
- `logger.py` - Structured logging setup
- `zmq_utils.py` - ZMQ communication helpers
- `exceptions.py` - Custom exceptions
- `enums.py` - Enumeration types
- `experiment.py` - Experiment tracking

### `docs/` - Documentation

Organized by category:

```
docs/
├── guides/                 # User guides
│   ├── MIGRATION_GUIDE.md
│   ├── QUICK_START_PARALLEL.md
│   └── SAFETY_KILL_SWITCH.md
├── reference/              # Technical reference
│   ├── ARCHITECTURE.md
│   ├── COMMUNICATION_PROTOCOL.md
│   ├── DATA_INTEGRATION.md
│   ├── FLASK_INTERFACE_REQUIREMENTS.md
│   ├── LABVIEW_INTEGRATION.md
│   ├── PARALLEL_ARCHITECTURE.md
│   ├── PROJECT_STRUCTURE.md (this file)
│   └── SECULAR_COMPARISON.md
└── server/                 # Server-specific docs
    ├── OPTIMIZATION.md     # Hardware optimization
    └── TROUBLESHOOTING.md  # Common issues & fixes
```

### `logs/` - Runtime Logs

```
logs/
└── server/
    ├── camera.log      # Camera server logs
    ├── flask.log       # Web UI logs
    ├── launcher.log    # Launcher activity
    └── manager.log     # Control manager logs
```

### `scripts/` - Utility Scripts

```
scripts/
├── service/                    # Windows service
│   ├── install-windows-service.bat
│   └── lab-control.service
└── setup/                      # Installation
    ├── requirements-server.txt
    └── setup_server_optimized.bat
```

### `server/` - Server Components

```
server/
├── cam/                        # Camera acquisition
│   ├── camera_server.py
│   ├── camera_server_parallel.py
│   ├── camera_recording.py
│   ├── image_handler.py
│   └── image_handler_optimized.py
├── communications/             # Communication
│   ├── manager.py
│   ├── lab_comms.py
│   ├── labview_interface.py
│   └── data_server.py
└── Flask/                      # Web dashboard
    └── flask_server.py
```

### `tests/` - Testing

```
tests/
├── test_core.py
├── test_image_handler.py
└── benchmark_image_handler.py
```

### `tools/` - Diagnostic Tools

```
tools/
└── check_server.py     # Pre-flight diagnostic
```

## Server PC Setup (Intel Core i9 + Quadro P400)

For the server PC with optimized hardware:

1. **Setup**: Run `scripts/setup/setup_server_optimized.bat`
2. **Verify**: Run `python tools/check_server.py`
3. **Docs**: Read `docs/server/OPTIMIZATION.md`
4. **Troubleshoot**: Check `docs/server/TROUBLESHOOTING.md`
5. **Start**: Run `python launcher.py`

## Adding New Files

Follow these conventions:

| Type | Location |
|------|----------|
| Server components | `server/<category>/` |
| Documentation | `docs/<category>/` |
| Setup scripts | `scripts/setup/` |
| Service scripts | `scripts/service/` |
| Diagnostic tools | `tools/` |
| Tests | `tests/` |

## Configuration

The main configuration file is `config/settings.yaml`:
- Uses YAML format
- Forward slashes for paths (even on Windows)
- All components read from this single source
- Changes require service restart

## Logs

Log files are created automatically in `logs/server/`:
- Each service has its own log file
- Launcher logs to `logs/server/launcher.log`
- Log rotation is configured in settings.yaml
