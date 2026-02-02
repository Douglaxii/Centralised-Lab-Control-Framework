# API Documentation

Complete API documentation for the Multi-Ion Lab System.

## Overview

The MLS provides multiple APIs for different use cases:

| API | Protocol | Port | Use Case |
|-----|----------|------|----------|
| **REST API** | HTTP | 5000 | Web UI, external scripts |
| **ZMQ Protocol** | ZMQ | 5555-5557 | Low-latency control |
| **Python API** | Python | - | Application development |

## Quick Start

### HTTP REST API

```bash
# Check system health
curl http://localhost:5000/health

# Get system status
curl http://localhost:5000/api/status

# Set electrode voltages
curl -X POST http://localhost:5000/api/set \
  -H "Content-Type: application/json" \
  -d '{"device": "trap", "value": [10, 10, 6, 37]}'
```

### ZMQ API

```python
import zmq
import json

ctx = zmq.Context()
socket = ctx.socket(zmq.REQ)
socket.connect("tcp://localhost:5557")

# Set parameters
socket.send_json({
    "action": "SET",
    "source": "USER",
    "params": {"ec1": 10.0, "ec2": 10.0}
})
response = socket.recv_json()
```

### Python API

```python
from core import get_config, get_tracker

# Get configuration
config = get_config()

# Track experiments
tracker = get_tracker()
exp = tracker.create_experiment(parameters={"target": 307})
```

## Contents

- [Complete API Reference](reference.md) - Detailed API documentation

## API Categories

### Hardware Control
- Setting electrode voltages
- RF voltage control
- Piezo control
- DDS frequency setting
- Toggle control (oven, B-field, etc.)

### Experiments
- Running secular sweeps
- Secular frequency comparison
- Optimization control

### Safety
- Kill switch status
- Emergency stop
- Safety mode toggle

### Data
- Real-time telemetry streaming
- Camera video feed
- Recent data queries
