# MLS Documentation

Documentation for the Multi-Ion Lab System (MLS).

---

## Quick Start

New to MLS? Start here:

1. **[User Guide](USER_GUIDE.md)** - System setup and operation
2. **[Architecture](ARCHITECTURE.md)** - System design and components
3. **[API Reference](API_REFERENCE.md)** - Complete API documentation

---

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](USER_GUIDE.md) | Installation, operation, and troubleshooting |
| [Architecture](ARCHITECTURE.md) | System design, components, and data flow |
| [API Reference](API_REFERENCE.md) | REST API, ZMQ protocol, and Python API |
| [Hardware](HARDWARE.md) | Hardware integration (ARTIQ, LabVIEW, Camera) |
| [Development](DEVELOPMENT.md) | Developer guide and contribution guidelines |

---

## System Architecture Overview

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

## Port Reference

| Port | Service | Protocol |
|------|---------|----------|
| 5000 | Flask Web UI | HTTP |
| 5555 | Manager PUB | ZMQ |
| 5556 | Manager PULL | ZMQ |
| 5557 | Manager REP | ZMQ |
| 5558 | Camera Server | TCP |
| 5559 | LabVIEW SMILE | TCP |

---

## Quick Commands

```bash
# Start all services
python launcher.py

# Check status
python launcher.py --status

# Run diagnostics
python tools/check_server.py
```

---

*Last Updated: 2026-02-05*
