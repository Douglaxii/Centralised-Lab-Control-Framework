# Camera Infinity Mode Implementation Summary

## Overview

This implementation adds comprehensive camera infinity mode support to the MLS (Multi-Level System) framework, replicating and extending the functionality from the original `mhi_cam` and `artiq` repositories.

## What Was Implemented

### 1. Documentation (`docs/guides/CAMERA_ACTIVATION.md`)
Comprehensive documentation covering:
- System architecture and data flow
- Communication protocols between components
- Activation sequences (automatic and manual)
- JSON data formats
- Configuration options
- API reference
- Migration guide from mhi_cam

### 2. ARTIQ Camera Fragment (`artiq/fragments/cam.py`)
Updated and extended the camera fragment with:
- **Camera class**: Basic TTL trigger control
  - `trigger()`: Send TTL pulse (default 100μs)
  - `trigger_short()`: Short pulse for sweeps (default 10μs)
  - `trigger_multiple()`: Multiple pulses with delays
  - HTTP-based camera control (start/stop infinity mode)
  - Camera settings configuration
  - Analysis parameter configuration
  
- **AutoCamera class**: Automated camera control
  - `boot_camera()`: Initialize and start recording
  - `boot_analysis()`: Configure and start image analysis
  - `save_close_analysis()`: Save and cleanup analysis
  - Automatic host_setup()/host_cleanup() integration

### 3. ARTIQ Worker (`artiq/experiments/artiq_worker.py`)
Enhanced the worker with camera command handling:
- `START_CAMERA_INF`: Handle camera infinity mode start
- `STOP_CAMERA`: Handle camera stop
- `CAMERA_SETTINGS`: Update camera configuration
- `CAMERA_TRIGGER`: Execute TTL trigger on hardware
- Heartbeat includes camera state

### 4. Manager (`server/communications/manager.py`)
Added camera auto-start functionality:
- `_auto_start_camera()`: Automatically start camera on manager launch
- Configuration-driven (`camera.auto_start`)
- Signals ARTIQ worker when camera is ready
- Sends initial TTL trigger if configured
- Camera status included in manager status response

### 5. Image Handler (`server/cam/image_handler.py`)
New module for frame processing:
- Reads raw JPG frames from `E:/Data/jpg_frames/`
- Detects ions using peak finding and Gaussian fitting
- Creates overlay images with ion markers
- Saves processed frames to `E:/Data/jpg_frames_labelled/`
- Saves ion data to JSON in `E:/Data/ion_data/`

**JSON Format:**
```json
{
    "timestamp": "2026-02-02T14:30:15.123456",
    "frame_number": 1234,
    "ions": {
        "ion_1": {"pos_x": 320.5, "pos_y": 240.3, "sig_x": 15.2, "R_y": 8.7}
    },
    "fit_quality": 0.95,
    "processing_time_ms": 45.2
}
```

### 6. Flask Routes (`server/Flask/flask_server.py`)
Added camera control API endpoints:
- `POST /api/camera/start`: Start camera recording
- `POST /api/camera/stop`: Stop camera recording
- `GET /api/camera/status`: Get camera status
- `POST /api/camera/trigger`: Send TTL trigger
- `GET/POST /api/camera/settings`: Get/set camera settings
- `GET /api/ion_data/latest`: Get latest ion position data

### 7. Configuration (`config/settings.yaml`)
Added camera configuration section:
```yaml
camera:
  auto_start: true
  mode: "inf"
  send_initial_trigger: true
  host: "127.0.0.1"
  port: 5558
  raw_frames_path: "E:/Data/jpg_frames"
  labelled_frames_path: "E:/Data/jpg_frames_labelled"
  ion_data_path: "E:/Data/ion_data"
  infinite_mode:
    max_frames: 100
    exposure_ms: 300
    trigger_mode: "software"
  processing:
    enabled: true
    roi: [180, 220, 425, 495]
    filter_radius: 6
```

## Communication Flow

### Auto-Start Sequence (Manager Launch)
```
1. Manager starts
   └── _init_camera() called
       └── CameraInterface connects to camera_server
       └── _auto_start_camera() called (if enabled)
           ├── Sends START_INF to camera_server (TCP)
           ├── Publishes START_CAMERA_INF to ARTIQ (ZMQ)
           └── Optionally sends TTL trigger (ZMQ)

2. Camera Server receives START_INF
   └── Starts infinite capture
   └── Saves frames to E:/Data/jpg_frames/

3. ARTIQ Worker receives START_CAMERA_INF
   └── Sets camera_inf_active = True
   └── Ready to receive CAMERA_TRIGGER commands

4. Image Handler (separate thread)
   └── Watches E:/Data/jpg_frames/
   └── Processes new frames
   ├── Saves labelled frames to E:/Data/jpg_frames_labelled/
   └── Saves ion data JSON to E:/Data/ion_data/
```

### Manual Trigger Sequence
```
1. Flask receives POST /api/camera/trigger
   └── Sends CAMERA_TRIGGER to Manager (ZMQ REQ/REP)

2. Manager receives CAMERA_TRIGGER
   └── Publishes CAMERA_TRIGGER to ARTIQ (ZMQ PUB/SUB)

3. ARTIQ Worker receives CAMERA_TRIGGER
   └── Executes TTL pulse on camera_trigger device
   └── Camera captures frame
```

## Directory Structure

```
E:/Data/
├── jpg_frames/                    # Raw JPG frames from camera
│   └── YYMMDD/
│       └── frame{counter}_YYYY-MM-DD_HH-MM-SS_mmmmmm.jpg
├── jpg_frames_labelled/           # Processed frames with overlays
│   └── YYMMDD/
│       └── frame*_labelled.jpg
├── ion_data/                      # Ion position and fit data (JSON)
│   └── YYMMDD/
│       └── ion_data_YYYY-MM-DD_HH-MM-SS_mmmmmm.json
└── telemetry/                     # Other telemetry data
```

## Usage

### Automatic Start
The camera will automatically start in infinity mode when the manager launches if `camera.auto_start: true` in settings.yaml.

### Manual Control via Flask API
```bash
# Start camera
curl -X POST http://localhost:5000/api/camera/start \
  -H "Content-Type: application/json" \
  -d '{"mode": "infinite", "trigger": true}'

# Stop camera
curl -X POST http://localhost:5000/api/camera/stop

# Get status
curl http://localhost:5000/api/camera/status

# Send TTL trigger
curl -X POST http://localhost:5000/api/camera/trigger

# Get latest ion data
curl http://localhost:5000/api/ion_data/latest
```

### ARTIQ Experiment Usage
```python
from ndscan.experiment import ExpFragment, make_fragment_scan_exp
from cam import Camera, AutoCamera

class MyExperiment(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.cam = self.setattr_fragment("camera", Camera)
        # Or use AutoCamera for automatic setup
        # self.autocam = self.setattr_fragment("autocam", AutoCamera)
    
    @kernel
    def run_once(self):
        # Trigger camera via TTL
        self.cam.trigger(100.0)  # 100μs pulse
```

### Standalone Image Handler
```bash
# Run image handler as standalone process
python server/cam/image_handler.py
```

## Migration from mhi_cam

| Feature | mhi_cam | MLS |
|---------|---------|-----|
| Camera start | Manual button in Flask | Auto-start + API |
| Communication | Flask → TCP → Camera Server | Manager → TCP → Camera Server |
| Frame paths | Y:/Stein/Server/Live_Frames/ | E:/Data/jpg_frames/ |
| Analysis | Separate server | Integrated image_handler.py |
| JSON format | Custom | Standardized (ion_data/*.json) |
| TTL Trigger | Via orca_quest.py Cam class | Via cam.py Camera fragment |

## Components to Start

1. **Camera Server** (from mhi_cam or existing)
   ```bash
   python server/cam/camera_server.py
   ```

2. **Manager** (auto-starts camera)
   ```bash
   python server/communications/manager.py
   ```

3. **Image Handler** (optional, for processing)
   ```bash
   python server/cam/image_handler.py
   ```

4. **ARTIQ Worker** (for TTL triggers)
   ```bash
   # Via ARTIQ dashboard or command line
   artiq_run artiq/experiments/artiq_worker.py
   ```

5. **Flask Server** (for web UI and API)
   ```bash
   python server/Flask/flask_server.py
   ```

## Configuration Checklist

- [ ] Camera server running on port 5558
- [ ] Directories exist and are writable:
  - `E:/Data/jpg_frames/`
  - `E:/Data/jpg_frames_labelled/`
  - `E:/Data/ion_data/`
- [ ] `camera.auto_start: true` in settings.yaml
- [ ] ARTIQ device_db.py has `camera_trigger` device defined
- [ ] ZMQ ports configured correctly (5555-5558)

## Testing

1. Start manager with auto-start enabled
2. Verify camera server receives START_INF command
3. Check frames are being saved to `E:/Data/jpg_frames/`
4. Verify image handler creates labelled frames
5. Check ion data JSON files in `E:/Data/ion_data/`
6. Test Flask API endpoints
7. Test TTL trigger from ARTIQ

## Future Enhancements

- Real-time ion position streaming via WebSocket
- Integration with Turbo algorithm for adaptive ROI
- Automatic exposure adjustment based on ion brightness
- Multi-ion tracking across frames
- H5 file analysis integration
