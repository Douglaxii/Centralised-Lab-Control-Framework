---

> ?? **DEPRECATED**: This file has been moved. Please see the new documentation structure.
> 
> **New Location**: See README.md for the reorganized documentation.
> 
> This file will be removed in version 3.0.

---
# LabVIEW SMILE Integration Guide

This document describes how to integrate the Python Control Manager with your SMILE LabVIEW program for remote hardware control.

## Overview

The Control Manager communicates with LabVIEW via **TCP sockets** using a **JSON-based protocol**. When you change settings in the web dashboard, the manager automatically forwards these commands to LabVIEW.

## Supported Hardware Controls

| Device | Type | Range | Command Example |
|--------|------|-------|-----------------|
| U_RF | Voltage | 0 - 1000 V | `{"command": "set_voltage", "device": "U_RF", "value": 500.0}` |
| Piezo | Voltage | -10 to +10 V | `{"command": "set_voltage", "device": "piezo", "value": 2.5}` |
| Be+ Oven | Toggle | on/off | `{"command": "set_toggle", "device": "be_oven", "value": true}` |
| B-field | Toggle | on/off | `{"command": "set_toggle", "device": "b_field", "value": true}` |
| Bephi | Toggle | on/off | `{"command": "set_toggle", "device": "bephi", "value": false}` |
| UV3 | Toggle | on/off | `{"command": "set_toggle", "device": "uv3", "value": true}` |
| E-gun | Toggle | on/off | `{"command": "set_toggle", "device": "e_gun", "value": false}` |
| HD Shutter 1 | Shutter | open/close | `{"command": "set_shutter", "device": "hd_shutter_1", "value": true}` |
| HD Shutter 2 | Shutter | open/close | `{"command": "set_shutter", "device": "hd_shutter_2", "value": true}` |
| DDS | Frequency | MHz | `{"command": "set_frequency", "device": "dds", "value": 212.5}` |

## Configuration

Edit `config/settings.yaml`:

```yaml
labview:
  enabled: true                 # Enable/disable LabVIEW communication
  host: "192.168.1.100"         # IP address of LabVIEW/SMILE computer
  port: 5559                    # TCP port LabVIEW listens on
  timeout: 5.0                  # Command timeout (seconds)
  retry_delay: 1.0              # Retry delay on failure
  max_retries: 3                # Max retry attempts
  auto_reconnect: true          # Auto-reconnect if connection lost
```

## Communication Protocol

### Connection

1. LabVIEW acts as **TCP Server** (listener)
2. Python Manager is **TCP Client** (connects to LabVIEW)
3. Connection is persistent (maintained open)
4. Auto-reconnect on connection loss

### Message Format

All messages are **JSON strings terminated by newline (`\n`)**.

#### Command from Python to LabVIEW:

```json
{
  "command": "set_voltage",
  "device": "U_RF",
  "value": 500.0,
  "timestamp": 1706380800.123,
  "request_id": "REQ_000001_1706380800123"
}
```

#### Response from LabVIEW to Python:

```json
{
  "request_id": "REQ_000001_1706380800123",
  "status": "ok",
  "device": "U_RF",
  "value": 500.0,
  "message": null,
  "timestamp": 1706380800.456
}
```

### Status Codes

| Status | Meaning |
|--------|---------|
| `ok` | Command executed successfully |
| `error` | Command failed (check `message` field) |
| `busy` | Device busy, command queued or rejected |

### Command Types

#### 1. Set Voltage (U_RF, Piezo)
```json
{
  "command": "set_voltage",
  "device": "U_RF",
  "value": 500.0
}
```

#### 2. Set Toggle (Be+ Oven, B-field, Bephi, UV3, E-gun)
```json
{
  "command": "set_toggle",
  "device": "be_oven",
  "value": true
}
```

#### 3. Set Shutter (HD Valve)
```json
{
  "command": "set_shutter",
  "device": "hd_shutter_1",
  "value": true
}
```

#### 4. Set Frequency (DDS)
```json
{
  "command": "set_frequency",
  "device": "dds",
  "value": 212.5
}
```

#### 5. Get Status
```json
{
  "command": "get_status",
  "device": "all"
}
```

Response:
```json
{
  "request_id": "...",
  "status": "ok",
  "device": "all",
  "value": {
    "U_RF": 500.0,
    "piezo": 0.0,
    "be_oven": false,
    "b_field": true,
    "bephi": false,
    "uv3": false,
    "e_gun": false,
    "hd_shutter_1": false,
    "hd_shutter_2": false,
    "dds_freq": 212.5
  }
}
```

#### 6. Emergency Stop
```json
{
  "command": "emergency_stop",
  "device": "all"
}
```

#### 7. Ping (Keepalive)
```json
{
  "command": "ping",
  "device": "system"
}
```

## LabVIEW Implementation Example

### Block Diagram Structure

```
[TCP Listener] → [Wait on Connection] → [While Loop]
                                     ↓
                              [Read Line (\n)]
                                     ↓
                              [JSON Parse]
                                     ↓
                              [Case Structure]
                                     ↓
                        ┌──────────┼──────────┐
                   [Voltage]  [Toggle]  [Frequency]
                        ↓          ↓          ↓
                   [Set DAC]  [Set DIO]  [Set DDS]
                        ↓          ↓          ↓
                   [JSON Response] → [Write Line]
```

### LabVIEW VI Structure

1. **TCP Server VI**
   - Port: 5559 (configurable)
   - Listen for incoming connections
   - Handle multiple commands per connection

2. **Command Parser VI (IMPORTANT: TCP Buffer Handling)**
   - **Input:** Raw TCP data stream
   - **CRITICAL:** Must buffer data until newline (`\n`) is received
   - Parse complete JSON strings only after receiving `\n`
   - Route to appropriate handler

   ⚠️ **TCP Fragmentation Warning:** TCP is a stream protocol. A single `TCP Read` may return:
   - A partial JSON message (e.g., `{"command": "set_`)
   - A complete message (e.g., `{"command": "set_voltage", ...}\n`)
   - Multiple messages (e.g., `{"command":...}\n{"command":...}\n`)

3. **Device Handlers**
   - `Set U_RF.vi`: Controls RF voltage via DAC
   - `Set Piezo.vi`: Controls piezo voltage
   - `Set Toggle.vi`: Controls digital outputs (oven, B-field, etc.)
   - `Set DDS.vi`: Controls DDS frequency
   - `Set Shutter.vi`: Controls HD valve shutters

4. **Response Builder VI**
   - Input: Command result
   - Build JSON response with matching `request_id`
   - Include `status` (ok/error) and `message` if error

### Example LabVIEW Code Snippets

#### TCP Listener with Buffer Handling (CORRECT WAY)
```
port = 5559
listener = TCP Create Listener(port)
data_buffer = ""

WHILE (running)
    connection = TCP Wait On Listener(listener, timeout=-1)
    data_buffer = ""  // Clear buffer on new connection
    
    WHILE (connected)
        // Read raw bytes (do NOT use delim mode here)
        raw_data = TCP Read (mode=raw, max_bytes=4096, timeout=100ms)
        
        IF (raw_data received)
            // Append to buffer
            data_buffer = data_buffer + raw_data
            
            // Process all complete messages in buffer
            WHILE (data_buffer contains '\n')
                // Extract one line from buffer
                line, data_buffer = Split At First '\n'(data_buffer)
                line = Trim(line)
                
                IF (line not empty)
                    command = JSON Unflatten(line)
                    result = Execute Command(command)
                    response = JSON Flatten(result)
                    TCP Write (response + '\n')
                END IF
            END WHILE
        END IF
        
        // Check for disconnect or timeout
        IF (connection lost)
            BREAK
        END IF
    END WHILE
END WHILE
```

#### INCORRECT - Direct JSON Parse (Do NOT Use)
```
// WARNING: This will FAIL with TCP fragmentation!
WHILE (connected)
    data = TCP Read (delim=\n)           // May not work as expected
    command = JSON Unflatten(data)      // Will fail on partial data
    ...
END WHILE
```

#### Buffer Processing VI (Recommended Implementation)
```
VI: Process_TCP_Buffer.vi

Inputs:
    - buffer (string, shift register)
    - new_data (string from TCP Read)
    
Outputs:
    - buffer (updated)
    - complete_messages (array of strings)
    
Logic:
    1. Append new_data to buffer
    2. Initialize empty messages array
    3. WHILE buffer contains '\n':
           Split buffer at first '\n' -> message, buffer
           Add message to messages array
    4. Return updated buffer and messages array
```

#### Command Executor (Case Structure)
```
CASE command OF
    "set_voltage":
        IF device == "U_RF"
            Set DAC Channel (U_RF, value)
        ELSE IF device == "piezo"
            Set DAC Channel (Piezo, value)
        END IF
        
    "set_toggle":
        DIO Channel = Lookup DIO(device)
        Write Digital Line (DIO Channel, value)
        
    "set_shutter":
        Shutter Channel = Extract Number(device)
        Write Digital Line (Shutter Channel, value)
        
    "set_frequency":
        Set DDS Frequency (value)
        
    "get_status":
        status = Read All Device Status()
        
    "emergency_stop":
        Set All Voltages to 0
        Turn Off All Toggles
        Close All Shutters
        
    "ping":
        // Just respond with ok
END CASE
```

## Testing

### Test LabVIEW Connection

1. Start your LabVIEW TCP Server (port 5559)
2. Start the Python Manager
3. Check manager logs for:
   ```
   INFO - Connected to LabVIEW at 192.168.1.100:5559
   ```

### Test Individual Commands

Run the standalone test interface:

```bash
python server/communications/labview_interface.py
```

Commands:
```
> status           # Check connection and LabVIEW status
> rf 500          # Set U_RF to 500V
> piezo 2.5       # Set piezo to 2.5V
> oven 1          # Turn on Be+ oven
> bfield 1        # Turn on B-field
> uv3 1           # Turn on UV3
> egun 1          # Turn on e-gun
> estop           # Emergency stop
> quit            # Exit
```

### Test via Web Dashboard

1. Open `http://localhost:5000`
2. Try controls:
   - Set RF Voltage to 400V
   - Toggle Be+ Oven on
   - Set Piezo to 1.0V
3. Verify LabVIEW receives commands

## Troubleshooting

### Connection Issues

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| "Failed to connect to LabVIEW" | LabVIEW not running | Start LabVIEW TCP Server |
| | Wrong IP address | Check `labview.host` in config |
| | Firewall blocking port | Open port 5559 in firewall |
| | Port already in use | Change port in config |

### Command Failures

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| Command returns "error" | Device not responding | Check hardware connections |
| | Invalid value | Check value is within valid range |
| | Device busy | Retry command or check device state |

### Data Format Issues

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| "Invalid JSON response" | Missing newline terminator | Ensure `\n` after each JSON |
| | Malformed JSON | Validate JSON syntax |
| | Wrong encoding | Use UTF-8 encoding |
| "Unflatten JSON error" at random times | TCP fragmentation - partial message received | Implement buffer handling (see TCP Buffer section above) |
| Missing commands | Multiple messages in one TCP read | Process all lines in buffer, not just first |

### TCP Fragmentation Issues

**Problem:** LabVIEW occasionally shows "JSON parse error" or receives incomplete data

**Root Cause:** TCP is a stream protocol, not a packet protocol. Messages may be split across multiple `TCP Read` calls, or multiple messages may arrive in a single call.

**Solution:** Always use buffer-based reading:
1. Maintain a string buffer (shift register in loop)
2. Append each `TCP Read` result to the buffer
3. Split buffer at newline characters
4. Only process complete lines
5. Keep remainder in buffer for next iteration

See "TCP Listener with Buffer Handling" example above for correct implementation.

## Security Considerations

1. **Network**: Use internal network only (192.168.x.x)
2. **Firewall**: Restrict port 5559 to specific IPs if possible
3. **Validation**: LabVIEW should validate all values before applying
4. **Safety Limits**: Implement hardware limits in LabVIEW (not just Python)

## Safety Integration

### Kill Switch System

The control system implements a **triple-layer kill switch** for time-limited outputs:

| Device | Time Limit | Purpose |
|--------|------------|---------|
| Piezo Output | 10 seconds max | Prevent piezo damage from sustained voltage |
| E-Gun | 30 seconds max | Prevent e-gun overheating |

**Layers:**
1. **Flask UI**: Visual countdown, manual stop button
2. **Control Manager**: Publishes emergency zero commands
3. **LabVIEW Worker**: Direct hardware commands (final layer)

See [SAFETY_KILL_SWITCH.md](SAFETY_KILL_SWITCH.md) for complete documentation.

### Emergency Stop

When Safety Mode is engaged from the web dashboard:

1. Python sends `emergency_stop` command
2. All kill switches are triggered immediately
3. LabVIEW should:
   - Immediately set U_RF to 0V
   - Turn off Be+ oven
   - Turn off B-field
   - Turn off UV3
   - Turn off E-gun
   - Close all HD shutters
   - Set piezo to 0V

### Hardware Safety Requirements

**CRITICAL:** LabVIEW must ALSO implement independent hardware limits:

```
Recommended Hardware Protections:
├── Piezo Output
│   ├── Hardware timer: 10s max ON time
│   ├── Overcurrent protection: <100mA
│   └── Thermal shutdown: >50°C
│
├── E-Gun
│   ├── Hardware timer: 30s max ON time
│   ├── Thermal protection: >80°C
│   └── Current limiting: <500mA
│
└── All Outputs
    ├── Independent watchdog timer
    └── Emergency cutoff relay
```

The Python kill switch is a **software safety layer**, not a replacement for hardware protection.

## Advanced Features

### Status Callback

LabVIEW can push status updates to Python by sending unsolicited JSON:

```json
{
  "request_id": "STATUS_UPDATE",
  "status": "ok", 
  "device": "U_RF",
  "value": 495.2,
  "timestamp": 1706380800.789
}
```

Python will log these but not expect a response.

### Batch Commands

For atomic operations, LabVIEW can accept a batch:

```json
{
  "command": "batch",
  "device": "multiple",
  "value": [
    {"device": "U_RF", "value": 500.0},
    {"device": "b_field", "value": true}
  ]
}
```

All operations in the batch should be applied simultaneously.

## Sending Data to Python (File-Based)

In addition to receiving commands, LabVIEW programs can **send telemetry data** to the Python dashboard by writing files to the shared network drive.

### Supported Data Types

| Source | Directory | Format | Content |
|--------|-----------|--------|---------|
| Wavemeter | `Y:\Xi\Data\telemetry\wavemeter\` | CSV | `timestamp,frequency_mhz` |
| SMILE PMT | `Y:\Xi\Data\telemetry\smile\pmt\` | CSV | `timestamp,pmt_counts` |
| SMILE Pressure | `Y:\Xi\Data\telemetry\smile\pressure\` | CSV | `timestamp,pressure_mbar` |

### File Format

**CSV Format:**
```
1706380800.123,212.456789
1706380800.623,212.456812
```

- One line per data point
- Fields: `timestamp,value` (comma-separated)
- Timestamp: Unix epoch in seconds (with decimals for ms)
- File extension: `.dat`

### LabVIEW Implementation Example

```
[While Loop]
    │
    ├─> [Read Wavemeter] ──> Frequency
    │
    ├─> [Get Date/Time In Seconds] ──> Timestamp
    │
    ├─> [Format Into String] ──> "%.3f,%.6f\n"
    │
    ├─> [Build Path] ──> "Y:\Xi\Data\telemetry\wavemeter\freq_001.dat"
    │
    └─> [Write to Text File]
```

### Important Notes

1. **Write atomically**: Write to `.tmp` file, then rename to `.dat`
2. **Manage disk space**: Delete old files periodically (Python doesn't delete them)
3. **Rate limit**: 1-10 Hz is sufficient for most telemetry

See [DATA_INTEGRATION.md](DATA_INTEGRATION.md) for complete details.

## Integration Checklist

- [ ] LabVIEW TCP Server running on port 5559
- [ ] Python Manager configured with correct LabVIEW IP
- [ ] Test `set_voltage` command (U_RF)
- [ ] Test `set_voltage` command (Piezo)
- [ ] Test `set_toggle` commands (all 5 toggles)
- [ ] Test `set_shutter` commands
- [ ] Test `set_frequency` command
- [ ] Test `get_status` command
- [ ] Test `emergency_stop` command
- [ ] Test auto-reconnect (restart LabVIEW, verify reconnection)
- [ ] Verify safety defaults work correctly
