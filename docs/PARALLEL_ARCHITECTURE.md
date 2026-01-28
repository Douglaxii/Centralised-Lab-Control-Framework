# Parallel Execution Architecture

## Overview

This document describes the optimized architecture for running **Camera Server**, **Control Manager**, and **Flask Web Server** in parallel on a single PC.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Single PC Architecture                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐            │
│  │   Camera     │     │   Manager    │     │    Flask     │            │
│  │   Server     │     │              │     │   Server     │            │
│  │  (Port 5558) │     │ (Port 5557)  │     │ (Port 5000)  │            │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘            │
│         │                    │                    │                    │
│         │  TCP (frames)      │  ZMQ (commands)    │  HTTP (web)        │
│         │                    │                    │                    │
│  ┌──────▼────────────────────▼────────────────────▼───────┐            │
│  │                    Shared Resources                     │            │
│  │  ┌─────────────────────────────────────────────────┐   │            │
│  │  │           Shared Telemetry Storage               │   │            │
│  │  │  (Python multiprocessing shared memory)          │   │            │
│  │  └─────────────────────────────────────────────────┘   │            │
│  │                                                         │            │
│  │  ┌─────────────────────────────────────────────────┐   │            │
│  │  │           Y:/Xi/Data/ (Network Drive)           │   │            │
│  │  │  - jpg_frames/      (raw camera frames)         │   │            │
│  │  │  - jpg_frames_labelled/  (processed frames)     │   │            │
│  │  │  - telemetry/       (LabVIEW data files)        │   │            │
│  │  └─────────────────────────────────────────────────┘   │            │
│  └─────────────────────────────────────────────────────────┘            │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │              Unified Launcher (launcher.py)              │            │
│  │         Process management, health monitoring            │            │
│  └─────────────────────────────────────────────────────────┘            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### 1. Camera Server (`server/cam/camera_server.py`)

**Purpose**: Receive camera frames via TCP, process images, save results

**Ports**:
- `5558` - Frame data (TCP)
- `5559` - Commands (TCP)

**Key Optimizations**:
- Producer-consumer pattern with bounded queue (size 50)
- Dedicated thread for image processing
- JPG compression at 85% quality
- Date-organized directory structure

**Data Flow**:
```
Camera Device → TCP:5558 → [Queue] → Image Processor → Y:/Xi/Data/jpg_frames_labelled/
                                                    ↓
                                              Flask (streaming)
```

### 2. Control Manager (`server/communications/manager.py`)

**Purpose**: Coordinate hardware, algorithms, and data collection

**Ports**:
- `5555` - Commands to ARTIQ (ZMQ PUB)
- `5556` - Data from ARTIQ (ZMQ PULL)
- `5557` - Flask requests (ZMQ REP)

**Key Optimizations**:
- ZMQ IPC transport for same-PC (faster than TCP)
- File polling with debouncing (1s interval)
- Shared telemetry storage (no file I/O for Flask)
- Async command processing

**Data Flow**:
```
Flask → ZMQ:5557 → Manager → ZMQ:5555 → ARTIQ Worker
                    ↑
LabVIEW Files ──────┘ (Y:/Xi/Data/telemetry/)
```

### 3. Flask Server (`server/Flask/flask_server.py`)

**Purpose**: Web UI for control and visualization

**Ports**:
- `5000` - HTTP web interface

**Key Optimizations**:
- Multi-threaded WSGI server
- Server-Sent Events (SSE) for real-time data
- Direct memory access to telemetry (no IPC overhead)
- Efficient frame streaming from disk

**Data Flow**:
```
Browser → HTTP:5000 → Flask → Shared Telemetry (memory)
                          ↓
                    Y:/Xi/Data/jpg_frames_labelled/ (MJPEG stream)
```

## Inter-Process Communication (IPC)

### Method 1: Shared Memory (Telemetry)

Used for high-frequency telemetry data (laser frequency, PMT counts, etc.)

```python
# data_server.py - Shared storage
_shared_telemetry_data = {
    "laser_freq": deque(maxlen=1000),  # Thread-safe
    "pmt": deque(maxlen=1000),
    ...
}
_telemetry_lock = threading.RLock()
```

**Access Pattern**:
- Manager writes (acquires lock)
- Flask reads (acquires lock)
- Zero file I/O for telemetry

### Method 2: Filesystem (Images)

Used for large binary data (camera frames)

```
Y:/Xi/Data/
├── jpg_frames/              # Raw frames (optional, for debugging)
├── jpg_frames_labelled/     # Processed frames (Flask streams from here)
└── telemetry/               # LabVIEW data files
```

**Access Pattern**:
- Camera Server writes
- Flask reads (streaming)
- LabVIEW writes
- Manager reads

### Method 3: ZMQ (Commands)

Used for reliable command/control

```python
# ZMQ sockets (same-PC optimized)
ctx = zmq.Context()

# Flask → Manager (REQ/REP)
socket = ctx.socket(zmq.REQ)
socket.connect("tcp://127.0.0.1:5557")  # Localhost for speed

# Manager → ARTIQ (PUB/SUB)
socket = ctx.socket(zmq.PUB)
socket.bind("tcp://127.0.0.1:5555")
```

## Unified Launcher

The launcher (`launcher.py`) provides:

### Features

| Feature | Description |
|---------|-------------|
| **Staggered Startup** | Services start in order: Camera → Manager → Flask |
| **Health Monitoring** | Automatic restart on failure (max 3 restarts/min) |
| **Process Management** | Clean shutdown, signal handling |
| **Status Reporting** | Real-time status of all services |
| **Log Aggregation** | Centralized logging with rotation |

### Usage

```bash
# Start all services
python launcher.py

# Start in background
python launcher.py --daemon

# Check status
python launcher.py --status

# Restart all
python launcher.py --restart

# Stop all
python launcher.py --stop

# Interactive mode
python launcher.py --interactive
```

### Interactive Commands

```
launcher> status       # Show service status
launcher> restart camera  # Restart camera server
launcher> stop         # Stop all services
launcher> quit         # Stop and exit
```

## Performance Optimizations

### 1. Memory Management

**Shared Telemetry Buffers**:
- Pre-allocated deques with maxlen
- Thread-safe RLock
- No dynamic allocation during operation

**Image Processing**:
- Bounded queue prevents memory bloat
- In-place image operations where possible
- Explicit cache cleanup

### 2. CPU Optimization

**Thread Priorities** (Windows):
```python
# Manager gets higher priority for responsive control
manager_thread = threading.Thread(target=manager_loop)
if os.name == 'nt':
    # Set above-normal priority
    pass  # Implementation in manager.py
```

**Frame Skipping**:
- Camera can skip frames if processing falls behind
- Configurable: `skip_frames: 0` (process all) or `skip_frames: 2` (process every 3rd)

### 3. I/O Optimization

**File Watching**:
```python
# Debounced file polling (reduces duplicate reads)
if time_since_last_check > poll_interval:
    new_files = get_new_files()
    if new_files:
        process_files(new_files)
```

**Batch Processing**:
- Read multiple files in one batch
- Reduces filesystem overhead

### 4. Network Optimization

**Localhost Binding**:
```yaml
# config/parallel_config.yaml
manager:
  bind_host: "127.0.0.1"  # Only local connections
```

**ZMQ IPC Transport** (Linux/Mac):
```python
# Faster than TCP for same-PC
socket.bind("ipc:///tmp/manager.sock")
```

## Startup Sequence

```
Time →

T+0.0s  ┌─────────────────────────────────────┐
        │  Launcher starts                    │
        └─────────────────────────────────────┘

T+0.1s  ┌─────────────────────────────────────┐
        │  Camera Server starts (Port 5558)   │
        │  - Creates output directories       │
        │  - Starts processor thread          │
        │  - Starts command thread            │
        │  - Listens for connections          │
        └─────────────────────────────────────┘

T+1.1s  ┌─────────────────────────────────────┐
        │  Manager starts (Port 5557)         │
        │  - Initializes ZMQ sockets          │
        │  - Starts LabVIEW file reader       │
        │  - Starts background threads        │
        │  - Waits for Flask connections      │
        └─────────────────────────────────────┘

T+2.1s  ┌─────────────────────────────────────┐
        │  Flask starts (Port 5000)           │
        │  - Loads configuration              │
        │  - Connects to Manager              │
        │  - Starts HTTP server               │
        │  - Ready for browser connections    │
        └─────────────────────────────────────┘

T+3.0s  All services ready
```

## Resource Usage

### Typical Resource Consumption

| Service | CPU | Memory | Network | Disk I/O |
|---------|-----|--------|---------|----------|
| Camera | 15-30% | 200-500 MB | Low (TCP) | High (JPG writes) |
| Manager | 5-10% | 50-100 MB | Low (ZMQ) | Low (file polling) |
| Flask | 5-15% | 100-200 MB | Medium (HTTP) | Low (frame reads) |
| **Total** | 25-55% | 350-800 MB | Medium | High |

### Scaling Considerations

**If CPU-bound**:
- Reduce camera frame rate
- Increase `skip_frames`
- Lower JPEG quality

**If Memory-bound**:
- Reduce telemetry buffer size
- Reduce camera queue size
- Enable more aggressive GC

**If I/O-bound**:
- Use SSD for `Y:/Xi/Data/`
- Enable image compression
- Reduce file polling frequency

## Troubleshooting

### Services Won't Start

```bash
# Check port conflicts
netstat -an | findstr "5558 5559 5000"

# Check logs
tail -f logs/launcher.log
tail -f logs/manager.log

# Manual start for debugging
python server/cam/camera_server.py
```

### High CPU Usage

```bash
# Check which service is using CPU
python launcher.py --status

# Enable profiling
export MLS_PROFILE=1
python launcher.py
```

### Memory Leaks

```bash
# Monitor memory usage
python -m memory_profiler launcher.py

# Check for circular references
python -c "import gc; gc.set_debug(gc.DEBUG_LEAK)"
```

### Communication Issues

```bash
# Test ZMQ connectivity
python -c "
import zmq
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.connect('tcp://127.0.0.1:5557')
sock.send_json({'action': 'STATUS'})
print(sock.recv_json())
"

# Test file permissions
touch Y:/Xi/Data/test.txt
```

## Development Workflow

### 1. Start Development Mode

```bash
# Terminal 1: Start all services
python launcher.py --interactive

# Or start individually for debugging:
python server/cam/camera_server.py
python server/communications/manager.py
python server/Flask/flask_server.py
```

### 2. Hot Reload

```bash
# Flask auto-reloads on code changes
# Camera and Manager require restart

launcher> restart camera
launcher> restart manager
```

### 3. Debugging

```bash
# Enable debug logging
export MLS_LOG_LEVEL=DEBUG
python launcher.py

# Or modify config/parallel_config.yaml
logging:
  level: "DEBUG"
```

## Production Deployment

### 1. Systemd Service (Linux)

```ini
# /etc/systemd/system/lab-control.service
[Unit]
Description=Lab Control System
After=network.target

[Service]
Type=simple
User=labuser
WorkingDirectory=/opt/lab-control
ExecStart=/usr/bin/python3 launcher.py --daemon
ExecStop=/usr/bin/python3 launcher.py --stop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Windows Service

```powershell
# Use NSSM (Non-Sucking Service Manager)
nssm install LabControl "C:\Python39\python.exe" "C:\LabControl\launcher.py --daemon"
nssm start LabControl
```

### 3. Docker (Optional)

```dockerfile
# Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 5000 5555 5556 5557 5558
CMD ["python", "launcher.py", "--daemon"]
```

## Summary

This architecture provides:

1. **Efficiency**: Optimized for same-PC execution with shared memory
2. **Reliability**: Health monitoring and automatic restart
3. **Simplicity**: Single launcher manages all services
4. **Observability**: Centralized logging and status reporting
5. **Flexibility**: Easy to scale across multiple PCs if needed

The key insight is using the right IPC mechanism for each data type:
- **Small, frequent data** → Shared memory (telemetry)
- **Large binary data** → Filesystem (images)
- **Commands** → ZMQ (reliable, ordered)
