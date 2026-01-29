# Server PC Issues - Fixed

## Issues Found

### 1. YAML Parse Error (CRITICAL)
**Error:** `found unknown escape character 'X'`

**Root Cause:** The `settings.yaml` file had Windows paths with backslashes that YAML interpreted as escape sequences:
```yaml
# BAD - YAML thinks \X is an escape sequence
output_base: "Y:\Xi\Data\server"
```

**Fix Applied:** Changed `config/settings.yaml` to use:
- Forward slashes: `Y:/Xi/Data/server` (works on Windows)
- Or single quotes: `'Y:\Xi\Data\server'` (no escape interpretation)

### 2. Wrong Configuration File Being Used
**Problem:** The server was using `config/settings.yaml` with placeholder values instead of the server-specific config.

**Fix Applied:** Updated `config/settings.yaml` with correct server values:
- `master_ip`: 192.168.1.100 → 134.99.120.40
- `output_base`: Y:/Xi/Data → Y:/Xi/Data/server
- `labview/host`: 192.168.1.100 → 172.17.1.217
- Camera paths: Updated to E:/mls_frames/...

### 3. Missing OpenCV (Initially)
**Error:** `ModuleNotFoundError: No module named 'cv2'`

**Status:** Already fixed in your environment (verified by diagnostic).

## Configuration Changes Made

| Setting | Old Value | New Value |
|---------|-----------|-----------|
| master_ip | 192.168.1.100 | 134.99.120.40 |
| output_base | Y:/Xi/Data | Y:/Xi/Data/server |
| camera_frames | Y:/Stein/... | E:/mls_frames/camera_frames |
| jpg_frames | Y:/Xi/Data/jpg_frames | E:/mls_frames/jpg_frames |
| jpg_frames_labelled | Y:/Xi/Data/... | E:/mls_frames/jpg_frames_labelled |
| labview/host | 192.168.1.100 | 172.17.1.217 |

## Paths That Need to Exist on Server

The following paths will be created automatically, but ensure drives exist:
- `Y:\Xi\Data\server` (output data)
- `E:\mls_frames\` (camera frames - local SSD for performance)

## Verification

Run the diagnostic script to verify:
```bash
python check_server.py
```

Expected output:
```
[OK] YAML parse successful
[OK] Master IP: 134.99.120.40
[OK] All dependencies installed
```

## Next Steps

1. **Verify the paths exist** on your server:
   - Check that `Y:` drive is mapped
   - Check that `E:` drive exists for local frames

2. **Test the server**:
   ```bash
   python launcher.py
   ```

3. **If services still fail**, check individual logs:
   ```bash
   type logs\manager.log
   type logs\camera.log
   type logs\flask.log
   ```

## Note on Previous Errors

The `server_log/settings.yaml` file was a backup/reference but was not being used. The actual file being used is `config/settings.yaml` which is now fixed.

The logs showed continuous restart loops because:
1. YAML parsing failed → services couldn't start
2. Launcher detected failures → kept restarting
3. Cycle repeated

This should now be resolved.
