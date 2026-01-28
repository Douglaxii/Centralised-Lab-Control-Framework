# Project Audit: Data Structure and Protocol Inconsistencies

## Date: 2026-01-27
## Auditor: Code Review

---

## 1. CRITICAL: Duplicate Enum Definitions

### Problem
`SystemMode` and `AlgorithmState` enums are defined in BOTH:
- `server/communications/manager.py` (lines 48-63)
- `server/Flask/flask_server.py` (lines 75-90)

### Risk
Serialization/deserialization mismatches when comparing enum values across components.

### Fix
Move enums to `core/exceptions.py` or create `core/enums.py` and import everywhere.

---

## 2. CRITICAL: Missing Flask Route for COMPARE Command

### Problem
Manager has `_handle_compare()` method for COMPARE action (line ~400+), but Flask server has NO corresponding `/api/compare` route.

### Risk
Users cannot trigger secular comparison from web dashboard.

### Fix
Add `/api/compare` POST route in flask_server.py that forwards to manager.

---

## 3. HIGH: Parameter Name Inconsistency - RF Voltage

### Problem
- Manager `VALID_PARAMS` uses `"u_rf"` (line 102)
- Config `hardware.worker_defaults` has NO `u_rf` key
- Secular comparison uses `u_rf_mV` (SMILE) and `u_rf_real` (actual)
- Flask uses `u_rf` expecting volts

### Risk
Unit confusion: Is u_rf in volts or mV? Different components interpret differently.

### Fix
- Standardize on `u_rf_volts` for real voltage
- Use `u_rf_smile_mV` for SMILE interface value
- Add clear comments about 700mV -> 100V scaling

---

## 4. HIGH: Command Type Mismatch - ARTIQ Protocol

### Problem
Manager publishes these command types:
- `SET_DC` - handled by ARTIQ ✓
- `SET_COOLING` - handled by ARTIQ ✓
- `SET_RF` - published by manager (line 432+) but NOT handled by ARTIQ worker
- `RUN_SWEEP` - handled by ARTIQ ✓

### Risk
RF voltage commands from manager never reach ARTIQ hardware.

### Fix
Add `SET_RF` handler in `artiq_worker.py` or remove RF from ARTIQ commands (if RF is SMILE-only).

---

## 5. MEDIUM: Config Key Inconsistency

### Problem
Manager's `_publish_cooling_update()` sends:
```python
msg = {
    "type": "SET_COOLING",
    "values": {
        "freq0", "amp0", "freq1", "amp1", "sw0", "sw1"
    }
}
```

But config only defines defaults for `sw0`, `sw1` (cooling shutters), NOT the freq/amp parameters.

### Risk
ARTIQ worker uses stale or undefined default values.

### Fix
Add `freq0`, `amp0`, `freq1`, `amp1` to `hardware.worker_defaults` in config.

---

## 6. MEDIUM: RF Scaling Inconsistency

### Problem
- `secular_comparison.py`: `RF_VOLTAGE_SCALE = 100.0 / 700.0` (0.1429)
- Manager COMPARE command: uses `u_rf_real = u_rf_mV * 0.1` (approximate)

### Risk
Incorrect RF voltage calculations leading to wrong theoretical frequencies.

### Fix
Use shared constant: `RF_SCALE_V_PER_MV = 100.0 / 700.0`

---

## 7. MEDIUM: Data Channel Naming Inconsistency

### Problem
- Data server uses: `laser_freq`
- Flask chart IDs use: `laser` (line 759: `charts['laser']`)
- Manager response uses: `laser_freq`

### Risk
Telemetry data not displayed on correct chart.

### Fix
Standardize on `laser_freq` everywhere.

---

## 8. LOW: Missing Parameter Ranges

### Problem
Manager's `PARAM_RANGES` (lines 116-124) only defines ranges for:
- `u_rf`, `ec1`, `ec2`, `comp_h`, `comp_v`, `piezo`, `dds_profile`

Missing ranges for:
- `freq0`, `freq1` (should be ~200-220 MHz)
- `amp0`, `amp1` (should be 0-1)
- `sw0`, `sw1` (booleans)

### Risk
No validation for cooling parameters.

### Fix
Add ranges for all parameters.

---

## 9. LOW: Data Source Tracking Inconsistency

### Problem
- Data server tracks: `wavemeter`, `smile`, `camera`
- Flask status bar shows: `wavemeter`, `smile`, `worker`, `camera`, `turbo`
- Manager tracks: `worker_alive`

### Risk
Confusion about which data sources are which.

### Fix
Create canonical list of data sources in config.

---

## 10. LOW: Secular Comparison Result Upload

### Problem
`SecularComparisonResult` has `to_json()` method but no explicit schema version.

### Risk
Future changes break backwards compatibility.

### Fix
Add `schema_version` field to result dataclass.

---

## Recommended Priority Order

1. **P0 (Critical)**: Fix duplicate enums - causes serialization bugs
2. **P0 (Critical)**: Add Flask /api/compare route - feature not accessible
3. **P1 (High)**: Fix RF voltage naming and scaling - causes wrong physics
4. **P1 (High)**: Add SET_RF handler to ARTIQ or clarify RF control path
5. **P2 (Medium)**: Add missing config defaults
6. **P2 (Medium)**: Fix data channel naming
7. **P3 (Low)**: Add parameter validation ranges
8. **P3 (Low)**: Add schema versioning

---

## Files Requiring Changes

1. `core/enums.py` (NEW) - Centralize enums
2. `server/communications/manager.py` - Fix RF scaling, import enums
3. `server/Flask/flask_server.py` - Add /api/compare, import enums, fix channel names
4. `artiq/experiments/artiq_worker.py` - Add SET_RF handler or document
5. `config/settings.yaml` - Add missing defaults
6. `server/analysis/secular_comparison.py` - Use shared RF scale constant
