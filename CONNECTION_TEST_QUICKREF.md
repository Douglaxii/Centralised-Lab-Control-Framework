# 🔌 Connection Test Quick Reference

## Run Tests

```bash
# All tests
python test_connections.py

# Specific component
python test_connections.py --camera
python test_connections.py --manager
python test_connections.py --artiq
python test_connections.py --labview

# Verbose output
python test_connections.py --verbose

# Export results
python test_connections.py --export results.json
```

## Port Reference

| Service | Port | Test Command |
|---------|------|--------------|
| Camera Flask | 5000 | `--camera` |
| Camera ZMQ | 5558 | `--camera` |
| Camera CMD | 5001 | `--camera` |
| Manager ZMQ | 5557 | `--manager` |
| ARTIQ Master CMD | 5555 | `--artiq` |
| ARTIQ Master DATA | 5556 | `--artiq` |
| LabVIEW ZMQ | 5559 | `--labview` |

## Status Icons

| Icon | Meaning |
|------|---------|
| ✅ | PASS - Working correctly |
| ⚠️ | WARN - Connected with issues |
| ❌ | FAIL - Connection failed |
| ⏭️ | SKIP - Test skipped |

## Common Fixes

### Camera Flask (5000) Failed
```bash
# Start Flask server
python -m src.server.api.flask_server
```

### LabVIEW (5559) Failed
1. Check SMILE PC is on: `ping 172.17.1.217`
2. Check LabVIEW ZMQ server running
3. Check firewall on SMILE PC

### ARTIQ (5555) No Data
- Normal if no worker running
- Start ARTIQ worker to see data

## Files

| File | Purpose |
|------|---------|
| `test_connections.py` | Main test script |
| `test_connections.bat` | Windows wrapper |
| `test_connections.sh` | Linux/Mac wrapper |
| `test_config_example.yaml` | Config template |
| `docs/CONNECTION_TESTING.md` | Full documentation |

## Need Help?

See full documentation: `docs/CONNECTION_TESTING.md`
