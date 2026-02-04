# Data Flow Diagrams

## 1. Command Flow (Applet → Hardware)

```
┌─────────────┐     HTTP POST      ┌─────────────┐
│   Applet    │ ─────────────────► │   Manager   │
│  (Flask)    │                    │  (ZMQ REQ)  │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ ZMQ PUB
                                          │ (5555)
                                          ▼
┌─────────────┐     ZMQ SUB      ┌─────────────┐
│    FPGA     │ ◄────────────────│   ARTIQ     │
│   (KASLI)   │                  │   Worker    │
└──────┬──────┘                  └─────────────┘
       │
       │ TTL
       ▼
┌─────────────┐
│  Hardware   │
│  (PMT/DDS)  │
└─────────────┘
```

**Timing:** ~10-50ms end-to-end latency

---

## 2. Result Flow (Hardware → Applet)

```
┌─────────────┐     TTL Count      ┌─────────────┐
│    PMT      │ ─────────────────► │    FPGA     │
│  Counter    │                    │   (KASLI)   │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ Kernel
                                          │ fetch
                                          ▼
                                   ┌─────────────┐
                                   │   ARTIQ     │
                                   │   Worker    │
                                   │ (ZMQ PUSH)  │
                                   └──────┬──────┘
                                          │
                                          │ ZMQ PULL
                                          │ (5556)
                                          ▼
┌─────────────┐     ZMQ REP      ┌─────────────┐
│   Applet    │ ◄────────────────│   Manager   │
│  (Flask)    │   JSON Response  │             │
└─────────────┘                  └─────────────┘
```

**Timing:** ~10-50ms end-to-end latency

---

## 3. Live Plotting Flow (Real-time)

```
┌─────────────┐    ARTIQ Dataset   ┌─────────────┐
│   ARTIQ     │ ─────────────────► │   ARTIQ     │
│   Worker    │    Broadcast       │   Master    │
│             │                    │  (dataset   │
│             │                    │   notify)   │
└─────────────┘                    └──────┬──────┘
                                          │
                                          │ IPC/Broadcast
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
            ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
            │   Applet 1  │      │   Applet 2  │      │   Applet N  │
            │   (Plot)    │      │   (Plot)    │      │   (Plot)    │
            └─────────────┘      └─────────────┘      └─────────────┘
```

**Timing:** ~100ms refresh interval

---

## 4. Camera Data Flow

### 4.1 Infinity Mode (Live View)

```
┌─────────────┐    HTTP GET      ┌─────────────┐
│   Flask     │ ───────────────► │   Camera    │
│   Server    │  /start_camera_inf│   Server    │
└──────┬──────┘                  └──────┬──────┘
       │                                │
       │ HTTP GET /get_last_frame       │ TCP (5558)
       │ (polling)                      │
       ▼                                ▼
┌─────────────┐                  ┌─────────────┐
│   Browser   │                  │ Hamamatsu   │
│   (Live     │                  │   ORCA      │
│    View)    │                  │  (DCIMG)    │
└─────────────┘                  └─────────────┘
```

**Timing:** ~1s refresh (HTTP polling)

### 4.2 Recording Mode (Sweep)

```
┌─────────────┐    HTTP POST     ┌─────────────┐
│   Applet    │ ───────────────► │   Flask     │
│  (Start     │  /start_camera   │   Server    │
│   Sweep)    │  with ROI        │             │
└─────────────┘                  └──────┬──────┘
                                        │
                                        │ HTTP
                                        ▼
                                 ┌─────────────┐
                                 │   Camera    │
                                 │   Server    │
                                 │ (Recording) │
                                 └──────┬──────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
             ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
             │   Frame 1   │    │   Frame 2   │    │   Frame N   │
             │  (DCIMG)    │    │  (DCIMG)    │    │  (DCIMG)    │
             └──────┬──────┘    └─────────────┘    └─────────────┘
                    │
                    ▼
             ┌─────────────┐
             │   Analysis  │
             │   (JPG +    │
             │  Position)  │
             └─────────────┘
```

**Timing:** Frame acquisition at exposure time + trigger delay

---

## 5. LabVIEW Integration Flow

```
┌─────────────┐    File Write    ┌─────────────┐
│   LabVIEW   │ ───────────────► │ Telemetry   │
│   Client    │  (JSON/CSV)      │   Files     │
│             │  Every 1-5s      │             │
└─────────────┘                  └──────┬──────┘
                                        │
                                        │ File Watch
                                        │ (polling)
                                        ▼
                                 ┌─────────────┐
                                 │   Manager   │
                                 │   (File     │
                                 │   Reader)   │
                                 └──────┬──────┘
                                        │
                                        │ In-Memory
                                        │ Cache
                                        ▼
                                 ┌─────────────┐
                                 │   Flask     │
                                 │   (HTTP     │
                                 │   Endpoint) │
                                 └──────┬──────┘
                                        │
                                        │ HTTP GET
                                        ▼
                                 ┌─────────────┐
                                 │   Browser   │
                                 │   (Display) │
                                 └─────────────┘
```

**Timing:** 1-5s latency due to file polling

---

## 6. Complete System Data Flow

```
                              ┌──────────────────────────────────────────┐
                              │           BROWSER (User Interface)       │
                              │  ┌──────────┐ ┌──────────┐ ┌──────────┐  │
                              │  │  Applet  │ │  Applet  │ │   Live   │  │
                              │  │ Sweep    │ │ Calib    │ │   Plot   │  │
                              │  └────┬─────┘ └────┬─────┘ └────┬─────┘  │
                              └───────┼────────────┼────────────┼────────┘
                                      │            │            │
                                      └────────────┼────────────┘
                                                   │
                                          HTTP (port 5000)
                                                   │
                              ┌────────────────────┼────────────────────┐
                              │                    │                    │
                              ▼                    ▼                    ▼
                       ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
                       │   Manager   │     │   Camera    │     │   LabVIEW   │
                       │   (ZMQ)     │     │   Control   │     │   Reader    │
                       │             │     │   (HTTP)    │     │  (Files)    │
                       │  ┌───────┐  │     │             │     │             │
                       │  │  REP  │  │     │             │     │             │
                       │  │(5557) │  │     │             │     │             │
                       │  └───┬───┘  │     │             │     │             │
                       │  ┌───┴───┐  │     │             │     │             │
                       │  │ PUB   │  │     │             │     │             │
                       │  │(5555) │  │     │             │     │             │
                       │  └───┬───┘  │     └──────┬──────┘     └─────────────┘
                       │  ┌───┴───┐  │            │
                       │  │ PULL  │  │            │ TCP (5558)
                       │  │(5556) │  │            │
                       │  └───────┘  │            │
                       └──────┬──────┘            │
                              │                   │
              ZMQ PUB/SUB     │                   │
                              │            ┌──────┴──────┐
                              │            │   Camera    │
                              │            │   Server    │
                              │            │             │
                              │            │ ┌─────────┐ │
                              │            │ │Infinity │ │
                              │            │ │ Mode    │ │
                              │            │ └─────────┘ │
                              │            │ ┌─────────┐ │
                              │            │ │Record   │ │
                              │            │ │ Mode    │ │
                              │            │ └─────────┘ │
                              │            └──────┬──────┘
                              │                   │
                              │                   │ USB3
                              ▼                   ▼
                       ┌─────────────┐     ┌─────────────┐
                       │   ARTIQ     │     │ Hamamatsu   │
                       │   Worker    │     │   ORCA      │
                       │             │     │   Camera    │
                       │ ┌─────────┐ │     │             │
                       │ │ Secular │ │     └─────────────┘
                       │ │ Sweep   │ │
                       │ └────┬────┘ │
                       │ ┌────┴────┐ │
                       │ │ Camera  │ │
                       │ │Fragment │ │
                       │ └────┬────┘ │
                       │ ┌────┴────┐ │
                       │ │Compens- │ │
                       │ │ ation   │ │
                       │ └─────────┘ │
                       └──────┬──────┘
                              │
                              │ PCIe
                              ▼
                       ┌─────────────┐
                       │   KASLI     │
                       │    FPGA     │
                       │             │
                       │  ┌───────┐  │
                       │  │  TTL  │  │
                       │  │  I/O  │  │
                       │  └───┬───┘  │
                       │  ┌───┴───┐  │
                       │  │  DDS  │  │
                       │  │Urukul │  │
                       │  └───────┘  │
                       └──────┬──────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
            ▼                 ▼                 ▼
      ┌──────────┐     ┌──────────┐     ┌──────────┐
      │    PMT   │     │  Camera  │     │   DDS    │
      │  Counter │     │  Trigger │     │  Outputs │
      └──────────┘     └──────────┘     └──────────┘
```

---

## 7. Data Format Specifications

### 7.1 ZMQ Message Format

```json
{
  "category": "PMT_MEASURE" | "SECULAR_SWEEP" | "CAM_SWEEP" | "ERROR",
  "timestamp": "2026-02-02T19:45:22.462887+01:00",
  "exp_id": "exp_20260202_194522",
  "applet_id": "cam_sweep_applet",
  "payload": {
    // Command-specific data
  },
  "metadata": {
    "priority": 1,
    "retry_count": 0
  }
}
```

### 7.2 Sweep Result Format

```json
{
  "experiment_id": "sweep_20260202_194522",
  "timestamp": "2026-02-02T19:45:22.462887+01:00",
  "parameters": {
    "start_freq_khz": 400.0,
    "end_freq_khz": 450.0,
    "steps": 50,
    "on_time_ms": 100,
    "off_time_ms": 100,
    "dds_choice": "axial"
  },
  "data": {
    "frequencies_khz": [400.0, 401.0, ..., 450.0],
    "pmt_counts": [45, 67, ..., 89],
    "sig_x": [0.1, 0.2, ..., 0.15],
    "r_y": [0.05, 0.08, ..., 0.12]
  },
  "fits": {
    "pmt_fit": {
      "center_khz": 423.5,
      "fwhm_khz": 2.1,
      "amplitude": 123.4,
      "goodness": "good"
    }
  }
}
```

### 7.3 Camera Configuration Format

```json
{
  "mode": "infinity" | "recording",
  "exposure_ms": 100.0,
  "roi": {
    "x": 500,
    "y": 500,
    "width": 200,
    "height": 200
  },
  "trigger": {
    "source": "software" | "ttl",
    "edge": "rising" | "falling"
  },
  "output": {
    "format": "dcimg" | "jpg",
    "directory": "data/camera/20260202"
  }
}
```

---

## 8. Latency Budget

| Path | Component | Typical | Worst Case |
|------|-----------|---------|------------|
| Command | HTTP parse | 1ms | 5ms |
| Command | ZMQ send | 0.1ms | 1ms |
| Command | ARTIQ kernel | 5ms | 50ms |
| Command | Hardware exec | 1-100ms | 1000ms |
| Result | Hardware read | 0.1ms | 1ms |
| Result | ZMQ return | 0.1ms | 1ms |
| Result | HTTP response | 1ms | 5ms |
| Camera | Mode switch | 500ms | 2000ms |
| Camera | Trigger+exposure | 100ms | 1000ms |
| LabVIEW | File poll | 1000ms | 5000ms |

**Total Command Latency:** ~10-50ms (typical), ~100ms (worst)  
**Total Camera Sweep:** ~10-60s (depends on steps × timing)
