# Data Directory Standardization - Summary

## Changes Made

Your lab data directory has been standardized to use `E:/Data` as the central location for all data.

---

## 📁 New Directory Structure

```
E:/Data/
├── telemetry/              # LabVIEW writes real-time data here
│   ├── wavemeter/          # Laser frequency (*.dat)
│   ├── smile/pmt/          # PMT counts (*.dat)
│   ├── smile/pressure/     # Vacuum pressure (*.dat)
│   └── camera/             # Position tracking (*.json)
│
├── camera/                 # Camera data
│   ├── raw_frames/         # Raw JPG frames
│   ├── processed_frames/   # Annotated frames (for web UI)
│   ├── dcimg/              # DCIMG recordings
│   └── settings/           # Camera config files
│
├── experiments/            # Experiment metadata
├── analysis/               # Analysis outputs
│   ├── results/
│   └── settings/
├── logs/                   # All log files
├── debug/                  # Debug output
└── backup/                 # Backups
```

---

## 🔧 Files Updated

### Configuration Files
| File | Changes |
|------|---------|
| `MLS/config/settings.yaml` | `output_base` now `E:/Data`, all paths updated |
| `MLS/config/parallel_config.yaml` | Camera paths and log paths updated |

### Python Code Files
| File | Changes |
|------|---------|
| `MLS/server/communications/manager.py` | Telemetry path updated |
| `MLS/server/communications/labview_interface.py` | Pressure monitoring path updated |
| `MLS/server/communications/data_server.py` | Data storage path updated |
| `MLS/server/Flask/flask_server.py` | Frame paths updated |
| `MLS/server/cam/camera_server.py` | Frame save path updated |
| `MLS/server/cam/image_handler_server.py` | Frame paths updated |
| `MLS/core/experiment.py` | Experiment metadata path updated |

---

## 🚀 Setup Steps (Run These)

### Step 1: Create Directory Structure
Double-click and run:
```
D:\setup_data_directory.bat
```

### Step 2: Update LabVIEW VIs
Change the save locations in your LabVIEW programs:

| VI | Old Path | New Path |
|----|----------|----------|
| Wavemeter.vi | `Y:\Xi\Data\...` | `E:\Data\telemetry\wavemeter\` |
| SMILE.vi | `Y:\Xi\Data\...` | `E:\Data\telemetry\smile\pmt\` |
| SMILE.vi | `Y:\Xi\Data\...` | `E:\Data\telemetry\smile\pressure\` |

### Step 3: Migrate Existing Data (Optional)
If you have existing data in `Y:/Xi/Data` or `E:/mls_frames`, copy it:

```batch
REM Copy old telemetry data
xcopy "Y:\Xi\Data\telemetry\*" "E:\Data\telemetry\" /E /I /H

REM Copy old camera frames
xcopy "E:\mls_frames\jpg_frames\*" "E:\Data\camera\raw_frames\" /E /I /H
xcopy "E:\mls_frames\jpg_frames_labelled\*" "E:\Data\camera\processed_frames\" /E /I /H
```

### Step 4: Restart Servers
1. Stop all running servers (use `start_servers.bat` → option 7)
2. Start servers again (use `start_servers.bat` → option 2)

---

## 📊 Path Migration Reference

| Data Type | Old Location | New Location |
|-----------|--------------|--------------|
| Telemetry | `Y:/Xi/Data/telemetry/` | `E:/Data/telemetry/` |
| Raw Frames | `Y:/Xi/Data/jpg_frames/` or `E:/mls_frames/jpg_frames/` | `E:/Data/camera/raw_frames/` |
| Processed Frames | `Y:/Xi/Data/jpg_frames_labelled/` or `E:/mls_frames/jpg_frames_labelled/` | `E:/Data/camera/processed_frames/` |
| DCIMG Files | `E:/mls_frames/camera_dcimg/` | `E:/Data/camera/dcimg/` |
| Camera Settings | `E:/mls_frames/camera_settings/` | `E:/Data/camera/settings/` |
| Logs | `MLS/logs/` | `E:/Data/logs/` |
| Experiments | `Y:/Xi/Data/server/experiments/` | `E:/Data/experiments/` |

---

## ✅ Verification Checklist

After setup, verify:

- [ ] `E:/Data/` directory exists with all subfolders
- [ ] LabVIEW VIs are writing to `E:/Data/telemetry/`
- [ ] Camera server is saving frames to `E:/Data/camera/raw_frames/`
- [ ] Web UI shows camera feed (uses `E:/Data/camera/processed_frames/`)
- [ ] Telemetry appears in web UI (reads from `E:/Data/telemetry/`)
- [ ] Log files are being written to `E:/Data/logs/`

---

## 🐛 Troubleshooting

### "E: drive not found"
- Ensure your external drive is connected
- Check Windows Explorer for the correct drive letter
- If different from E:, edit `setup_data_directory.bat` and `MLS/config/settings.yaml`

### "Permission denied"
- Right-click `setup_data_directory.bat` → "Run as administrator"
- Check folder permissions on E:/Data

### "Data not showing in web UI"
1. Check files are being created:
   ```powershell
   Get-ChildItem E:\Data\telemetry\wavemeter\ | Select-Object -First 5
   ```
2. Check Manager logs: `E:/Data/logs/manager.log`
3. Restart all servers

---

## 📚 Documentation

Full documentation:
- `D:\DATA_DIRECTORY_STANDARD.md` - Complete data directory guide
- `D:\SERVER_STARTUP_GUIDE.md` - Server startup guide
- `E:/Data/README.txt` - Quick reference (created by setup script)

---

## ⚠️ Important Notes

1. **Backup First**: If you have existing data in `Y:/Xi/Data`, back it up before migrating
2. **LabVIEW Update Required**: Your VIs must be updated to write to new paths
3. **Drive Letter**: If E: is not your data drive, update all configurations
4. **Old Paths Deprecated**: `Y:/Xi/Data` and `E:/mls_frames` paths are no longer used

---

## 🔄 Rollback (If Needed)

To revert to old paths:
1. Restore original `settings.yaml` from git
2. Restore original Python files from git
3. Restart servers
