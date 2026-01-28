# Server PC Deployment Package

**Target System:** Master/Server PC (Windows/Linux)  
**Purpose:** Central coordinator, web UI, camera control, data analysis

## Contents

```
deploy_server/
├── server/             # Server components
│   ├── communications/ # Manager (ZMQ coordinator)
│   ├── cam/           # Camera server and image analysis
│   ├── Flask/         # Web UI
│   └── analysis/      # Data analysis tools
├── core/               # Shared utilities (config, logging, ZMQ)
├── config/             # Configuration files
├── tests/              # Unit tests
├── docs/               # Documentation
├── lab_comms.py        # Communication library
└── requirements.txt    # Python dependencies
```

## Quick Start

### 1. Clone to Server PC

Copy this `deploy_server/` folder to your Master PC (e.g., `C:\LabControl\`)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Edit `config/settings.yaml` with your settings:
- Network IPs for all components
- Data storage paths
- Hardware parameters

### 4. Start Server Components

Terminal 1 - Manager (ZMQ coordinator):
```bash
cd server/communications
python manager.py
```

Terminal 2 - Flask Web UI:
```bash
cd server/Flask
python flask_server.py
```

Terminal 3 - Camera Server (optional):
```bash
cd server/cam
python camera_server.py
```

Then open browser: http://localhost:5000

## Main Components

| File | Purpose |
|------|---------|
| `server/communications/manager.py` | Central ZMQ coordinator |
| `server/Flask/flask_server.py` | Web UI server |
| `server/cam/camera_server.py` | Camera acquisition |
| `server/cam/image_handler.py` | Ion detection/analysis |
| `server/analysis/` | Data analysis tools |

## Network Requirements

- This PC is the central hub
- Must be reachable by ARTIQ VM and Lab PC
- Firewall must allow ZMQ ports (5555, 5556, 5000, etc.)

## Directory Structure on Server

Data is typically stored on a network drive:
```
Y:/Xi/Data/
├── [date]/
│   ├── experiments/    # Experiment data
│   └── metadata/       # Experiment metadata
```

## See Also

- Architecture: `docs/ARCHITECTURE.md`
- Main project: `../README.md`
