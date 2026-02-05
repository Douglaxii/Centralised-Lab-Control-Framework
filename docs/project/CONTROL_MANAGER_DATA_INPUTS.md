# Control Manager - Data Input Formats

**Date:** 2026-02-05  
**Purpose:** Document the three data inputs to the Control Manager: PMT signal, Pressure, and Laser Frequency

---

## Overview

The Control Manager receives three primary data inputs from LabVIEW hardware:

| Input | Source | File Location | Format | Unit |
|-------|--------|---------------|--------|------|
| **PMT Signal** | SMILE.vi | `telemetry/smile/pmt/*.dat` | CSV | counts |
| **Pressure** | SMILE.vi | `telemetry/smile/pressure/*.dat` | CSV | mbar |
| **Laser Frequency** | Wavemeter.vi | `telemetry/wavemeter/*.dat` | CSV | MHz |

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW ARCHITECTURE                             │
└─────────────────────────────────────────────────────────────────────────────┘

[SMILE.vi] ───┬───> PMT counts ─────┐
              │                      │
              └───> Pressure (mbar) ─┼───> Write files ───┐
                                      │    to Y:/Xi/Data/   │
[Wavemeter.vi] ───> Frequency (MHz) ─┘    /telemetry/       │
                                                            │
                              ┌─────────────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │  LabVIEWFileReader │ (Manager)
                    │  (File Watcher)    │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │   PMT    │    │ Pressure │    │  Laser   │
    │  Buffer  │    │  Buffer  │    │  Buffer  │
    │(circular)│    │(circular)│    │(circular)│
    └────┬─────┘    └────┬─────┘    └────┬─────┘
         │                │                │
         └────────────────┼────────────────┘
                          ▼
                   ┌─────────────┐
                   │ Flask Server│
                   │  (Port 5000)│
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │   Web UI    │
                   │  (Dashboard)│
                   └─────────────┘
```

---

## 1. PMT Signal (Photon Counts)

### Source
**SMILE.vi** - PMT (PhotoMultiplier Tube) counter

### File Location
```
Y:/Xi/Data/telemetry/smile/pmt/*.dat
```

### File Format
**CSV Format:** `timestamp,value`

```csv
1706380800.123,1250.0
1706380800.623,1248.5
1706380801.123,1251.0
```

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | float | Unix timestamp (seconds since 1970-01-01) |
| `value` | float | PMT photon counts (arbitrary units) |

### Example Values
- Dark counts: ~50-100
- Single ion fluorescence: ~1000-2000
- Multiple ions: Scales with ion count

### Storage
- Internal channel name: `pmt`
- Buffer: 1000 points, 5-minute rolling window
- Data source tracking: `smile`

---

## 2. Pressure (Chamber Vacuum)

### Source
**SMILE.vi** - Vacuum gauge/pressure sensor

### File Location
```
Y:/Xi/Data/telemetry/smile/pressure/*.dat
```

### File Format
**CSV Format:** `timestamp,value`

```csv
1706380800.123,1.2e-10
1706380800.623,1.2e-10
1706380801.123,1.3e-10
```

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | float | Unix timestamp |
| `value` | float | Pressure in mbar (millibar) |

### Example Values
| Pressure | State |
|----------|-------|
| 1e-10 mbar | Excellent vacuum |
| 5e-10 mbar | Normal operation |
| 1e-9 mbar | Warning threshold |
| 5e-9 mbar | CRITICAL - Kill switch triggered |
| 1e-6 mbar | Atmospheric leak |

### Safety Critical
Pressure monitoring is **SAFETY CRITICAL**:
- Threshold: 5e-9 mbar (configurable)
- Action: Immediate kill of piezo and e-gun
- Response time: < 50ms

### Storage
- Internal channel name: `pressure`
- Buffer: 1000 points, 5-minute rolling window
- Data source tracking: `smile`

---

## 3. Laser Frequency

### Source
**Wavemeter.vi** - Laser wavemeter (HighFinesse or similar)

### File Location
```
Y:/Xi/Data/telemetry/wavemeter/*.dat
```

### File Format
**CSV Format:** `timestamp,value`

```csv
1706380800.123,212.456789
1706380800.623,212.456812
1706380801.123,212.456798
```

### Fields
| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | float | Unix timestamp |
| `value` | float | Laser frequency in MHz |

### Example Values
- Be+ cooling: ~212.5 MHz (313 nm)
- Typical drift: ±0.001 MHz over minutes
- Lock stability: Better than 0.0001 MHz

### Storage
- Internal channel name: `laser_freq`
- Buffer: 1000 points, 5-minute rolling window
- Data source tracking: `wavemeter`

---

## Implementation Details

### Python Code (Manager)

The `LabVIEWFileReader` class reads these files:

```python
# From src/server/manager/manager.py

class LabVIEWFileReader:
    """
    Expected directory structure:
        E:/Data/telemetry/
        ├── wavemeter/*.dat      - CSV: timestamp,frequency_mhz
        ├── smile/pmt/*.dat      - CSV: timestamp,pmt_counts
        ├── smile/pressure/*.dat - CSV: timestamp,pressure_mbar
        └── camera/*.json        - JSON: pos_x, pos_y, sig_x, sig_y
    """
    
    def _read_csv_file(self, filepath: Path) -> tuple:
        """Read CSV file: timestamp,value"""
        with open(filepath, 'r') as f:
            line = f.readline().strip()
            if ',' in line:
                parts = line.split(',')
                timestamp = float(parts[0])
                value = float(parts[1])
                return timestamp, value
```

### Data Storage (Shared Buffers)

```python
# From src/server/comms/data_server.py

_shared_telemetry_data = {
    "pressure": deque(maxlen=1000),      # From SMILE/pressure
    "laser_freq": deque(maxlen=1000),    # From wavemeter
    "pmt": deque(maxlen=1000),           # From SMILE/pmt
    # ... other channels
}
```

### Flask Access

```python
# Flask server reads from shared buffers
def get_telemetry_for_time_window(window_seconds: float = 300.0):
    real_telemetry, real_lock = get_telemetry_data()
    with real_lock:
        for key, deque_data in real_telemetry.items():
            # Format: [(timestamp, value), ...]
            points = [{"t": ts, "v": val} for ts, val in deque_data]
```

---

## LabVIEW Implementation

### PMT Data Writer (SMILE.vi)

```labview
[Read PMT Counter] ──> Counts (float)
    │
[Get Date/Time In Seconds] ──> Timestamp (float)
    │
[Format Into String: "%.3f,%.1f"] ──> CSV Line
    │
[Build Path: "Y:\Xi\Data\telemetry\smile\pmt\pmt_001.dat"]
    │
[Write to Text File]
```

**Output file content:**
```
1706380800.123,1250.0
```

### Pressure Data Writer (SMILE.vi)

```labview
[Read Pressure Gauge] ──> Pressure (float, mbar)
    │
[Get Date/Time In Seconds] ──> Timestamp (float)
    │
[Format Into String: "%.3f,%.6e"] ──> CSV Line
    │
[Build Path: "Y:\Xi\Data\telemetry\smile\pressure\pres_001.dat"]
    │
[Write to Text File]
```

**Output file content:**
```
1706380800.123,1.200000e-10
```

### Wavemeter Data Writer (Wavemeter.vi)

```labview
[Read Wavemeter] ──> Frequency (float, MHz)
    │
[Get Date/Time In Seconds] ──> Timestamp (float)
    │
[Format Into String: "%.3f,%.6f"] ──> CSV Line
    │
[Build Path: "Y:\Xi\Data\telemetry\wavemeter\freq_001.dat"]
    │
[Write to Text File]
```

**Output file content:**
```
1706380800.123,212.456789
```

---

## File Naming Convention

| Source | Suggested Pattern | Example |
|--------|------------------|---------|
| PMT | `pmt_<counter>.dat` | `pmt_001.dat` |
| Pressure | `pres_<timestamp>.dat` | `pres_20240205_143022.dat` |
| Wavemeter | `freq_<timestamp>.dat` | `freq_20240205_143022.dat` |

**Important:** Use `.dat` extension. Files are processed in order of creation time.

---

## Configuration

### Default Paths (config.yaml)

```yaml
paths:
  output_base: "Y:/Xi/Data"
  labview_telemetry: "Y:/Xi/Data/telemetry"

labview:
  enabled: true
  host: "172.17.1.217"
  port: 5559
  pressure_threshold_mbar: 5.0e-9  # Safety threshold
```

### Development Mode (without LabVIEW)

```yaml
labview:
  enabled: false  # Disables TCP connection to SMILE
```

File reader still works - you can manually create test files.

---

## Testing

### Manual Test (PowerShell)

```powershell
# Create test PMT data
$timestamp = ([DateTimeOffset]::UtcNow).ToUnixTimeSeconds()
"$timestamp,1250.0" | Out-File -FilePath "Y:\Xi\Data\telemetry\smile\pmt\test.dat"

# Create test pressure data
"$timestamp,1.2e-10" | Out-File -FilePath "Y:\Xi\Data\telemetry\smile\pressure\test.dat"

# Create test wavemeter data
"$timestamp,212.456789" | Out-File -FilePath "Y:\Xi\Data\telemetry\wavemeter\test.dat"
```

### Manual Test (Python)

```python
import time
import os

base_path = "Y:/Xi/Data/telemetry"
timestamp = time.time()

# Write PMT data
with open(f"{base_path}/smile/pmt/test.dat", "w") as f:
    f.write(f"{timestamp},1250.0\n")

# Write pressure data
with open(f"{base_path}/smile/pressure/test.dat", "w") as f:
    f.write(f"{timestamp},1.2e-10\n")

# Write wavemeter data
with open(f"{base_path}/wavemeter/test.dat", "w") as f:
    f.write(f"{timestamp},212.456789\n")
```

---

## API Endpoints

### Get Recent Data

```bash
# Get recent PMT data (last 60 seconds)
curl "http://localhost:5000/api/data/recent/pmt?window=60"

# Response:
{
  "status": "ok",
  "channel": "pmt",
  "count": 60,
  "data": [
    {"timestamp": 1706380800.1, "value": 1250.0},
    {"timestamp": 1706380800.2, "value": 1248.5}
  ]
}
```

### Get Data Sources Status

```bash
curl "http://localhost:5000/api/data/sources"

# Response:
{
  "wavemeter": {
    "connected": true,
    "last_seen": 1706380800.5,
    "file_count": 120
  },
  "smile": {
    "connected": true,
    "last_seen": 1706380800.4,
    "file_count": 240
  }
}
```

### Real-time Stream (SSE)

```bash
curl "http://localhost:5000/api/telemetry/stream"

# Server-Sent Events format:
data: {"pmt": [...], "pressure": [...], "laser_freq": [...], ...}
```

---

## Troubleshooting

### No Data in Dashboard

1. **Check files exist:**
   ```powershell
   Get-ChildItem "Y:\Xi\Data\telemetry\smile\pmt"
   Get-ChildItem "Y:\Xi\Data\telemetry\smile\pressure"
   Get-ChildItem "Y:\Xi\Data\telemetry\wavemeter"
   ```

2. **Verify file format:**
   ```powershell
   Get-Content "Y:\Xi\Data\telemetry\smile\pmt\test.dat"
   # Should be: timestamp,value
   ```

3. **Check Manager logs:**
   ```
   INFO - LabVIEWFileReader started - watching Y:/Xi/Data/telemetry
   ```

### Pressure Alert Triggered

Check actual pressure:
```powershell
Get-Content "Y:\Xi\Data\telemetry\smile\pressure\*.dat" | Select-Object -Last 1
```

If pressure > 5e-9 mbar, kill switch activates.

---

**Last Updated:** 2026-02-05
