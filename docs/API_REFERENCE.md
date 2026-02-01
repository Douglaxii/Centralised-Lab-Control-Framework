# MLS API Reference

Complete API documentation for the Multi-Ion Lab System.

---

## Table of Contents

1. [Flask REST API](#flask-rest-api)
2. [Manager ZMQ Protocol](#manager-zmq-protocol)
3. [Optimization API](#optimization-api)
4. [LabVIEW TCP Protocol](#labview-tcp-protocol)
5. [Camera TCP Protocol](#camera-tcp-protocol)
6. [Python Core API](#python-core-api)
7. [Error Codes](#error-codes)

---

## Flask REST API

Base URL: `http://localhost:5000`

### Health & Status

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": 1706745600.123,
  "uptime_seconds": 3600.5,
  "version": "1.0.0",
  "checks": {
    "server": "ok",
    "manager_connected": true,
    "telemetry_available": true,
    "camera_path_accessible": true
  }
}
```

#### GET /api/status
Get complete system status.

**Response:**
```json
{
  "mode": "MANUAL",
  "params": {
    "u_rf_volts": 200.0,
    "ec1": 0.0,
    "ec2": 0.0,
    "comp_h": 0.0,
    "comp_v": 0.0,
    "piezo": 2.4,
    "b_field": true,
    ...
  },
  "worker_alive": true,
  "camera": {
    "latency_ms": 120.5,
    "is_live": true,
    "fps": 30.0,
    "ion_position": {...}
  },
  "turbo": {
    "status": "IDLE",
    "iteration": 0,
    "safety_engaged": true
  },
  "kill_switch": {
    "piezo": {"armed": false, "limit": 10.0},
    "e_gun": {"armed": false, "limit": 10.0}
  }
}
```

### Hardware Control

#### POST /api/set
Unified control endpoint for all devices.

**Request Body:**
```json
{"device": "u_rf", "value": 300.0}
{"device": "trap", "value": [10, 10, 6, 37]}
{"device": "piezo", "value": 2.5}
{"device": "dds", "value": 135.0}
{"device": "b_field", "value": 1}
```

**Response:**
```json
{"status": "success", "device": "u_rf", "value": 300.0}
```

#### POST /api/control/electrodes
Set electrode voltages.

**Request:**
```json
{
  "ec1": 10.0,
  "ec2": 10.0,
  "comp_h": 6.0,
  "comp_v": 37.0
}
```

#### POST /api/control/rf
Set RF voltage.

**Request:**
```json
{"u_rf_volts": 200.0}
```

#### POST /api/control/piezo/setpoint
Set piezo voltage setpoint (0-4V).

**Request:**
```json
{"voltage": 2.4}
```

#### POST /api/control/piezo/output
Enable/disable piezo output with kill switch.

**Request:**
```json
{"enable": true}
```

**Response:**
```json
{
  "status": "success",
  "output": true,
  "voltage": 2.4,
  "kill_switch": {
    "armed": true,
    "time_limit_seconds": 10,
    "warning": "AUTO-SHUTOFF AFTER 10 SECONDS"
  }
}
```

#### POST /api/control/toggle/{name}
Set toggle state (b_field, be_oven, uv3, e_gun, bephi).

**Request:**
```json
{"state": true}
```

**Note:** `e_gun` has kill switch protection (30s max ON time).

#### POST /api/control/dds
Set DDS profile and/or frequency.

**Request:**
```json
{
  "dds_profile": 0,
  "dds_freq_Mhz": 135.0
}
```

### Safety & Kill Switch

#### GET /api/killswitch/status
Get kill switch status.

#### POST /api/killswitch/trigger
Manually trigger kill switch.

**Request:**
```json
{"device": "piezo"}
```

#### POST /api/safety/toggle
Master safety switch.

**Request:**
```json
{"engage": true}  // Enter SAFE mode
{"engage": false} // Enter AUTO mode
```

### Experiments

#### POST /api/sweep
Trigger sweep experiment.

**Request:**
```json
{
  "target_frequency_khz": 307,
  "span_khz": 40,
  "steps": 41
}
```

#### POST /api/compare
Trigger secular frequency comparison.

**Request:**
```json
{
  "ec1": 10.0,
  "ec2": 10.0,
  "comp_h": 6.0,
  "comp_v": 37.0,
  "u_rf_mV": 1400
}
```

#### GET /api/experiment?id={exp_id}
Get experiment status.

### Real-time Streams

#### GET /video_feed
MJPEG video stream from camera.

#### GET /api/telemetry/stream
Server-sent events for telemetry data.

**Event Format:**
```json
{
  "timestamp": 1706745600.123,
  "pmt": [{"t": 1234567890, "v": 150}],
  "laser_freq": [{"t": 1234567890, "v": 212.5}],
  "pressure": [{"t": 1234567890, "v": 1.2e-10}],
  "ions": {
    "ion_count": 2,
    "ions": [
      {"ion_id": 0, "pos_x": 100, "pos_y": 200, "sig_x": 2.0, "sig_y": 3.0}
    ]
  }
}
```

---

## Manager ZMQ Protocol

### Socket Configuration

| Socket | Pattern | Port | Purpose |
|--------|---------|------|---------|
| Client | REP | 5557 | Flask/Turbo requests |
| Command | PUB | 5555 | Broadcast to workers |
| Data | PULL | 5556 | Receive from workers |

### Request Format

```json
{
  "action": "SET|GET|STOP|SWEEP|MODE|...",
  "source": "USER|FLASK|TURBO",
  "exp_id": "EXP_...",
  "params": {...}
}
```

### Actions

#### SET
Set hardware parameters.

**Request:**
```json
{
  "action": "SET",
  "source": "USER",
  "params": {
    "ec1": 10.0,
    "ec2": 10.0,
    "u_rf_volts": 200.0
  }
}
```

**Response:**
```json
{
  "status": "success",
  "mode": "MANUAL",
  "params": {"ec1": 10.0, "ec2": 10.0}
}
```

#### GET
Get parameter values.

#### STOP
Emergency stop - enters SAFE mode.

#### SWEEP
Start frequency sweep.

**Request:**
```json
{
  "action": "SWEEP",
  "source": "USER",
  "params": {
    "target_frequency_khz": 307,
    "span_khz": 40,
    "steps": 41
  }
}
```

#### COMPARE
Start secular comparison.

#### MODE
Change system mode.

**Request:**
```json
{
  "action": "MODE",
  "mode": "MANUAL|AUTO|SAFE"
}
```

#### CAMERA_START / CAMERA_STOP
Control camera recording.

#### OPTIMIZE_START
Start two-phase optimization.

**Request:**
```json
{
  "action": "OPTIMIZE_START",
  "target_be_count": 1,
  "target_hd_present": true,
  "turbo_max_iterations": 50,
  "mobo_max_iterations": 30
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Optimization started in Phase I (TuRBO)",
  "phase": "BE_LOADING_TURBO"
}
```

#### OPTIMIZE_STOP
Stop optimization.

**Response:**
```json
{
  "status": "success",
  "message": "Optimization stopped",
  "final_phase": "BE_LOADING_TURBO",
  "iterations": 12
}
```

#### OPTIMIZE_SUGGESTION (ASK)
Get next parameters to evaluate.

**Response:**
```json
{
  "status": "success",
  "params": {
    "piezo": 2.3,
    "be_pi_laser_duration_ms": 350,
    "cooling_power_mw": 0.8
  },
  "metadata": {
    "phase": "be_loading_turbo",
    "iteration": 5,
    "trust_region_length": 0.6
  }
}
```

#### OPTIMIZE_RESULT (TELL)
Register experimental results.

**Request:**
```json
{
  "action": "OPTIMIZE_RESULT",
  "measurements": {
    "total_fluorescence": 125.0,
    "cycle_time_ms": 5200,
    "ion_count": 1
  }
}
```

**Response:**
```json
{
  "status": "success",
  "iteration": 6,
  "cost": 45.2,
  "best_cost": 42.1
}
```

#### OPTIMIZE_STATUS
Get optimization status.

**Response:**
```json
{
  "status": "success",
  "phase": "BE_LOADING_TURBO",
  "state": "RUNNING",
  "iteration": 6,
  "target_be_count": 1,
  "target_hd_present": true,
  "turbo_config": {
    "max_iterations": 50,
    "n_init": 10
  },
  "mobo_config": {
    "max_iterations": 30,
    "n_init": 5
  }
}
```

#### OPTIMIZE_RESET
Reset optimization state.

**Response:**
```json
{
  "status": "success",
  "message": "Optimization state cleared"
}
```

---

## LabVIEW TCP Protocol

**Connection:** TCP to LabVIEW PC (default: 172.17.1.217:5559)

**Message Format:** JSON with newline termination

### Commands

#### Set RF Voltage
```json
{"command": "SET_U_RF", "value": 700.0}
```

#### Set Piezo Voltage
```json
{"command": "SET_PIEZO", "value": 2.4}
```

#### Set Toggle
```json
{"command": "SET_BE_OVEN", "value": true}
```

#### Set DDS Frequency
```json
{"command": "SET_DDS", "value": 135.0}
```

#### Get All Values
```json
{"command": "GET_ALL"}
```

**Response:**
```json
{
  "U_RF": 700.0,
  "Piezo": 2.4,
  "BeOven": false,
  "BField": true,
  ...
}
```

#### Apply Safety Defaults
```json
{"command": "APPLY_SAFETY_DEFAULTS"}
```

---

## Camera TCP Protocol

**Connection:** TCP to localhost:5558

**Commands:**
- `START` - Start DCIMG recording
- `START_INF` - Start infinite capture
- `STOP` - Stop recording
- `STATUS` - Get status
- `EXP_ID:{id}` - Set experiment ID

---

## Python Core API

### Configuration

```python
from core import get_config

config = get_config()
master_ip = config.master_ip
cmd_port = config.cmd_port
```

### Experiment Tracking

```python
from core import get_tracker

tracker = get_tracker()
exp = tracker.create_experiment(parameters={"target": 307})
exp.start()

# Use exp.exp_id in commands
exp.add_result("key", value)
exp.transition_to("phase_name")
```

### Logging

```python
from core import setup_logging

logger = setup_logging(component="my_module")
logger.info("Message")
```

### Two-Phase Optimizer

```python
from server.optimizer import TwoPhaseController, Phase, OptimizationConfig

# Create controller
config = OptimizationConfig(
    target_be_count=1,
    target_hd_present=True
)
controller = TwoPhaseController(config)

# Start Phase I (TuRBO)
controller.start_phase(Phase.BE_LOADING_TURBO)

# ASK-TELL loop
params, metadata = controller.ask()
# ... run experiment ...
controller.tell({
    "total_fluorescence": measured_value,
    "cycle_time_ms": elapsed_time
})

# Transition to Phase II (MOBO)
controller.start_phase(Phase.GLOBAL_MOBO)
```

---

## Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| TIMEOUT | Manager not responding | Check if manager is running |
| ZMQ_ERROR | Network error | Check network connectivity |
| VALIDATION_ERROR | Invalid parameter | Check parameter ranges |
| INVALID_MODE | Invalid mode change | Check current mode |
| UNKNOWN_ACTION | Unrecognized command | Check action name |
| CAMERA_NOT_AVAILABLE | Camera server down | Start camera server |

---

## Data Types

### IonParameters

| Field | Type | Description |
|-------|------|-------------|
| ion_id | int | Ion index (0-19) |
| pos_x | float | X position (pixels) |
| pos_y | float | Y position (pixels) |
| sig_x | float | Gaussian sigma X |
| sig_y | float | SHM turning point Y |

### FrameData

| Field | Type | Description |
|-------|------|-------------|
| timestamp | float | Unix timestamp |
| frame_id | str | Unique identifier |
| ion_count | int | Number of ions (0-20) |
| ions | List[IonParameters] | Per-ion data |
