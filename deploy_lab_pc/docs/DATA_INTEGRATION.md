# LabVIEW Data Integration Guide

This guide explains how to integrate data from your LabVIEW programs (Wavemeter.vi and SMILE.vi) into the Flask dashboard's telemetry display.

## Architecture Overview

```
[Wavemeter.vi] ──┐
                 ├──TCP:5560──> [Data Ingestion Server] ──┐
[SMILE.vi] ──────┘                                       │
                                                 [Shared Memory]
                                                          │
[Flask Server] <──────────────────────────────────────────┘
         │
         └──> [Web Browser] (Real-time plots)
```

## How It Works

1. **Data Ingestion Server** (`server/communications/data_server.py`) listens on TCP port 5560
2. **LabVIEW programs** connect and send JSON data over TCP
3. **Server stores** data in shared rolling buffers (300-second window)
4. **Flask reads** from shared buffers and streams to web dashboard
5. **Dashboard displays** real-time plots with data from both LabVIEW and simulated sources

## Configuration

### 1. Server Configuration

Edit `config/settings.yaml`:

```yaml
data_ingestion:
  enabled: true
  host: "0.0.0.0"        # Listen on all interfaces
  port: 5560             # TCP port for LabVIEW data
  timeout: 5.0
  max_connections: 10
```

### 2. LabVIEW Configuration

Ensure your LabVIEW programs connect to:
- **IP Address**: IP of the Python server (e.g., `192.168.1.100`)
- **Port**: `5560`
- **Protocol**: TCP

## Data Protocol

### JSON Format

Each data sample must be a single line of JSON terminated with newline (`\n`):

```json
{"source": "wavemeter", "channel": "laser_freq", "value": 212.456789, "timestamp": 1706380800.123}
```

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `source` | string | Data source identifier | `"wavemeter"`, `"smile"` |
| `channel` | string | Measurement channel | `"laser_freq"`, `"pmt"` |
| `value` | float | The measurement value | `212.456789` |
| `timestamp` | float | Unix timestamp (seconds) | `1706380800.123` |

### Channel Mapping

#### Wavemeter.vi Channels

| Channel Name | Maps To | Description | Unit |
|--------------|---------|-------------|------|
| `laser_freq` | `laser_freq` | Laser frequency | MHz |
| `frequency` | `laser_freq` | Alias | MHz |
| `freq` | `laser_freq` | Alias | MHz |

#### SMILE.vi Channels

| Channel Name | Maps To | Description | Unit |
|--------------|---------|-------------|------|
| `pmt` | `pmt` | PMT photon counts | counts |
| `pmt_counts` | `pmt` | Alias | counts |
| `photon_counts` | `pmt` | Alias | counts |
| `pressure` | `pressure` | Chamber pressure | mbar |
| `chamber_pressure` | `pressure` | Alias | mbar |
| `vacuum` | `pressure` | Alias | mbar |

## LabVIEW Implementation

### Wavemeter.vi Example

**Block Diagram:**
```
[Initialize]
    │
    ├─> [TCP Open Connection] ──> Server: "192.168.1.100", Port: 5560
    │
    └─> [While Loop]
            │
            ├─> [Read Wavemeter] ──> Frequency (MHz)
            │
            ├─> [Build JSON Cluster]
            │       source: "wavemeter"
            │       channel: "laser_freq"
            │       value: <frequency>
            │       timestamp: [Get Date/Time In Seconds]
            │
            ├─> [Flatten To JSON]
            │
            ├─> [Concatenate Strings] ──> JSON + "\n"
            │
            ├─> [TCP Write]
            │
            ├─> [Wait] ──> 100-500 ms
            │
            └─> [Check Stop]
```

**JSON Output Example:**
```json
{"source": "wavemeter", "channel": "laser_freq", "value": 212.456789, "timestamp": 1706380800.123}
```

### SMILE.vi Example

**Block Diagram:**
```
[Initialize]
    │
    ├─> [TCP Open Connection] ──> Server: "192.168.1.100", Port: 5560
    │
    └─> [While Loop]
            │
            ├─> [Read PMT] ──> Counts
            ├─> [Build JSON] ──> source: "smile", channel: "pmt"
            ├─> [TCP Write]
            │
            ├─> [Read Pressure] ──> mbar  
            ├─> [Build JSON] ──> source: "smile", channel: "pressure"
            ├─> [TCP Write]
            │
            ├─> [Wait] ──> 100-500 ms
            │
            └─> [Check Stop]
```

**JSON Output Examples:**
```json
{"source": "smile", "channel": "pmt", "value": 1250.0, "timestamp": 1706380800.123}
{"source": "smile", "channel": "pressure", "value": 1.2e-10, "timestamp": 1706380800.124}
```

## Starting the System

### Step 1: Start Data Server

```bash
python server/communications/data_server.py
```

You should see:
```
📊 Data Server listening on 0.0.0.0:5560
   Ready for LabVIEW connections (Wavemeter.vi, SMILE.vi)
```

### Step 2: Start Flask Server

```bash
python server/Flask/flask_server.py
```

### Step 3: Start LabVIEW Programs

Run your `Wavemeter.vi` and `SMILE.vi` programs.

### Step 4: Verify Connection

In the Python console, you should see:
```
📡 Connection from ('192.168.1.50', 12345)
Data: wavemeter/laser_freq = 212.457
Data: smile/pmt = 1250.0
Data: smile/pressure = 1.2e-10
```

## Testing Without LabVIEW

Use the mock sender to test the system:

```bash
# Simulate both wavemeter and SMILE
python labview/mock_labview_sender.py --wavemeter --smile

# Wavemeter only
python labview/mock_labview_sender.py --wavemeter-only

# SMILE only  
python labview/mock_labview_sender.py --smile-only

# Custom rates
python labview/mock_labview_sender.py --wavemeter --smile --freq-rate 5.0 --pmt-rate 10.0
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
    "wavemeter": {"connected": true, "last_seen": 1706380800.5},
    "smile": {"connected": true, "last_seen": 1706380800.4}
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

- **Status Bar**: Green dots indicate connected data sources (Wavemeter, SMILE)
- **Telemetry Plots**: 
  - **Laser Frequency** (MHz) - from Wavemeter.vi
  - **PMT** (counts) - from SMILE.vi
  - **Pressure** (mbar) - from SMILE.vi
  - **Pos X/Y, Sig X/Y** - from camera (simulated if no real data)

## Troubleshooting

### LabVIEW Can't Connect

1. **Check server is running:**
   ```bash
   python server/communications/data_server.py
   ```

2. **Verify IP address:**
   - LabVIEW must connect to Python server's IP
   - If running on same PC: `127.0.0.1`
   - If different PCs: Check network settings

3. **Check firewall:**
   - Open port 5560 on Python server
   - Allow LabVIEW through firewall

4. **Test with mock sender:**
   ```bash
   python labview/mock_labview_sender.py --wavemeter --smile
   ```

### Data Not Showing in Plots

1. **Check data format:**
   - Ensure valid JSON
   - Must end with newline (`\n`)
   - Use correct source/channel names

2. **Verify in server console:**
   - Should see "Data: wavemeter/laser_freq = ..."

3. **Check browser console:**
   - Open developer tools (F12)
   - Check for JSON parse errors

### Connection Drops

1. **Enable auto-reconnect in LabVIEW:**
   - Try to reconnect every 5 seconds on failure

2. **Check network stability:**
   - Use wired connection if possible
   - Check for IP conflicts

## Performance Considerations

### Update Rates

Recommended maximum rates:
- **Wavemeter**: 1-10 Hz (laser frequency doesn't change rapidly)
- **PMT**: 10-100 Hz (depends on experiment)
- **Pressure**: 0.1-1 Hz (slow changes)

### Buffer Size

The server keeps:
- **300 seconds** of history (5 minutes)
- **1000 data points** per channel (rolling buffer)

Old data is automatically discarded.

### Network Bandwidth

Typical bandwidth per source:
- JSON overhead: ~100 bytes per sample
- At 10 Hz: ~1 KB/s per channel
- Negligible impact on modern networks

## Advanced Topics

### Sending Multiple Channels

You can send multiple channels in one TCP message:
```json
{"source": "smile", "channel": "pmt", "value": 1250, "timestamp": 1706380800.1}
{"source": "smile", "channel": "pressure", "value": 1.2e-10, "timestamp": 1706380800.1}
```

### Custom Metadata

Add extra fields (ignored by server, useful for debugging):
```json
{
  "source": "wavemeter",
  "channel": "laser_freq",
  "value": 212.456,
  "timestamp": 1706380800.123,
  "unit": "MHz",
  "laser_name": "369nm_cooling",
  "labview_version": "2021"
}
```

### Multiple LabVIEW Instances

You can run multiple VIs on different PCs, all sending to the same server:
- Wavemeter PC: `192.168.1.10`
- SMILE PC: `192.168.1.20`
- Python Server: `192.168.1.100:5560`

## Complete Startup Sequence

```bash
# Terminal 1: Data Ingestion Server
python server/communications/data_server.py

# Terminal 2: Control Manager
python server/communications/manager.py

# Terminal 3: Flask Web Server
python server/Flask/flask_server.py

# (Optional) Terminal 4: Mock LabVIEW for testing
python labview/mock_labview_sender.py --wavemeter --smile
```

Then:
1. Start LabVIEW VIs (or use mock sender)
2. Open browser to `http://localhost:5000`
3. Verify data sources show green dots
4. Watch telemetry plots update in real-time
