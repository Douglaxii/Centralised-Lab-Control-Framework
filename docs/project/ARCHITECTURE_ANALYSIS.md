# Architecture Analysis: Ion Trap Control System

**Date:** 2026-02-02  
**Scope:** ndscan + MLS/ARTIQ integration, scalability, and data flow

---

## Executive Summary

The system demonstrates a **well-structured multi-layer architecture** with clear separation between:
- **Hardware abstraction** (ARTIQ fragments)
- **Experiment logic** (ndscan experiments)
- **Management layer** (MLS server with ZMQ communication)
- **Applet interface** (Flask-based GUI)

**Key strengths:** Fragment-based composition, ZMQ-based distributed communication, real-time plotting with incremental updates.

**Key areas for improvement:** Parameter validation, error propagation, async patterns, and dataset consolidation.

---

## 1. Current Architecture Overview

### 1.1 Layer Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                        FLASK APPLETS                            │
│         (cam_sweep, sim_calibration, auto_compensation)         │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP (port 5000)
┌──────────────────────────────▼──────────────────────────────────┐
│                         MANAGER                                 │
│    - ZMQ REQ/REP (port 5557) for applet commands                │
│    - ZMQ PUB/SUB (port 5555) to ARTIQ                           │
│    - ZMQ PULL (port 5556) from ARTIQ                            │
│    - File watcher for LabVIEW telemetry                           │
│    - Flask server for camera control                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │ ZMQ (PUB→5555, PULL←5556)
┌──────────────────────────────▼──────────────────────────────────┐
│                      ARTIQ MASTER                               │
│    - artiq_worker.py (MainWorker ExpFragment)                   │
│    - Device database (device_db.py)                               │
│    - Repository experiments                                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ PCIe/Network
┌──────────────────────────────▼──────────────────────────────────┐
│                     KASLI FPGA CORE                             │
│    - TTL I/O (ttl0_counter, ttl4, camera_trigger)               │
│    - DDS (urukul0_ch0=Axial, urukul0_ch1=Radial)                │
│    - Core device                                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ TTL/USB/TCP
┌──────────────────────────────▼──────────────────────────────────┐
│                      PERIPHERALS                                │
│    - Hamamatsu Camera (TCP port 5558)                           │
│    - PMT Counter                                                  │
│    - LabVIEW (file-based telemetry)                               │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Fragment Hierarchy

```
Fragment (ndscan)
└── ExpFragment (ndscan)
    └── BaseExperiment (ndscan.experiment.entry_point)
        └── MainWorker (MLS/artiq)
            ├── Compensation (fragment)
            ├── EndCaps (fragment)
            ├── RamanCooling (fragment)
            ├── SecularSweep (fragment)
            └── Camera (fragment)
```

### 1.3 Data Flow Paths

| Path | Direction | Mechanism | Latency |
|------|-----------|-----------|---------|
| Command | Applet → Manager → ARTIQ | ZMQ REQ/REP + PUB/SUB | ~10-50ms |
| Results | ARTIQ → Manager → Applet | ZMQ PULL + HTTP | ~10-50ms |
| Live Plot | ARTIQ → Applets | ARTIQ datasets ( broadcast) | ~100ms |
| Camera Data | Camera → Flask → Manager | HTTP + File I/O | ~1s |
| LabVIEW Data | Files → Manager | File polling | ~1-5s |

---

## 2. Detailed Component Analysis

### 2.1 ndscan Framework

#### 2.1.1 Fragment System

**Strengths:**
- Clean composition via `setattr_fragment()`
- Lifecycle hooks: `build_fragment()`, `host_setup()`, `device_setup()`
- Parameter scoping with `fqn` (fully qualified name)
- Automatic result channel registration

**Key Classes:**
- `Fragment`: Base class with parameter/result registry
- `ExpFragment`: Runnable fragment with scan support
- `FragmentScanExperiment`: Full scanning with UI integration

**Pattern Example:**
```python
class SecularSweep(Fragment):
    def build_fragment(self):
        self.setattr_param("freq", FloatParam, "Frequency", default=400*kHz)
        self.setattr_param("dds_choice", EnumParam, "DDS", 
                          options={"axial": "axial", "radial": "radial"})
    
    def host_setup(self):
        # Host-side device selection
        self.dds = self.urukul0_ch0 if self.dds_choice.get() == "axial" else self.urukul0_ch1
    
    @kernel
    def device_setup(self):
        # Kernel-side initialization
        self.dds.init()
```

#### 2.1.2 Scan System

**Components:**
- `ScanRunner`: Executes scan loops with retry logic
- `ScanGenerator`: Linear, Refining, List generators
- `ScanSpec`: Complete scan description

**RTIO Underflow Handling:**
```python
# From scan_runner.py - automatic retry with backoff
while True:
    try:
        self._run_scan_core(scan_spec)
    except RTIOUnderflow:
        self.num_underflows += 1
        delay_mu(...)
```

#### 2.1.3 Result Channels

**Types:**
- `FloatChannel`: Scalar float results
- `IntChannel`: Scalar integer results
- `OpaqueChannel`: String/blob data

**Storage:**
- ARTIQ datasets for live plotting
- HDF5 files for persistence
- Broadcast to all connected applets

### 2.2 MLS/ARTIQ Integration

#### 2.2.1 Communication Protocol

**Message Format:**
```python
{
    "category": "PMT_MEASURE" | "CAM_SWEEP" | "SECULAR_SWEEP" | ...,
    "timestamp": <ISO8601>,
    "payload": { ... },
    "exp_id": <optional experiment ID>,
    "applet_id": <source applet>
}
```

**Socket Pattern:**
- **PUB/SUB (5555):** Manager publishes to ARTIQ (one-way broadcast)
- **PULL (5556):** Manager receives from ARTIQ (one-way results)
- **REQ/REP (5557):** Applets request from Manager (synchronous)

#### 2.2.2 Experiment Context

**Thread-local experiment tracking:**
```python
# core/experiment_context.py
class ExperimentContext:
    exp_id: str      # Unique experiment identifier
    applet_id: str   # Source applet
    priority: int    # Execution priority
    created_at: datetime
```

**Usage pattern:**
```python
with experiment_context(applet_id="cam_sweep", priority=1):
    result = manager.send_command_to_artiq(...)
```

### 2.3 Camera Integration

#### 2.3.1 Dual Mode Operation

**Infinity Mode:**
- Continuous circular buffer capture
- Used for: Live view, ion position tracking
- Frame rate: Maximum hardware rate
- ROI: User-defined or full sensor

**Recording Mode:**
- Fixed N frames with DCIMG + JPG output
- Used for: Sweeps, calibration, analysis
- Triggered: TTL pulse per frame
- ROI: Calculated from ion position

#### 2.3.2 Trigger Synchronization

```python
@kernel
def run_point(self):
    # Hardware-synchronized camera trigger
    with parallel:
        self.dds.cfg_sw(True)
        self.pmt.gate_rising(self.on_time.get())
        self.cam.pulse(10*us)  # Camera trigger
```

---

## 3. Scalability Assessment

### 3.1 Current Bottlenecks

| Component | Limitation | Impact |
|-----------|------------|--------|
| ZMQ PULL socket | Single consumer thread | Throughput capped at ~1k msg/sec |
| File-based LabVIEW | Polling interval (1-5s) | Stale data for real-time decisions |
| Camera HTTP | Synchronous requests | Blocking during mode switches |
| HDF5 Result Loading | Full file read | Slow for large datasets |
| Fragment Rebuild | Per-experiment initialization | ~500ms overhead per scan |

### 3.2 Scalability Improvements

#### 3.2.1 Async Communication Layer

**Current (Synchronous):**
```python
# Blocking ZMQ request-response
self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
self.pub_socket.send_json(cmd)
result = self.pull_socket.recv_json()  # Blocks
```

**Improved (Async with Futures):**
```python
# Non-blocking with asyncio
async def send_command(cmd):
    future = asyncio.Future()
    pending_commands[cmd["id"]] = future
    await pub_socket.send_json(cmd)
    return await asyncio.wait_for(future, timeout=30)
```

#### 3.2.2 Connection Pooling

**Current:** New HTTP connection per camera request
**Improved:** Keep-alive session with retry logic

```python
class CameraClient:
    def __init__(self):
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10)
        self.session.mount('http://', adapter)
```

#### 3.2.3 Result Streaming

**Current:** Complete datasets broadcast after scan
**Improved:** Chunked streaming for real-time updates

```python
# Incremental result channel
class StreamingResultChannel:
    def push(self, value):
        super().push(value)
        # Broadcast immediately, not batched
        self._broadcast_incremental(value)
```

---

## 4. Data Flow Optimizations

### 4.1 LabVIEW Integration

**Current:** File-based telemetry with polling
```
LabVIEW → File (1-5s interval) → Manager reads → Flask displays
```

**Optimized:** Direct TCP socket or shared memory
```
LabVIEW → TCP socket → Manager → Flask (real-time)
```

**Alternative:** ZeroMQ PUB from LabVIEW
```
LabVIEW (PUB) → Manager (SUB) → Flask (WebSocket)
```

### 4.2 Dataset Consolidation

**Current:** Multiple file formats (HDF5, DCIMG, CSV, JSON)

**Unified Schema:**
```
experiment_YYYY-MM-DD_HHMMSS/
├── metadata.json          # Experiment parameters
├── data.h5               # ARTIQ scan results
├── camera/
│   ├── frames.dcimg      # Raw camera data
│   └── analysis.json     # Camera analysis results
├── labview/
│   └── telemetry.h5      # Consolidated LabVIEW data
└── analysis/
    └── fits.json         # Fit results (Lorentzian, etc.)
```

### 4.3 Result Caching

**Current:** Reload from HDF5 on every access
**Improved:** LRU cache with cache invalidation

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def load_result(exp_id: str) -> dict:
    return load_hdf5_file(f"{exp_id}/data.h5")
```

---

## 5. Specific Improvement Recommendations

### 5.1 High Priority

#### 5.1.1 Add Parameter Validation

**Current:** Parameters validated at kernel runtime
**Risk:** Late failure, wasted scan time

**Recommendation:** Add schema validation in `build_fragment()`

```python
class ValidatedFragment(Fragment):
    def build_fragment(self):
        self.setattr_param("freq", FloatParam, "Frequency",
                          default=400*kHz,
                          validators=[
                              RangeValidator(100*kHz, 1000*kHz),
                              StepValidator(1*kHz)
                          ])
```

#### 5.1.2 Improve Error Propagation

**Current:** Errors logged but not propagated to applets
**Risk:** Silent failures, stuck experiments

**Recommendation:** Standardized error response format

```python
{
    "category": "ERROR",
    "error_type": "RTIO_UNDERFLOW" | "HARDWARE_TIMEOUT" | "VALIDATION_ERROR",
    "message": "Human-readable description",
    "recoverable": true/false,
    "suggested_action": "retry" | "abort" | "check_hardware"
}
```

#### 5.1.3 Implement Circuit Breaker

For hardware errors that could damage equipment:

```python
class SafetyMonitor:
    def __init__(self):
        self.error_counts = defaultdict(int)
        self.circuit_state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def record_error(self, error_type):
        self.error_counts[error_type] += 1
        if self.error_counts[error_type] > THRESHOLD:
            self.trip_circuit(error_type)
```

### 5.2 Medium Priority

#### 5.2.1 Fragment Hot-Reload

**Current:** Full ARTIQ restart to update fragments
**Improved:** Dynamic fragment reloading

```python
class HotReloader:
    def reload_fragment(self, fragment_name):
        # Unload old fragment
        # Reload module from disk
        # Rebuild fragment tree
        # Preserve device state
```

#### 5.2.2 Scan Resumption

**Current:** Failed scans restart from beginning
**Improved:** Checkpoint-based resumption

```python
class ResumableScan:
    def __init__(self):
        self.checkpoint_file = ".scan_checkpoint.json"
    
    def run(self):
        if self.checkpoint_exists():
            self.resume_from_checkpoint()
        else:
            self.run_from_start()
```

#### 5.2.3 Parallel Scan Execution

For independent parameter sweeps:

```python
class ParallelScanRunner:
    def run_parallel(self, scans: List[ScanSpec]):
        # Partition scan points across available hardware
        # Use thread pool for host-side operations
        # Merge results
```

### 5.3 Low Priority

#### 5.3.1 WebSocket for Real-time Updates

Replace HTTP polling with WebSocket push:

```python
# Flask-SocketIO integration
@socketio.on('subscribe')
def handle_subscription(exp_id):
    join_room(exp_id)
    
@socketio.on('scan_update')
def broadcast_update(exp_id, data):
    emit('update', data, room=exp_id)
```

#### 5.3.2 Result Database

SQLite/PostgreSQL backend for experiment history:

```python
class ExperimentDatabase:
    def store_result(self, exp_id: str, metadata: dict):
        # Indexed storage for fast queries
        # Full-text search on parameter descriptions
        # Tag-based organization
```

---

## 6. Implementation Roadmap

### Phase 1: Stability (Weeks 1-2)
1. Add comprehensive error response handling
2. Implement parameter validation layer
3. Add health check endpoints

### Phase 2: Performance (Weeks 3-4)
1. Implement async communication layer
2. Add result caching
3. Optimize camera mode switching

### Phase 3: Features (Weeks 5-6)
1. Scan checkpoint/resumption
2. Fragment hot-reload
3. Unified data schema

### Phase 4: Scale (Weeks 7-8)
1. Parallel scan execution
2. WebSocket integration
3. Result database migration

---

## 7. Code Quality Observations

### 7.1 Positive Patterns

1. **Fragment composition:** Clean, testable units
2. **ZMQ architecture:** Decoupled, language-agnostic
3. **Type hints:** Good use of Python typing
4. **Docstrings:** Comprehensive documentation
5. **Error handling:** try/except with logging

### 7.2 Areas for Improvement

1. **Inconsistent naming:** `cam` vs `camera`, `pmt` vs `ttl0_counter`
2. **Magic numbers:** Hardcoded timeouts, ports scattered in code
3. **Duplicate logic:** Similar sweep logic in multiple files
4. **No unit tests:** No test coverage for critical paths
5. **Configuration scattered:** Settings in multiple JSON files

### 7.3 Suggested Refactoring

```python
# Centralize configuration
# config/schema.py
class SystemConfig(BaseModel):
    zmq: ZMQConfig
    camera: CameraConfig
    hardware: HardwareConfig
    
    @validator('zmq')
    def validate_ports(cls, v):
        assert v.pub_port != v.pull_port
        return v

# Dependency injection for testability
# fragments/base.py
class InjectableFragment(Fragment):
    def __init__(self, device_provider=None):
        self._device_provider = device_provider or DefaultDeviceProvider()
```

---

## 8. Conclusion

The current architecture provides a **solid foundation** for ion trap control with:
- Clean separation of concerns
- Modular hardware abstraction
- Real-time visualization capabilities

**Key immediate actions:**
1. Implement error response standardization
2. Add parameter validation
3. Create unified data schema
4. Add basic test coverage

**Long-term vision:**
- Async-first communication
- Real-time streaming results
- Horizontal scaling for multi-trap setups

The system is well-positioned for incremental improvements without major architectural changes.
