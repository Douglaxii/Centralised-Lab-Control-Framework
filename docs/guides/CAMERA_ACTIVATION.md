# Camera Infinity Mode Activation System

## Overview

This document describes the camera infinity mode activation system implemented in the MLS (Multi-Level System) framework. This system enables automatic camera recording when the manager starts, with frame processing and ion data extraction.

## Architecture

The camera activation system follows a multi-layer communication pattern:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CAMERA ACTIVATION FLOW                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐     ZMQ      ┌──────────────┐     TCP      ┌─────────────────┐ │
│  │   ARTIQ     │◄────────────►│   Manager    │◄────────────►│  Camera Server  │ │
│  │   Worker    │   Command    │  (Python)    │   Command    │    (TCP 5558)   │ │
│  └──────┬──────┘              └──────┬───────┘              └────────┬────────┘ │
│         │                            │                               │          │
│         │ TTL Trigger                │ Auto-start                    │ DCAM API │
│         ▼                            ▼                               ▼          │
│  ┌─────────────┐              ┌──────────────┐              ┌─────────────────┐ │
│  │   Camera    │              │   Flask      │              │   Hamamatsu     │ │
│  │  Hardware   │              │   Server     │              │     CCD         │ │
│  │  (TTL4)     │              │  (HTTP 5000) │              │   (DCIMG)       │ │
│  └─────────────┘              └──────┬───────┘              └────────┬────────┘ │
│                                      │                               │          │
│                                      │ MJPEG Stream                  │ Frames   │
│                                      ▼                               ▼          │
│                               ┌──────────────┐              ┌─────────────────┐ │
│                               │   Browser    │              │  Frame Files    │ │
│                               │   Client     │              │  (JPG/DCIMG)    │ │
│                               └──────────────┘              └─────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Frame Processing Pipeline

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Raw Camera     │    │   Image Handler │    │  Processed      │
│  Frames         │───►│   (Analysis)    │───►│  Frames         │
│  (DCIMG/JPG)    │    │                 │    │  (Labelled)     │
└─────────────────┘    └────────┬────────┘    └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   Ion Data      │
                       │   (JSON)        │
                       └─────────────────┘
```

### Directory Structure

```
E:/Data/
├── jpg_frames/                    # Raw JPG frames from camera
│   └── YYMMDD/
│       └── frameXXXX_YYYY-MM-DD_HH-MM-SS_mmmmmm.jpg
├── jpg_frames_labelled/           # Processed frames with overlays
│   └── YYMMDD/
│       └── frameXXXX_YYYY-MM-DD_HH-MM-SS_mmmmmm_labelled.jpg
├── ion_data/                      # Ion position and fit data
│   └── YYMMDD/
│       └── ion_data_YYYY-MM-DD_HH-MM-SS_mmmmmm.json
└── telemetry/                     # Other telemetry data
    ├── wavemeter/
    ├── smile/
    └── camera/
```

## JSON Data Format

### Ion Data JSON Structure

```json
{
    "timestamp": "2026-02-02T14:30:15.123456",
    "frame_number": 1234,
    "ions": {
        "ion_1": {
            "pos_x": 320.5,
            "pos_y": 240.3,
            "sig_x": 15.2,
            "R_y": 8.7
        },
        "ion_2": {
            "pos_x": 350.2,
            "pos_y": 245.1,
            "sig_x": 14.8,
            "R_y": 8.5
        }
    },
    "fit_quality": 0.95,
    "processing_time_ms": 45.2
}
```

### Alternative Format (per-frame array)

```json
{
    "timestamp": "2026-02-02T14:30:15.123456",
    "frames": [
        {
            "frame_id": 1234,
            "ions": {
                "ion_1": {"pos_x": 320.5, "pos_y": 240.3, "sig_x": 15.2, "R_y": 8.7},
                "ion_2": {"pos_x": 350.2, "pos_y": 245.1, "sig_x": 14.8, "R_y": 8.5}
            }
        }
    ]
}
```

## Communication Protocol

### 1. Manager to Camera Server (TCP)

The Manager uses the `CameraInterface` class to communicate with the camera server:

```python
# Commands
START      - Start single recording (DCIMG + JPG)
START_INF  - Start infinite capture mode
STOP       - Stop current capture
STATUS     - Get camera status
EXP_ID:id  - Set experiment ID for metadata
```

### 2. Manager to ARTIQ Worker (ZMQ PUB/SUB)

The Manager publishes commands to ARTIQ workers:

```json
{
    "type": "START_CAMERA_INF",
    "values": {},
    "exp_id": "exp_20260202_143015",
    "timestamp": 1706884215.123
}
```

### 3. ARTIQ Worker to Manager (ZMQ PUSH/PULL)

ARTIQ workers push status updates:

```json
{
    "timestamp": 1706884215.456,
    "source": "ARTIQ",
    "category": "STATUS",
    "payload": {
        "status": "CAMERA_TRIGGERED",
        "exp_id": "exp_20260202_143015"
    },
    "exp_id": "exp_20260202_143015"
}
```

### 4. Flask to Manager (ZMQ REQ/REP)

Flask uses request-reply pattern to send commands to Manager:

```json
// Request
{
    "action": "START_CAMERA",
    "source": "FLASK",
    "mode": "infinite"
}

// Response
{
    "status": "success",
    "camera_active": true,
    "mode": "infinite"
}
```

## Activation Sequence

### Automatic Start (Manager Launch)

1. **Manager Initialization**
   ```python
   manager = ControlManager()
   manager._init_camera()  # Creates CameraInterface
   ```

2. **Auto-start Camera**
   ```python
   if config.get('camera.auto_start', True):
       manager.camera.start_recording(mode='inf')
   ```

3. **Signal ARTIQ Worker**
   ```python
   manager.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
   manager.pub_socket.send_json({
       "type": "START_CAMERA_INF",
       "timestamp": time.time()
   })
   ```

4. **ARTIQ Worker Response**
   ```python
   def _process_commands(self):
       if cmd_type == "START_CAMERA_INF":
           # Camera already started by manager
           # Just acknowledge
           self._send_status("CAMERA_INF_ACK", {})
   ```

### Manual Start (via Flask)

1. **HTTP Request**
   ```
   POST /api/camera/start
   {"mode": "infinite"}
   ```

2. **Flask Handler**
   ```python
   @app.route('/api/camera/start', methods=['POST'])
   def start_camera():
       resp = send_to_manager({
           "action": "START_CAMERA",
           "source": "FLASK",
           "mode": "infinite"
       })
       return jsonify(resp)
   ```

3. **Manager Handler**
   ```python
   def handle_request(self, req):
       if action == "START_CAMERA":
           mode = req.get("mode", "inf")
           success = self.camera.start_recording(mode=mode)
           return {"status": "success" if success else "error"}
   ```

## Hardware Trigger

### TTL Trigger from ARTIQ

The ARTIQ worker can trigger individual frames via TTL pulse:

```python
@kernel
def trigger_camera_ttl(self):
    """Send TTL pulse to trigger camera."""
    self.cam.trigger(100.0)  # 100us pulse
```

This is used when:
- Synchronizing camera with other hardware events
- Triggering specific frames during experiments
- Coordinated multi-device acquisitions

## Configuration

### settings.yaml

```yaml
# Camera configuration
camera:
  enabled: true
  auto_start: true           # Start camera when manager launches
  host: "127.0.0.1"
  port: 5558
  
  # Frame paths
  raw_frames_path: "E:/Data/jpg_frames"
  labelled_frames_path: "E:/Data/jpg_frames_labelled"
  ion_data_path: "E:/Data/ion_data"
  
  # Capture settings
  infinite_mode:
    max_frames: 100          # Circular buffer size
    exposure_ms: 300
    trigger_mode: "software"
  
  # Image processing
  processing:
    enabled: true
    roi_x_start: 180
    roi_x_finish: 220
    roi_y_start: 425
    roi_y_finish: 495
    filter_radius: 6

# Network ports
network:
  master_ip: "127.0.0.1"
  cmd_port: 5555             # Manager PUB -> Worker SUB
  data_port: 5556            # Worker PUSH -> Manager PULL
  client_port: 5557          # Flask REQ -> Manager REP
  camera_port: 5558          # Manager -> Camera Server
```

## API Reference

### CameraInterface (Manager)

```python
class CameraInterface:
    def __init__(self, host='127.0.0.1', port=5558)
    def start_recording(mode='inf', exp_id=None) -> bool
    def stop_recording() -> bool
    def get_status() -> Dict[str, Any]
```

### Camera Fragment (ARTIQ)

```python
class Camera(Fragment):
    def trigger(self, pulse_duration_us: float = 100.0)
    def trigger_short(self, pulse_duration_us: float = 10.0)
```

### Flask Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/api/camera/start` | POST | Start camera recording |
| `/api/camera/stop` | POST | Stop camera recording |
| `/api/camera/status` | GET | Get camera status |
| `/api/camera/settings` | POST | Update camera settings |
| `/video_feed` | GET | MJPEG video stream |

## Safety Considerations

1. **Kill Switch Integration**: Camera can be stopped via manager's kill switch
2. **Resource Cleanup**: Frames are automatically cleaned up in infinite mode
3. **Error Handling**: Camera errors don't crash the manager
4. **Watchdog**: Camera server has internal watchdog for freeze detection

## Troubleshooting

### Camera not starting automatically

Check manager logs for:
- Camera server connection errors
- Port conflicts (5558)
- Configuration `camera.auto_start` setting

### No frames in video feed

Verify:
- Camera server is running: `python server/cam/camera_server.py`
- Frame directories exist and are writable
- Image handler is processing frames

### TTL trigger not working

Check:
- ARTIQ device database has `camera_trigger` defined
- TTL cable is connected
- Camera is in external trigger mode (if using hardware trigger)

## Migration from mhi_cam

### Key Differences

| Feature | mhi_cam | MLS |
|---------|---------|-----|
| Flask server | Full control | View-only (manager controls) |
| Camera start | Manual button | Auto + Manual |
| Frame paths | Y:/Stein/Server/ | E:/Data/ |
| Analysis | Separate server | Integrated |
| JSON format | Custom | Standardized |

### Backward Compatibility

The MLS system maintains compatibility with mhi_cam's:
- DCAM API interface
- TCP command protocol
- Frame file formats
