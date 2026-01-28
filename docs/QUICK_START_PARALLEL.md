# Quick Start - Parallel Execution

## Prerequisites

1. **Python 3.8+** installed
2. **Y: drive mapped** to network storage (or create local folder)
3. **Dependencies installed**:
   ```bash
   pip install -r requirements.txt
   ```

## Quick Start

### 1. Single Command Start

```bash
# Start all services interactively
python launcher.py

# Or start in background
python launcher.py --daemon
```

### 2. Verify Status

```bash
# Check all services are running
python launcher.py --status
```

Expected output:
```
======================================================================
Service         Status       PID      Port   Health   Uptime    
----------------------------------------------------------------------
Camera          running      12345    5558   ✓        5m30s     
Manager         running      12346    5557   ✓        5m29s     
Flask           running      12347    5000   ✓        5m28s     
======================================================================
```

### 3. Access Web Interface

Open browser: http://localhost:5000

## Interactive Commands

When running interactively:

```
launcher> status              # Show current status
launcher> restart camera      # Restart camera server
launcher> restart manager     # Restart control manager
launcher> restart flask       # Restart flask server
launcher> restart             # Restart all services
launcher> stop                # Stop all services
launcher> quit                # Stop and exit
launcher> help                # Show help
```

## Common Operations

### Restart After Code Changes

```bash
# Full restart
launcher> restart

# Or restart just the changed service
launcher> restart flask
```

### Check Logs

```bash
# All logs in one place
tail -f logs/launcher.log

# Individual service logs
tail -f logs/camera.log
tail -f logs/manager.log
tail -f logs/flask.log
```

### Stop Everything

```bash
# From interactive mode
launcher> quit

# Or from another terminal
python launcher.py --stop

# Or kill the process
Ctrl+C (when in interactive mode)
```

## Troubleshooting

### Port Already in Use

```bash
# Find what's using port 5000
# Windows:
netstat -ano | findstr "5000"
taskkill /PID <PID> /F

# Linux/Mac:
lsof -i :5000
kill -9 <PID>
```

### Services Not Starting

1. **Check Python path**:
   ```bash
   python -c "import sys; print(sys.path)"
   ```

2. **Check imports**:
   ```bash
   python -c "from server.cam.camera_server import main; print('OK')"
   ```

3. **Check Y: drive**:
   ```bash
   # Windows
   dir Y:\Xi\Data
   
   # Or create test folder
   mkdir Y:\Xi\Data\telemetry
   ```

### High CPU/Memory

```bash
# Check resource usage
python launcher.py --status

# Reduce camera load
# Edit config/parallel_config.yaml:
camera:
  skip_frames: 2          # Process every 3rd frame
  jpeg_quality: 70        # Lower quality
```

### Flask Can't Connect to Manager

```bash
# Test ZMQ connection
python -c "
import zmq
ctx = zmq.Context()
s = ctx.socket(zmq.REQ)
s.connect('tcp://127.0.0.1:5557')
s.send_json({'action': 'STATUS'})
print(s.recv_json())
"
```

## Development Mode

### Start Individual Services

For debugging individual components:

```bash
# Terminal 1: Camera
python server/cam/camera_server.py

# Terminal 2: Manager
python server/communications/manager.py

# Terminal 3: Flask
python server/Flask/flask_server.py
```

### Enable Debug Logging

```bash
# Set environment variable
export MLS_LOG_LEVEL=DEBUG  # Linux/Mac
set MLS_LOG_LEVEL=DEBUG     # Windows

python launcher.py
```

### Hot Reload (Flask only)

```bash
# Flask auto-reloads on code changes
# Other services require manual restart
export FLASK_ENV=development
python server/Flask/flask_server.py
```

## Configuration

### Change Ports

Edit `config/settings.yaml`:

```yaml
network:
  camera_port: 5558      # Camera server
  client_port: 5557      # Manager

flask:
  port: 5000             # Web interface
```

### Change Data Path

```yaml
paths:
  output_base: "Y:/Xi/Data"  # Or local path
```

### Performance Tuning

```yaml
optimization:
  memory:
    telemetry_buffer_size: 500      # Reduce memory
  
  cpu:
    camera_thread_priority: "low"   # Reduce CPU
```

## Production Deployment

### Windows Service

```powershell
# Using NSSM
nssm install LabControl python "C:\path\to\launcher.py --daemon"
nssm set LabControl AppDirectory "C:\path\to\lab-control"
nssm start LabControl
```

### Linux Systemd

```bash
sudo cp scripts/lab-control.service /etc/systemd/system/
sudo systemctl enable lab-control
sudo systemctl start lab-control
sudo systemctl status lab-control
```

### Auto-start on Boot (Windows)

```powershell
# Create scheduled task
$action = New-ScheduledTaskAction -Execute "python" -Argument "C:\path\to\launcher.py --daemon"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "LabControl"
```

## API Endpoints

Once running, these endpoints are available:

| Endpoint | Description |
|----------|-------------|
| `http://localhost:5000/` | Main dashboard |
| `http://localhost:5000/api/status` | System status |
| `http://localhost:5000/api/telemetry/stream` | Real-time telemetry (SSE) |
| `http://localhost:5000/video_feed` | Camera stream (MJPEG) |

## Next Steps

1. **Configure LabVIEW** to send data to `Y:/Xi/Data/telemetry/`
2. **Connect camera** to send frames to TCP port 5558
3. **Open browser** to http://localhost:5000
4. **Read full documentation** in `docs/PARALLEL_ARCHITECTURE.md`
