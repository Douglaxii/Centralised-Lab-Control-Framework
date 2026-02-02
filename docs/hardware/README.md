# Hardware Integration

Documentation for hardware components and their integration with MLS.

## Contents

| Document | Description |
|----------|-------------|
| [LabVIEW Integration](labview.md) | SMILE/LabVIEW TCP communication protocol |
| [Camera Hardware](camera.md) | Hamamatsu CCD camera setup and configuration |

## Hardware Overview

The MLS coordinates multiple hardware systems:

```
┌─────────────────────────────────────────────────────────────┐
│                     HARDWARE LAYER                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   LabVIEW    │  │    ARTIQ     │  │    Camera    │      │
│  │    SMILE     │  │   Worker     │  │   Server     │      │
│  │              │  │              │  │              │      │
│  │ • RF Voltage │  │ • DC Electrodes│ • DCIMG      │      │
│  │ • Piezo      │  │ • DDS (Raman)│  │ • Live Stream│      │
│  │ • Toggles    │  │ • TTL        │  │ • Analysis   │      │
│  │ • DDS        │  │ • PMT        │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Communication Protocols

| Hardware | Protocol | Port | Interface |
|----------|----------|------|-----------|
| ARTIQ | ZMQ PUB/SUB | 5555-5556 | manager.py |
| LabVIEW | TCP JSON | 5559 | labview_interface.py |
| Camera | TCP | 5558 | camera_server.py |

## Configuration

Hardware settings are in `config/settings.yaml`:

```yaml
labview:
  enabled: true
  host: "192.168.1.100"
  port: 5559
  timeout: 5.0

camera:
  enabled: true
  host: "127.0.0.1"
  port: 5558
  
hardware:
  worker_defaults:
    ec1: 0.0
    ec2: 0.0
    comp_h: 0.0
    comp_v: 0.0
    u_rf_volts: 200.0
```
