# Lab Control Framework (MLS)

A distributed control system for ion trap experiments, coordinating ARTIQ hardware control, camera acquisition, and data analysis.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start all services
python launcher.py

# Access dashboard
http://localhost:5000
```

## System Requirements

- Python 3.10+
- Windows 10/11 or Linux
- Network access to LabVIEW PC and ARTIQ

## Architecture

```
Flask UI (5000) <---> Manager (ZMQ 5557) <---> ARTIQ Worker
                           |
                           v
                      LabVIEW (TCP 5559)
```

## Project Structure

```
MLS/
├── launcher.py           # Main entry point
├── core/                 # Shared utilities (config, logging, etc.)
├── server/
│   ├── communications/   # Manager, LabVIEW interface, data server
│   ├── cam/              # Camera server and image processing
│   └── Flask/            # Web dashboard
├── artiq/                # ARTIQ hardware control
├── config/               # Configuration files
└── docs/                 # Documentation
```

## Key Features

- **Kill Switch Protection**: Auto-shutdown for piezo (10s) and e-gun (10s)
- **Real-time Telemetry**: Live charts with scatter plot mode
- **Safety Systems**: Triple-layer protection
- **Experiment Tracking**: Full audit trail

## API Documentation

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md)

## Safety

⚠️ **CRITICAL**: This system controls high-voltage hardware. Always:
1. Verify kill switches are functioning
2. Test emergency stop before experiments
3. Never disable safety features in production
