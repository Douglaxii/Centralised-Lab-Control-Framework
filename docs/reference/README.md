# Reference Documentation

Technical reference materials for MLS.

## Contents

| Document | Description |
|----------|-------------|
| [Data Formats](data_formats.md) | File formats and data integration |
| [Optimization](optimization.md) | Bayesian optimization user guide |
| [BO Architecture](bo_architecture.md) | Two-phase optimizer design |
| [Secular Comparison](secular_comparison.md) | Frequency comparison system |

## Quick Reference

### Data Paths

```
Y:/Xi/Data/
├── YYMMDD/
│   ├── sweep_json/         # Sweep results (JSON)
│   ├── cam_json/           # Camera data (JSON)
│   ├── metadata/           # Experiment context
│   └── dcimg/              # Camera recordings
```

### Experiment ID Format

```
EXP_HHMMSS_XXXXXXXX
```

Example: `EXP_143022_A1B2C3D4`

### Configuration File

All settings in `config/settings.yaml`:

```yaml
network:
  master_ip: "192.168.1.100"
  cmd_port: 5555
  data_port: 5556
  client_port: 5557
  camera_port: 5558
```

### Port Summary

| Port | Service | Protocol |
|------|---------|----------|
| 5000 | Flask Web UI | HTTP |
| 5555 | Manager PUB | ZMQ |
| 5556 | Manager PULL | ZMQ |
| 5557 | Manager REP | ZMQ |
| 5558 | Camera Server | TCP |
| 5559 | LabVIEW SMILE | TCP |
| 5560 | Data Ingestion | TCP |

## Related Documentation

- [API Reference](../api/reference.md) - Complete API documentation
- [Architecture](../architecture/) - System architecture
- [Hardware](../hardware/) - Hardware integration guides
