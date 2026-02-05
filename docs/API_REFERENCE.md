# MLS API Reference

Complete API reference for the Multi-Ion Lab System.

---

## Table of Contents

1. [REST API](#rest-api)
2. [ZMQ Protocol](#zmq-protocol)
3. [Python API](#python-api)

---

## REST API

Base URL: `http://localhost:5000`

### System Endpoints

#### Health Check
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "manager": "connected",
    "camera": "connected",
    "labview": "disconnected"
  },
  "timestamp": "2026-02-05T19:45:22"
}
```

#### System Status
```http
GET /api/status
```

**Response:**
```json
{
  "system_status": "ready",
  "current_mode": "idle",
  "hardware": {
    "u_rf_volts": 200.0,
    "ec1": 10.0,
    "ec2": 10.0,
    "comp_h": 0.0,
    "comp_v": 0.0
  }
}
```

### Hardware Control

#### Set Parameters
```http
POST /api/set
Content-Type: application/json

{
  "device": "trap",
  "value": [10, 10, 6, 37]
}
```

**Parameters:**
- `device`: `"trap"`, `"rf"`, `"dds"`, etc.
- `value`: Array or single value depending on device

**Response:**
```json
{
  "success": true,
  "device": "trap",
  "values_set": [10, 10, 6, 37]
}
```

#### Get Parameters
```http
GET /api/get?device=trap
```

### Experiment Control

#### Run Sweep
```http
POST /api/sweep
Content-Type: application/json

{
  "target_frequency_khz": 307,
  "span_khz": 40,
  "steps": 41,
  "on_time_ms": 100,
  "off_time_ms": 100,
  "dds_choice": "axial"
}
```

**Response:**
```json
{
  "experiment_id": "sweep_20260205_194522",
  "status": "started",
  "parameters": {
    "start_freq_khz": 287,
    "end_freq_khz": 327,
    "steps": 41
  }
}
```

### Camera Control

#### Start Camera (Infinity Mode)
```http
GET /camera/start_infinity
```

#### Stop Camera
```http
GET /camera/stop_infinity
```

#### Get Last Frame
```http
GET /camera/get_last_frame
```

**Response:** JPEG image

#### Start Recording
```http
POST /camera/start
Content-Type: application/json

{
  "exposure_ms": 100,
  "roi": {
    "x": 500,
    "y": 500,
    "width": 200,
    "height": 200
  }
}
```

### Safety

#### Kill Switch
```http
POST /api/kill
```

**Response:**
```json
{
  "success": true,
  "message": "Emergency stop activated"
}
```

---

## ZMQ Protocol

### Connection Details

| Socket | Pattern | Address | Purpose |
|--------|---------|---------|---------|
| Commands | PUB/SUB | `tcp://master_ip:5555` | Receive commands |
| Data | PUSH/PULL | `tcp://master_ip:5556` | Send data |
| Client | REQ/REP | `tcp://master_ip:5557` | Direct requests |

### Message Format

```json
{
  "category": "SET_DC" | "SECULAR_SWEEP" | "PMT_MEASURE" | "CAM_SWEEP",
  "timestamp": "2026-02-05T19:45:22.462887+01:00",
  "exp_id": "exp_20260205_194522",
  "applet_id": "control_applet",
  "payload": {
    // Command-specific data
  },
  "metadata": {
    "priority": 1,
    "retry_count": 0
  }
}
```

### Commands

#### SET_DC
```json
{
  "category": "SET_DC",
  "payload": {
    "ec1": 10.0,
    "ec2": 10.0,
    "comp_h": 6.0,
    "comp_v": 37.0
  }
}
```

#### SECULAR_SWEEP
```json
{
  "category": "SECULAR_SWEEP",
  "payload": {
    "target_frequency_khz": 307,
    "span_khz": 40,
    "steps": 41,
    "on_time_ms": 100,
    "off_time_ms": 100,
    "dds_choice": "axial"
  }
}
```

#### SET_RF
```json
{
  "category": "SET_RF",
  "payload": {
    "u_rf_volts": 200.0
  }
}
```

### Python ZMQ Example

```python
import zmq
import json

# Create context
ctx = zmq.Context()

# Client socket (REQ/REP)
client = ctx.socket(zmq.REQ)
client.connect("tcp://localhost:5557")

# Send command
client.send_json({
    "action": "SET",
    "source": "USER",
    "params": {"ec1": 10.0, "ec2": 10.0}
})

# Receive response
response = client.recv_json()
print(response)
```

---

## Python API

### Configuration

```python
from src.core.config.config import get_config

# Get full configuration
config = get_config()

# Access values
master_ip = config.network.master_ip
cmd_port = config.network.cmd_port
```

### ControlManager

```python
from src.server.manager.manager import ControlManager

manager = ControlManager()

# Set parameters
manager.set_parameter("ec1", 10.0)
manager.set_parameter("trap", [10, 10, 6, 37])

# Run experiment
result = manager.run_experiment(
    experiment_type="secular_sweep",
    parameters={"target_frequency_khz": 307}
)

# Emergency stop
manager.emergency_stop()
```

### Camera Client

```python
from src.hardware.camera.camera_client import CameraClient

client = CameraClient()

# Connect
client.connect()

# Start infinity mode
client.start_infinity()

# Get frame
frame = client.get_last_frame()

# Stop
client.stop_infinity()
```

### Optimization

```python
from src.optimizer.turbo import TuRBOOptimizer

optimizer = TuRBOOptimizer(
    target_frequency=307.0,
    span_khz=40.0,
    steps=41
)

# Run optimization
result = optimizer.run()

# Access results
best_params = result.best_parameters
best_score = result.best_score
```

---

## Data Formats

### Sweep Result

```json
{
  "experiment_id": "sweep_20260205_194522",
  "timestamp": "2026-02-05T19:45:22",
  "parameters": {
    "start_freq_khz": 287.0,
    "end_freq_khz": 327.0,
    "steps": 41
  },
  "data": {
    "frequencies_khz": [287.0, 288.0, ...],
    "pmt_counts": [45, 67, ...],
    "sig_x": [0.1, 0.2, ...],
    "r_y": [0.05, 0.08, ...]
  },
  "fits": {
    "pmt_fit": {
      "center_khz": 307.5,
      "fwhm_khz": 2.1,
      "amplitude": 123.4
    }
  }
}
```

### Camera Configuration

```json
{
  "mode": "infinity",
  "exposure_ms": 100.0,
  "roi": {
    "x": 500,
    "y": 500,
    "width": 200,
    "height": 200
  },
  "trigger": {
    "source": "software",
    "edge": "rising"
  }
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request |
| 404 | Not found |
| 500 | Internal server error |
| 503 | Service unavailable |

### Error Response Format

```json
{
  "success": false,
  "error": "INVALID_PARAMETER",
  "message": "EC1 voltage out of range",
  "details": {
    "parameter": "ec1",
    "value": 100.0,
    "allowed_range": [-1, 50]
  }
}
```

---

*Last Updated: 2026-02-05*
