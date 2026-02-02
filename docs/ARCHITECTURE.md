---

> ?? **DEPRECATED**: This file has been moved. Please see the new documentation structure.
> 
> **New Location**: See README.md for the reorganized documentation.
> 
> This file will be removed in version 3.0.

---
# Lab Control Framework Architecture

**Version:** 2.0  
**Last Updated:** 2026-02-01

## Overview

This framework provides a distributed control system for mixed-species ion trap experiments, coordinating:
- **ARTIQ** - Hardware control (DACs, DDS, TTL)
- **LabVIEW/SMILE** - High voltage RF, piezo, oven, e-gun control
- **Camera** - Image acquisition and processing
- **Two-Phase Optimizer** - TuRBO + MOBO Bayesian optimization
- **Web UI** - User interface and monitoring

## System Architecture

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
┌─────────────────────────────────────────────────────────────────┐
│                     HARDWARE LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │     DC       │  │     DDS      │  │     TTL      │          │
│  │  (Zotino)    │  │  (Urukul)    │  │  (Camera)    │          │
│  │  Endcaps     │  │   Raman      │  │   Trigger    │          │
│  │ Compensation │  │   Cooling    │  │    PMT       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DATA LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │     H5       │  │    JPG       │  │    JSON      │          │
│  │  (ARTIQ)     │  │  (Camera)    │  │ (Analysis)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Communication Patterns

### 1. Client → Manager (REQ/REP)
- **Port:** 5557
- **Pattern:** Request-Reply
- **Used by:** Flask UI, TuRBO, Scripts
- **Message format:** JSON

Example:
```json
{
  "action": "SET",
  "source": "USER",
  "params": {"ec1": 5.0, "ec2": 5.0},
  "exp_id": "EXP_143022_A1B2C3D4"
}
```

### 2. Manager → Workers (PUB/SUB)
- **Port:** 5555
- **Pattern:** Publish-Subscribe
- **Used by:** Manager broadcasts to all workers
- **Topics:** "ARTIQ", "ALL"

Example:
```json
{
  "type": "SET_DC",
  "values": {"ec1": 5.0, "ec2": 5.0},
  "exp_id": "EXP_143022_A1B2C3D4"
}
```

### 3. Workers → Manager (PUSH/PULL)
- **Port:** 5556
- **Pattern:** Push-Pull
- **Used by:** Workers send data/heartbeats to Manager

Example:
```json
{
  "timestamp": 1699999999.123,
  "source": "ARTIQ",
  "category": "SWEEP_COMPLETE",
  "payload": {"status": "SWEEP_COMPLETE", "steps": 41},
  "exp_id": "EXP_143022_A1B2C3D4"
}
```

## Experiment Lifecycle

```
┌─────────────┐
│   CREATE    │ ← User/API creates experiment
└──────┬──────┘
       │ generates exp_id
       ▼
┌─────────────┐
│  CONFIGURE  │ ← SET_DC, SET_COOLING commands
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    SWEEP    │ ← RUN_SWEEP command
└──────┬──────┘
       │ captures H5 + camera images
       ▼
┌─────────────┐
│   ANALYZE   │ ← Fit sweep data
└──────┬──────┘
       │ saves JSON results
       ▼
┌─────────────┐
│   COMPLETE  │ ← All components done
└─────────────┘
```

## Configuration System

Configuration is centralized in `config/settings.yaml`:

```yaml
network:
  master_ip: "192.168.1.100"
  cmd_port: 5555
  data_port: 5556
  client_port: 5557

paths:
  artiq_data: "C:/artiq-master/results"
  output_base: "Y:/Xi/Data"
  labview_tdms: "Y:/Xi/Data/PMT"     # LabVIEW TDMS files
  camera_frames: "Y:/Stein/Server/Camera_Frames"

hardware:
  worker_defaults:
    ec1: 0.0
    ec2: 0.0
    sweep_target: 307
```

Access in code:
```python
from core import get_config

config = get_config()
ip = config.master_ip
port = config.cmd_port
```

## Safety Systems

### Watchdog Timer
- Worker resets to safe defaults if no command received for 60 seconds
- Heartbeats sent every 10 seconds to confirm liveness
- Manager monitors worker health

### Safety States
When triggered:
1. All DC voltages → 0V
2. All shutters → CLOSED
3. System mode → SAFE
4. Event logged with full context

### Connection Retry
- Exponential backoff for ZMQ connections
- Configurable max retries
- Graceful degradation on failure

## Experiment Tracking

Every experiment gets a unique ID:
```
EXP_HHMMSS_XXXXXXXX
```

Context is propagated through all components:
1. Manager creates experiment context
2. exp_id sent with every command
3. Workers include exp_id in all data
4. Analysis saves results with exp_id
5. Complete audit trail preserved

## Directory Structure

```
Y:/Xi/Data/
├── YYMMDD/
│   ├── sweep_json/
│   │   ├── HHMMSS_sweep_EXP_xxxx.json
│   │   └── HHMMSS_sweep_EXP_yyyy.json
│   ├── cam_json/
│   │   ├── HHMMSS_data_EXP_xxxx.json
│   │   └── HHMMSS_proc.jpg
│   ├── metadata/
│   │   └── EXP_xxxx_context.json
│   └── dcimg/
│       └── record_YYYY-MM-DD_HH-MM-SS.dcimg
```

## Component Details

### ControlManager (server/communications/manager.py)
- Central coordinator
- Mode management (MANUAL/AUTO/SAFE)
- Request routing
- Health monitoring
- Experiment tracking
- Two-Phase optimizer integration
- LabVIEW interface management
- Kill switch monitoring

### Two-Phase Optimizer (server/optimizer/)
Bayesian optimization using TuRBO (Phase I) and MOBO (Phase II):

**Phase I - Component Optimization:**
- `TwoPhaseController` - Main coordinator with ASK-TELL interface
- `TuRBOOptimizer` - Trust Region Bayesian Optimization
- Optimizes individual stages (Be+ loading, ejection, HD+ loading)

**Phase II - Global Optimization:**
- `MOBOOptimizer` - Multi-Objective Bayesian Optimization
- Balances yield vs speed trade-offs
- Enforces purity and stability constraints

**Key Features:**
- Warm start: Phase I data seeds Phase II
- Pareto front for trade-off analysis
- Constraint handling for safe experiments

See [BO.md](BO.md) for detailed optimization architecture.

### ARTIQ Worker (artiq/experiments/artiq_worker.py)
- Hardware control
- Command execution
- Watchdog safety
- Heartbeat generation
- Dataset broadcasting

### Camera Server (server/cam/)
- DCIMG recording
- Frame capture
- Live streaming
- Cleanup management
- Trigger synchronization

### Image Handler (server/cam/image_handler.py)
- Ion detection
- 2D Gaussian fitting
- Position tracking
- Metadata extraction

### LabVIEW Interface (server/communications/labview_interface.py)
- TCP communication with LabVIEW SMILE program
- RF voltage control (U_RF)
- Piezo voltage control
- Hardware toggles (oven, B-field, etc.)
- DDS frequency setting
- Emergency stop handling

### Data Ingestion Server (server/communications/data_server.py)
- Receives telemetry from LabVIEW instruments
- Wavemeter frequency data
- SMILE PMT counts and pressure readings
- Rolling window data storage

### Analysis (artiq/analyze_sweep.py)
- H5 file parsing
- Lorentzian fitting
- Result JSON generation
- Experiment correlation

## Development Guidelines

### Adding a New Command

1. Define command type in manager:
```python
def handle_request(self, req):
    elif action == "MY_COMMAND":
        return self._handle_my_command(req)
```

2. Implement handler:
```python
def _handle_my_command(self, req):
    params = req.get("params", {})
    self._publish_my_command(params)
    return {"status": "success"}
```

3. Add publisher:
```python
def _publish_my_command(self, params):
    msg = {"type": "MY_COMMAND", "values": params}
    self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
    self.pub_socket.send_json(msg)
```

4. Handle in worker:
```python
elif cmd_type == "MY_COMMAND":
    self._handle_my_command(payload)
```

### Adding a New Worker

1. Create worker class with ZMQ setup
2. Subscribe to relevant topics
3. Send heartbeats
4. Implement safety defaults
5. Include exp_id in all messages

## Troubleshooting

### ZMQ Connection Issues
- Check firewall settings on Master PC
- Verify IP addresses in config
- Check port availability: `netstat -an | findstr 5555`

### Worker Timeout
- Check ARTIQ dashboard for errors
- Verify network connectivity
- Check worker logs in `logs/artiq_worker.log`

### Missing Experiment Data
- Check exp_id propagation
- Verify all components use same config
- Check file permissions on output paths

## Migration from Legacy Code

The `LabCommLegacy` class in `server/communications/lab_comms.py` maintains backwards compatibility.
New code should use the `LabComm` class with context managers:

```python
# Old
from server.communications.lab_comms import LabComm
comm = LabComm("ARTIQ", role="WORKER")
comm.send_data({...})

# New
from server.communications.lab_comms import LabComm
with LabComm("ARTIQ", role="WORKER", exp_id=exp_id) as comm:
    comm.send_data({...})
```
