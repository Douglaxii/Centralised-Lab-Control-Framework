# MLS Documentation

Welcome to the Multi-Ion Lab System (MLS) documentation. This guide covers everything from system architecture to daily operation.

**Last Updated:** 2026-02-02  
**Version:** 2.0

---

## Quick Start

New to MLS? Start here:

1. **[System Overview](architecture/README.md)** - Understand the big picture
2. **[Installation Guide](guides/CONDA_SETUP.md)** - Set up your environment
3. **[Safety Systems](guides/SAFETY_KILL_SWITCH.md)** - Critical safety information
4. **[API Quick Reference](api/README.md)** - Start controlling the system

---

## Documentation Structure

### [🏗️ Architecture](architecture/)
System design, communication protocols, and component interactions.

| Document | Description |
|----------|-------------|
| [Overview](architecture/overview.md) | High-level system architecture |
| [Communication](architecture/communication.md) | ZMQ/TCP protocols and message formats |

### [📚 API Reference](api/)
Complete API documentation for all interfaces.

| Document | Description |
|----------|-------------|
| [Reference](api/reference.md) | REST API, ZMQ protocol, Python API |

### [📖 Guides](guides/)
Step-by-step instructions for common tasks.

| Document | Description |
|----------|-------------|
| [Conda Setup](guides/CONDA_SETUP.md) | Environment installation and configuration |
| [Camera Activation](guides/CAMERA_ACTIVATION.md) | Camera system operation |
| [Safety Kill Switch](guides/SAFETY_KILL_SWITCH.md) | Safety system operation |

### [🔧 Hardware](hardware/)
Hardware integration guides.

| Document | Description |
|----------|-------------|
| [LabVIEW Integration](hardware/labview.md) | SMILE/LabVIEW interface |
| [Camera Hardware](hardware/camera.md) | Hamamatsu CCD setup |

### [💻 Development](development/)
Resources for developers.

| Document | Description |
|----------|-------------|
| [Naming Conventions](development/naming_conventions.md) | Code style and naming standards |
| [Testing](development/testing.md) | Test procedures and calibration |

### [📋 Reference](reference/)
Technical reference materials.

| Document | Description |
|----------|-------------|
| [Data Formats](reference/data_formats.md) | File formats and data integration |
| [Optimization](reference/optimization.md) | Bayesian optimization guide |
| [Bayesian Optimization Architecture](reference/bo_architecture.md) | Two-phase optimizer design |
| [Secular Comparison](reference/secular_comparison.md) | Frequency comparison system |

---

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Web UI     │  │   TuRBO      │  │   Jupyter    │          │
│  │   (Flask)    │  │   (Auto)     │  │   (Analysis) │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CONTROL LAYER                               │
│                  ControlManager (ZMQ)                            │
│           ┌──────────────────────────────────┐                  │
│           │     REQ/REP  │  PUB  │  PULL     │                  │
│           │     5557     │ 5555  │  5556     │                  │
│           └──────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│     ARTIQ       │  │    LabVIEW      │  │     Camera      │
│    Worker       │  │    SMILE        │  │    Server       │
│   (Hardware)    │  │   (Hardware)    │  │   (Imaging)     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Common Tasks

### Starting the System

```bash
# Start all services
python launcher.py

# Or start individually:
python -m server.communications.manager  # Control Manager
python -m server.Flask.flask_server      # Web UI
python -m server.cam.camera_server       # Camera
```

### Accessing the Dashboard

- **Web Dashboard:** http://localhost:5000
- **Health Check:** http://localhost:5000/health
- **API Status:** http://localhost:5000/api/status

### Running Tests

```bash
# Run calibration tests
python tests/calibration_test.py --all

# Test pressure safety
python tests/test_pressure_safety.py
```

---

## Important Safety Notes

⚠️ **CRITICAL:** Always review the [Safety Kill Switch Guide](guides/SAFETY_KILL_SWITCH.md) before operating the system.

Key safety features:
- **Triple-layer kill switch** for piezo (10s max) and e-gun (30s max)
- **Pressure monitoring** with automatic shutdown
- **Emergency stop** accessible from all interfaces
- **Hardware limits** independent of software

---

## Documentation Status

| Document | Status | Last Updated |
|----------|--------|--------------|
| Architecture | ✅ Current | 2026-02-01 |
| API Reference | ✅ Current | 2026-02-01 |
| Conda Setup | ✅ Current | 2026-02-01 |
| Camera Activation | ✅ Current | 2026-02-02 |
| Safety Kill Switch | ✅ Current | 2026-01-28 |
| LabVIEW Integration | ✅ Current | 2026-01-28 |
| Optimization | ✅ Current | 2026-02-01 |

---

## Contributing to Documentation

When adding or updating documentation:

1. Follow the existing structure and formatting
2. Update the status table above
3. Update internal links if moving files
4. Add entries to the appropriate navigation sections

---

## Support

For issues or questions:
1. Check the relevant documentation section
2. Review logs in `logs/` directory
3. Run diagnostics: `python launcher.py --status`
