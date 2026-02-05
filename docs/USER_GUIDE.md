# MLS User Guide

Complete guide for using the Multi-Ion Lab System (MLS).

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [System Operation](#system-operation)
3. [Safety Systems](#safety-systems)
4. [Camera Operation](#camera-operation)
5. [Bayesian Optimization](#bayesian-optimization)
6. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

- Python 3.11+
- Conda (recommended)

### Installation

```bash
# Clone and navigate to the project
cd mls

# Create conda environment
conda env create -f scripts/setup/environment.yml
conda activate mls

# Verify installation
python -c "import flask, zmq, numpy, cv2; print('All OK!')"
```

### Configuration

All configuration is in a single file: `config/config.yaml`

Select your environment:
```yaml
environment: development  # or "production"
```

Two profiles are provided:
- **`development`** - For laptop testing (local paths, debug logging, LabVIEW disabled)
- **`production`** - For lab PC (network drives, external triggers, LabVIEW enabled)

You can also set via environment variable:
```bash
set MLS_ENV=development    # Windows
export MLS_ENV=production  # Linux/Mac
```

Key settings to customize:
```yaml
profiles:
  development:
    network:
      master_ip: "192.168.56.101"  # Your ARTIQ IP
    
    paths:
      base: "./data"               # Your data directory
    
    services:
      flask:
        port: 5000                  # Web UI port
      optimizer:
        port: 5050                  # TuRBO UI port
      applet:
        port: 5051                  # Applet UI port
```

---

## System Operation

### Starting the System

```bash
# Start all services
python launcher.py

# Or start individually:
python -m src.server.manager.manager       # Control Manager
python -m src.server.api.flask_server      # Web UI
python -m src.hardware.camera.camera_server # Camera Server
```

### Accessing the Dashboard

| Service | URL |
|---------|-----|
| Web Dashboard | http://localhost:5000 |
| Health Check | http://localhost:5000/health |
| API Status | http://localhost:5000/api/status |

### Common API Commands

```bash
# Check system status
curl http://localhost:5000/api/status

# Set electrode voltages
curl -X POST http://localhost:5000/api/set \
  -H "Content-Type: application/json" \
  -d '{"device": "trap", "value": [10, 10, 6, 37]}'

# Trigger sweep
curl -X POST http://localhost:5000/api/sweep \
  -H "Content-Type: application/json" \
  -d '{"target_frequency_khz": 307, "span_khz": 40, "steps": 41}'
```

---

## Safety Systems

### Kill Switch System

The system implements a **triple-layer kill switch** for safety:

| Layer | Mechanism | Timeout |
|-------|-----------|---------|
| Software | Manager-enforced limits | 10s (piezo), 30s (e-gun) |
| Hardware | Independent watchdog | 15s (piezo), 35s (e-gun) |
| Emergency | Manual stop button | Immediate |

### Safety Limits

- **Piezo Output:** 10 seconds maximum ON time
- **E-Gun:** 30 seconds maximum ON time
- **Pressure:** Automatic shutdown above threshold

### Emergency Stop

```bash
# Via API
curl -X POST http://localhost:5000/api/kill

# Via Python
from src.server.manager.manager import ControlManager
manager = ControlManager()
manager.emergency_stop()
```

---

## Camera Operation

### Camera Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| Infinity | Continuous live view | Alignment, monitoring |
| Recording | Triggered capture | Experiments, sweeps |

### Activating Infinity Mode

```bash
# Start infinity mode
curl http://localhost:5000/camera/start_infinity

# Get live frame
curl http://localhost:5000/camera/get_last_frame

# Stop infinity mode
curl http://localhost:5000/camera/stop_infinity
```

### Recording Mode

```python
# Start recording with ROI
import requests

response = requests.post('http://localhost:5000/camera/start', json={
    'exposure_ms': 100,
    'roi': {'x': 500, 'y': 500, 'width': 200, 'height': 200},
    'trigger': 'ttl'
})
```

### Camera Parameters

| Parameter | Range | Default |
|-----------|-------|---------|
| Exposure | 1-10000 ms | 100 ms |
| ROI Width | 1-2048 px | 200 px |
| ROI Height | 1-2048 px | 200 px |

---

## Bayesian Optimization

### Two-Phase Optimizer

The system uses a two-phase Bayesian optimization approach:

1. **Phase I (TuRBO):** Fast local optimization
2. **Phase II (MOBO):** Multi-objective global optimization

### Running Optimization

```bash
# Access optimizer interface
http://localhost:5000/turbo

# Or programmatically
from src.optimizer.turbo import TuRBOOptimizer

optimizer = TuRBOOptimizer()
optimizer.run(target_frequency=307.0)
```

### Optimization Parameters

| Parameter | Description | Typical Range |
|-----------|-------------|---------------|
| target_frequency_khz | Target secular frequency | 300-400 kHz |
| span_khz | Sweep range | 20-50 kHz |
| steps | Number of points | 21-101 |
| batch_size | Parallel evaluations | 1-5 |

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection refused | Service not running | Check `launcher.py --status` |
| ZMQ timeout | Network issue | Verify IP in config |
| Camera not found | USB disconnected | Check camera connection |
| Slow response | High load | Check CPU/memory usage |

### Log Files

Check logs for detailed error information:

```bash
# View logs
tail -f logs/manager.log
tail -f logs/flask.log
tail -f logs/camera.log
```

### Diagnostic Commands

```bash
# Check server status
python launcher.py --status

# Test connections
python tools/check_server.py

# Verify configuration
python scripts/setup/validate_setup.py
```

### Port Conflicts

If ports are already in use:

```bash
# Find process using port
netstat -ano | findstr :5555

# Kill process (Windows)
taskkill /PID <PID> /F
```

---

## Support

For issues:
1. Check relevant section above
2. Review logs in `logs/` directory
3. Run diagnostics: `python launcher.py --status`
4. Contact system administrator

---

*Last Updated: 2026-02-05*
