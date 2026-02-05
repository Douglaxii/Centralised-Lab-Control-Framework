# MLS System Architecture

This document describes the architecture of the Multi-Ion Lab System (MLS).

---

## Overview

MLS is a distributed control system for trapped ion experiments. It coordinates multiple hardware systems through a centralized manager with ZMQ-based communication.

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Web UI     │  │   TuRBO      │  │   Jupyter    │          │
│  │   (Flask)    │  │   (Auto)     │  │   (Analysis) │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼────────────────┼────────────────┼───────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CONTROL LAYER                               │
│                    ControlManager                                │
│              (ZMQ Coordinator - manager.py)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   REQ/REP    │  │    PUB       │  │    PULL      │          │
│  │  Port 5557   │  │  Port 5555   │  │  Port 5556   │          │
│  │  (Clients)   │  │  (Commands)  │  │  (Data)      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────┬────────────────┬────────────────┬───────────────────┘
          │                │                │
          │                ▼                │
          │         ┌──────────────┐        │
          │         │   ARTIQ      │        │
          │         │   Worker     │        │
          │         │ (experiments)│        │
          │         └──────────────┘        │
          │                │                │
          ▼                ▼                ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│     ARTIQ       │  │    LabVIEW      │  │     Camera      │
│    Worker       │  │    SMILE        │  │    Server       │
│   (Hardware)    │  │   (Hardware)    │  │   (Imaging)     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Components

### 1. ControlManager

Central coordinator managing all system communication.

**Location:** `src/server/manager/manager.py`

**ZMQ Sockets:**

| Port | Pattern | Purpose |
|------|---------|---------|
| 5555 | PUB/SUB | Command distribution |
| 5556 | PUSH/PULL | Data/telemetry collection |
| 5557 | REQ/REP | Client requests/responses |

**Key Methods:**
```python
# Set hardware parameters
set_parameter(device, value)

# Execute experiments
run_experiment(experiment_type, parameters)

# Emergency stop
emergency_stop()
```

### 2. ARTIQ Worker

Handles hardware control via the ARTIQ framework.

**Location:** `artiq/`

**Fragments:**
- `compensation.py` - DC electrode control
- `endcaps.py` - Endcap voltage control
- `raman_control.py` - Raman cooling beams
- `dds_controller.py` - DDS frequency control
- `pmt_counter.py` - PMT photon counting
- `camera_trigger.py` - Camera TTL trigger

**Experiments:**
- `set_dc_exp.py` - DC voltage setting
- `secular_sweep_exp.py` - Frequency sweep
- `pmt_measure_exp.py` - Photon counting

### 3. LabVIEW Interface

TCP-based communication with LabVIEW SMILE.

**Location:** `src/server/comms/labview_interface.py`

**Protocol:** JSON over TCP (port 5559)

**Supported Commands:**
- RF voltage control
- Piezo control
- Toggle control (oven, B-field, etc.)

### 4. Camera Server

Image acquisition and processing.

**Location:** `src/hardware/camera/`

**Modes:**
- **Infinity:** Continuous live view (HTTP polling)
- **Recording:** Triggered capture (DCIMG format)

**Protocol:** TCP (port 5558)

### 5. Flask Web Server

REST API and web interface.

**Location:** `src/server/api/flask_server.py`

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health check |
| `/api/status` | GET | Get system status |
| `/api/set` | POST | Set parameters |
| `/api/sweep` | POST | Run frequency sweep |
| `/camera/start` | POST | Start camera recording |
| `/camera/stop` | POST | Stop camera |

---

## Communication Protocols

### ZMQ Message Format

```json
{
  "category": "PMT_MEASURE" | "SECULAR_SWEEP" | "CAM_SWEEP" | "ERROR",
  "timestamp": "2026-02-05T19:45:22.462887+01:00",
  "exp_id": "exp_20260205_194522",
  "applet_id": "cam_sweep_applet",
  "payload": { /* Command-specific data */ },
  "metadata": {
    "priority": 1,
    "retry_count": 0
  }
}
```

### TCP Protocol (LabVIEW)

```json
{
  "action": "SET_RF",
  "params": {
    "u_rf_mv": 1000
  },
  "timestamp": "2026-02-05T19:45:22"
}
```

---

## Data Flow

### Command Flow (Applet → Hardware)

```
┌─────────────┐     HTTP POST      ┌─────────────┐
│   Applet    │ ─────────────────► │   Manager   │
│  (Flask)    │                    │  (ZMQ REQ)  │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ ZMQ PUB
                                          │ (5555)
                                          ▼
┌─────────────┐     ZMQ SUB      ┌─────────────┐
│    FPGA     │ ◄────────────────│   ARTIQ     │
│   (KASLI)   │                  │   Worker    │
└──────┬──────┘                  └─────────────┘
       │
       │ TTL
       ▼
┌─────────────┐
│  Hardware   │
│  (PMT/DDS)  │
└─────────────┘
```

**Latency:** ~10-50ms end-to-end

### Result Flow (Hardware → Applet)

```
┌─────────────┐     TTL Count      ┌─────────────┐
│    PMT      │ ─────────────────► │    FPGA     │
│  Counter    │                    │   (KASLI)   │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ Kernel
                                          │ fetch
                                          ▼
                                   ┌─────────────┐
                                   │   ARTIQ     │
                                   │   Worker    │
                                   │ (ZMQ PUSH)  │
                                   └──────┬──────┘
                                          │
                                          │ ZMQ PULL
                                          │ (5556)
                                          ▼
┌─────────────┐     ZMQ REP      ┌─────────────┐
│   Applet    │ ◄────────────────│   Manager   │
│  (Flask)    │   JSON Response  │             │
└─────────────┘                  └─────────────┘
```

---

## Port Assignments

| Port | Service | Protocol | Purpose |
|------|---------|----------|---------|
| 5000 | Flask Web UI | HTTP | Web interface & API |
| 5555 | Manager PUB | ZMQ | Command distribution |
| 5556 | Manager PULL | ZMQ | Data collection |
| 5557 | Manager REP | ZMQ | Client requests |
| 5558 | Camera Server | TCP | Camera control & streaming |
| 5559 | LabVIEW SMILE | TCP | LabVIEW control |
| 5560 | Telemetry | TCP | Instrument telemetry |

---

## Configuration

Main configuration file: `config/config.yaml`

```yaml
environment: development  # or "production"

profiles:
  development:
    network:
      master_ip: "192.168.56.101"
      cmd_port: 5555
      data_port: 5556
      client_port: 5557
      camera_port: 5558
    
    services:
      flask: { host: "127.0.0.1", port: 5000 }
      manager: { enabled: true }
      camera: { enabled: true, port: 5558 }
      optimizer: { enabled: true, port: 5050 }
      applet: { enabled: true, port: 5051 }
    
    hardware:
      defaults:
        u_rf_volts: 200.0
        ec1: 0.0
        ec2: 0.0
        comp_h: 0.0
        comp_v: 0.0
```

---

## Directory Structure

```
mls/
├── config/              # Configuration
│   ├── config.yaml     # Unified configuration (all settings)
│   └── README.md       # Config documentation
│
├── src/                # Source code
│   ├── core/           # Shared utilities
│   │   ├── config/
│   │   ├── exceptions/
│   │   ├── logging/
│   │   └── utils/
│   │
│   ├── server/         # Server components
│   │   ├── api/        # Flask REST API
│   │   ├── comms/      # Communication (ZMQ, TCP)
│   │   └── manager/    # ControlManager
│   │
│   ├── hardware/       # Hardware interfaces
│   │   └── camera/     # Camera server
│   │
│   ├── optimizer/      # Bayesian optimization
│   │   └── flask_optimizer/
│   │
│   └── frontend/       # User interfaces
│       └── applet/
│
├── artiq/              # ARTIQ experiments & fragments
│   ├── experiments/
│   └── fragments/
│
├── scripts/            # Utility scripts
│   ├── setup/          # Setup scripts
│   └── windows/        # Windows batch scripts
│
├── logs/               # Log files
├── data/               # Data storage
└── docs/               # Documentation
```

---

*Last Updated: 2026-02-05*
