# MLS Project Documentation Index

## Quick Navigation

### 📁 Folder Structure

```
docs/
├── project/          - Project planning & architecture
├── guides/           - How-to guides
├── reference/        - Technical reference
└── INDEX.md          - This file

scripts/
├── setup/            - Installation & setup scripts
├── maintenance/      - Cleanup & maintenance scripts
└── deployment/       - Deployment scripts
```

---

## 📋 Project Documentation (`docs/project/`)

| Document | Purpose | Size |
|----------|---------|------|
| [ARCHITECTURE_ANALYSIS.md](project/ARCHITECTURE_ANALYSIS.md) | System architecture overview | 17 KB |
| [DATA_FLOW_DIAGRAM.md](project/DATA_FLOW_DIAGRAM.md) | Data flow visualization | 18 KB |
| [DATA_DIRECTORY_STANDARD.md](project/DATA_DIRECTORY_STANDARD.md) | Directory structure standard | 7 KB |
| [DATA_STANDARDIZATION_SUMMARY.md](project/DATA_STANDARDIZATION_SUMMARY.md) | Data format standards | 5 KB |
| [IMMEDIATE_IMPROVEMENTS.md](project/IMMEDIATE_IMPROVEMENTS.md) | Improvement roadmap | 22 KB |
| [PHASE3_COMPLETE_SUMMARY.md](project/PHASE3_COMPLETE_SUMMARY.md) | Phase 3 implementation summary | 8 KB |
| [PHASE3_MIGRATION_GUIDE.md](project/PHASE3_MIGRATION_GUIDE.md) | Migration instructions | 7 KB |
| [SERVER_STARTUP_GUIDE.md](project/SERVER_STARTUP_GUIDE.md) | Server startup procedures | 5 KB |
| [DEBUG_REPORT.md](project/DEBUG_REPORT.md) | Debug analysis report | 5 KB |
| [CLEANUP_COMPLETE.md](project/CLEANUP_COMPLETE.md) | Cleanup completion report | 5 KB |

**Total: 10 documents, ~99 KB**

---

## 📖 Guides (`docs/guides/`)

| Document | Purpose |
|----------|---------|
| [CAMERA_INTEGRATION_GUIDE.md](guides/CAMERA_INTEGRATION_GUIDE.md) | Camera setup & infinity mode |

---

## 📚 Reference (`docs/reference/`)

| Document | Purpose |
|----------|---------|
| [DEVICE_COMMAND_REFERENCE.md](reference/DEVICE_COMMAND_REFERENCE.md) | Device & command reference |

---

## 🚀 Scripts (`scripts/`)

### Setup (`scripts/setup/`)
| Script | Purpose |
|--------|---------|
| `setup_data_directory.bat` | Initialize data directories |
| `start_servers.bat` | Start all servers |

### Maintenance (`scripts/maintenance/`)
| Script | Purpose |
|--------|---------|
| `cleanup_script.ps1` | Clean temporary files |

### Deployment (`scripts/deployment/`)
| Script | Purpose |
|--------|---------|
| *(Add deployment scripts here)* |

---

## 🔧 ARTIQ Code (`artiq/`)

### Core Fragments
| File | Description |
|------|-------------|
| `Artiq_Worker.py` | Main ZMQ worker (EnvExperiment) |
| `ec.py` | Endcaps control |
| `comp.py` | Compensation electrodes |
| `raman_control.py` | Raman cooling beams |
| `dds_controller.py` | DDS frequency control |
| `pmt_counter.py` | PMT photon counting |
| `camera_trigger.py` | Camera TTL trigger |
| `sweeping.py` | Sweep orchestrator |

### Experiments (`artiq/experiments/`)
| File | Description |
|------|-------------|
| `set_dc_exp.py` | DC voltage setting experiment |
| `secular_sweep_exp.py` | Frequency sweep experiment |
| `pmt_measure_exp.py` | PMT measurement experiment |
| `emergency_zero_exp.py` | Emergency shutdown experiment |

### Utilities (`artiq/utils/`)
| File | Description |
|------|-------------|
| `config_loader.py` | YAML configuration loader |
| `async_comm.py` | Async ZMQ communication |
| `experiment_submitter.py` | Unified experiment submission |

---

## 📊 Configuration (`config/`)

| File | Purpose |
|------|---------|
| `config.yaml` | Main configuration |
| `services.yaml` | Service orchestration |
| `hardware.yaml` | Hardware settings |
| `artiq/artiq_config.yaml` | ARTIQ-specific config |

---

## 📝 How to Use This Documentation

### For New Users
1. Start with [SERVER_STARTUP_GUIDE.md](project/SERVER_STARTUP_GUIDE.md)
2. Read [ARCHITECTURE_ANALYSIS.md](project/ARCHITECTURE_ANALYSIS.md)
3. Follow [PHASE3_MIGRATION_GUIDE.md](project/PHASE3_MIGRATION_GUIDE.md)

### For Developers
1. Check [DEVICE_COMMAND_REFERENCE.md](reference/DEVICE_COMMAND_REFERENCE.md)
2. Review [DATA_FLOW_DIAGRAM.md](project/DATA_FLOW_DIAGRAM.md)
3. See [CAMERA_INTEGRATION_GUIDE.md](guides/CAMERA_INTEGRATION_GUIDE.md)

### For Maintenance
1. Run `scripts/maintenance/cleanup_script.ps1`
2. Check [CLEANUP_COMPLETE.md](project/CLEANUP_COMPLETE.md)
3. Review [DEBUG_REPORT.md](project/DEBUG_REPORT.md)

---

## 🔍 Quick Reference

### IP Addresses
- ARTIQ Master: `192.168.56.101`
- Manager: (localhost or same)
- Camera Server: Port 5558

### Ports
| Service | Port | Protocol |
|---------|------|----------|
| ARTIQ Commands | 5555 | ZMQ PUB/SUB |
| ARTIQ Data | 5556 | ZMQ PUSH/PULL |
| Manager Client | 5557 | ZMQ REQ/REP |
| Camera Server | 5558 | TCP |
| Flask Web UI | 5001 | HTTP |

### Key Commands
```bash
# Start servers
scripts/setup/start_servers.bat

# Cleanup
scripts/maintenance/cleanup_script.ps1 -All

# Run ARTIQ Worker
artiq_run artiq/Artiq_Worker.py
```

---

## 📅 Last Updated

2024-02-03 - Phase 3 Complete

---

## 🆘 Support

For issues:
1. Check [DEBUG_REPORT.md](project/DEBUG_REPORT.md)
2. Review logs in `logs/debug/`
3. Run cleanup script
4. Verify configuration in `config/`
