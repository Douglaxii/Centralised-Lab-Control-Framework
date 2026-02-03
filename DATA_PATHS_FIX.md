# Data Paths Fix Summary

## Problem
The camera server and related modules were using inconsistent data paths:
- `camera_recording.py`: Used `camera_frames` from config (pointing to Y:/Xi/Data in production)
- `image_handler.py`: Used hardcoded `~/Data/jpg_frames` as default
- `camera_server.py`: Had hardcoded E:/data paths
- `launcher.py`: Had hardcoded E:/data paths

## Solution
All camera-related modules now use consistent paths from `config/config.yaml`.

## Data Directory Structure

### Development (Laptop)
```
./data/
├── jpg_frames/              # Raw frames from camera
├── jpg_frames_labelled/     # Processed frames with overlays
├── ion_data/                # Ion position data (JSON)
├── ion_uncertainty/         # Uncertainty calculations
├── camera/
│   ├── settings/           # Camera settings
│   └── dcimg/              # DCIMG recordings
└── logs/                   # Log files
```

### Production (Manager PC)
```
E:/data/                     # Local fast storage
├── jpg_frames/              # Raw frames from camera
├── jpg_frames_labelled/     # Processed frames
├── ion_data/                # Ion position data
├── ion_uncertainty/         # Uncertainty calculations
└── camera/
    └── settings/           # Camera settings

Y:/Xi/Data/                  # Network storage
├── camera/
│   ├── raw_frames/         # Raw frames (alternative)
│   ├── dcimg/              # DCIMG recordings
│   └── live_frames/        # Live frame buffer
├── telemetry/              # Telemetry data
└── logs/                   # Server logs
```

## Configuration

All paths are defined in `config/config.yaml`:

```yaml
paths:
  jpg_frames: "./data/jpg_frames"              # or "E:/data/jpg_frames"
  jpg_frames_labelled: "./data/jpg_frames_labelled"
  ion_data: "./data/ion_data"
  ion_uncertainty: "./data/ion_uncertainty"
  camera_settings: "./data/camera/settings"

camera:
  raw_frames_path: "./data/jpg_frames"
  labelled_frames_path: "./data/jpg_frames_labelled"
  ion_data_path: "./data/ion_data"
  ion_uncertainty_path: "./data/ion_uncertainty"
```

## Files Modified

### 1. config/config.yaml
- Added `ion_uncertainty` path
- Changed `camera_frames` to point to `jpg_frames` (consistent)
- Updated both development and production profiles

### 2. src/launcher.py
- Added camera service to launcher
- Updated `_ensure_data_directories()` to use paths from config
- Removed hardcoded E:/data paths

### 3. src/hardware/camera/camera_server.py
- Updated `ensure_directories()` to use paths from config
- Falls back to ./data paths if config unavailable

### 4. src/hardware/camera/camera_recording.py
- Updated to use `jpg_frames` path from config
- Falls back to ./data/jpg_frames

### 5. src/hardware/camera/image_handler.py
- Updated to load default paths from config
- Falls back to ~/Data/... if config unavailable

## Testing

1. Check current paths:
```python
from core import get_config
config = get_config()
print(config.get('paths.jpg_frames'))
print(config.get('camera.raw_frames_path'))
```

2. Verify directories are created on startup:
```bash
python src/launcher.py
# Check that all data directories exist
```

3. Test camera service:
```bash
python src/launcher.py --service camera
# Or start all services:
python src/launcher.py
```

## Environment Switching

Use the switch_env.py script to switch between environments:

```bash
# Development (laptop)
python switch_env.py dev

# Production (manager PC)
python switch_env.py prod
```

This updates the `environment` field in config.yaml, which determines which profile is active.

## Troubleshooting

### Issue: Camera server can't write to directory
**Solution**: Ensure the paths in config.yaml are correct for your environment and the directories are writable.

### Issue: Image handler uses wrong default path
**Solution**: The image_handler now loads defaults from config. If config is unavailable, it falls back to ~/Data/...

### Issue: Paths don't exist on manager PC
**Solution**: Run the launcher - it will create all required directories automatically based on config.
