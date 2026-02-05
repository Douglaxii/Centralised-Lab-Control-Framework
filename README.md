# Mixed-Species Loading System (MLS)

A distributed control system for automated mixed-species ion trap experiments, featuring Two-Phase Bayesian optimization for ion loading.

## Overview

MLS coordinates multiple hardware subsystems for loading and manipulating Beryllium (Be+) and Hydrogen-Deuteride (HD+) ions in a Paul trap:

- **ARTIQ** - Pulse sequencing, DC electrodes, cooling lasers
- **LabVIEW/SMILE** - High voltage RF, piezo, oven, e-gun
- **Camera** - Ion imaging and counting
- **Wavemeter** - HighFinesse WS7 frequency monitoring
- **Two-Phase Optimizer** - TuRBO (Phase I) + MOBO (Phase II) Bayesian optimization

## Quick Start

### 1. Environment Setup

```bash
# Auto-detect environment and setup
python scripts/setup_env.py

# Or force specific environment
python scripts/setup_env.py --dev   # Development (laptop)
python scripts/setup_env.py --prod  # Production (lab PC)

# Switch environment
python scripts/switch_env.py dev    # or prod
```

### 2. Start All Services

```bash
# Start all services (Manager, Flask API, Optimizer, Applet)
python -m src.launcher

# Access dashboards
http://localhost:5000    # Main control interface
http://localhost:5050    # Optimizer interface
http://localhost:5051    # Applet interface
```

### Service Management

```bash
# Check service status
python -m src.launcher --status

# Stop all services
python -m src.launcher --stop

# Start specific services only
python -m src.launcher --services manager,api,optimizer,applet
```

## Architecture

### Smart Master Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Main Flask  │  │  Optimizer   │  │   Applet     │          │
│  │  (Port 5000) │  │  (Port 5050) │  │  (Port 5051) │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼─────────────────┼─────────────────┼──────────────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
                            ▼ ZMQ REQ/REP (Port 5557)
┌─────────────────────────────────────────────────────────────────┐
│                    CONTROL MANAGER (Smart Master)                │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              REQUEST HANDLERS                            │   │
│  │  SET | GET | SWEEP | OPTIMIZE_* | CAMERA_* | STATUS     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│  ┌─────────────────────────┼─────────────────────────────┐     │
│  │              TWO-PHASE OPTIMIZER                        │     │
│  │         (TuRBO Phase I → MOBO Phase II)                 │     │
│  └─────────────────────────┼─────────────────────────────┘     │
│                            │                                     │
│  ┌─────────────────────────┼─────────────────────────────┐     │
│  │              HARDWARE INTERFACES                        │     │
│  │  Camera | LabVIEW | ARTIQ | Wavemeter | Kill Switches  │     │
│  └─────────────────────────┼─────────────────────────────┘     │
└────────────────────────────┼────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   ARTIQ      │    │   LabVIEW    │    │   Camera     │
│   (ZMQ 5555) │    │   /SMILE     │    │   (TCP 5558) │
└──────────────┘    │  (TCP 5559)  │    └──────────────┘
                    └──────────────┘
                           │
                    ┌──────────────┐
                    │  Wavemeter   │
                    │  (TCP 1790)  │
                    └──────────────┘
```

### Key Design Principles

1. **ControlManager is Central** - All commands flow through ControlManager
2. **Fragment Architecture** - Modular components for hardware/services
3. **Two-Phase Optimization** - TuRBO for component tuning, MOBO for global optimization
4. **ASK-TELL Interface** - Clean separation between optimizer and hardware
5. **Safety First** - Kill switches and mode-based protection

## Project Structure

```
mls/
├── src/                        # Source code
│   ├── launcher.py             # Unified service launcher
│   ├── core/                   # Shared utilities
│   │   ├── config/            # Configuration management
│   │   ├── logging/           # Logging utilities
│   │   ├── exceptions/        # Custom exceptions
│   │   └── utils/             # ZMQ helpers, enums, tracking
│   │
│   ├── services/               # Server programs
│   │   ├── manager/           # ControlManager with fragments
│   │   ├── api/               # Flask REST API (port 5000)
│   │   ├── camera/            # Hamamatsu camera server
│   │   ├── comms/             # LabVIEW interface, data server
│   │   ├── optimizer/         # TuRBO/MOBO optimizer (port 5050)
│   │   └── applet/            # Experiment applets (port 5051)
│   │
│   └── analysis/               # Physics calculations
│       ├── secular_comparison.py
│       └── eigenmodes/
│
├── config/                     # Configuration
│   ├── config.yaml            # Main config (dev/prod profiles)
│   └── README.md
│
├── scripts/                    # Utility scripts
│   ├── setup_env.py           # Environment setup
│   ├── switch_env.py          # Switch dev/prod
│   └── README.md
│
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md
│   ├── API_REFERENCE.md
│   ├── USER_GUIDE.md
│   ├── HARDWARE.md
│   └── DEVELOPMENT.md
│
├── logs/                       # Log files
├── data/                       # Data storage
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Service Ports

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| Flask API | 5000 | HTTP | Main web interface |
| Optimizer | 5050 | HTTP | Bayesian optimization UI |
| Applet | 5051 | HTTP | Experiment applets |
| Manager CMD | 5555 | ZMQ | ARTIQ commands |
| Manager DATA | 5556 | ZMQ | Telemetry data |
| Manager CLIENT | 5557 | ZMQ | Client requests |
| Camera | 5558 | TCP | Camera server |
| LabVIEW | 5559 | TCP | SMILE interface |
| Wavemeter | 1790 | TCP | HighFinesse WS7 |

## Configuration

Main configuration file: `config/config.yaml`

```yaml
environment: development  # or production

profiles:
  development:
    network:
      master_ip: "192.168.56.101"
      cmd_port: 5555
    services:
      flask: {port: 5000}
      optimizer: {port: 5050}
```

See [config/README.md](config/README.md) for details.

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](docs/USER_GUIDE.md) | Installation and operation |
| [Architecture](docs/ARCHITECTURE.md) | System design and data flow |
| [API Reference](docs/API_REFERENCE.md) | REST API and ZMQ protocol |
| [Hardware](docs/HARDWARE.md) | Hardware integration |
| [Development](docs/DEVELOPMENT.md) | Developer guide |

## Safety ⚠️

**CRITICAL**: This system controls high-voltage hardware (up to 200V RF).

1. **Always** verify kill switches function before experiments
2. **Always** test emergency STOP procedures
3. **Never** disable safety features in production
4. **Always** monitor pressure when using e-gun or piezo

## License

Proprietary - See LICENSE file
