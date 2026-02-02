# Communication Protocol Specification

**Version:** 1.0  
**Date:** 2026-01-28

## Table of Contents

1. [Network Architecture Overview](#network-architecture-overview)
2. [Port Assignments](#port-assignments)
3. [Protocol Summary](#protocol-summary)
4. [ZMQ Communication Patterns](#zmq-communication-patterns)
5. [TCP Communication Patterns](#tcp-communication-patterns)
6. [JSON Message Formats](#json-message-formats)
7. [Component-Specific Protocols](#component-specific-protocols)
8. [Error Handling](#error-handling)

## Network Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NETWORK ARCHITECTURE                               │
└─────────────────────────────────────────────────────────────────────────────┘

                                    ┌──────────────┐
                                    │  Flask Web   │
                                    │     UI       │
                                    │  :5000 HTTP  │
                                    └──────┬───────┘
                                           │
                                           │ REQ/REP
                                           │ (ZMQ Port 5557)
                                           ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  LabVIEW     │◄──►│   Control    │◄──►│   ARTIQ      │    │   Camera     │
│   SMILE      │TCP │   Manager    │ZMQ │   Worker     │    │   Server     │
│  :5559       │    │   :5555-5557 │    │   :5555-5556 │    │   :5558      │
└──────────────┘    └──────┬───────┘    └──────────────┘    └──────────────┘
                           │
                           │ PULL (Port 5556)
                           ▼
                    ┌──────────────┐
                    │ Data Ingest. │
                    │   Server     │
                    │   :5560      │
                    └──────────────┘
                           ▲
                           │ TCP (JSON Lines)
                    ┌──────┴───────┐
                    │  LabVIEW     │
                    │  Wavemeter   │
                    └──────────────┘

IP Configuration:
- Master/Manager IP: 192.168.1.100 (configurable in settings.yaml)
- All services bind to 0.0.0.0 (all interfaces) unless specified
```

## Port Assignments

| Port | Protocol | Pattern | Component | Direction | Purpose |
|------|----------|---------|-----------|-----------|---------|
| **5555** | ZMQ | PUB/SUB | Manager → Workers | Outbound | Command distribution |
| **5556** | ZMQ | PUSH/PULL | Workers → Manager | Inbound | Data/telemetry collection |
| **5557** | ZMQ | REQ/REP | Flask ↔ Manager | Bidirectional | Client requests/responses |
| **5558** | TCP | Raw Socket | Camera Server | Bidirectional | Camera control & streaming |
| **5559** | TCP | JSON Lines | LabVIEW SMILE | Bidirectional | Hardware control (RF, Piezo, Toggles) |
| **5560** | TCP | JSON Lines | Data Ingestion | Inbound | Telemetry from LabVIEW instruments |
| **5000** | HTTP | REST/SSE | Flask Web UI | Bidirectional | Web interface & streaming |

### Port Usage Matrix

```
                    ┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
                    │  5555   │  5556   │  5557   │  5558   │  5559   │  5560   │
┌───────────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│ Control Manager   │  BIND   │  BIND   │  BIND   │    -    │ CONNECT │  BIND   │
│ ARTIQ Worker      │ CONNECT │ CONNECT │    -    │    -    │    -    │    -    │
│ Flask Server      │    -    │    -    │ CONNECT │    -    │    -    │    -    │
│ Camera Server     │    -    │    -    │    -    │  BIND   │    -    │    -    │
│ LabVIEW SMILE     │    -    │    -    │    -    │    -    │  BIND   │ CONNECT │
│ LabVIEW Wavemeter │    -    │    -    │    -    │    -    │    -    │ CONNECT │
└───────────────────┴─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘
```

## Protocol Summary

### ZMQ Patterns

#### PUB/SUB (Port 5555) - Command Distribution
- **Publisher:** Control Manager
- **Subscribers:** ARTIQ Worker, Other Workers
- **Topic Filtering:** Workers subscribe to their device name (e.g., "ARTIQ") and "ALL"
- **Message Format:** Multipart ZMQ message `[topic, json_payload]`

#### PUSH/PULL (Port 5556) - Data Collection
- **Pushers:** ARTIQ Worker, Other Workers
- **Puller:** Control Manager
- **Pattern:** Load-balanced queue (round-robin)
- **Message Format:** JSON object

#### REQ/REP (Port 5557) - Client Requests
- **Requester:** Flask Server
- **Replier:** Control Manager
- **Pattern:** Synchronous request-response
- **Timeout:** 5 seconds default

### TCP Patterns

#### LabVIEW Interface (Port 5559)
- **Protocol:** JSON over TCP (newline-delimited)
- **Connection:** Persistent with keepalive pings
- **Retry:** 3 attempts with exponential backoff

#### Data Ingestion (Port 5560)
- **Protocol:** JSON Lines (one object per line)
- **Sources:** Wavemeter.vi, SMILE.vi, Camera
- **Buffering:** 5-minute rolling window

## ZMQ Communication Patterns

### Command Flow (Manager → Workers)

```
┌──────────────┐                    ┌──────────────┐
│   Manager    │──PUB [topic]──────►│  SUB Socket  │
│  (Port 5555) │──SNDMORE──────────►│   (Worker)   │
│              │──JSON payload─────►│              │
└──────────────┘                    └──────────────┘
```

### Data Flow (Workers → Manager)

```
┌──────────────┐                    ┌──────────────┐
│ PUSH Socket  │──JSON payload─────►│ PULL Socket  │
│   (Worker)   │                    │  (Manager)   │
└──────────────┘                    │  (Port 5556) │
                                    └──────────────┘
```

### Client Request Flow (Flask ↔ Manager)

```
┌──────────────┐                    ┌──────────────┐
│  REQ Socket  │──JSON Request─────►│  REP Socket  │
│    (Flask)   │◄───JSON Response───│  (Manager)   │
└──────────────┘                    │  (Port 5557) │
                                    └──────────────┘
```

## TCP Communication Patterns

### LabVIEW SMILE Control (Port 5559)

```
┌──────────────┐                    ┌──────────────┐
│   Manager    │◄──TCP JSON───────►│  LabVIEW     │
│              │   (persistent)    │   SMILE.vi   │
└──────────────┘                    └──────────────┘

Request Format:
{"command": "set_voltage", "device": "U_RF", "value": 200.0, 
 "timestamp": 1706380800.123, "request_id": "REQ_000001_..."}

Response Format:
{"request_id": "REQ_000001_...", "status": "ok", "device": "U_RF",
 "value": 200.0, "timestamp": 1706380800.125}
```

### Data Ingestion (Port 5560)

```
┌──────────────┐                    ┌──────────────┐
│ LabVIEW      │──TCP JSON Lines──►│ Data Server  │
│ Instruments  │   (streaming)     │  (Port 5560) │
└──────────────┘                    └──────────────┘

Data Format (one per line):
{"source": "wavemeter", "channel": "laser_freq", "value": 212.456, 
 "timestamp": 1706380800.123}
```

## JSON Message Formats

### ZMQ Command Messages (Port 5555)

#### Common Command Structure
```json
{
  "timestamp": 1706380800.123,
  "target": "ARTIQ",
  "params": {
    "type": "SET_DC",
    ...
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### SET_DC - Set DC Electrodes
**Sender:** Control Manager  
**Receiver:** ARTIQ Worker  
**Topic:** "ALL"

```json
{
  "timestamp": 1706380800.123,
  "target": "ALL",
  "params": {
    "type": "SET_DC",
    "values": {
      "ec1": 10.0,
      "ec2": 10.0,
      "comp_h": 6.0,
      "comp_v": 37.0
    }
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| ec1 | float | -100 to 100 V | Endcap 1 voltage |
| ec2 | float | -100 to 100 V | Endcap 2 voltage |
| comp_h | float | -100 to 100 V | Horizontal compensation |
| comp_v | float | -100 to 100 V | Vertical compensation |

#### SET_COOLING - Set Raman Cooling Parameters
**Sender:** Control Manager  
**Receiver:** ARTIQ Worker  
**Topic:** "ALL"

```json
{
  "timestamp": 1706380800.123,
  "target": "ALL",
  "params": {
    "type": "SET_COOLING",
    "values": {
      "freq0": 212.5,
      "amp0": 0.05,
      "freq1": 212.5,
      "amp1": 0.05,
      "sw0": false,
      "sw1": false
    }
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| freq0 | float | 200-220 MHz | Raman 0 frequency |
| amp0 | float | 0-1 | Raman 0 amplitude |
| freq1 | float | 200-220 MHz | Raman 1 frequency |
| amp1 | float | 0-1 | Raman 1 amplitude |
| sw0 | bool | true/false | Shutter 0 state |
| sw1 | bool | true/false | Shutter 1 state |

#### SET_RF - Set RF Voltage
**Sender:** Control Manager  
**Receiver:** ARTIQ Worker, LabVIEW  
**Topic:** "ALL"

```json
{
  "timestamp": 1706380800.123,
  "target": "ALL",
  "params": {
    "type": "SET_RF",
    "values": {
      "u_rf_volts": 200.0
    }
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| u_rf_volts | float | 0-500 V | Real RF voltage (not SMILE mV) |

#### SET_PIEZO - Set Piezo Voltage
**Sender:** Control Manager  
**Receiver:** ARTIQ Worker, LabVIEW  
**Topic:** "ALL"

```json
{
  "timestamp": 1706380800.123,
  "target": "ALL",
  "params": {
    "type": "SET_PIEZO",
    "values": {
      "piezo": 2.5
    }
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| piezo | float | 0-4 V | Piezo voltage for laser tuning |

#### RUN_SWEEP - Execute Secular Frequency Sweep
**Sender:** Control Manager  
**Receiver:** ARTIQ Worker  
**Topic:** "ARTIQ"

```json
{
  "timestamp": 1706380800.123,
  "target": "ARTIQ",
  "params": {
    "type": "RUN_SWEEP",
    "values": {
      "target_frequency_khz": 307.0,
      "span_khz": 40.0,
      "steps": 41,
      "attenuation_db": 25.0,
      "on_time_ms": 300.0,
      "off_time_ms": 300.0
    }
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| target_frequency_khz | float | 0-500 kHz | Center frequency |
| span_khz | float | 0-100 kHz | Total sweep span |
| steps | int | 2-1000 | Number of sweep points |
| attenuation_db | float | 0-31 dB | DDS attenuation |
| on_time_ms | float | 1-1000 ms | Gate on time |
| off_time_ms | float | 1-1000 ms | Delay between points |

### ZMQ Data Messages (Port 5556)

#### Common Data Structure
```json
{
  "timestamp": 1706380800.123,
  "source": "ARTIQ",
  "category": "HEARTBEAT",
  "payload": {},
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### HEARTBEAT - Worker Health Status
**Sender:** ARTIQ Worker  
**Receiver:** Control Manager

```json
{
  "timestamp": 1706380800.123,
  "source": "ARTIQ",
  "category": "HEARTBEAT",
  "payload": {
    "status": "alive",
    "state": {
      "ec1": 10.0,
      "ec2": 10.0,
      ...
    },
    "safety_triggered": false
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### SWEEP_COMPLETE - Sweep Finished Notification
**Sender:** ARTIQ Worker  
**Receiver:** Control Manager

```json
{
  "timestamp": 1706380800.123,
  "source": "ARTIQ",
  "category": "SWEEP_COMPLETE",
  "payload": {
    "status": "SWEEP_COMPLETE",
    "exp_id": "EXP_240128_A1B2C3D4",
    "target": 307.0,
    "span": 40.0,
    "steps": 41,
    "file_path": "Y:/Xi/Data/2026-01-28/sweep_123456.h5"
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### ERROR - Error Notification
**Sender:** ARTIQ Worker  
**Receiver:** Control Manager

```json
{
  "timestamp": 1706380800.123,
  "source": "ARTIQ",
  "category": "ERROR",
  "payload": {
    "error": "Hardware timeout",
    "details": "PMT not responding"
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### SAFETY_TRIGGER - Safety Event
**Sender:** ARTIQ Worker  
**Receiver:** Control Manager

```json
{
  "timestamp": 1706380800.123,
  "source": "ARTIQ",
  "category": "SAFETY_TRIGGER",
  "payload": {
    "trigger_type": "connection_loss",
    "safety_count": 1,
    "previous_state": {...}
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

### Client Request/Response (Port 5557)

#### SET Request
**Sender:** Flask Server  
**Receiver:** Control Manager

```json
{
  "action": "SET",
  "source": "USER",
  "params": {
    "ec1": 10.0,
    "ec2": 10.0,
    "comp_h": 6.0,
    "comp_v": 37.0
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### SET Response
```json
{
  "status": "success",
  "mode": "MANUAL",
  "params": {
    "ec1": 10.0,
    "ec2": 10.0,
    "comp_h": 6.0,
    "comp_v": 37.0
  }
}
```

#### SWEEP Request
```json
{
  "action": "SWEEP",
  "source": "USER",
  "params": {
    "target_frequency_khz": 307.0,
    "span_khz": 40.0,
    "steps": 41
  },
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### SWEEP Response
```json
{
  "status": "started",
  "exp_id": "EXP_240128_A1B2C3D4"
}
```

#### STOP Request (Emergency)
```json
{
  "action": "STOP",
  "source": "FLASK_SAFETY",
  "reason": "Safety switch engaged"
}
```

### LabVIEW SMILE Protocol (Port 5559)

#### Command Types

| Command | Device | Value Type | Description |
|---------|--------|------------|-------------|
| set_voltage | U_RF | float (V) | RF voltage 0-1000V |
| set_voltage | piezo | float (V) | Piezo 0-4V |
| set_toggle | be_oven | bool | Be+ oven on/off |
| set_toggle | b_field | bool | B-field on/off |
| set_toggle | bephi | bool | Bephi on/off |
| set_toggle | uv3 | bool | UV3 laser on/off |
| set_toggle | e_gun | bool | Electron gun on/off |
| set_shutter | hd_shutter_1 | bool | HD valve shutter 1 |
| set_shutter | hd_shutter_2 | bool | HD valve shutter 2 |
| set_frequency | dds | float (MHz) | DDS frequency |
| get_status | all | null | Query all device states |
| emergency_stop | all | null | Immediate stop |
| ping | system | null | Keepalive |

#### LabVIEW Command Format
```json
{
  "command": "set_voltage",
  "device": "U_RF",
  "value": 200.0,
  "timestamp": 1706380800.123,
  "request_id": "REQ_000001_1706380800123"
}
```

#### LabVIEW Response Format
```json
{
  "request_id": "REQ_000001_1706380800123",
  "status": "ok",
  "device": "U_RF",
  "value": 200.0,
  "message": null,
  "timestamp": 1706380800.125
}
```

Status values: `ok`, `error`, `busy`

### Data Ingestion Protocol (Port 5560)

#### Telemetry Data Format
```json
{
  "source": "wavemeter",
  "channel": "laser_freq",
  "value": 212.456789,
  "timestamp": 1706380800.123
}
```

#### Valid Sources
- `wavemeter` - Laser frequency data
- `smile` - PMT counts, pressure
- `camera` - Position data from image analysis
- `artiq` - Experimental data
- `turbo` - Algorithm telemetry

#### Channel Mapping

| External Channel | Internal Channel | Description |
|-----------------|------------------|-------------|
| laser_freq, frequency, wavemeter | laser_freq | Laser frequency (MHz) |
| pmt, pmt_counts, photon_counts | pmt | PMT counts |
| pressure, chamber_pressure, vacuum | pressure | Chamber pressure (mbar) |
| pos_x, position_x, ion_x | pos_x | Ion X position |
| pos_y, position_y, ion_y | pos_y | Ion Y position |
| sig_x, sigma_x, width_x | sig_x | Signal width X |
| sig_y, sigma_y, width_y | sig_y | Signal width Y |

### Camera Server Protocol (Port 5558)

#### Commands (Plain Text)

| Command | Response | Description |
|---------|----------|-------------|
| START | `OK: Aufnahme gestartet` | Start single capture |
| START_INF | `OK:Inf Aufnahme gestartet` | Start continuous capture |
| STOP | `OK: Aufnahme gestoppt` | Stop capture |
| STATUS | `Kamera bereit` | Query status |
| EXP_ID:{id} | - | Set experiment ID |

## Component-Specific Protocols

### Control Manager

**Bindings:**
- PUB socket on `tcp://*:5555`
- PULL socket on `tcp://*:5556`
- REP socket on `tcp://*:5557`

**Valid Parameters:**
```python
VALID_PARAMS = {
    "u_rf",  # RF Voltage (0-1500mVV)
    "ec1", "ec2", "comp_h", "comp_v",  # Electrodes (-1 to 50V)
    "sw0","amp0", "sw1","amp1"  # ramanboard (1 or 0, [0,1])
    "bephi", "b_field", "be_oven", "uv3", "e_gun",  # 1 or 0
    "hd_voltage",  # Piezo (0-4V)
    "hd_shutter"   # piezo valve (1,0)
    "dds_freq_Mhz"  # DDS frequency (0-500 MHz)
}
```

### ARTIQ Worker

**Connections:**
- SUB socket to `tcp://{master_ip}:5555`
- PUSH socket to `tcp://{master_ip}:5556`

**Subscriptions:** `ARTIQ`, `ALL`

**Watchdog Timeout:** 60 seconds (configurable)

**Heartbeat Interval:** 10 seconds (configurable)

### Flask Server

**ZMQ Connection:**
- REQ socket to `tcp://{manager_ip}:5557`
- Timeout: 5000ms

**HTTP Endpoints:** See [API Reference](../api/reference.md)

## Error Handling

### ZMQ Error Codes

| Code | Description | Action |
|------|-------------|--------|
| `TIMEOUT` | Request timed out | Retry with backoff |
| `ZMQ_ERROR` | Socket error | Reconnect socket |
| `VALIDATION_ERROR` | Invalid parameters | Return error to user |
| `UNKNOWN_ACTION` | Unrecognized command | Log and ignore |
| `INTERNAL_ERROR` | Server error | Log and notify |
| `NO_EXPERIMENT` | No active experiment | Create or reject |

### Safety States

When safety is triggered:
1. All voltages set to 0V
2. All toggles set to OFF
3. DDS profile reset to 0
4. Mode switched to SAFE
5. Turbo algorithm stopped

### Reconnection Strategy

```python
# Exponential backoff retry
max_retries = 5
base_delay = 1.0  # seconds

for attempt in range(max_retries):
    try:
        connect()
        break
    except ConnectionError:
        delay = base_delay * (2 ** attempt)
        sleep(delay)
```

## Appendix A: Configuration Reference

### settings.yaml Network Section

```yaml
network:
  master_ip: "192.168.1.100"
  cmd_port: 5555
  data_port: 5556
  client_port: 5557
  camera_port: 5558
  connection_timeout: 5.0
  receive_timeout: 1.0
  watchdog_timeout: 60.0
  heartbeat_interval: 10.0
  max_retries: 5
  retry_base_delay: 1.0
```

### LabVIEW Configuration

```yaml
labview:
  enabled: true
  host: "192.168.1.100"
  port: 5559
  timeout: 5.0
  retry_delay: 1.0
  max_retries: 3
```

### Data Ingestion Configuration

```yaml
data_ingestion:
  enabled: true
  host: "0.0.0.0"
  port: 5560
  timeout: 5.0
  max_connections: 10
```

## Appendix B: Quick Reference Card

### Port Quick Reference

| Port | Component | Socket Type | Bind/Connect |
|------|-----------|-------------|--------------|
| 5555 | Manager | ZMQ PUB | BIND |
| 5556 | Manager | ZMQ PULL | BIND |
| 5557 | Manager | ZMQ REP | BIND |
| 5555 | ARTIQ | ZMQ SUB | CONNECT |
| 5556 | ARTIQ | ZMQ PUSH | CONNECT |
| 5557 | Flask | ZMQ REQ | CONNECT |
| 5558 | Camera | TCP | BIND |
| 5559 | LabVIEW | TCP | BIND |
| 5560 | Data Server | TCP | BIND |

### Message Type Quick Reference

| Category | Direction | Port | Pattern |
|----------|-----------|------|---------|
| Command | Manager → Workers | 5555 | PUB/SUB |
| Data | Workers → Manager | 5556 | PUSH/PULL |
| Request | Flask ↔ Manager | 5557 | REQ/REP |
| LabVIEW | Manager ↔ SMILE | 5559 | TCP JSON |
| Telemetry | Instruments → Manager | 5560 | TCP JSON Lines |
