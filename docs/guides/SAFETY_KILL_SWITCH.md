# Safety Kill Switch System

## Overview

The Safety Kill Switch System provides **triple-layer protection** for time-limited hardware outputs to prevent accidental damage or unsafe operating conditions.

**Protected Devices:**
- **Piezo Output**: Maximum 10 seconds ON time
- **E-Gun**: Maximum 30 seconds ON time

## Three-Layer Protection Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 1: FLASK UI                            │
│  - User interface warnings and confirmations                     │
│  - Visual countdown timers                                       │
│  - Manual kill switch button                                     │
│  - 5 Hz status polling                                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   LAYER 2: CONTROL MANAGER                      │
│  - Central coordinator kill switch                               │
│  - Publishes emergency zero commands to workers                  │
│  - Integrates with STOP/safety commands                          │
│  - 10 Hz watchdog monitoring                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   LAYER 3: LABVIEW WORKER                       │
│  - Final hardware-level protection                               │
│  - Direct TCP commands to SMILE interface                        │
│  - 20 Hz watchdog (fastest response)                             │
│  - Independent of Flask and Manager                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      HARDWARE (SMILE)                           │
│  - Physical voltage outputs                                      │
│  - Must ALSO implement hardware limits                           │
└─────────────────────────────────────────────────────────────────┘
```

## Layer 1: Flask Server Kill Switch

**File:** `server/Flask/flask_server.py`

**Features:**
- Visual countdown timer on UI (updates 5 times/second)
- Color-coded warnings:
  - **Green**: >50% time remaining
  - **Yellow**: <50% time remaining
  - **Red**: <20% time remaining (urgent)
- Confirmation dialogs before enabling
- Kill switch banner with manual STOP button
- Auto-reset when time limit exceeded

**API Endpoints:**
```
POST /api/control/piezo/output      # Enable/disable with kill switch
POST /api/control/toggle/e_gun      # Enable/disable with kill switch
GET  /api/killswitch/status         # Get status of all devices
POST /api/killswitch/trigger        # Manual trigger
```

**Configuration:**
```python
KILL_SWITCH_LIMITS = {
    "piezo": 10.0,   # 10 seconds
    "e_gun": 30.0,   # 30 seconds
}
```

## Layer 2: Manager Kill Switch

**File:** `server/communications/manager.py`

**Class:** `ManagerKillSwitch`

**Features:**
- Receives arming commands from Flask
- Publishes emergency zero commands to all workers
- Integrated with STOP command
- 10 Hz watchdog monitoring

**Key Methods:**
```python
# Arm kill switch (when output enabled)
kill_switch.arm("piezo", metadata)
kill_switch.arm("e_gun", metadata)

# Disarm kill switch (when output disabled by user)
kill_switch.disarm("piezo")
kill_switch.disarm("e_gun")

# Manual trigger
kill_switch.trigger(device, reason)
```

**Emergency Zero Command:**
When triggered, the manager publishes:
```json
{
  "type": "EMERGENCY_ZERO",
  "device": "piezo",
  "reason": "kill_switch_triggered",
  "timestamp": 1706380800.123
}
```

## Layer 3: LabVIEW Worker Kill Switch

**File:** `server/communications/labview_interface.py`

**Class:** `LabVIEWKillSwitch`

**Features:**
- Fastest response time (20 Hz watchdog)
- Direct TCP commands to SMILE LabVIEW
- Final safety layer before hardware
- Independent operation (works even if Flask/Manager fail)

**Integration:**
```python
# Automatically armed when voltage/state set
def set_piezo_voltage(self, voltage):
    if voltage > 0:
        self.kill_switch.arm("piezo")
    else:
        self.kill_switch.disarm("piezo")
    # ... send command

def set_e_gun(self, state):
    if state:
        self.kill_switch.arm("e_gun")
    else:
        self.kill_switch.disarm("e_gun")
    # ... send command
```

## User Interface

### Piezo Control

```
┌─────────────────────────────────────────────────────┐
│ Piezo Control (Kill Switch: 10s max)  [SAFETY CRITICAL]
├─────────────────────────────────────────────────────┤
│ Set: [2.50] V [Set]  Slider: [─────────●────] 2.50V │
│ [OUTPUT ON]  [TIMER: 7.3s]                          │
└─────────────────────────────────────────────────────┘
```

**Workflow:**
1. User sets desired voltage using input or slider
2. User clicks "OUTPUT ON" button
3. Confirmation dialog appears:
   > "⚠️ WARNING: Piezo output will be limited to 10 seconds...\n\nEnable output?"
4. If confirmed:
   - Button changes to "OUTPUT ON" (orange with pulsing animation)
   - Timer display appears (counting down from 10)
   - Kill switch banner appears at top of page
5. When timer reaches 0: Automatic shutdown to 0V

### E-Gun Control

```
┌─────────────────────────────────────────────────────┐
│ E-Gun (Kill Switch: 30s max)                        │
├─────────────────────────────────────────────────────┤
│ [E-Gun]  [TIMER: 23s]                               │
└─────────────────────────────────────────────────────┘
```

**Workflow:**
1. User clicks "E-Gun" button
2. Confirmation dialog appears:
   > "⚠️ WARNING: E-Gun will be limited to 30 seconds...\n\nEnable E-Gun?"
3. If confirmed:
   - Button turns orange with pulsing animation
   - Timer appears (counting down from 30)
4. When timer reaches 0: Automatic shutdown

### Kill Switch Banner

When any protected device is active, a red banner appears:

```
┌─────────────────────────────────────────────────────────────────┐
│ ⚠️ KILL SWITCH ACTIVE: PIEZO  Auto-shutdown in [ 5.2s ] [STOP]  │
└─────────────────────────────────────────────────────────────────┘
```

The "STOP" button allows immediate manual shutdown.

## Kill Switch Triggers

A kill switch can be triggered by:

1. **Time Limit Exceeded** (automatic)
   - Piezo: After 10 seconds
   - E-gun: After 30 seconds

2. **Manual Trigger** (user-initiated)
   - Clicking STOP button on banner
   - Calling `/api/killswitch/trigger` API

3. **Safety Shutdown** (system-initiated)
   - STOP command from safety system
   - Emergency stop button
   - Mode change to SAFE

4. **Application Shutdown** (system-initiated)
   - Flask server shutdown
   - Manager shutdown
   - LabVIEW interface shutdown

## API Reference

### Set Piezo Setpoint
```http
POST /api/control/piezo/setpoint
Content-Type: application/json

{"voltage": 2.5}
```

**Response:**
```json
{
  "status": "success",
  "setpoint": 2.5,
  "output_active": false
}
```

### Enable/Disable Piezo Output
```http
POST /api/control/piezo/output
Content-Type: application/json

{"enable": true}
```

**Response:**
```json
{
  "status": "success",
  "output": true,
  "voltage": 2.5,
  "kill_switch": {
    "armed": true,
    "time_limit_seconds": 10,
    "warning": "AUTO-SHUTOFF AFTER 10 SECONDS"
  }
}
```

### Toggle E-Gun
```http
POST /api/control/toggle/e_gun
Content-Type: application/json

{"state": true}
```

**Response:**
```json
{
  "status": "success",
  "toggle": "e_gun",
  "state": true,
  "kill_switch": {
    "armed": true,
    "time_limit_seconds": 30,
    "warning": "AUTO-SHUTOFF AFTER 30 SECONDS"
  }
}
```

### Get Kill Switch Status
```http
GET /api/killswitch/status
```

**Response:**
```json
{
  "status": "success",
  "devices": {
    "piezo": {
      "active": true,
      "elapsed_seconds": 3.5,
      "remaining_seconds": 6.5,
      "time_limit": 10,
      "killed": false
    },
    "e_gun": {
      "active": false,
      "time_limit": 30,
      ...
    }
  },
  "limits": {
    "piezo": 10.0,
    "e_gun": 30.0
  }
}
```

### Manual Trigger
```http
POST /api/killswitch/trigger
Content-Type: application/json

{"device": "piezo"}
```

## Implementation Checklist

### For Developers

- [ ] Kill switch class implemented in Flask server
- [ ] Kill switch class implemented in Manager
- [ ] Kill switch class implemented in LabVIEW interface
- [ ] UI shows countdown timers
- [ ] UI shows confirmation dialogs
- [ ] API endpoints documented
- [ ] Emergency zero commands published
- [ ] Shutdown handlers trigger kill switches
- [ ] Logs include kill switch events

### For Operators

- [ ] Understand 10s limit for piezo
- [ ] Understand 30s limit for e-gun
- [ ] Know how to manually trigger kill switch
- [ ] Verify kill switch works in testing
- [ ] Report any kill switch failures immediately

### For Hardware Engineers

- [ ] SMILE LabVIEW implements hardware limits
- [ ] Piezo driver has overcurrent protection
- [ ] E-gun has thermal protection
- [ ] Independent hardware timer as backup

## Troubleshooting

### Kill Switch Triggered Unexpectedly

**Symptoms:** Output turns off before time limit

**Possible Causes:**
1. Multiple kill switch layers triggering (expected - all layers should trigger)
2. Time synchronization issues between layers
3. Manual trigger by another user

**Solution:**
- Check logs for trigger reason
- Verify system time is synchronized
- Re-enable output if safe to do so

### Kill Switch Not Triggering

**Symptoms:** Output stays on beyond time limit

**Possible Causes:**
1. Kill switch thread crashed
2. LabVIEW connection lost
3. Watchdog thread blocked

**Solution:**
- Check logs for errors
- Verify all components are running
- Use manual kill switch if needed
- Restart components if necessary

### False Triggers

**Symptoms:** Kill switch triggers immediately or sporadically

**Possible Causes:**
1. Incorrect time calculation
2. System clock issues
3. Race conditions

**Solution:**
- Check system clock
- Review kill switch logic
- Update to latest software version

## Safety Notes

⚠️ **IMPORTANT:**

1. The kill switch system is a **software safety layer**, not a replacement for hardware limits.

2. Always implement **hardware-level protection** in SMILE LabVIEW:
   - Hardware timers
   - Overcurrent protection
   - Thermal protection

3. **Test the kill switch system regularly**:
   ```bash
   # Test piezo kill switch
   curl -X POST http://localhost:5000/api/control/piezo/output \
     -H "Content-Type: application/json" \
     -d '{"enable": true}'
   # Wait 10 seconds, verify it turns off
   
   # Test e-gun kill switch
   curl -X POST http://localhost:5000/api/control/toggle/e_gun \
     -H "Content-Type: application/json" \
     -d '{"state": true}'
   # Wait 30 seconds, verify it turns off
   ```

4. **Never disable or bypass** the kill switch system without authorization and risk assessment.

5. **Report any anomalies** immediately to the safety officer.

## Log Messages

When kill switch operates, expect these log messages:

```
# Arming
WARNING - Kill switch ARMED for piezo (max 10s)
WARNING - Kill switch ARMED for e_gun (max 30s)

# Normal disarm
INFO - Kill switch disarmed for piezo (was active for 5.2s)

# Time limit trigger
ERROR - KILL SWITCH TRIGGERED for piezo: TIME LIMIT EXCEEDED (10s)
ERROR - MANAGER KILL SWITCH: Zeroing piezo voltage
ERROR - LABVIEW KILL SWITCH EXECUTING for piezo: TIME LIMIT (10s)

# Manual trigger
ERROR - KILL SWITCH TRIGGERED for e_gun: MANUAL TRIGGER

# Emergency stop
ERROR - Emergency stop: triggering kill switches
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-28 | Initial kill switch implementation |

## Contact

For questions or issues with the kill switch system:
- Safety Officer: [Contact]
- Technical Lead: [Contact]
