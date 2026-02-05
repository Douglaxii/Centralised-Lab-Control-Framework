# MLS Scripts

This directory contains utility scripts for the Mixed-Species Loading System (MLS).

## Windows Batch Scripts (`windows/`)

### Quick Start

| Script | Purpose |
|--------|---------|
| `start_all.bat` | Start all MLS services (Manager, Camera, Flask, Applet, Optimizer) |
| `start_without_camera.bat` | Start all services except camera (useful for testing without hardware) |
| `start_manager_only.bat` | Start only the Control Manager |
| `start_camera_only.bat` | Start only the Camera Server |
| `stop_all.bat` | Stop all running MLS services |
| `status.bat` | Check status of all services |

### Usage

Double-click any batch file, or run from command prompt:

```cmd
scripts\windows\start_all.bat
```

## Environment Switching

Switch between development (laptop) and production (manager PC) environments:

```bash
# Show current environment
python scripts/switch_env.py

# Switch to development
python scripts/switch_env.py dev

# Switch to production
python scripts/switch_env.py prod
```

## Setup Scripts (`setup/`)

| Script | Purpose |
|--------|---------|
| `setup_manager_pc.py` | Initial setup for the manager PC |
| `validate_setup.py` | Validate installation and dependencies |
| `environment.yml` | Conda environment specification |

## Advanced Usage

### Start specific services

```bash
# Using Python directly
python -m src.launcher --service manager    # Start only manager
python -m src.launcher --service camera     # Start only camera
python -m src.launcher --service flask      # Start only Flask dashboard

# Start all services
python -m src.launcher

# Start in daemon mode (background)
python -m src.launcher --daemon

# Check status
python -m src.launcher --status

# Stop all services
python -m src.launcher --stop

# Restart all services
python -m src.launcher --restart
```

### Service Dependencies

```
manager (5557) <- Required by all other services
    ↓
camera (5558) <- Optional, can run without hardware
    ↓
flask (5000) <- Requires manager
    ↓
applet (5051) <- Requires manager, flask
optimizer (5050) <- Requires manager, flask
```

## Service Ports

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| Control Manager | 5557 | ZMQ REQ/REP | Central command hub |
| Camera Server | 5558 | TCP | Hamamatsu CCD camera control |
| Flask Dashboard | 5000 | HTTP | Main web interface |
| Applet Server | 5051 | HTTP | Experiment applets |
| Optimizer Server | 5050 | HTTP | Bayesian optimization UI |

## Troubleshooting

### Camera fails to start

If camera hardware is not connected, use:
```bash
python -m src.launcher --service manager,flask,applet,optimizer
# OR
scripts\windows\start_without_camera.bat
```

### Port already in use

Check what's using the port:
```cmd
netstat -ano | findstr :5557
```

Then kill the process:
```cmd
taskkill /PID <pid> /F
```

### View service logs

Logs are stored in `logs/` directory:
- `logs/launcher.log` - Launcher activity
- `logs/manager.log` - Control Manager
- `logs/camera.log` - Camera Server
- `logs/flask.log` - Flask Dashboard
