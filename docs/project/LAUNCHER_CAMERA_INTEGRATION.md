# Launcher Camera Integration

**Date:** 2026-02-05  
**Purpose:** Document the integration of camera server into the unified launcher

---

## Summary

The camera server has been fully integrated into the MLS unified launcher. Now a single command starts all necessary programs including the camera server.

## Changes Made

### 1. Launcher Updates (`src/launcher.py`)

#### Service Configuration
- Camera service is now included in `SERVICES` dictionary
- Marked as `required: False` (system can run without camera hardware)
- Startup delay of 1.0s to ensure manager is ready first

#### Enhanced Service Management
- Added TCP health check support for services (like camera)
- Added `wait_for_ready()` method to verify port is listening before starting next service
- Improved error handling for optional vs required services

#### Startup Order
```
1. manager (5557)   - REQUIRED - ZMQ Control Manager
2. camera (5558)    - Optional - Camera TCP Server (waits for port ready)
3. flask (5000)     - REQUIRED - Main Dashboard
4. applet (5051)    - Optional - Applet Server
5. optimizer (5050) - Optional - Optimizer Server
```

### 2. Camera Server Updates (`src/hardware/camera/camera_server.py`)

#### New Commands
- `PING` - Health check for launcher monitoring (returns `PONG`)
- `READY` - Check if server is ready (returns `READY: yes/no`)

#### Documentation
- Updated module docstring with usage information
- Added command reference

### 3. Batch Scripts (`scripts/windows/`)

Created convenient Windows batch files:

| Script | Purpose |
|--------|---------|
| `start_all.bat` | Start all services including camera |
| `start_without_camera.bat` | Start all except camera (testing without hardware) |
| `start_manager_only.bat` | Start only the manager |
| `start_camera_only.bat` | Start only the camera server |
| `stop_all.bat` | Stop all services |
| `status.bat` | Check service status |

### 4. Documentation (`scripts/README.md`)

Created comprehensive documentation for all scripts.

---

## Usage

### Start All Services (Including Camera)

```bash
# Using Python
python -m src.launcher

# Using batch file (Windows)
scripts\windows\start_all.bat
```

### Start Without Camera (Testing)

```bash
# Using batch file (Windows)
scripts\windows\start_without_camera.bat

# Or manually exclude camera
python -m src.launcher --service manager,flask,applet,optimizer
```

### Start Individual Services

```bash
# Camera only
python -m src.launcher --service camera

# Manager only
python -m src.launcher --service manager

# Flask dashboard only
python -m src.launcher --service flask
```

### Check Status

```bash
python -m src.launcher --status
```

Output:
```
============================================================
MLS Service Status
============================================================
[RUNNING] manager         | Port: 5557 | PID: 12345
   URL: tcp://localhost:5557
   Status: running

[RUNNING] camera          | Port: 5558 | PID: 12346
   URL: tcp://localhost:5558
   Status: running

[RUNNING] flask           | Port: 5000 | PID: 12347
   URL: http://localhost:5000
   Status: running
...
```

### Stop All Services

```bash
# Using Python
python -m src.launcher --stop

# Using batch file
scripts\windows\stop_all.bat
```

---

## Service Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                     SERVICE HIERARCHY                        │
└─────────────────────────────────────────────────────────────┘

manager (5557) [REQUIRED]
    │
    ├── camera (5558) [Optional]
    │       └─ Can run without hardware (will fail gracefully)
    │
    ├── flask (5000) [REQUIRED]
    │       └─ Requires manager
    │
    ├── applet (5051) [Optional]
    │       └─ Requires manager, flask
    │
    └── optimizer (5050) [Optional]
            └─ Requires manager, flask
```

---

## Health Checks

The launcher now performs health checks for TCP-based services:

1. **Process Check** - Verifies the process is running
2. **Port Check** - Attempts TCP connection to verify port is listening
3. **Ready Wait** - Waits up to 30 seconds for service to be ready

If an optional service (like camera) fails:
- Warning is logged
- Other services continue starting
- System remains operational

If a required service (like manager) fails:
- Error is logged
- All services are stopped
- Launcher exits with error code

---

## Configuration

### Auto-Start Settings

Camera auto-start can be controlled via `config/config.yaml`:

```yaml
profiles:
  development:
    camera:
      auto_start: false      # Don't auto-start in development
      
  production:
    camera:
      auto_start: true       # Auto-start in production
```

### Required vs Optional Services

Modify `src/launcher.py` to change service requirements:

```python
SERVICES = {
    'camera': {
        'required': False,    # Change to True if camera is mandatory
        ...
    }
}
```

---

## Troubleshooting

### Camera Fails to Start

If camera hardware is not available:

```bash
# Option 1: Use batch file
scripts\windows\start_without_camera.bat

# Option 2: Exclude camera from command
python -m src.launcher --service manager,flask,applet,optimizer
```

### Port Already in Use

Check what's using the port:

```cmd
netstat -ano | findstr :5558
```

Kill the process:

```cmd
taskkill /PID <pid> /F
```

### View Logs

- `logs/launcher.log` - Launcher activity
- `logs/camera.log` - Camera server logs
- `logs/manager.log` - Control manager logs

---

## Migration from Separate Camera Startup

### Old Way (Before)

```bash
# Terminal 1
python -m src.server.manager.manager

# Terminal 2
python -m src.hardware.camera.camera_server

# Terminal 3
python -m src.server.api.flask_server
```

### New Way (After)

```bash
# Single command starts everything
python -m src.launcher

# Or use batch file
cripts\windows\start_all.bat
```

---

## Technical Details

### Service Manager Enhancements

```python
class ServiceManager:
    def check_health(self) -> bool:
        """Check process health and TCP port connectivity."""
        
    def wait_for_ready(self, timeout: float = 30.0) -> bool:
        """Wait for TCP port to be listening."""
```

### Camera Server Protocol

The camera server now supports health check commands:

```python
# Health check
client.send(b"PING")
response = client.recv(1024)  # b"PONG\n"

# Ready check
client.send(b"READY")
response = client.recv(1024)  # b"READY: yes\n" or b"READY: busy\n"
```

---

## Future Improvements

1. **Service Dependencies** - Explicit dependency graph instead of hardcoded order
2. **Docker Support** - Container orchestration for each service
3. **Web UI for Launcher** - Browser-based service management
4. **Auto-Restart Policy** - Configurable restart strategies per service
5. **Service Discovery** - Dynamic port allocation

---

**Last Updated:** 2026-02-05
