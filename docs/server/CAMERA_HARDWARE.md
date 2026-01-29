# Camera Hardware Setup

## Hamamatsu CCD Camera Integration

The camera server requires the Hamamatsu DCAM-API SDK to control the CCD camera.

## Current Status

**Mock modules installed** for testing without actual hardware. These generate synthetic camera frames for development.

## Required Hardware Drivers

For actual camera operation, install:

### 1. Hamamatsu DCAM-API SDK

Download from: https://www.hamamatsu.com/us/en/product/cameras/software/dcam-api.html

**Required files from SDK:**
- `dcamcon.py` - Camera connection wrapper
- `dcamapi4.py` - API constants and structures
- `dcimgnp.py` - DCIMG file handling
- `dcamcon_live_capturing.py` - Live preview functions

**Installation:**
1. Install DCAM-API SDK
2. Copy the Python files above to `server/cam/`
3. Replace the mock files (or rename them as .bak)

### 2. Camera Settings

Ensure `config/settings.yaml` has correct paths:

```yaml
paths:
  camera_frames: "E:/mls_frames/camera_frames"
  camera_settings: "E:/mls_frames/camera_settings"
  camera_dcimg: "E:/mls_frames/camera_dcimg"
  live_frames: "E:/mls_frames/live_frames"
  jpg_frames: "E:/mls_frames/jpg_frames"
  jpg_frames_labelled: "E:/mls_frames/jpg_frames_labelled"

hardware:
  camera:
    target_temperature: -20.0    # CCD cooling target
    cooler_timeout: 300          # seconds
    max_frames_default: 100
    exposure_default: 0.3
    trigger_mode: "extern"       # "extern" or "software"
```

## Camera Commands

The camera server accepts TCP commands on port 5558:

| Command | Description |
|---------|-------------|
| `START` | Start single recording (DCIMG + JPG) |
| `START_INF` | Start infinite capture mode (JPG only) |
| `STOP` | Stop current capture |
| `STATUS` | Get camera status |
| `EXP_ID:<id>` | Set experiment ID for metadata |

## Testing

### With Mock Camera (Current)

```bash
python server/cam/camera_server.py
```

The mock camera generates synthetic frames with Gaussian "ion" spots for testing.

### With Real Camera

After installing DCAM-API SDK:

```bash
python server/cam/camera_server.py
```

The server will connect to the actual Hamamatsu CCD camera.

## Architecture

```
camera_server.py (TCP interface)
    ↓
camera_logic.py (high-level control)
    ↓
camera_recording.py (recording logic)
    ↓
dcamcon.py (Hamamatsu SDK wrapper)
    ↓
Hamamatsu CCD Camera
```

## Troubleshooting

### "No module named 'dcamcon'"

Install Hamamatsu DCAM-API SDK and copy the Python files to `server/cam/`.

### Camera not detected

1. Check USB/PCIe connection
2. Verify DCAM-API driver installation
3. Check Windows Device Manager for "Hamamatsu DCAM"

### Cooling failed

- Check camera has power
- Wait longer for cooldown (up to 5 minutes)
- Check `target_temperature` setting is realistic (typically -20°C to -40°C)

### Frames not saving

- Ensure output directories exist and are writable
- Check disk space on Y: and E: drives
- Verify network drive Y: is mapped correctly

## Files

### Mock Files (Current)
These are placeholders for testing:
- `server/cam/dcamcon.py` - Mock camera driver
- `server/cam/dcamapi4.py` - Mock API constants
- `server/cam/dcimgnp.py` - Mock file format
- `server/cam/dcamcon_live_capturing.py` - Mock live preview
- `server/cam/screeninfo.py` - Mock display info

### Real Files (From SDK)
Replace mock files with these from Hamamatsu SDK:
- `dcamcon.py`
- `dcamapi4.py`
- `dcimgnp.py`
- `dcamcon_live_capturing.py`

### Application Files
- `server/cam/camera_server.py` - Main TCP server
- `server/cam/camera_logic.py` - High-level camera control
- `server/cam/camera_recording.py` - Recording logic
