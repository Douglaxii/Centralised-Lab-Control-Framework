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

2. **Command Parser VI**
   - Input: JSON string
   - Parse `command`, `device`, `value` fields
   - Route to appropriate handler

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

#### TCP Listener (Pseudocode)
```
port = 5559
listener = TCP Create Listener(port)

WHILE (running)
    connection = TCP Wait On Listener(listener, timeout=-1)
    
    WHILE (connected)
        data = TCP Read (delim=\n)
        IF (data available)
            command = JSON Parse(data)
            result = Execute Command(command)
            response = JSON Build(result)
            TCP Write (response + \n)
        END IF
    END WHILE
END WHILE
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

## Security Considerations

1. **Network**: Use internal network only (192.168.x.x)
2. **Firewall**: Restrict port 5559 to specific IPs if possible
3. **Validation**: LabVIEW should validate all values before applying
4. **Safety Limits**: Implement hardware limits in LabVIEW (not just Python)

## Safety Integration

When Safety Mode is engaged from the web dashboard:

1. Python sends `emergency_stop` command
2. LabVIEW should:
   - Immediately set U_RF to 0V
   - Turn off Be+ oven
   - Turn off B-field
   - Turn off UV3
   - Turn off E-gun
   - Close all HD shutters
   - Set piezo to 0V

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
