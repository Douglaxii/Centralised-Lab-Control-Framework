# Flask Web Interface Requirements Specification

**Document Version:** 1.0  
**Date:** 2026-01-28  
**Project:** Lab Control Framework - Ion Trap Control System  

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture Requirements](#2-architecture-requirements)
3. [Visual Design Requirements](#3-visual-design-requirements)
4. [Page Structure Requirements](#4-page-structure-requirements)
5. [Hardware Control Requirements](#5-hardware-control-requirements)
6. [Safety System Requirements](#6-safety-system-requirements)
7. [Data Streaming Requirements](#7-data-streaming-requirements)
8. [API Endpoint Requirements](#8-api-endpoint-requirements)
9. [Communication Protocol Requirements](#9-communication-protocol-requirements)
10. [Configuration Requirements](#10-configuration-requirements)

---

## 1. Overview

### 1.1 Purpose
The Flask Web Interface provides a scientific dashboard for real-time monitoring and control of an ion trap experiment system. It serves as the primary user interface for researchers to interact with hardware, monitor telemetry, and execute experimental procedures.

### 1.2 Core Functions
- **Real-time CCD camera streaming** with ion position overlays
- **Hardware control** for voltages, toggles, and DDS parameters
- **Telemetry visualization** with 300-second rolling window graphs
- **Turbo algorithm** control and monitoring
- **Safety kill switch** management with time-limited outputs
- **Experiment management** and sweep execution

### 1.3 Target Users
- Experimental physicists operating the ion trap
- System administrators monitoring hardware health
- Automated algorithms (TuRBO) interfacing via API

---

## 2. Architecture Requirements

### 2.1 System Layout
```
┌─────────────────────────────────────────────────────────────────┐
│                      KILL SWITCH BANNER                          │
│              (Red pulsing banner when active)                    │
├─────────────────────────────────────────────────────────────────┤
│  MODE: [MANUAL/AUTO/SAFE]    ● ARTIQ  ● Wave  ● SMILE  ● Cam   │
├───────────────────────────────┬─────────────────────────────────┤
│                               │                                 │
│   ┌─────────────────────┐     │     ┌─────────────────────┐    │
│   │                     │     │     │  PMT Telemetry      │    │
│   │   CCD Camera Feed   │     │     ├─────────────────────┤    │
│   │   (MJPEG Stream)    │     │     │  Pressure Telemetry │    │
│   │                     │     │     ├─────────────────────┤    │
│   │   Ion position      │     │     │  Laser Frequency    │    │
│   │   overlay with      │     │     ├─────────────────────┤    │
│   │   fit parameters    │     │     │  Navigation Tiles   │    │
│   └─────────────────────┘     │     └─────────────────────┘    │
│                               │                                 │
│   ┌─────────────────────┐     │                                 │
│   │  Control Cockpit    │     │                                 │
│   │  - Voltages         │     │                                 │
│   │  - Toggles          │     │                                 │
│   │  - Piezo (KS)       │     │                                 │
│   │  - E-Gun (KS)       │     │                                 │
│   └─────────────────────┘     │                                 │
│                               │                                 │
└───────────────────────────────┴─────────────────────────────────┘
```

### 2.2 Column Distribution
| Column | Width | Content | Ratio |
|--------|-------|---------|-------|
| Left | 50% | Camera (75%) + Controls (25%) | 3:1 |
| Right | 50% | Telemetry Stack | 4 tiles |

### 2.3 Technology Stack
| Component | Technology | Version/Notes |
|-----------|------------|---------------|
| Backend | Flask | Python 3.x |
| Frontend | Vanilla JS | No frameworks |
| Styling | CSS3 | CSS Variables for theming |
| Charts | Chart.js | CDN delivery |
| Fonts | Google Fonts | Inter, Fira Code |
| Streaming | MJPEG | multipart/x-mixed-replace |
| Real-time | SSE | Server-Sent Events |

---

## 3. Visual Design Requirements

### 3.1 Color Palette
| Purpose | Hex Code | Usage |
|---------|----------|-------|
| Background Primary | `#F9FAFB` | Page background |
| Background Card | `#FFFFFF` | Panel backgrounds |
| Background Console | `#F3F4F6` | Console/log areas |
| Border Primary | `#E5E7EB` | Card borders, dividers |
| Border Focus | `#3B82F6` | Input focus states |
| Text Primary | `#111827` | Headings, primary text |
| Text Secondary | `#6B7280` | Labels, secondary text |
| Text Muted | `#9CA3AF` | Placeholders, hints |
| Accent Blue | `#3B82F6` | Primary buttons, links |
| Accent Blue Hover | `#2563EB` | Button hover states |
| Accent Green | `#10B981` | Success, live indicators |
| Accent Green Light | `#D1FAE5` | Success backgrounds |
| Accent Red | `#EF4444` | Errors, kill switch, danger |
| Accent Red Light | `#FEE2E2` | Error backgrounds |
| Accent Red Dark | `#991B1B` | Dark error text |
| Accent Yellow | `#F59E0B` | Warnings, caution |
| Accent Orange | `#F97316` | Kill switch active state |
| Accent Purple | `#8B5CF6` | Pressure telemetry |
| Accent Cyan | `#06B6D4` | Laser frequency telemetry |

### 3.2 Typography
| Element | Font | Size | Weight |
|---------|------|------|--------|
| UI Text | Inter | 0.75-0.85rem | 400-600 |
| Monospace Data | Fira Code | 0.8-0.9rem | 500 |
| Labels | Inter | 0.65-0.75rem | 600 |
| Headings | Inter | 1.0-1.2rem | 600 |
| Timer Displays | Fira Code | 0.75rem | 600 |

### 3.3 Spacing System
| Token | Value | Usage |
|-------|-------|-------|
| `--spacing-xs` | 2px | Minimal gaps |
| `--spacing-sm` | 4px | Tight spacing |
| `--spacing-md` | 8px | Standard spacing |
| `--spacing-lg` | 12px | Large gaps |
| `--spacing-xl` | 16px | Section padding |

### 3.4 Border Radius
| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | 4px | Buttons, inputs |
| `--radius-md` | 6px | Cards, panels |

---

## 4. Page Structure Requirements

### 4.1 Main Dashboard (`/`)
**Layout:** Two-column grid with status bar and conditional kill switch banner

#### Status Bar Components:
| Element | Display | States |
|---------|---------|--------|
| Mode Indicator | Text badge | MANUAL (yellow), AUTO (green), SAFE (red) |
| ARTIQ Status | Dot + label | Green=alive, Gray=inactive, Red=error |
| Wavemeter Status | Dot + label | Same as above |
| SMILE Status | Dot + label | Same as above |
| Camera Status | Dot + label | Same as above |

#### Camera Section Requirements:
- **Stream Source:** MJPEG from `/video_feed`
- **Resolution:** Adaptive (max 100% container)
- **Overlay Elements:**
  - "● LIVE" indicator (green, pulsing animation)
  - Latency display (e.g., "Lat: 45ms")
  - Ion position coordinates (e.g., "Pos: 320, 240")
  - High delay warning (red banner when >500ms)
- **Position Marker:** Thin green circle (20px radius, 1px thickness) + fit parameters text

#### Control Cockpit Requirements:
**Row 1 - Primary Controls:**
| Control | Type | Range | Default |
|---------|------|-------|---------|
| RF Voltage | Number input + button | 0-500 V | 200 |
| DDS Frequency | Number input + button | 0-500 kHz | 0 |
| DDS Profile | Dropdown | 0-3 | 0 |
| Electrodes | Two number inputs | -100 to 100 V | 0 |

**Row 2 - Compensation & Toggles:**
| Control | Type | Range | Default |
|---------|------|-------|---------|
| Comp H | Number input | -100 to 100 V | 0 |
| Comp V | Number input | -100 to 100 V | 0 |
| Bephi | Toggle button | On/Off | Off |
| B-Field | Toggle button | On/Off | On |
| Oven | Toggle button | On/Off | Off |

**Row 3 - Piezo Control (Kill Switch Protected):**
| Element | Specification |
|---------|--------------|
| Setpoint Input | 0-4V, 0.01 step, numeric |
| Slider | 0-4V range, synchronized with input |
| Output Button | "OUTPUT ON/OFF", orange when active, pulsing animation |
| Timer Display | Countdown from 10s, color-coded (green/yellow/red) |
| Kill Switch Badge | Red "KILL SWITCH" label |

**Row 4 - Lasers & E-Gun:**
| Control | Type | Kill Switch | Time Limit |
|---------|------|-------------|------------|
| UV3 | Toggle | No | N/A |
| E-Gun | Toggle | Yes | 10s |

#### Right Column - Telemetry Stack:
| Tile | Data Source | Y-Axis | Color |
|------|-------------|--------|-------|
| PMT | DataIngestionServer | Photon counts | Orange |
| Pressure | DataIngestionServer | mbar | Purple |
| Laser Frequency | DataIngestionServer | MHz | Cyan |
| Navigation | N/A | Links to /turbo, /tools | N/A |

**Chart Specifications:**
- Type: Line chart with fill
- Window: 300 seconds rolling
- Update rate: 2 Hz (SSE)
- Y-axis: 3 tick marks maximum
- Grid: Horizontal only
- Animation: Disabled for performance

---

### 4.2 TuRBO Control Page (`/turbo`)
**Layout:** 2x2 grid of panels

| Panel | Content |
|-------|---------|
| Top-Left | Algorithm Control (Start/Stop/Pause/Reset) |
| Top-Right | Optimization Metrics (iterations, best value, trust region) |
| Bottom-Left | Parameter Space configuration |
| Bottom-Right | Algorithm Log (streaming console) |

**Algorithm States:**
| State | Color | Description |
|-------|-------|-------------|
| IDLE | Gray | Algorithm ready but not running |
| RUNNING | Green | Algorithm active |
| OPTIMIZING | Blue | Currently optimizing parameters |
| CONVERGED | Green | Optimization converged |
| DIVERGING | Red | Optimization diverging |
| ERROR | Red | Error condition |

**Log Console Requirements:**
- Dark background (#1F2937)
- Monospace font (Fira Code)
- Color-coded levels: INFO (green), WARNING (yellow), ERROR (red), ITERATION (blue)
- Timestamps on all entries
- Auto-scroll to latest

---

### 4.3 Tools Page (`/tools`)
**Layout:** 2x2 grid of tool panels

| Panel | Function |
|-------|----------|
| Top-Left | Secular Sweep Scan (frequency sweep execution) |
| Top-Right | Auto Compensation (ion positioning) |
| Bottom-Left | Secular Frequency Comparison |
| Bottom-Right | Quick Tools grid |

**Secular Sweep Parameters:**
| Parameter | Range | Default |
|-----------|-------|---------|
| Target Freq | 0-500 kHz | 307 kHz |
| Span | 0-100 kHz | 40 kHz |
| Steps | 2-1000 | 41 |
| Attenuation | 0-31 dB | 25 dB |
| On Time | 1-1000 ms | 300 ms |
| Off Time | 1-1000 ms | 300 ms |

---

## 5. Hardware Control Requirements

### 5.1 Electrode Control
**Endpoint:** `POST /api/control/electrodes`

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| ec1 | float | -100 to 100 V | Endcap 1 voltage |
| ec2 | float | -100 to 100 V | Endcap 2 voltage |
| comp_h | float | -100 to 100 V | Horizontal compensation |
| comp_v | float | -100 to 100 V | Vertical compensation |

### 5.2 RF Voltage Control
**Endpoint:** `POST /api/control/rf`

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| u_rf_volts | float | 0-500 V | Real RF voltage (not SMILE mV) |

### 5.3 Piezo Control
**Setpoint Endpoint:** `POST /api/control/piezo/setpoint`
- Sets target voltage without enabling output
- Range: 0-4V

**Output Endpoint:** `POST /api/control/piezo/output`
- Enables/disables actual voltage output
- Kill switch armed when enabled (10s limit)
- Auto-zeros when kill switch triggers

### 5.4 Toggle Controls
**Endpoint:** `POST /api/control/toggle/{name}`

| Toggle | Kill Switch | Time Limit | Default |
|--------|-------------|------------|---------|
| bephi | No | N/A | Off |
| b_field | No | N/A | On |
| be_oven | No | N/A | Off |
| uv3 | No | N/A | Off |
| e_gun | Yes | 10s | Off |

### 5.5 DDS Control
**Endpoint:** `POST /api/control/dds`

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| profile | int | 0-7 | DDS profile selection |
| freq_khz | float | 0-500 kHz | DDS frequency |

---

## 6. Safety System Requirements

### 6.1 Kill Switch System
**Protected Devices:**
| Device | Time Limit | Auto-action |
|--------|------------|-------------|
| Piezo Output | 10 seconds | Zero voltage to 0V |
| E-Gun | 10 seconds (testing mode) | Turn off |

### 6.2 Kill Switch UI Requirements
1. **Banner Display:** Red pulsing banner appears when any kill switch is active
2. **Countdown Timer:** Shows remaining time with color coding:
   - Green: >50% time remaining (>5s for piezo)
   - Yellow: <50% time remaining
   - Red: <20% time remaining (urgent)
3. **Manual Stop Button:** "STOP NOW" button on banner for immediate kill
4. **Confirmation Dialog:** Warning dialog before enabling kill-switch-protected devices

### 6.3 Safety Shutdown
**Endpoint:** `POST /api/safety/toggle`

When engaged:
1. Sends STOP signal to manager
2. Triggers all active kill switches
3. Resets all voltages to 0V
4. Turns off all toggles
5. Halts Turbo algorithm
6. Sets mode to SAFE

---

## 7. Data Streaming Requirements

### 7.1 Camera Stream
**Endpoint:** `GET /video_feed`
- Format: MJPEG multipart/x-mixed-replace
- Target FPS: 30
- Frame source: `Y:/Xi/Data/jpg_frames_labelled/YYMMDD/*_labelled.jpg`
- Fallback: Simulated frame if no camera data

### 7.2 Telemetry Stream
**Endpoint:** `GET /api/telemetry/stream`
- Protocol: Server-Sent Events (SSE)
- Update rate: 2 Hz
- Data window: 300 seconds
- Channels: pos_x, pos_y, sig_x, sig_y, pressure, laser_freq, pmt

### 7.3 Turbo Log Stream
**Endpoint:** `GET /api/turbo/logs/stream`
- Protocol: Server-Sent Events (SSE)
- Real-time algorithm log entries
- Heartbeat every 5 seconds

---

## 8. API Endpoint Requirements

### 8.1 Complete Endpoint List

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/turbo` | GET | TuRBO control page |
| `/tools` | GET | Tools page |
| `/video_feed` | GET | MJPEG camera stream |
| `/api/telemetry/stream` | GET | SSE telemetry stream |
| `/api/turbo/logs/stream` | GET | SSE algorithm logs |
| `/api/status` | GET | Full system status |
| `/api/control/electrodes` | POST | Set electrode voltages |
| `/api/control/rf` | POST | Set RF voltage |
| `/api/control/piezo/setpoint` | POST | Set piezo setpoint |
| `/api/control/piezo/output` | POST | Enable/disable piezo output |
| `/api/control/toggle/{name}` | POST | Set toggle state |
| `/api/control/dds` | POST | Set DDS parameters |
| `/api/killswitch/status` | GET | Get kill switch status |
| `/api/killswitch/trigger` | POST | Manual kill switch trigger |
| `/api/safety/toggle` | POST | Engage/disengage safety |
| `/api/safety/status` | GET | Get safety status |
| `/api/turbo/logs` | GET | Get Turbo logs (REST) |
| `/api/mode` | POST | Change system mode |
| `/api/sweep` | POST | Trigger frequency sweep |
| `/api/compare` | POST | Trigger secular comparison |
| `/api/experiment` | GET | Get experiment status |
| `/api/experiments` | GET | List recent experiments |
| `/api/data/sources` | GET | Get LabVIEW data source status |
| `/api/data/recent/{channel}` | GET | Get recent channel data |

---

## 9. Communication Protocol Requirements

### 9.1 ZMQ Connection to Manager
| Property | Value |
|----------|-------|
| Socket Type | REQ (Client) |
| Target | Manager REP socket |
| Port | 5557 (configurable) |
| Timeout | 5000ms |
| Retry Logic | 1 retry with reconnect |

### 9.2 Message Format (Flask → Manager)
```json
{
  "action": "SET|GET|STATUS|SWEEP|MODE|STOP|COMPARE",
  "source": "USER|FLASK|FLASK_SAFETY",
  "params": {},
  "exp_id": "EXP_HHMMSS_XXXXXXXX"
}
```

### 9.3 Camera Frame Retrieval
1. Monitor `Y:/Xi/Data/jpg_frames_labelled/YYMMDD/` directory
2. Find most recent `*_labelled.jpg` file
3. Check freshness (< 5 seconds old)
4. Read companion JSON for fit parameters
5. Add overlays and encode to MJPEG

---

## 10. Configuration Requirements

### 10.1 Required Configuration (settings.yaml)
```yaml
network:
  master_ip: "192.168.1.100"
  client_port: 5557

paths:
  output_base: "Y:/Xi/Data"
  jpg_frames_labelled: "Y:/Xi/Data/jpg_frames_labelled"

labview:
  enabled: true
  host: "192.168.1.100"
  port: 5559

data_ingestion:
  enabled: true
  port: 5560
```

### 10.2 Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_PORT` | 5000 | HTTP server port |
| `FLASK_HOST` | 0.0.0.0 | Bind address |
| `MANAGER_IP` | From config | Manager ZMQ IP |

### 10.3 File System Permissions
- Read access to: `Y:/Xi/Data/jpg_frames_labelled/`
- Write access to: `logs/` directory

---

## Appendix A: Mode Definitions

| Mode | Description | Turbo State | Safety |
|------|-------------|-------------|--------|
| MANUAL | User controls hardware | IDLE | Engaged |
| AUTO | Algorithm controls hardware | RUNNING | Disengaged |
| SAFE | Emergency safe state | STOPPED | Engaged |

## Appendix B: Algorithm States

| State | Description |
|-------|-------------|
| IDLE | Waiting for start command |
| RUNNING | Algorithm executing |
| OPTIMIZING | Active parameter optimization |
| CONVERGED | Optimization complete |
| DIVERGING | Unstable condition detected |
| STOPPED | Safety stop or manual stop |

## Appendix C: Data Source Channels

| Channel | Source | Unit | Update Rate |
|---------|--------|------|-------------|
| laser_freq | Wavemeter | MHz | 1 Hz |
| pmt | SMILE | counts | 1 Hz |
| pressure | SMILE | mbar | 1 Hz |
| pos_x | Camera | pixels | From image handler |
| pos_y | Camera | pixels | From image handler |
| sig_x | Camera | pixels | From image handler |
| sig_y | Camera | pixels | From image handler |

---

**End of Document**
