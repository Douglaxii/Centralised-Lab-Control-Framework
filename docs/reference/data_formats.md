# LabVIEW Data Integration Guide (File-Based)

This guide explains how to send data from your LabVIEW programs (Wavemeter.vi and SMILE.vi) to the Flask dashboard's telemetry display using **file-based communication** via the shared network drive `Y:\Xi\Data\`.

> **Note:** LabVIEW writes TDMS format files to `Y:\Xi\Data\PMT\`

## Architecture Overview

```
[Wavemeter.vi] ──┐
                 ├──writes files──> Y:\Xi\Data\telemetry\ ──┐
[SMILE.vi] ──────┘                                          │
                                                            ├──┐
[Camera Analysis] ──writes JSON──> Y:\Xi\Data\telemetry\ ──┘  │
                                                              │
                                                   [DataServer] (File Watcher)
                                                              │
[Flask Server] <──────────────────────────────────────────────┘
         │
         └──> [Web Browser] (Real-time plots)
```

## How It Works

1. **LabVIEW programs write data files** to `Y:\Xi\Data\telemetry\` subdirectories
2. **DataServer** (running inside Manager) watches these directories for new files
3. **Files are parsed** and data is stored in shared rolling buffers (5-minute window)
4. **Flask reads** from shared buffers and streams to web dashboard
5. **Dashboard displays** real-time plots with data from all sources

## Why File-Based?

- **Simple**: No TCP connections, sockets, or network code needed in LabVIEW
- **Reliable**: Files act as a buffer - no data loss if Python is temporarily busy
- **Debuggable**: Files are persistent - you can inspect what was sent
- **Flexible**: LabVIEW PCs just need access to `Y:\` drive (already required for other data)

## Directory Structure

```
Y:\Xi\Data\telemetry\
├── wavemeter\              # Laser frequency data
│   ├── freq_001.dat
│   ├── freq_002.dat
│   └── ...
├── smile\
│   ├── pmt\               # PMT counts
│   │   ├── pmt_001.dat
│   │   └── ...
│   └── pressure\          # Chamber pressure
│       ├── pres_001.dat
│       └── ...
└── camera\                # Ion position data (JSON)
    ├── pos_001.json
    └── ...
```

## Configuration

Edit `config/settings.yaml`:

```yaml
data_ingestion:
  enabled: true
  poll_interval: 0.5              # Check for new files every 500ms
  delete_after_processing: false  # Keep original files (LabVIEW manages cleanup)
  telemetry_path: "telemetry"     # Subdir under output_base
  
  sources:
    wavemeter:
      enabled: true
      subdir: "wavemeter"
      pattern: "*.dat"
      format: "csv"              # timestamp,value
      channel: "laser_freq"
      
    smile:
      enabled: true
      subdirs:
        pmt: "smile/pmt"
        pressure: "smile/pressure"
      pattern: "*.dat"
      format: "csv"
      channels:
        pmt: "pmt"
        pressure: "pressure"
        
    camera:
      enabled: true
      subdir: "camera"
      pattern: "*.json"
      format: "json"
      channels: ["pos_x", "pos_y", "sig_x", "sig_y"]
```

## File Formats

### CSV Format (Wavemeter, SMILE)

Simple text file with `timestamp,value` pairs:

```csv
1706380800.123,212.456789
1706380800.623,212.456812
1706380801.123,212.456798
```

**Fields:**
- `timestamp`: Unix timestamp in seconds (with decimal for milliseconds)
- `value`: The measurement value (float)

**File naming:** Any `.dat` extension works. Suggested patterns:
- `freq_YYYYMMDD_HHMMSS.dat`
- `pmt_001.dat`
- `pressure_temp.dat`

### JSON Format (Camera Position Data)

For multi-value data like camera position:

```json
{
  "timestamp": 1706380800.123,
  "pos_x": 150.5,
  "pos_y": 220.3,
  "sig_x": 5.2,
  "sig_y": 4.8
}
```

**Fields:**
- `timestamp`: Unix timestamp (optional, defaults to file read time)
- `pos_x`, `pos_y`: Ion position in pixels
- `sig_x`, `sig_y`: Gaussian width / signal spread

## LabVIEW Implementation

### Wavemeter.vi Example

**Block Diagram:**
```
[Initialize]
    │
    └─> [While Loop]
            │
            ├─> [Read Wavemeter] ──> Frequency (MHz)
            │
            ├─> [Get Date/Time In Seconds] ──> Timestamp
            │
            ├─> [Format Into String] ──> "%.3f,%.6f" (timestamp, frequency)
            │
            ├─> [Build Path]
            │       Base: "Y:\Xi\Data\telemetry\wavemeter\"
            │       Filename: "freq_" + [Format Date/Time] + ".dat"
            │
            ├─> [Write to Text File]
            │       Content: timestamp + "," + frequency + "\n"
            │
            ├─> [Wait] ──> 100-500 ms
            │
            └─> [Check Stop]
```

**File Content Example:**
```
1706380800.123,212.456789
```

### SMILE.vi Example

**Block Diagram (PMT):**
```
[Initialize]
    │
    └─> [While Loop]
            │
            ├─> [Read PMT] ──> Counts
            │
            ├─> [Get Date/Time In Seconds] ──> Timestamp
            │
            ├─> [Format Into String] ──> "%.3f,%.1f" (timestamp, counts)
            │
            ├─> [Build Path]
            │       Base: "Y:\Xi\Data\telemetry\smile\pmt\"
            │       Filename: "pmt_" + [increment counter] + ".dat"
            │
            ├─> [Write to Text File]
            │       Content: timestamp + "," + counts + "\n"
            │
            ├─> [Read Pressure Gauge] ──> Pressure (mbar)
            │
            ├─> [Write to Text File]
            │       Path: "Y:\Xi\Data\telemetry\smile\pressure\pres_xxx.dat"
            │       Content: timestamp + "," + pressure + "\n"
            │
            ├─> [Wait] ──> 100-500 ms
            │
            └─> [Check Stop]
```

**File Content Examples:**
```
# Y:\Xi\Data\telemetry\smile\pmt\pmt_001.dat
1706380800.123,1250.0

# Y:\Xi\Data\telemetry\smile\pressure\pres_001.dat  
1706380800.124,1.2e-10
```

### Important LabVIEW Notes

1. **File Permissions**: Ensure LabVIEW has write access to `Y:\Xi\Data\telemetry\`
2. **Atomic Writes**: Write to a temp file, then rename to `.dat` to ensure complete writes
3. **File Cleanup**: Implement periodic cleanup of old files (DataServer doesn't delete by default)
4. **Rate Limiting**: Don't write too frequently - 1-10 Hz is usually sufficient

**Recommended File Write Pattern (Atomic):**
```
1. Format data string: timestamp + "," + value + "\n"
2. Generate temp filename: "Y:\...\wavemeter\freq_001.tmp"
3. Write to temp file
4. Rename to final filename: "freq_001.dat"
   (This ensures DataServer never sees partial files)
```

## Starting the System

### Step 1: Start Control Manager

The DataServer runs automatically inside the Manager:

```bash
python server/communications/manager.py
```

You should see:
```
INFO - DataServer started - watching Y:/Xi/Data/telemetry/
```

### Step 2: Start Flask Server

```bash
python server/Flask/flask_server.py
```

### Step 3: Start LabVIEW Programs

Run your `Wavemeter.vi` and `SMILE.vi` programs. They should start writing files to `Y:\Xi\Data\telemetry\`.

### Step 4: Verify Data Flow

Check that files are being created:
```powershell
# PowerShell
Get-ChildItem Y:\Xi\Data\telemetry\wavemeter\ -Name
Get-ChildItem Y:\Xi\Data\telemetry\smile\pmt\ -Name
```

In the Manager console, you should see:
```
📈 Files: 12 | Sources active: 2/3 | Watchers: 3
```

## Testing Without LabVIEW

Create test files manually:

```powershell
# Test wavemeter data
"1706380800.123,212.456789" | Out-File -FilePath "Y:\Xi\Data\telemetry\wavemeter\test.dat"

# Test SMILE PMT data  
"1706380800.123,1250.0" | Out-File -FilePath "Y:\Xi\Data\telemetry\smile\pmt\test.dat"

# Test pressure data
"1706380800.123,1.2e-10" | Out-File -FilePath "Y:\Xi\Data\telemetry\smile\pressure\test.dat"
```

Or use Python:
```python
import time

# Write test data
timestamp = time.time()
with open("Y:/Xi/Data/telemetry/wavemeter/test.dat", "w") as f:
    f.write(f"{timestamp},212.456789\n")
```

## API Endpoints

The Flask server provides these data-related endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/telemetry/stream` | GET | SSE stream of all telemetry data |
| `/api/data/sources` | GET | Data source connection status |
| `/api/data/recent/<channel>` | GET | Recent data for specific channel |
| `/api/status` | GET | Full system status including data sources |

### Example: Get Data Source Status

```bash
curl http://localhost:5000/api/data/sources
```

Response:
```json
{
  "status": "ok",
  "sources": {
    "wavemeter": {
      "connected": true,
      "last_seen": 1706380800.5,
      "file_count": 120,
      "last_value": 212.456
    },
    "smile": {
      "connected": true,
      "last_seen": 1706380800.4,
      "file_count": 240,
      "last_value": 1250.0
    }
  }
}
```

### Example: Get Recent PMT Data

```bash
curl "http://localhost:5000/api/data/recent/pmt?window=60"
```

Response:
```json
{
  "status": "ok",
  "channel": "pmt",
  "count": 300,
  "data": [
    {"timestamp": 1706380800.1, "value": 1250.0},
    {"timestamp": 1706380800.2, "value": 1248.0},
    ...
  ]
}
```

## Dashboard Display

The web dashboard shows:

- **Status Bar**: Green dots indicate active data sources (Wavemeter, SMILE)
- **Telemetry Plots**: 
  - **Laser Frequency** (MHz) - from Wavemeter.vi
  - **PMT** (counts) - from SMILE.vi
  - **Pressure** (mbar) - from SMILE.vi
  - **Pos X/Y, Sig X/Y** - from camera image analysis

## Troubleshooting

### Files Not Being Processed

1. **Check paths exist:**
   ```powershell
   Test-Path "Y:\Xi\Data\telemetry\wavemeter"
   Test-Path "Y:\Xi\Data\telemetry\smile\pmt"
   ```

2. **Verify file format:**
   ```powershell
   Get-Content "Y:\Xi\Data\telemetry\wavemeter\test.dat"
   # Should show: timestamp,value
   ```

3. **Check DataServer logs:**
   ```
   INFO - Watching Y:\Xi\Data\telemetry\wavemeter for *.dat
   ```

### Data Not Showing in Plots

1. **Check file content format:**
   - Must be: `timestamp,value` (no spaces, unless using TSV)
   - Timestamp should be Unix epoch (seconds since 1970-01-01)

2. **Verify in Manager console:**
   - Should see: `📈 Files: X | Sources active: Y/Z`

3. **Check browser console:**
   - Open developer tools (F12)
   - Check for SSE connection errors

### Permission Errors

1. **Check LabVIEW can write to Y: drive:**
   - Test with simple file write in LabVIEW
   - Check Windows file permissions

2. **Verify Python can read:**
   ```python
   import os
   print(os.listdir("Y:/Xi/Data/telemetry/wavemeter"))
   ```

## Performance Considerations

### Update Rates

Recommended maximum rates:
- **Wavemeter**: 1-10 Hz (laser frequency doesn't change rapidly)
- **PMT**: 10-100 Hz (depends on experiment)
- **Pressure**: 0.1-1 Hz (slow changes)

### File Management

- DataServer **polls every 500ms** by default
- Files are **NOT deleted** after processing (configurable)
- Implement cleanup in LabVIEW to prevent disk full:
  - Delete files older than 1 hour
  - Or keep only last N files

### Buffer Size

The server keeps:
- **5 minutes** (300 seconds) of history
- **1000 data points** per channel (rolling buffer)

Old data is automatically discarded from memory (original files remain).

## Comparison: File-Based vs TCP-Based

| Aspect | File-Based (Current) | TCP-Based (Old) |
|--------|---------------------|-----------------|
| **Complexity** | Low - just write files | High - need TCP code |
| **Reliability** | High - files buffer data | Medium - network issues |
| **Latency** | ~500ms (poll interval) | ~10-100ms |
| **Debug** | Easy - inspect files | Hard - wireshark needed |
| **Rate Limit** | File system I/O | Network bandwidth |

For most lab telemetry (slow-changing values), file-based is preferred for simplicity.

## Complete Startup Sequence

```bash
# Terminal 1: Control Manager (includes DataServer)
python server/communications/manager.py

# Terminal 2: Flask Web Server
python server/Flask/flask_server.py

# (Optional) Terminal 3: Test file writer
python -c "
import time
while True:
    with open('Y:/Xi/Data/telemetry/wavemeter/test.dat', 'a') as f:
        f.write(f'{time.time()},{212.456 + 0.001 * (time.time() % 10)}\n')
    time.sleep(1)
"
```

Then:
1. Start LabVIEW VIs (they write files to `Y:\Xi\Data\telemetry\`)
2. Open browser to `http://localhost:5000`
3. Verify data sources show green dots
4. Watch telemetry plots update in real-time

## Migration from TCP

If you were using the old TCP-based data ingestion:

1. **Stop using `DataIngestionServer`** class - it's been replaced by `DataServer`
2. **Remove TCP connection code** from LabVIEW
3. **Replace with file write code** (see examples above)
4. **Update file paths** in config if needed
5. **Test file creation** before starting full system
