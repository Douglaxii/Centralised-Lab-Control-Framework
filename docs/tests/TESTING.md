# ARTIQ & LabVIEW Calibration Tests

This directory contains calibration and testing tools for the lab control framework.

## Files

| File | Description |
|------|-------------|
| `Calibration_Test.ipynb` | Interactive Jupyter notebook with GUI controls and plotting |
| `calibration_test.py` | Standalone command-line test script |
| `test_pressure_safety.py` | Pressure safety system test |
| `README.md` | This file |

## Quick Start

### Option 1: Jupyter Notebook (Recommended for Interactive Use)

```bash
# Install dependencies if needed
pip install jupyter matplotlib numpy pyzmq pyyaml

# Start Jupyter
jupyter notebook

# Open: Calibration_Test.ipynb
```

**Features:**
- Interactive sliders for ARTIQ parameters (DC electrodes, RF, cooling)
- Interactive controls for LabVIEW (U_RF, Piezo, toggles, DDS)
- Real-time latency measurement
- Automatic plotting of results
- Safety limit verification
- Export test reports

### Option 2: Command-Line Script

```bash
# Run all tests
python calibration_test.py --all

# Run specific tests
python calibration_test.py --latency --iterations 20
python calibration_test.py --sweep --start 100 --stop 300 --steps 20
python calibration_test.py --toggle-test --cycles 5
python calibration_test.py --limits

# Skip plotting and cleanup
python calibration_test.py --all --no-plots --no-cleanup
```

## Test Descriptions

### 1. Latency Test (`--latency`)

Measures round-trip command latency for:
- **ARTIQ**: STATUS, GET, SET commands
- **LabVIEW**: STATUS, SET_RF, SET_PIEZO, SET_TOGGLE commands

Statistics calculated:
- Mean, Std Dev, Min, Max
- Median, P95, P99 percentiles

### 2. RF Sweep Test (`--sweep`)

Performs a voltage sweep from start to stop voltage:
- Measures latency at each step
- Plots voltage profile and latency vs voltage
- Tests both ARTIQ and LabVIEW RF control

Default: 100V → 300V in 20 steps

### 3. Toggle Response Test (`--toggle-test`)

Cycles a toggle device (default: B-field) on/off:
- Measures ON and OFF latencies
- Calculates average cycle time
- Plots latency distribution

### 4. Safety Limit Test (`--limits`)

Verifies parameter validation:
- Tests values outside allowed ranges
- Verifies rejection of invalid parameters
- Tests acceptance of valid parameters

## System Requirements

### Network Configuration
Ensure the config file (`config/settings.yaml`) has correct IPs:

```yaml
network:
  master_ip: "192.168.1.100"      # Your Control Manager PC
  client_port: 5557               # Manager REQ/REP port

labview:
  host: "192.168.1.100"           # LabVIEW PC IP
  port: 5559                      # LabVIEW TCP port
```

### Dependencies

```bash
# Core dependencies (always required)
pip install pyyaml

# For ARTIQ tests
pip install pyzmq

# For plotting (optional)
pip install matplotlib numpy

# For Jupyter notebook
pip install jupyter ipywidgets
```

## Safety Features

The tests include several safety mechanisms:

1. **Parameter Validation**: Tests verify that invalid values are rejected
2. **Automatic Cleanup**: Safety defaults applied after tests (unless `--no-cleanup`)
3. **Emergency Stop**: Available in Jupyter interface and via LabVIEW command
4. **Voltage Limits**: 
   - U_RF: 500V max (ARTIQ), 1000V max (LabVIEW)
   - Electrodes: ±100V
   - Piezo: 0-4V

### Pressure Safety Monitor

The LabVIEW interface includes a **pressure safety monitor** for vacuum protection:

**How it works:**
1. Monitors pressure from SMILE/LabVIEW via `Y:/Xi/Data/telemetry/smile/pressure/*.dat` files
2. Checks pressure at 20 Hz (50ms interval)
3. If pressure exceeds threshold (default: 5×10⁻⁹ mbar):
   - **Immediately** kills piezo voltage (sets to 0V)
   - **Immediately** turns off e-gun
   - Notifies Control Manager via callback
   - Logs the event

**Configuration** (in `config/settings.yaml`):
```yaml
labview:
  pressure_threshold_mbar: 5.0e-9    # Alert threshold
  pressure_check_interval: 0.05      # 20 Hz check rate
```

**Testing:**
```bash
# Run pressure safety test
python tests/test_pressure_safety.py

# Test with real LabVIEW connection
python tests/test_pressure_safety.py --real-labview --threshold 1e-8
```

**Hysteresis:** The alert resets when pressure drops to `threshold / 2` to prevent rapid cycling.

## Output Files

After running tests, these files may be generated:

| File | Description |
|------|-------------|
| `latency_comparison.png` | Latency statistics plots |
| `rf_sweep_test.png` | RF sweep voltage/latency plots |
| `toggle_test.png` | Toggle response plots |
| `calibration_report_YYYYMMDD_HHMMSS.json` | Full test report (JSON) |

## Troubleshooting

### Connection Failures

```bash
# Test ARTIQ connectivity
python -c "import zmq; ctx = zmq.Context(); s = ctx.socket(zmq.REQ); s.connect('tcp://192.168.1.100:5557'); print('OK')"

# Test LabVIEW connectivity
python -c "import socket; s = socket.socket(); s.connect(('192.168.1.100', 5559)); print('OK')"
```

### Import Errors

If you get import errors, ensure you're running from the project root:

```bash
cd D:\MLS
python tests\calibration_test.py --all
```

Or in Jupyter:
```python
import sys
sys.path.insert(0, r'D:\MLS')
```

## Calibration Checklist

Use these tests to verify your setup:

- [ ] ARTIQ connection working (latency < 100ms)
- [ ] LabVIEW connection working (latency < 100ms)
- [ ] RF voltage control responds (both ARTIQ and LabVIEW)
- [ ] DC electrode control responds
- [ ] Toggle devices respond (B-field, oven, etc.)
- [ ] Parameter limits enforced correctly
- [ ] Emergency stop functions

## Support

For issues or questions, check:
1. Configuration in `config/settings.yaml`
2. Service status: `python launcher.py --status`
3. Logs in `logs/` directory
