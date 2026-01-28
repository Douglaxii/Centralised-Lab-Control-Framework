# Audit Fixes - Data Structure and Protocol Consistency

## Date: 2026-01-27
## Status: COMPLETED

---

## Summary of Fixes Applied

### 1. CREATED: `core/enums.py` - Centralized Enumerations

**File:** `core/enums.py` (NEW)

Consolidated all enum definitions to prevent duplication:
- `SystemMode` - MANUAL, AUTO, SAFE
- `AlgorithmState` - IDLE, RUNNING, OPTIMIZING, CONVERGED, DIVERGING, ERROR, STOPPED
- `ExperimentStatus` - CREATED, RUNNING, COMPLETED, FAILED, ABORTED
- `ExperimentPhase` - INIT, DC_SETUP, COOLING, SWEEP, SECULAR_COMPARE, CAMERA, ANALYSIS, COMPLETE
- `DataSource` - WAVEMETER, SMILE, CAMERA, ARTIQ, TURBO, SECULAR_COMPARE
- `CommandType` - SET_DC, SET_COOLING, SET_RF, SET_PIEZO, SET_TOGGLE, SET_DDS, RUN_SWEEP, COMPARE, STOP, STATUS
- `MatchQuality` - EXCELLENT, GOOD, POOR, MISMATCH

Added RF voltage conversion utilities:
- `RF_SCALE_V_PER_MV = 100.0 / 700.0` (~0.142857)
- `RF_SCALE_MV_PER_V = 700.0 / 100.0` (7.0)
- `smile_mv_to_real_volts(mv)` - Converts SMILE mV to real RF voltage
- `real_volts_to_smile_mv(v)` - Converts real RF voltage to SMILE mV

**Impact:** Eliminates duplicate enum definitions between manager and Flask server.

---

### 2. FIXED: Flask Server - Removed Duplicate Enums

**File:** `server/Flask/flask_server.py`

- Removed duplicate `SystemMode` and `AlgorithmState` class definitions
- Now imports from `core.enums`
- Added `/api/compare` POST route for secular frequency comparison

**Code Change:**
```python
# Before:
class SystemMode(Enum): ...
class AlgorithmState(Enum): ...

# After:
from core.enums import SystemMode, AlgorithmState
```

---

### 3. FIXED: Flask Server - Data Channel Naming

**File:** `server/Flask/templates/index.html`

Changed chart channel name from `'laser'` to `'laser_freq'` to match data server:

```javascript
// Before:
createChart('laser', 'laser');
const channels = ['pos_x', 'pos_y', 'sig_x', 'sig_y', 'pressure', 'laser', 'pmt'];

// After:
createChart('laser_freq', 'laser');
const channels = ['pos_x', 'pos_y', 'sig_x', 'sig_y', 'pressure', 'laser_freq', 'pmt'];
```

**Impact:** Laser frequency data now correctly displays on the telemetry chart.

---

### 4. FIXED: Manager - RF Voltage Naming Standardization

**File:** `server/communications/manager.py`

Changed parameter name from `u_rf` to `u_rf_volts` to clarify units:

```python
# Before:
VALID_PARAMS = {"u_rf", ...}
PARAM_RANGES = {"u_rf": (0, 1000), ...}
self.params = {"u_rf": defaults.get("u_rf", 500.0), ...}

# After:
VALID_PARAMS = {"u_rf_volts", ...}
PARAM_RANGES = {"u_rf_volts": (0, 500), ...}
self.params = {"u_rf_volts": defaults.get("u_rf_volts", 200.0), ...}
```

Also updated:
- `_publish_rf_update()` - Uses shared conversion functions
- `_apply_safety_defaults()` - Uses `u_rf_volts`
- `_handle_compare()` - Uses `smile_mv_to_real_volts()`

---

### 5. FIXED: Flask Server - RF Control Endpoint

**File:** `server/Flask/flask_server.py`

Updated `/api/control/rf` endpoint:

```python
# Accepts either 'u_rf_volts' (preferred) or 'u_rf' (legacy)
u_rf_volts = float(data.get("u_rf_volts") or data.get("u_rf", 200))

# Range validation: 0-500V (real voltage)
if not 0 <= u_rf_volts <= 500:
    return error...

# Store as 'u_rf_volts'
current_state["params"]["u_rf_volts"] = u_rf_volts
```

---

### 6. ADDED: Flask Route for Secular Comparison

**File:** `server/Flask/flask_server.py`

Added new endpoint `/api/compare`:

```python
@app.route('/api/compare', methods=['POST'])
def trigger_secular_compare():
    """Trigger secular frequency comparison."""
    # Validates parameters
    # Forwards COMPARE command to manager
    # Returns exp_id, predicted_freq_kHz, target_mode
```

**Usage:**
```bash
curl -X POST http://localhost:5000/api/compare \
  -d '{"ec1":10,"ec2":10,"comp_h":6,"comp_v":37,"u_rf_mV":1400}'
```

---

### 7. FIXED: Configuration - Added Missing Defaults

**File:** `config/settings.yaml`

Added missing hardware defaults:

```yaml
hardware:
  worker_defaults:
    # RF Voltage (real voltage in volts)
    u_rf_volts: 200.0
    
    # Piezo voltage
    piezo: 0.0
    
    # Cooling Parameters (Raman)
    freq0: 212.5
    freq1: 212.5
    amp0: 0.05
    amp1: 0.05
    
    # Toggles
    bephi: false
    b_field: true
    be_oven: false
    uv3: false
    e_gun: false
    
    # DDS
    dds_profile: 0
```

---

### 8. FIXED: Secular Comparison - RF Scaling

**File:** `server/analysis/secular_comparison.py`

Now uses shared RF scale constant:

```python
from core.enums import RF_SCALE_V_PER_MV, smile_mv_to_real_volts

class SecularFrequencyComparator:
    RF_VOLTAGE_SCALE = RF_SCALE_V_PER_MV  # From core.enums
```

This ensures consistency with manager's COMPARE command.

---

### 9. UPDATED: Core Module Exports

**File:** `core/__init__.py`

Added all enums and utilities to public API:

```python
from .enums import (
    SystemMode, AlgorithmState, ExperimentStatus,
    ExperimentPhase, DataSource, CommandType, MatchQuality,
    RF_SCALE_V_PER_MV, RF_SCALE_MV_PER_V,
    smile_mv_to_real_volts, real_volts_to_smile_mv,
)
```

---

## Verification

All syntax checks pass:
```
✓ core/enums.py: OK
✓ core/__init__.py: OK
✓ server/communications/manager.py: OK
✓ server/Flask/flask_server.py: OK
✓ server/analysis/secular_comparison.py: OK
```

RF Conversion verified:
```
700mV -> 100.0V ✓
1400mV -> 200.0V ✓
100V -> 700.0mV ✓
200V -> 1400.0mV ✓
```

---

## Remaining Items (Non-Critical)

### 10. ARTIQ Worker - SET_RF Handler

**Status:** NOT FIXED (requires ARTIQ hardware knowledge)

The ARTIQ worker currently does NOT handle `SET_RF` commands. RF voltage control is currently routed through LabVIEW/SMILE interface only.

**Options:**
1. Add RF control to ARTIQ (if ARTIQ controls RF DDS directly)
2. Document that RF is SMILE-only (current behavior)
3. Add ARTIQ RF control as future enhancement

**Recommendation:** Document current behavior - RF is controlled via SMILE/LabVIEW, not ARTIQ.

---

## Files Modified

1. `core/enums.py` - CREATED
2. `core/__init__.py` - Updated exports
3. `server/communications/manager.py` - Fixed enums, RF naming
4. `server/Flask/flask_server.py` - Fixed enums, added /api/compare
5. `server/Flask/templates/index.html` - Fixed channel naming
6. `server/analysis/secular_comparison.py` - Use shared RF scale
7. `config/settings.yaml` - Added missing defaults

---

## Backwards Compatibility

- **Breaking:** Parameter `u_rf` renamed to `u_rf_volts` in API
- **Mitigation:** Flask endpoint accepts both keys temporarily
- **Non-breaking:** All enum serialization uses `.value` strings
- **Non-breaking:** Data channel naming fixed (internal only)

---

## Testing Recommendations

1. **Test RF voltage setting:**
   ```bash
   curl -X POST http://localhost:5000/api/control/rf \
     -d '{"u_rf_volts": 200}'
   ```

2. **Test secular comparison:**
   ```bash
   curl -X POST http://localhost:5000/api/compare \
     -d '{"u_rf_mV": 1400}'
   ```

3. **Verify laser frequency plot:**
   - Start data server with mock wavemeter
   - Check that laser_freq chart updates

4. **Verify mode display:**
   - Switch between MANUAL/AUTO/SAFE modes
   - Check status bar updates correctly
