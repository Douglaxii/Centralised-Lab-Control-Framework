# Lab Server Startup Guide

## Quick Start (Recommended)

**Simply double-click `start_servers.bat` and select option `[2]` for Core servers.**

This starts:
1. Camera Server (Port 5558)
2. Control Manager (Port 5557) 
3. Flask Web UI (Port 5001)

Then open your browser to: **http://localhost:5001**

---

## What Each Program Does

### 1. Camera Server (`camera_server_parallel.py`)
- **Purpose**: Controls the Hamamatsu CCD camera
- **Port**: 5558 (TCP)
- **Must start first** - other servers depend on it
- Provides live image capture and DCIMG recording

### 2. Control Manager (`manager.py`)
- **Purpose**: Central brain that coordinates ALL lab components
- **Ports**: 5557 (ZMQ client), 5555 (commands), 5556 (data)
- **Features**:
  - Interfaces with ARTIQ (quantum control)
  - Interfaces with LabVIEW (SMILE hardware)
  - Safety kill switches (piezo: 10s max, e-gun: 30s max)
  - Pressure monitoring (emergency shutdown if > 5e-9 mbar)
  - Telemetry data collection
  - Turbo algorithm coordination

### 3. Flask Web UI (`flask_server.py`)
- **Purpose**: Modern web dashboard for lab control
- **Port**: 5001 (HTTP)
- **Access**: http://localhost:5001
- **Features**:
  - Live camera feed with ion position overlay
  - Real-time telemetry graphs (7 channels)
  - Control cockpit (voltages, toggles, lasers)
  - Turbo algorithm status and safety switch

### 4. Legacy Flask API (`flask_server_setup.py`)
- **Purpose**: Legacy web interface (kept for compatibility)
- **Port**: 5000 (HTTP)
- **Access**: http://localhost:5000
- **Features**:
  - DDS sweep control
  - Camera settings
  - DCIMG analysis forms
  - TOPO DDS control

---

## Communication Architecture

```
┌─────────────────┐     HTTP      ┌──────────────────┐
│   Web Browser   │◄─────────────►│  Flask Web UI    │ (Port 5001)
│                 │               │  (flask_server)  │
└─────────────────┘               └────────┬─────────┘
                                           │ ZMQ
                                           ▼
┌─────────────────┐               ┌──────────────────┐
│   ARTIQ Worker  │◄────ZMQ──────►│  Control Manager │ (Port 5557)
│  (Quantum Ctrl) │               │    (manager)     │
└─────────────────┘               └────────┬─────────┘
                                           │ TCP/ZMQ
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
            ┌──────────────┐      ┌─────────────────┐    ┌──────────────┐
            │Camera Server │      │ LabVIEW (SMILE) │    │ Data Storage │
            │  (Port 5558) │      │   (Hardware)    │    │  (telemetry) │
            └──────────────┘      └─────────────────┘    └──────────────┘
```

---

## Manual Startup (without script)

If you need to start servers manually:

### Terminal 1 - Camera Server
```batch
cd D:\MLS
python server\cam\camera_server_parallel.py
```

### Terminal 2 - Control Manager
```batch
cd D:\MLS
python server\communications\manager.py
```

### Terminal 3 - Flask Web UI
```batch
cd D:\MLS
python server\Flask\flask_server.py
```

### Terminal 4 - Legacy API (optional)
```batch
cd D:\mhi_cam\communication
python flask_server_setup.py
```

---

## Troubleshooting

### Port Already in Use
If you see "Port XXXX is already in use", the server may already be running.
- Use option `[8]` in the launcher to check status
- Or close the existing window and try again

### Camera Server Won't Start
- Check if camera is powered on
- Check if DCAM-API is installed
- Check if another program is using the camera

### Control Manager Can't Connect to LabVIEW
- Check if SMILE LabVIEW is running
- Verify LabVIEW TCP settings (default port 5559)
- Check firewall settings

### Flask Web UI Shows "Manager timeout"
- Make sure Control Manager is running
- Check if port 5557 is accessible

---

## File Locations

| Component | Location |
|-----------|----------|
| Camera Server | `D:\MLS\server\cam\camera_server_parallel.py` |
| Control Manager | `D:\MLS\server\communications\manager.py` |
| Flask Web UI | `D:\MLS\server\Flask\flask_server.py` |
| Legacy Flask API | `D:\mhi_cam\communication\flask_server_setup.py` |
| Data Storage | `Y:\Xi\Data\` |
| Logs | `D:\MLS\logs\` |

---

## Key Ports Summary

| Port | Service | Protocol |
|------|---------|----------|
| 5000 | Legacy Flask API | HTTP |
| 5001 | Flask Web UI | HTTP |
| 5555 | Command Publisher | ZMQ PUB |
| 5556 | Data Collector | ZMQ PULL |
| 5557 | Control Manager Client | ZMQ REP |
| 5558 | Camera Server | TCP |
| 5559 | LabVIEW Interface | TCP |
