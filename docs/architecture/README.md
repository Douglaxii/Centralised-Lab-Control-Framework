# System Architecture

This section covers the MLS system architecture, design principles, and communication protocols.

## Contents

- [Overview](overview.md) - High-level system architecture and components
- [Communication](communication.md) - Communication protocols (ZMQ, TCP) and message formats

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Web UI     │  │   TuRBO      │  │   Jupyter    │          │
│  │   (Flask)    │  │   (Auto)     │  │   (Analysis) │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼────────────────┼────────────────┼───────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CONTROL LAYER                               │
│                    ControlManager                                │
│              (ZMQ Coordinator - manager.py)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   REQ/REP    │  │    PUB       │  │    PULL      │          │
│  │  Port 5557   │  │  Port 5555   │  │  Port 5556   │          │
│  │  (Clients)   │  │  (Commands)  │  │  (Data)      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────┬────────────────┬────────────────┬───────────────────┘
          │                │                │
          │                ▼                │
          │         ┌──────────────┐        │
          │         │   ARTIQ      │        │
          │         │   Worker     │        │
          │         │ (experiments)│        │
          │         └──────────────┘        │
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     HARDWARE LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │     DC       │  │     DDS      │  │     TTL      │          │
│  │  (Zotino)    │  │  (Urukul)    │  │  (Camera)    │          │
│  │  Endcaps     │  │   Raman      │  │   Trigger    │          │
│  │ Compensation │  │   Cooling    │  │    PMT       │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DATA LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │     H5       │  │    JPG       │  │    JSON      │          │
│  │  (ARTIQ)     │  │  (Camera)    │  │ (Analysis)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### ControlManager
Central coordinator that manages all system communication through ZMQ sockets.

### ARTIQ Worker
Handles hardware control via ARTIQ framework (DACs, DDS, TTL).

### LabVIEW Interface
TCP-based communication with LabVIEW SMILE for RF, piezo, and toggles.

### Camera Server
Image acquisition and processing with real-time streaming.

### Two-Phase Optimizer
Bayesian optimization using TuRBO (Phase I) and MOBO (Phase II).

## Port Assignments

| Port | Protocol | Pattern | Purpose |
|------|----------|---------|---------|
| 5555 | ZMQ | PUB/SUB | Command distribution |
| 5556 | ZMQ | PUSH/PULL | Data/telemetry collection |
| 5557 | ZMQ | REQ/REP | Client requests/responses |
| 5558 | TCP | Raw Socket | Camera control & streaming |
| 5559 | TCP | JSON Lines | LabVIEW SMILE control |
| 5560 | TCP | JSON Lines | Telemetry from instruments |
| 5000 | HTTP | REST/SSE | Web interface & streaming |
