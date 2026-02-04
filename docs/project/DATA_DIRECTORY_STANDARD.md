# E:/Data Directory Standardization

## Overview

This document defines the standardized data directory structure for the Lab Control Framework. All data is now centralized under `E:/Data` with a clean, organized hierarchy.

---

## Directory Structure

```
E:/Data/
│
├── telemetry/                  # Real-time telemetry data (LabVIEW writes here)
│   ├── wavemeter/              # Laser frequency readings
│   │   └── *.dat               # Format: timestamp,frequency_mhz
│   │
│   ├── smile/                  # SMILE hardware data
│   │   ├── pmt/                # PMT counts
│   │   │   └── *.dat           # Format: timestamp,pmt_counts
│   │   │
│   │   └── pressure/           # Vacuum pressure
│   │       └── *.dat           # Format: timestamp,pressure_mbar
│   │
│   └── camera/                 # Camera position tracking
│       └── *.json              # Format: {"pos_x": ..., "pos_y": ..., ...}
│
├── camera/                     # Camera data
│   ├── raw_frames/             # Raw JPG frames from camera
│   │   └── YYMMDD/             # Date-organized subfolders
│   │       └── *.jpg
│   │
│   ├── processed_frames/       # Annotated frames for web UI
│   │   └── YYMMDD/             # Date-organized subfolders
│   │       └── *_labelled.jpg
│   │
│   ├── dcimg/                  # DCIMG recordings
│   │   └── YYMMDD/
│   │       └── *.dcimg
│   │
│   └── settings/               # Camera configuration files
│       └── *.json
│
├── experiments/                # Experiment metadata and results
│   └── YYYY-MM-DD/
│       └── [experiment_id]/
│           ├── metadata.json
│           ├── parameters.json
│           └── results/
│
├── analysis/                   # Analysis outputs
│   ├── results/                # Analysis results (plots, CSVs, etc.)
│   │   └── YYYY-MM-DD/
│   │
│   └── settings/               # Analysis configuration files
│       └── *.json
│
├── logs/                       # Application logs
│   ├── camera.log
│   ├── manager.log
│   ├── artiq_worker.log
│   └── analysis.log
│
├── debug/                      # Debug output and crash dumps
│
└── backup/                     # Data backups
    └── YYYY-MM-DD/
```

---

## Data Flow

### Telemetry Data (LabVIEW → Files → Manager → Flask)

```
LabVIEW VIs
    │
    ├── Wavemeter.vi ──> E:/Data/telemetry/wavemeter/*.dat
    │
    ├── SMILE.vi ──────> E:/Data/telemetry/smile/pmt/*.dat
    │                  > E:/Data/telemetry/smile/pressure/*.dat
    │
    └── Camera.vi ─────> E:/Data/telemetry/camera/*.json
                            │
                            ▼
                    Control Manager
                    (reads files)
                            │
                            ▼
                    Flask Web UI
                    (displays real-time)
```

### Camera Data Flow

```
Camera Hardware
    │
    ▼
Camera Server (TCP:5558)
    │
    ├──> E:/Data/camera/raw_frames/YYMMDD/*.jpg
    │
    └──> Image Processor
              │
              ├──> E:/Data/camera/processed_frames/YYMMDD/*_labelled.jpg
              │
              └──> E:/Data/telemetry/camera/*.json
```

---

## File Formats

### Telemetry Files

#### Wavemeter Data (`telemetry/wavemeter/*.dat`)
```csv
# Format: timestamp,frequency_mhz
1706380800.123,212.456789
1706380801.456,212.456812
```

#### SMILE PMT Data (`telemetry/smile/pmt/*.dat`)
```csv
# Format: timestamp,pmt_counts
1706380800.123,1250.0
1706380801.456,1248.5
```

#### SMILE Pressure Data (`telemetry/smile/pressure/*.dat`)
```csv
# Format: timestamp,pressure_mbar
1706380800.123,1.2e-10
1706380801.456,1.1e-10
```

#### Camera Position Data (`telemetry/camera/*.json`)
```json
{
  "timestamp": 1706380800.123,
  "pos_x": 150.5,
  "pos_y": 200.3,
  "sig_x": 12.4,
  "sig_y": 11.8
}
```

---

## Configuration Updates

### Files Modified

1. **`MLS/config/settings.yaml`**
   - `output_base`: Changed from `Y:/Xi/Data/server` to `E:/Data`
   - All camera paths updated to use `E:/Data/camera/`
   - Log paths updated to `E:/Data/logs/`

2. **`MLS/config/parallel_config.yaml`**
   - Camera frame paths updated
   - Log paths updated

### Migration from Old Paths

| Old Path | New Path |
|----------|----------|
| `Y:/Xi/Data/server` | `E:/Data` |
| `Y:/Xi/Data/jpg_frames` | `E:/Data/camera/raw_frames` |
| `Y:/Xi/Data/jpg_frames_labelled` | `E:/Data/camera/processed_frames` |
| `E:/mls_frames/camera_dcimg` | `E:/Data/camera/dcimg` |
| `Y:/Xi/Data/telemetry` | `E:/Data/telemetry` |
| `MLS/logs/` | `E:/Data/logs/` |

---

## Setup Instructions

### 1. Run the Setup Script

Double-click `setup_data_directory.bat` to create the directory structure.

### 2. Update LabVIEW VIs

Change file write paths in your LabVIEW programs:

- **Wavemeter.vi**: Save to `E:\Data\telemetry\wavemeter\`
- **SMILE.vi**: Save to `E:\Data\telemetry\smile\pmt\` and `E:\Data\telemetry\smile\pressure\`

### 3. Verify Configuration

Check that `MLS/config/settings.yaml` has:
```yaml
paths:
  output_base: "E:/Data"
```

### 4. Restart Servers

Stop and restart all lab servers to apply the new paths.

---

## Data Management Best Practices

### Daily
- Check `E:/Data/logs/` for errors
- Verify telemetry files are being written

### Weekly
- Archive old camera frames (move to backup)
- Clean up debug folder

### Monthly
- Backup `E:/Data/experiments/` to external storage
- Review and compress old DCIMG files

### Quarterly
- Full backup of `E:/Data/`
- Archive data older than 1 year to cold storage

---

## Troubleshooting

### Telemetry Not Showing in Web UI

1. Check files are being written:
   ```powershell
   Get-ChildItem E:\Data\telemetry\wavemeter\ -Name
   ```

2. Verify Manager is reading files (check logs):
   ```
   E:/Data/logs/manager.log
   ```

3. Check file format matches expected CSV structure

### Camera Frames Not Saving

1. Check disk space on E: drive
2. Verify camera server has write permissions
3. Check `E:/Data/logs/camera.log` for errors

### Disk Space Issues

Monitor space usage:
```powershell
Get-ChildItem E:\Data -Recurse | Group-Object Directory | 
    Select-Object Name, @{N="Size(MB)";E={[math]::Round((($_.Group | Measure-Object Length -Sum).Sum / 1MB), 2)}}
```

---

## Backup Strategy

### Automated Daily Backup (Robocopy)
```batch
robocopy E:\Data\experiments \\backup-server\lab-data\experiments /MIR /FFT /Z /XA:H /W:5 /R:3
robocopy E:\Data\telemetry \\backup-server\lab-data\telemetry /MIR /FFT /Z /XA:H /W:5 /R:3
```

### Critical Data (Immediate Backup)
- Experiment metadata
- Analysis results
- Camera calibration settings

### Large Data (Weekly Backup)
- Raw camera frames (keep only last 7 days local)
- DCIMG recordings

---

## Contact

For issues with the data directory structure, check:
1. `E:/Data/logs/` for error messages
2. MLS documentation in `D:/MLS/docs/`
3. Server status using `start_servers.bat` → option 8
