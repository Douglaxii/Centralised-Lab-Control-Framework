# ARTIQ Deployment Package

**Target System:** ARTIQ Linux Virtual Machine  
**Purpose:** Hardware control for ion trap experiments

## Contents

```
deploy_artiq/
├── artiq/              # ARTIQ experiments and fragments
│   ├── experiments/    # Main ARTIQ experiment files
│   └── fragments/      # Reusable hardware fragments
├── core/               # Shared utilities (config, logging, ZMQ)
├── config/             # Configuration files
├── tests/              # Unit tests
├── docs/               # Documentation
├── lab_comms.py        # Communication library
└── requirements.txt    # Python dependencies

```

## Quick Start

### 1. Clone to ARTIQ VM

```bash
# On ARTIQ Linux VM
cd ~
git clone <repo-url>
cd MLS/deploy_artiq
```

### 2. Install Dependencies

```bash
# In ARTIQ conda environment
pip install -r requirements.txt
```

### 3. Configure

Edit `config/settings.yaml` with your network settings:
- `master_ip`: IP of the Master/Server PC
- `artiq_ip`: IP of this ARTIQ VM

### 4. Run ARTIQ Worker

```bash
artiq_run artiq/experiments/artiq_worker.py
```

## Main Components

| File | Purpose |
|------|---------|
| `artiq/experiments/artiq_worker.py` | Main ARTIQ worker process |
| `artiq/experiments/trap_control.py` | DC electrode control |
| `artiq/fragments/secularsweep.py` | Secular frequency sweep |
| `lab_comms.py` | ZMQ communication with Manager |

## Network Requirements

- Must be able to reach Master PC on ZMQ ports (default: 5555, 5556)
- ARTIQ hardware must be connected and recognized

## See Also

- Main project: `../README.md`
- Architecture docs: `docs/ARCHITECTURE.md`
