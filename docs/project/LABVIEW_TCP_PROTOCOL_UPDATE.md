# LabVIEW TCP Protocol Update

**Date:** 2026-02-05  
**Purpose:** Document the simplified TCP protocol for LabVIEW/SMILE communication

---

## Summary

The LabVIEW TCP protocol has been simplified to use only two fields: `device` and `value`.

### Before (Legacy Format)
```json
{
  "command": "set_voltage",
  "device": "u_rf",
  "value": 200.0,
  "timestamp": 1706380800.123,
  "request_id": "REQ_000001_1706380800123"
}
```

### After (Simplified Format)
```json
{
  "device": "u_rf",
  "value": 200.0
}
```

---

## Supported Devices

| Device | Type | Range | Description |
|--------|------|-------|-------------|
| `u_rf` | float | 0-1000 | RF voltage in millivolts |
| `piezo` | float | 0-4 | Piezo voltage in volts |
| `hd_valve` | int | 0 or 1 | HD valve shutter (1=on, 0=off) |
| `be_oven` | int | 0 or 1 | Be+ oven (1=on, 0=off) |
| `uv3` | int | 0 or 1 | UV3 laser (1=on, 0=off) |
| `bephi` | int | 0 or 1 | Bephi (1=on, 0=off) |
| `b_field` | int | 0 or 1 | B-field (1=on, 0=off) |
| `e_gun` | int | 0 or 1 | Electron gun (1=on, 0=off) |

---

## Boolean Values

For boolean devices, always send:
- `1` for True/on
- `0` for False/off

### Examples

```json
// Turn on Be+ oven
{"device": "be_oven", "value": 1}

// Turn off electron gun
{"device": "e_gun", "value": 0}

// Set RF voltage to 200 mV
{"device": "u_rf", "value": 200.0}

// Set piezo to 2.5V
{"device": "piezo", "value": 2.5}
```

---

## Implementation Details

### Python Side (Already Updated)

The `labview_interface.py` module has been updated:

```python
# In _send_command_raw() method:
simplified_cmd = {
    "device": command.device,
    "value": 1 if command.value is True else (0 if command.value is False else command.value)
}

message = json.dumps(simplified_cmd) + "\n"
self.socket.sendall(message.encode('utf-8'))
```

### LabVIEW Side (Needs Update)

Your LabVIEW TCP server should:

1. **Parse JSON** with only `device` and `value` fields
2. **Handle boolean values** as integers (1/0)
3. **Respond** with simple "OK" or JSON `{"status": "ok"}`

#### LabVIEW Pseudocode

```labview
// TCP Read (until newline)
json_string = ReadTCP(connection)

// Parse JSON
data = JSON_Parse(json_string)
device = data["device"]
value = data["value"]

// Handle device
switch(device):
    case "u_rf":
        SetRFVoltage(value)
    case "piezo":
        SetPiezoVoltage(value)
    case "be_oven":
        SetBeOven(value == 1)
    case "e_gun":
        SetEGun(value == 1)
    // ... etc

// Send response
WriteTCP(connection, "OK\n")
```

---

## Code Changes

### File: `src/server/comms/labview_interface.py`

1. **Updated module docstring** to document simplified protocol
2. **Modified `_send_command_raw()`** to send only `device` and `value` fields
3. **Added boolean conversion** - True/False converted to 1/0
4. **Updated `_send_ping()`** to use simplified format with device="ping"

### File: `docs/integrations/COMMUNICATION_PROTOCOL.md`

Updated Section 6.5 (LabVIEW SMILE Protocol) with:
- Simplified device/value format
- Boolean handling (1/0)
- Updated examples

---

## Migration Guide

### For LabVIEW Developers

1. **Update TCP parser** to expect only `device` and `value` fields
2. **Remove dependency** on `command`, `timestamp`, `request_id` fields
3. **Update boolean handling** to check for integer 1/0 instead of boolean true/false
4. **Simplify response** - can now send simple "OK" instead of full JSON

### Backward Compatibility

The Python side still maintains internal structures (`LabVIEWCommand`, `LabVIEWCommandType`) for:
- Code organization
- Kill switch integration
- Retry logic

Only the wire format has been simplified.

---

## Testing

### Manual Test

```python
from src.server.comms.labview_interface import LabVIEWInterface

lv = LabVIEWInterface()
lv.connect()

# Should send: {"device": "u_rf", "value": 200.0}
lv.set_rf_voltage(200.0)

# Should send: {"device": "be_oven", "value": 1}
lv.set_be_oven(True)

# Should send: {"device": "e_gun", "value": 0}
lv.set_e_gun(False)
```

### Wire Format Verification

Use a TCP sniffer or add logging to verify:

```python
# Add to labview_interface.py _send_command_raw():
self.logger.info(f"TCP OUT: {message.strip()}")
```

Expected output:
```
TCP OUT: {"device": "u_rf", "value": 200.0}
TCP OUT: {"device": "be_oven", "value": 1}
TCP OUT: {"device": "piezo", "value": 2.5}
```

---

## Notes

- The protocol uses **newline (`\n`)** as message delimiter
- LabVIEW must buffer TCP data until newline is received (handles fragmentation)
- Response format is flexible: LabVIEW can send JSON or simple text
- All boolean values are converted to integers (1/0) before sending

---

**Last Updated:** 2026-02-05
