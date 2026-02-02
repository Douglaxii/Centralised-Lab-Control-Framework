# User Guides

Step-by-step guides for common MLS tasks.

## Available Guides

| Guide | Description |
|-------|-------------|
| [Conda Setup](CONDA_SETUP.md) | Environment installation and configuration |
| [Camera Activation](CAMERA_ACTIVATION.md) | Camera system operation and setup |
| [Safety Kill Switch](SAFETY_KILL_SWITCH.md) | Safety system operation and procedures |

## Quick Reference

### Starting the System

```bash
# Start all services
python launcher.py

# Or individually:
python -m server.communications.manager
python -m server.Flask.flask_server
python -m server.cam.camera_server
```

### Accessing Services

- **Web Dashboard:** http://localhost:5000
- **Health Check:** http://localhost:5000/health
- **API Status:** http://localhost:5000/api/status

### Common Commands

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

## Safety First

⚠️ **Always review the [Safety Kill Switch Guide](SAFETY_KILL_SWITCH.md) before operating the system.**

Key safety limits:
- **Piezo Output:** 10 seconds maximum ON time
- **E-Gun:** 30 seconds maximum ON time
- **Pressure:** Automatic shutdown above threshold
