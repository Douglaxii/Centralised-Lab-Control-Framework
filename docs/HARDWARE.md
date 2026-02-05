# MLS Hardware Documentation

Documentation for hardware components and integration.

---

## Table of Contents

1. [Hardware Overview](#hardware-overview)
2. [ARTIQ System](#artiq-system)
3. [LabVIEW/SMILE Integration](#labviewsmile-integration)
4. [Camera System](#camera-system)

---

## Hardware Overview

The MLS coordinates three main hardware systems:

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

### Communication Protocols

| Hardware | Protocol | Port | Interface |
|----------|----------|------|-----------|
| ARTIQ | ZMQ PUB/SUB | 5555-5557 | manager.py |
| LabVIEW | TCP JSON | 5559 | labview_interface.py |
| Camera | TCP | 5558 | camera_server.py |

---

## ARTIQ System

The ARTIQ system controls timing-critical hardware through the Kasli FPGA.

### Hardware Components

| Component | Device | Function |
|-----------|--------|----------|
| Zotino | DAC | DC electrode control |
| Urukul | DDS | Raman cooling beams |
| TTL | Digital I/O | Camera trigger, PMT gating |
| PMT | Counter | Photon counting |

### Fragments

**Location:** `artiq/fragments/`

| Fragment | File | Purpose |
|----------|------|---------|
| Compensation | `comp.py` | DC compensation electrodes |
| EndCaps | `ec.py` | Endcap voltages |
| RamanCooling | `raman_control.py` | Raman beam control |
| DDSController | `dds_controller.py` | DDS frequency/phase |
| PMTCounter | `pmt_counter.py` | Photon counting |
| CameraTrigger | `camera_trigger.py` | Camera TTL trigger |

### Experiments

**Location:** `artiq/experiments/`

| Experiment | File | Purpose |
|------------|------|---------|
| SetDC | `set_dc_exp.py` | Set electrode voltages |
| SecularSweep | `secular_sweep_exp.py` | Frequency sweep |
| PMTMeasure | `pmt_measure_exp.py` | Photon counting |
| EmergencyZero | `emergency_zero_exp.py` | Emergency shutdown |

### Configuration

```yaml
# config/artiq/artiq_config.yaml
hardware:
  worker_defaults:
    u_rf_volts: 200.0
    ec1: 0.0
    ec2: 0.0
    comp_h: 0.0
    comp_v: 0.0
```

---

## LabVIEW/SMILE Integration

The LabVIEW SMILE system controls RF, piezo, and various toggles via TCP.

### TCP Protocol

**Port:** 5559
**Format:** JSON over TCP

### Supported Commands

#### Set RF Voltage
```json
{
  "action": "SET_RF",
  "params": {"u_rf_mv": 1000},
  "timestamp": "2026-02-05T19:45:22"
}
```

#### Set Piezo
```json
{
  "action": "SET_PIEZO",
  "params": {"frequency_khz": 307, "amplitude_mv": 500}
}
```

#### Toggle Control
```json
{
  "action": "SET_TOGGLE",
  "params": {"name": "oven", "state": true}
}
```

### Safety Limits

| Parameter | Limit | Unit |
|-----------|-------|------|
| RF Voltage (SMILE) | 0-1400 | mV |
| RF Voltage (Real) | 0-200 | V |
| Piezo ON Time | 10 | s max |
| E-Gun ON Time | 30 | s max |

### Conversion

```python
from src.core.utils.enums import u_rf_mv_to_U_rf_v

# Convert SMILE mV to real V
U_rf_v = u_rf_mv_to_U_rf_v(u_rf_mv)  # U_rf_v = u_rf_mv * (100/700)
```

---

## Camera System

The Hamamatsu ORCA camera provides imaging capabilities.

### Camera Modes

| Mode | Description | Protocol |
|------|-------------|----------|
| Infinity | Continuous live view | HTTP polling |
| Recording | Triggered capture | DCIMG files |

### Specifications

| Parameter | Value |
|-----------|-------|
| Resolution | 2048 x 2048 |
| Pixel Size | 6.5 μm |
| Bit Depth | 16-bit |
| Interface | USB3 |

### Configuration

```yaml
# config/config.yaml
camera:
  enabled: true
  host: "127.0.0.1"
  port: 5558
  exposure_ms: 100
  roi:
    x: 500
    y: 500
    width: 200
    height: 200
```

### API

```python
from src.hardware.camera.camera_client import CameraClient

client = CameraClient()
client.connect()

# Infinity mode
client.start_infinity()
frame = client.get_last_frame()
client.stop_infinity()

# Recording mode
client.start_recording(
    exposure_ms=100,
    roi={'x': 500, 'y': 500, 'width': 200, 'height': 200}
)
```

### Image Processing

**Location:** `src/hardware/camera/image_handler.py`

| Function | Description |
|----------|-------------|
| `calculate_brightness()` | Compute image brightness |
| `find_ion_position()` | Locate ion in image |
| `calculate_uncertainty()` | Compute position uncertainty |

### Data Format

**DCIMG:** Native Hamamatsu format (16-bit raw)
**JPG:** Processed images with analysis overlay

---

## Hardware Configuration

Complete hardware settings in `config/hardware.yaml`:

```yaml
hardware:
  # DC Electrodes (Zotino DAC)
  electrodes:
    ec1:
      channel: 0
      range: [-1, 50]  # Volts
    ec2:
      channel: 1
      range: [-1, 50]
    comp_h:
      channel: 2
      range: [-1, 50]
    comp_v:
      channel: 3
      range: [-1, 50]

  # DDS (Urukul)
  dds:
    axial:
      device: "urukul0_ch0"
      default_freq_mhz: 215.5
    radial:
      device: "urukul0_ch1"
      default_freq_mhz: 215.5

  # RF (via LabVIEW)
  rf:
    min_mv: 0
    max_mv: 1400
    scale_factor: 0.142857  # V/mV

  # Camera
  camera:
    min_exposure_ms: 1
    max_exposure_ms: 10000
    default_exposure_ms: 100
```

---

*Last Updated: 2026-02-05*
