# Camera Control Module

This directory contains the camera control modules for the MLS (Multi-Level System) framework, providing support for Hamamatsu CCD cameras.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CAMERA CONTROL FLOW                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   Manager/Flask    ─────TCP────>   Camera Server   ────DCAM API──>   │
│   (camera_client)       5558       (camera_server)      (Hamamatsu)  │
│                                                                      │
│   ARTIQ Worker     ────TTL─────>   Camera Hardware                   │
│   (TTL trigger)                                                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Module Overview

### Core Modules (Required)

| Module | Purpose | Source |
|--------|---------|--------|
| `dcam.py` | Hamamatsu DCAM-API Python wrapper | Hamamatsu SDK |
| `dcamapi4.py` | Low-level DCAM-API ctypes bindings | Hamamatsu SDK |
| `dcamcon.py` | Console-based DCAM control | Hamamatsu SDK |
| `dcimgnp.py` | DCIMG file format handling | Hamamatsu SDK |

### MLS Implementation Modules

| Module | Purpose | Description |
|--------|---------|-------------|
| `camera_server.py` | TCP server | Receives commands, controls camera |
| `camera_logic.py` | Recording logic | Thread management for recording modes |
| `camera_recording.py` | Recording functions | DCIMG and infinite capture implementation |
| `camera_client.py` | TCP client | High-level `CameraInterface` class |
| `image_handler.py` | Frame processing | Ion detection and JSON export (Core Ultra 9 + Quadro P400 optimized) |

### Utility Modules (in `utils/`)

| Module | Purpose | Description |
|--------|---------|-------------|
| `utils/dcamcon_live_capturing.py` | Live display | OpenCV-based live frame display |
| `utils/dcam_live_capturing.py` | Live capture | Simple live capture demo |
| `utils/calculate_exposure.py` | Exposure calc | ROI-based exposure time calculation |
| `utils/triggered_dcimg_capturing.py` | Legacy capture | Standalone triggered capture script |
| `utils/screeninfo.py` | Display utils | Multi-monitor support |

## Directory Structure

```
server/cam/
├── Core API (from Hamamatsu SDK)
│   ├── dcam.py                 # Main DCAM API
│   ├── dcamapi4.py             # Low-level API bindings
│   ├── dcamcon.py              # Console control
│   └── dcimgnp.py              # DCIMG file format
│
├── Server/Client
│   ├── camera_server.py        # TCP server (port 5558)
│   ├── camera_client.py        # TCP client with CameraInterface
│   ├── camera_logic.py         # Recording thread management
│   └── camera_recording.py     # Main recording implementation
│
├── Processing
│   └── image_handler.py        # Frame processing & ion detection
│       # Optimized for Intel Core Ultra 9 + NVIDIA Quadro P400
│       # - Multi-scale peak detection
│       # - GPU-accelerated processing (OpenCL/CUDA)
│       # - Compact visualization
│
├── utils/                      # Utility scripts
│   ├── dcamcon_live_capturing.py
│   ├── dcam_live_capturing.py
│   ├── triggered_dcimg_capturing.py
│   ├── calculate_exposure.py
│   └── screeninfo.py
│
└── archive/                    # Archived/backup files
    └── image_handler_*.py      # Previous versions
```

## Usage

### 1. Start Camera Server

```bash
python server/cam/camera_server.py
```

The server listens on TCP port 5558 for commands:
- `START` - Start single DCIMG recording
- `START_INF` - Start infinite capture mode
- `STOP` - Stop recording
- `STATUS` - Get camera status

### 2. Control from Manager

```python
from server.cam.camera_client import CameraInterface

camera = CameraInterface(host='127.0.0.1', port=5558)

# Start recording
camera.start_recording(mode='inf', exp_id='exp_001')

# Check status
status = camera.get_status()

# Stop recording
camera.stop_recording()
```

### 3. Trigger from ARTIQ

```python
from artiq.experiment import *
from cam import Camera

class MyExp(ExpFragment):
    def build_fragment(self):
        self.cam = self.setattr_fragment('camera', Camera)
    
    @kernel
    def run_once(self):
        # Send TTL trigger to camera
        self.cam.trigger(100.0)  # 100μs pulse
```

### 4. Process Frames

```python
from server.cam.image_handler import ImageHandler

handler = ImageHandler(
    raw_frames_path='E:/Data/jpg_frames',
    labelled_frames_path='E:/Data/jpg_frames_labelled',
    ion_data_path='E:/Data/ion_data'
)

handler.start()
# ... runs in background, processes frames automatically
handler.stop()
```

## Configuration

Edit `config/settings.yaml`:

### Camera Settings
```yaml
camera:
  auto_start: true               # Auto-start on manager launch
  mode: "inf"                    # "inf" or "single"
  host: "127.0.0.1"
  port: 5558
  
  raw_frames_path: "E:/Data/jpg_frames"
  labelled_frames_path: "E:/Data/jpg_frames_labelled"
  ion_data_path: "E:/Data/ion_data"
  
  infinite_mode:
    max_frames: 100
    exposure_ms: 300
    trigger_mode: "software"
```

### Image Handler Settings
```yaml
image_handler:
  roi:
    x_start: 0
    x_finish: 500
    y_start: 10
    y_finish: 300
  
  detection:
    threshold_percentile: 99.5    # Lower = more sensitive
    min_snr: 6.0
    min_intensity: 35
    max_intensity: 65000
    min_sigma: 2.0
    max_sigma: 30.0
    max_ions: 10
    min_distance: 15
    edge_margin: 20
  
  visualization:
    panel_height_ratio: 0.25
    font_scale_title: 0.4
    font_scale_data: 0.32
  
  performance:
    num_threads: 8
    use_vectorized: true
    use_gpu: true
```

## Data Flow

### Frame Capture Flow

```
1. Camera Server receives START_INF
2. camera_logic.start_camera_inf() spawns thread
3. camera_recording.handle_infinite_capture_request():
   a. Initialize DCAM API
   b. Setup cooling
   c. Configure properties
   d. Start capture with dcamcap_start()
   e. Loop: wait for frames, save as JPG
4. Frames saved to E:/Data/jpg_frames/YYMMDD/
```

### Frame Processing Flow

```
1. Image Handler watches jpg_frames/ directory
2. On new frame:
   a. Read JPG with OpenCV (GPU-accelerated if available)
   b. Detect ions (multi-scale peak finding + Gaussian fit)
      - Intel MKL/NumPy vectorized operations
      - OpenCL/CUDA acceleration for filtering
   c. Create overlay with compact markers
   d. Save labelled frame to jpg_frames_labelled/
   e. Save ion data + uncertainties to ion_data/ as JSON
```

### Hardware Optimizations

**Intel Core Ultra 9:**
- NumPy MKL threading (8 threads)
- Vectorized operations for peak detection
- Optimized memory layout

**NVIDIA Quadro P400:**
- OpenCV OpenCL acceleration
- GPU-accelerated Gaussian filtering
- CUDA support (if available)

## File Formats

### JPG Frame Naming

```
frame{counter}_YYYY-MM-DD_HH-MM-SS_mmmmmm.jpg

Example: frame123_2026-02-02_14-30-15_123456.jpg
```

### Labelled Frame Naming

```
frame{counter}_YYYY-MM-DD_HH-MM-SS_mmmmmm_labelled.jpg
```

### Ion Data JSON Format

```json
{
    "timestamp": "2026-02-02T14:30:15.123456",
    "frame_number": 123,
    "ions": {
        "ion_1": {
            "pos_x": 320.5,
            "pos_y": 240.3,
            "sig_x": 15.2,
            "R_y": 8.7
        }
    },
    "fit_quality": 0.95,
    "processing_time_ms": 45.2
}
```

## API Reference

### CameraInterface

```python
class CameraInterface:
    def __init__(self, host='127.0.0.1', port=5558)
    def start_recording(mode='inf', exp_id=None) -> bool
    def stop_recording() -> bool
    def get_status() -> Dict[str, Any]
    def is_camera_available() -> bool
```

### ImageHandler

```python
class ImageHandler:
    def __init__(self, 
                 raw_frames_path=None, 
                 labelled_frames_path=None, 
                 ion_data_path=None,
                 ion_uncertainty_path=None,
                 roi=None,
                 config=None)  # Dict or ImageHandlerConfig
    
    def process_single_frame(filepath) -> Tuple[List[IonFitResult], np.ndarray]
    def get_statistics() -> Dict[str, Any]
    def get_latest_ion_data() -> Optional[Dict]

class ImageHandlerConfig:
    """Configuration dataclass with tunable parameters"""
    # Detection: threshold_percentile, min_snr, min_intensity, etc.
    # Visualization: panel_height_ratio, font_scale_title, etc.
    # Performance: num_threads, use_vectorized, use_gpu
```

## Troubleshooting

### Camera server not responding

1. Check if camera server is running:
   ```bash
   python server/cam/camera_server.py
   ```

2. Verify port 5558 is not blocked:
   ```bash
   netstat -an | findstr 5558
   ```

3. Check camera is connected and powered

### No frames being saved

1. Check directory permissions:
   ```python
   import os
   os.makedirs('E:/Data/jpg_frames', exist_ok=True)
   ```

2. Verify DCAM-API is installed:
   ```python
   from dcam import Dcamapi
   print(Dcamapi.init())
   ```

### Image handler not detecting ions

1. Check ROI settings match camera subarray
2. Verify OpenCV is installed: `pip install opencv-python`
3. Check threshold_sigma is appropriate for signal level

## Dependencies

Required:
- Hamamatsu DCAM-API SDK (dcam.py, dcamapi4.py, etc.)
- OpenCV: `pip install opencv-python`
- NumPy: `pip install numpy`
- SciPy: `pip install scipy` (for fitting)

Optional:
- screeninfo: `pip install screeninfo`

## License

The Hamamatsu DCAM-API modules (dcam.py, dcamapi4.py, dcamcon.py, dcimgnp.py) are copyrighted by Hamamatsu Photonics K.K.

MLS-specific modules follow the project license.
