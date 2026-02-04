# Manager PC Connection Testing

This document describes the connection test suite for verifying connectivity between all services on the Manager PC.

## Quick Start

### Run All Tests
```bash
# Windows
test_connections.bat

# Linux/Mac
./test_connections.sh

# Or directly with Python
python test_connections.py
```

### Run Specific Tests
```bash
# Test camera connections only
python test_connections.py --camera

# Test ARTIQ only
python test_connections.py --artiq

# Test LabVIEW only
python test_connections.py --labview

# Test Manager only
python test_connections.py --manager
```

## Test Coverage

### Camera Tests (`--camera`)

Tests the camera service connections:

1. **Flask HTTP Server** (Port 5000)
   - TCP port connectivity
   - Root endpoint `/`
   - Health endpoint `/health`
   - API status endpoint `/api/status`

2. **ZMQ Server** (Port 5558)
   - TCP port connectivity
   - ZMQ REQ/REP socket communication

3. **Command Listener** (Port 5001)
   - TCP port connectivity (mhi_cam compatibility)

### Manager Tests (`--manager`)

Tests the manager service:

1. **ZMQ Control Server** (Port 5557)
   - TCP port connectivity
   - REQ/REP socket communication

### ARTIQ Tests (`--artiq`)

Tests ARTIQ master connections:

1. **Command Port** (Port 5555)
   - TCP port connectivity
   - ZMQ PUB socket (receives commands from master)

2. **Data Port** (Port 5556)
   - TCP port connectivity
   - PULL socket (workers send data)

### LabVIEW Tests (`--labview`)

Tests LabVIEW interface on SMILE PC:

1. **ZMQ Server** (Port 5559)
   - TCP port connectivity
   - REQ/REP socket communication

## Configuration

### Default Configuration

The test suite uses these default settings (matching `config/config.yaml`):

```python
{
    "camera_flask_host": "127.0.0.1",
    "camera_flask_port": 5000,
    "camera_zmq_host": "127.0.0.1",
    "camera_zmq_port": 5558,
    "camera_cmd_host": "127.0.0.1",
    "camera_cmd_port": 5001,
    "manager_host": "127.0.0.1",
    "manager_cmd_port": 5557,
    "artiq_master_host": "127.0.0.1",
    "artiq_master_cmd_port": 5555,
    "artiq_master_data_port": 5556,
    "labview_host": "172.17.1.217",  # SMILE PC
    "labview_port": 5559,
    "timeout": 5.0,
}
```

### Custom Configuration

#### Command Line Overrides
```bash
# Test camera on different host
python test_connections.py --camera --camera-host 192.168.1.50

# Test LabVIEW on different host
python test_connections.py --labview --labview-host 192.168.1.100

# Test with verbose output
python test_connections.py --verbose
```

#### Config File
Create a custom config file (YAML or JSON):

```yaml
# custom_config.yaml
camera_flask_host: "192.168.1.50"
camera_flask_port: 5000
labview_host: "192.168.1.100"
labview_port: 5559
timeout: 10.0
```

Then use it:
```bash
python test_connections.py --config custom_config.yaml
```

## Understanding Results

### Status Types

| Status | Meaning | Action Needed? |
|--------|---------|----------------|
| ✅ **PASS** | Connection successful | No |
| ⚠️ **WARN** | Connected but with issues | Maybe |
| ❌ **FAIL** | Connection failed | Yes |
| ⏭️ **SKIP** | Test skipped (dependency missing) | Maybe |

### Common Issues

#### Camera Flask (Port 5000) - Connection Refused
```
❌ Camera Flask TCP Port
   → Port 5000 on 127.0.0.1 is closed (error 10061)
```
**Solution**: Start the Flask server:
```bash
python -m src.server.api.flask_server
```

#### Camera ZMQ (Port 5558) - No Response
```
⚠️ Camera ZMQ REQ/REP
   → Connected to 127.0.0.1:5558 but no response (may be normal)
```
**Solution**: This is often normal if the camera server is starting up. Check camera server logs.

#### LabVIEW (Port 5559) - Connection Refused
```
❌ LabVIEW ZMQ TCP Port
   → Port 5559 on 172.17.1.217 is closed
```
**Solution**: 
1. Check if SMILE PC is reachable: `ping 172.17.1.217`
2. Verify LabVIEW ZMQ server is running on SMILE PC
3. Check Windows Firewall on SMILE PC

#### ARTIQ (Port 5555) - No Data
```
✅ ARTIQ Master Command Port (ZMQ PUB)
   → ZMQ PUB/SUB on 127.0.0.1:5555 connected (no data yet)
```
**Solution**: This is normal if no ARTIQ worker is running. The PUB socket connects successfully.

## Exporting Results

Export test results to JSON for further analysis:

```bash
python test_connections.py --export results.json
```

The JSON output includes:
- Timestamp
- Configuration used
- All test results with details
- Summary statistics

Example JSON structure:
```json
{
  "timestamp": "2026-02-03 14:30:00",
  "config": { ... },
  "results": [
    {
      "name": "Camera Flask TCP Port",
      "status": "PASS",
      "message": "Port 5000 on 127.0.0.1 is open",
      "details": null,
      "duration_ms": 12.5
    }
  ],
  "summary": {
    "total": 15,
    "passed": 12,
    "failed": 1,
    "warnings": 2,
    "skipped": 0
  }
}
```

## Continuous Monitoring

For continuous monitoring, set up a scheduled task/cron job:

### Windows (Task Scheduler)
```batch
@echo off
python D:\MLS\test_connections.py --export D:\MLS\logs\connection_test_%date:~-4,4%%date:~-10,2%%date:~-7,2%.json
```

### Linux (Cron)
```bash
# Run every 5 minutes, log results
*/5 * * * * cd /opt/mls && python3 test_connections.py --export /var/log/mls/connection_test_$(date +\%Y\%m\%d_\%H\%M).json
```

## Troubleshooting

### Missing Dependencies

If you see:
```
⏭️ Camera Flask Health
   → requests not installed (pip install requests)
```

Install missing packages:
```bash
pip install requests pyzmq pyyaml
```

### Permission Denied

On Linux, you may need root to test certain ports:
```bash
sudo python3 test_connections.py
```

### ZMQ Context Errors

If you see ZMQ context errors, there may be a lingering process:
```bash
# Find and kill stuck Python processes
# Windows
taskkill /F /IM python.exe

# Linux
pkill -f test_connections.py
```

## Integration with CI/CD

Use in automated testing:

```yaml
# .github/workflows/test.yml
- name: Test Connections
  run: |
    python test_connections.py --export test_results.json
    # Fail if any critical tests fail
    python -c "import json,sys; r=json.load(open('test_results.json')); sys.exit(1 if r['summary']['failed'] > 0 else 0)"
```

## See Also

- [Server Startup Guide](SERVER_STARTUP_GUIDE.md)
- [Architecture Overview](architecture/communication.md)
- [Troubleshooting Guide](guides/TROUBLESHOOTING.md)
