# Lab Control Framework (MLS)

A distributed control system for ion trap experiments, coordinating ARTIQ hardware control, camera acquisition, and data analysis.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start all services
python launcher.py

# Access dashboard
open http://localhost:5000
```

## System Requirements

- Python 3.8+
- Windows 10/11 or Linux
- Network access to LabVIEW PC and ARTIQ
- ZMQ libraries

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Flask     │◄───►│   Manager   │◄───►│   ARTIQ     │
│   UI:5000   │     │   ZMQ:5557  │     │   Worker    │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │   LabVIEW   │
                    │   TCP:5559  │
                    └─────────────┘
```

## Project Structure

```
MLS/
├── launcher.py           # Main entry point
├── core/                 # Shared utilities
├── server/
│   ├── communications/   # Manager, LabVIEW interface
│   ├── cam/              # Camera server
│   └── Flask/            # Web dashboard
├── artiq/                # ARTIQ control code
├── config/               # Configuration files
└── docs/                 # Documentation
```

## Key Features

- **Multi-Ion Tracking**: Support for 0-20 ions with per-ion parameter storage
- **Kill Switch Protection**: Auto-shutdown for piezo (10s) and e-gun (10s)
- **Real-time Telemetry**: Live charts with scatter plot mode
- **Safety Systems**: Triple-layer protection (Flask → Manager → LabVIEW)
- **Experiment Tracking**: Full audit trail with unique IDs

## API Documentation

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for complete API documentation.

## Safety

⚠️ **CRITICAL**: This system controls high-voltage hardware. Always:
1. Verify kill switches are functioning
2. Test emergency stop before experiments
3. Never disable safety features in production

## License

Proprietary - For internal lab use only.
