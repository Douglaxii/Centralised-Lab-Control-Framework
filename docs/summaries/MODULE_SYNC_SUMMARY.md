# Camera Module Synchronization Summary

## Date
2026-02-02

## Source
`mhi_cam/Camera_Control/` → `MLS/server/cam/`

## Files Copied/Updated

### Core Hamamatsu SDK Modules (Real Implementation)
| File | Status | Purpose |
|------|--------|---------|
| `dcam.py` | ✅ Copied | Main DCAM API wrapper (Dcam, Dcamapi classes) |
| `dcamapi4.py` | ✅ Replaced | Low-level ctypes bindings for dcamapi.dll |
| `dcamcon.py` | ✅ Replaced | Console-based camera control |
| `dcimgnp.py` | ✅ Replaced | DCIMG file format handling |
| `dcamcon_live_capturing.py` | ✅ Copied | Live frame display utilities |

### Utility Modules
| File | Status | Purpose |
|------|--------|---------|
| `dcam_live_capturing.py` | ✅ Copied | Simple live capture demo |
| `calculate_exposure.py` | ✅ Copied | ROI-based exposure calculation |
| `triggered_dcimg_capturing.py` | ✅ Copied | Standalone triggered capture script |
| `camera_client.py` | ✅ Updated | TCP client with CameraInterface class |
| `__init__.py` | ✅ Copied | Package initialization |

### MLS Implementation (Already Present)
| File | Status | Purpose |
|------|--------|---------|
| `camera_server.py` | ✅ Existing | TCP server for camera control |
| `camera_logic.py` | ✅ Existing | Recording thread management |
| `camera_recording.py` | ✅ Existing | Main recording implementation |
| `image_handler.py` | ✅ Created | Frame processing & ion detection |
| `screeninfo.py` | ✅ Existing | Display utilities |
| `README.md` | ✅ Created | Documentation |

### Backup Files
| File | Status | Note |
|------|--------|------|
| `dcamcon_mock.py.bak` | ❌ Removed | Mock implementation backup |

## Comparison

### Before Sync
```
MLS/server/cam/ (Mock Implementation)
├── camera_logic.py         # Uses dcamcon
├── camera_recording.py     # Uses dcamcon
├── camera_server.py        # Uses camera_logic
├── dcamcon.py              # ⚠️ MOCK - generates synthetic frames
├── dcamapi4.py             # ⚠️ MOCK - stub functions
├── dcimgnp.py              # ⚠️ MOCK - stub functions
├── image_handler.py        # New module
└── screeninfo.py           # Utilities
```

### After Sync
```
MLS/server/cam/ (Real Implementation)
├── Core SDK (Hamamatsu)
│   ├── dcam.py             # Real DCAM API
│   ├── dcamapi4.py         # Real ctypes bindings
│   ├── dcamcon.py          # Real console control
│   ├── dcimgnp.py          # Real DCIMG handler
│   └── dcamcon_live_capturing.py
├── Utilities
│   ├── dcam_live_capturing.py
│   ├── calculate_exposure.py
│   ├── triggered_dcimg_capturing.py
│   ├── screeninfo.py
│   └── camera_client.py    # Updated with CameraInterface
├── MLS Implementation
│   ├── camera_server.py
│   ├── camera_logic.py
│   ├── camera_recording.py
│   └── image_handler.py
└── Package Files
    ├── __init__.py
    └── README.md
```

## Dependency Chain

```
camera_recording.py
├── dcamcon.py
│   ├── dcam.py
│   │   └── dcamapi4.py (requires dcamapi.dll)
│   └── dcamapi4.py
├── dcimgnp.py
└── dcamcon_live_capturing.py

camera_server.py
├── camera_logic.py
│   └── camera_recording.py
└── camera_client.py (optional utilities)

image_handler.py
├── OpenCV (cv2)
├── NumPy
└── SciPy (optional, for fitting)
```

## Key Changes

### 1. dcamcon.py
- **Before**: Mock implementation generating synthetic Gaussian spots
- **After**: Real implementation wrapping Hamamatsu DCAM-API

### 2. dcamapi4.py
- **Before**: Mock constants and stub functions
- **After**: Real ctypes bindings loading `dcamapi.dll`

### 3. dcimgnp.py
- **Before**: Mock DCIMG handling
- **After**: Real DCIMG file format operations

### 4. camera_client.py
- **Before**: Simple TCP client
- **After**: High-level `CameraInterface` class with full error handling

## Requirements

### System Requirements
- Hamamatsu DCAM-API SDK installed
- `dcamapi.dll` in system PATH or working directory
- Camera connected and powered on

### Python Dependencies
```bash
pip install opencv-python numpy scipy
```

### Optional
```bash
pip install screeninfo
```

## Testing

### Verify Module Imports (without camera)
```python
# This will fail on dcamapi.dll load (expected without SDK)
from dcam import Dcamapi
```

### Verify Module Imports (with camera SDK)
```bash
# Set path to dcamapi.dll if needed
set PATH=%PATH%;C:\Program Files\Hamamatsu\DCAM-API\bin

python -c "from dcam import Dcamapi; print('Success')"
```

### Test Camera Server
```bash
# Terminal 1: Start server
python server/cam/camera_server.py

# Terminal 2: Test client
python -c "
from server.cam.camera_client import CameraInterface
cam = CameraInterface()
print(cam.get_status())
"
```

## Notes

1. **SDK Installation**: The Hamamatsu DCAM-API SDK must be installed separately. Contact Hamamatsu Photonics for the SDK.

2. **Mock Mode**: If you need to test without the camera, restore the mock files:
   ```bash
   # Backup real files
   mv dcamcon.py dcamcon_real.py
   mv dcamapi4.py dcamapi4_real.py
   mv dcimgnp.py dcimgnp_real.py
   
   # Create mock versions (manual or from git history)
   ```

3. **Architecture**: The MLS implementation follows a layered architecture:
   - **Low-level**: Hamamatsu SDK (dcam.py, dcamapi4.py)
   - **Mid-level**: MLS wrappers (camera_logic.py, camera_recording.py)
   - **High-level**: Server/Client (camera_server.py, camera_client.py)
   - **Processing**: Image analysis (image_handler.py)

4. **Ports**:
   - Camera Server: TCP 5558
   - Flask Server: HTTP 5000
   - Manager ZMQ: 5555-5557

## Migration Status

✅ **COMPLETE** - All necessary modules from `mhi_cam/Camera_Control` have been synchronized to `MLS/server/cam/`.

The MLS camera server now has full support for Hamamatsu CCD cameras using the real DCAM-API SDK.
