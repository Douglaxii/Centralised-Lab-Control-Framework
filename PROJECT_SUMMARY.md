# Mixed-Species Loading System (MLS) - Complete Project Summary

## Overview

MLS is a **distributed control system for automated mixed-species ion trap experiments**, specifically designed for loading and manipulating Beryllium (Be+) and Hydrogen-Deuteride (HD+) ions in a Paul trap. The system features a sophisticated **Two-Phase Bayesian Optimization** approach for automated ion loading optimization.

---

## System Architecture

### Smart Master Pattern

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                              │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐     │
│   │  Main Flask  │  │ Applet Flask │  │   Direct ZMQ/CLI     │     │
│   │  (Port 5000) │  │ (Port 5051)  │  │                      │     │
│   └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘     │
└──────────┼─────────────────┼─────────────────────┼─────────────────┘
           │                 │                     │
           └─────────────────┴─────────────────────┘
                               │
                               ▼ ZMQ REQ/REP (Port 5557)
┌─────────────────────────────────────────────────────────────────────┐
│                    CONTROL MANAGER (Smart Master)                    │
│                              Port 5557                               │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              REQUEST HANDLERS                                │   │
│   │  SET | GET | SWEEP | OPTIMIZE_* | CAMERA_* | STATUS         │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              TWO-PHASE OPTIMIZER                             │   │
│   │         (TuRBO Phase I → MOBO Phase II)                      │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              HARDWARE INTERFACES                             │   │
│   │  Camera | LabVIEW | ARTIQ | Kill Switches                   │   │
│   └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   ARTIQ      │    │   LabVIEW    │    │   Camera     │
│   Worker     │    │  /SMILE      │    │   Server     │
│  (ZMQ 5555)  │    │  (TCP 5559)  │    │  (TCP 5558)  │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## Directory Structure

```
MLS/
├── scripts/              # Operational scripts
│   ├── windows/          # Windows batch files (.bat)
│   ├── linux/            # Linux shell scripts (.sh)
│   ├── setup/            # Setup and installation
│   ├── deployment/       # Deployment scripts
│   ├── maintenance/      # Maintenance utilities
│   └── switch_env.py     # Environment switcher
├── src/                  # All Python source code
│   ├── core/             # Core utilities
│   ├── hardware/         # Hardware interfaces
│   ├── server/           # Server components
│   ├── frontend/         # User interfaces
│   ├── analysis/         # Analysis tools
│   └── optimizer/        # Bayesian optimization
├── config/               # Configuration files
├── docs/                 # Documentation
├── tests/                # Test suite
├── tools/                # PowerShell modules & utilities
├── data/                 # Data storage
└── logs/                 # Log files
```

---

## Core Modules

### 1. Launcher & Entry Points

| File | Location | Purpose |
|------|----------|---------|
| `launcher.py` | `src/` | **Unified Service Launcher** - Starts all MLS services (Manager, Flask Dashboard, Applet Server, Optimizer Server). Provides service management, status monitoring, and automatic restart capabilities. |
| `__main__.py` | `src/` | Package entry point - allows `python -m src.launcher` |
| `switch_env.py` | `scripts/` | **Environment Switcher** - Quickly switch between development (laptop) and production (manager PC) environments by modifying config.yaml |

### 2. Core Utilities (`src/core/`)

| File | Purpose |
|------|---------|
| `config/config.py` | **Configuration Manager** - Singleton pattern configuration loader. Supports unified YAML config with multiple profiles (development/production). Loads from `config/config.yaml` with environment-based overrides. |
| `logging/logger.py` | **Logging Utilities** - Structured logging setup with rotation. Creates component-specific loggers with consistent formatting. |
| `exceptions/exceptions.py` | **Custom Exceptions** - Defines MLS-specific exceptions (ConnectionError, SafetyError, ConfigurationError, etc.) |
| `utils/enums.py` | **Enumerations** - System states (SystemMode: MANUAL/AUTO/SAFE), AlgorithmState, CommandType, etc. |
| `utils/experiment.py` | **Experiment Tracking** - Tracks experiment state, results, and metadata. Provides `get_tracker()` singleton. |
| `utils/hardware_interface.py` | **Hardware Interface Utils** - Unit conversions (e.g., `u_rf_mv_to_U_RF_V` - converts SMILE mV to real RF voltage) |
| `utils/zmq_utils.py` | **ZMQ Helpers** - ZeroMQ communication utilities, message formatting, and socket management |

### 3. Server Components (`src/server/`)

#### 3.1 Control Manager (`src/server/manager/`)

| File | Purpose |
|------|---------|
| `manager.py` | **ControlManager** - The "Smart Master" central coordinator. Manages all hardware communication via ZMQ. Handles commands: SET, GET, SWEEP, OPTIMIZE_*, CAMERA_*, STATUS. Implements safety kill switches (Piezo: 10s max, E-Gun: 30s max). Manages system modes (MANUAL/AUTO/SAFE). |

**Key Classes in manager.py:**
- `ControlManager` - Main coordinator class
- `CameraInterface` - Direct TCP interface to camera server (bypasses Flask)
- `LabVIEWInterface` - TCP interface to LabVIEW/SMILE hardware
- `ARTIQInterface` - ZMQ interface to ARTIQ worker
- `KillSwitchManager` - Safety-critical automatic shutdown for time-limited outputs

#### 3.2 Communications (`src/server/comms/`)

| File | Purpose |
|------|---------|
| `data_server.py` | **Data Ingestion Server** - Receives telemetry data from LabVIEW (Wavemeter, SMILE) via TCP. Stores in circular buffers for real-time dashboard display. |
| `labview_interface.py` | **LabVIEW TCP Interface** - Handles communication with LabVIEW VIs (SMILE_Data_Sender.vi, Wavemeter_Data_Sender.vi) |

#### 3.3 Flask API (`src/server/api/`)

| File | Purpose |
|------|---------|
| `flask_server.py` | **Main Dashboard Server (Port 5000)** - Scientific web interface with:<br>- CCD Camera streaming with position overlays<br>- Control Cockpit (voltages, hardware toggles, lasers)<br>- Real-time Telemetry Stack (7 graphs)<br>- Turbo Algorithm Status & Safety Switch<br>- Kill switch management for Piezo (10s) and E-Gun (10s) |

**Key Classes in flask_server.py:**
- `KillSwitchManager` - Flask-level safety enforcement
- `TelemetryBuffer` - Circular buffers for real-time data
- `CameraStream` - MJPEG streaming with ion position overlays

### 4. Hardware Interfaces (`src/hardware/`)

#### 4.1 ARTIQ Integration (`src/hardware/artiq/`)

ARTIQ (Advanced Real-Time Infrastructure for Quantum physics) controls pulse sequencing, DC electrodes, and cooling lasers.

| File | Purpose |
|------|---------|
| `Artiq_Worker.py` | **ZMQ Worker (Standalone Experiment)** - Long-running ARTIQ experiment that receives commands via ZMQ PUB/SUB (port 5555) and sends data via PUSH/PULL (port 5556). Runs continuously on ARTIQ hardware until terminated. |
| `ec.py` | **Endcaps Fragment** - Controls endcap electrodes (EC1, EC2) for axial confinement |
| `comp.py` | **Compensation Fragment** - Controls compensation electrodes (comp_h, comp_v) for ion position correction |
| `dds_controller.py` | **DDS Controller** - Controls Direct Digital Synthesis boards for RF signals |
| `raman_control.py` | **Raman Control** - Controls Raman laser pulses for ion manipulation |
| `sweeping.py` | **Sweeping Fragment** - Performs frequency sweeps for secular spectroscopy |
| `pmt_counter.py` | **PMT Counter** - Photon-counting PMT (PhotoMultiplier Tube) measurements |
| `camera_trigger.py` | **Camera Trigger** - TTL trigger generation for camera synchronization |
| `experiments/` | Standalone experiments: `pmt_measure_exp.py`, `secular_sweep_exp.py`, `set_dc_exp.py`, `emergency_zero_exp.py` |
| `utils/` | Utilities: `experiment_submitter.py`, `config_loader.py`, `async_comm.py` |

#### 4.2 Camera System (`src/hardware/camera/`)

Optimized for **Intel Core Ultra 9 + NVIDIA Quadro P400**.

| File | Purpose |
|------|---------|
| `camera_server.py` | **Camera TCP Server (Port 5558)** - Receives commands via TCP. Handles: START (single recording), START_INF (infinite capture with auto-cleanup), STOP, CLEAR_FRAMES, STATUS. |
| `camera_logic.py` | **Camera Logic** - High-level camera control abstraction. Manages DCIMG recording and JPG capture modes. |
| `camera_recording.py` | **Recording Backend** - Low-level Hamamatsu CCD camera control using DCAM-API. Handles exposure, triggering, and frame capture. |
| `image_handler.py` | **Image Processing** - Optimized ion detection with:<br>- Multi-scale peak detection (Intel MKL/NumPy)<br>- GPU acceleration (OpenCV CUDA/OpenCL)<br>- 2D Gaussian fitting<br>- Ion validation (SNR, circularity)<br>- Compact visualization |
| `dcam.py`, `dcamapi4.py`, `dcamcon.py` | Hamamatsu DCAM-API Python bindings |
| `utils/` | Camera utilities: exposure calculation, live capturing, trigger handling |

**Data Flow:**
```
Camera (Hamamatsu CCD) → DCIMG file → JPG frames → image_handler → ion_data (JSON)
                        ↘ jpg_frames/     ↘ jpg_frames_labelled/
```

#### 4.3 LabVIEW Interface (`src/hardware/labview/`)

| File | Purpose |
|------|---------|
| `mock_labview_sender.py` | **Mock LabVIEW** - Simulates Wavemeter.vi and SMILE.vi for testing without actual LabVIEW. Sends mock telemetry data to the data server. |
| `vi/SMILE_Data_Sender.vi` | LabVIEW VI for SMILE hardware control (oven, piezo, e-gun, RF voltage) |
| `vi/Wavemeter_Data_Sender.vi` | LabVIEW VI for wavemeter data (laser frequencies) |

### 5. Optimizer (`src/optimizer/`)

Two-Phase Bayesian Optimization for automated ion loading.

#### Phase I: Component-Level (TuRBO)
- **Goal**: Optimize individual experimental stages
- **Algorithm**: TuRBO-1 (Trust Region Bayesian Optimization)
- **Stages**: Be+ Loading → Be+ Ejection → HD+ Loading

#### Phase II: System-Level (MOBO)
- **Goal**: Multi-objective optimization balancing yield vs speed
- **Algorithm**: MOBO with qNEHVI (Noisy Expected Hypervolume Improvement)
- **Objectives**: Maximize HD+ count, Minimize cycle time
- **Constraints**: Be+ residual ≤ threshold, Pressure ≤ limit

| File | Purpose |
|------|---------|
| `two_phase_controller.py` | **Two-Phase Controller** - Orchestrates Phase I → Phase II transition. Implements ASK-TELL interface: controller provides parameters (ASK) → hardware executes → controller registers results (TELL). Handles warm start (Phase I data seeds Phase II). |
| `turbo.py` | **TuRBO Optimizer** - Trust Region Bayesian Optimization for Phase I. Maintains local trust regions that expand on success and shrink on failure. Better scaling for high dimensions (>20 params). |
| `mobo.py` | **MOBO Optimizer** - Multi-Objective Bayesian Optimization for Phase II. Uses qNEHVI with constraints. Manages Pareto front for trade-off visualization. |
| `parameters.py` | **Parameter Space** - Defines parameter bounds and constraints. Uses Absolute Time Windows (start_time, duration) instead of sequential delays to prevent the "Domino Effect". |
| `objectives.py` | **Objectives & Constraints** - Defines optimization objectives (yield, speed) and constraints (purity, stability). Supports dynamic objective/constraint addition. |
| `storage.py` | **Profile Storage** - Saves/loads optimization profiles (best parameters for different configurations) |

#### Flask Optimizer UI (`src/optimizer/flask_optimizer/`)

| File | Purpose |
|------|---------|
| `app.py` | **Optimizer Flask Server (Port 5050)** - Web interface for Bayesian optimization. Provides dashboard for monitoring optimization progress, viewing Pareto fronts, and managing profiles. |
| `launcher.py` | Optimizer service launcher |
| `static/js/gantt_chart.js` | Gantt chart visualization for timing parameters |
| `templates/` | HTML templates: dashboard, history, parameters, profiles |

### 6. Frontend / Applets (`src/frontend/applet/`)

Experiment applets for specific calibration and measurement tasks.

| File | Purpose |
|------|---------|
| `app.py` | **Applet Flask Server (Port 5051)** - Web interface for running experiments |
| `launcher.py` | Applet service launcher |
| `base.py` | **Base Experiment Class** - Abstract base class for all experiments. Provides manager communication, data saving, and status tracking. |
| `auto_compensation.py` | **Auto Compensation** - Automatic compensation voltage calibration:<br>1. Set u_rf=200V, record reference position<br>2. Set u_rf=100V, calibrate comp_h<br>3. Scan comp_v 30-50V<br>4. Fit cubic, find optimal comp_v from f'(x)=0 |
| `cam_sweep.py` | **Camera Sweep** - Secular frequency sweep with synchronized camera:<br>1. Detect ion position from infinity mode<br>2. Configure ROI-centered recording<br>3. Run ARTIQ sweep with TTL triggers<br>4. Collect PMT + position data<br>5. Fit Lorentzian to PMT, sig_x, R_y |
| `trap_eigenmode.py` | **Trap Eigenmode** - Calculate normal modes of trapped ions:<br>- Inputs: u_rf, ec1, ec2, masses<br>- Outputs: Eigenfrequencies, eigenvectors, equilibrium positions<br>- Uses `trap_sim_asy` physics module |
| `sim_calibration.py` | **Simulation Calibration** - Calibrate simulation parameters against measured data |
| `run_*.py` | Entry point scripts for each experiment |
| `templates/index.html` | Applet web interface |

### 7. Analysis Tools (`src/analysis/`)

| File | Purpose |
|------|---------|
| `secular_comparison.py` | **Secular Frequency Comparison** - Automated comparison of measured secular frequencies with theoretical predictions. Sets trap parameters, calculates theoretical frequencies, conducts secular scan ±20V, analyzes Lorentzian fits. |
| `eigenmodes/trap_sim_asy.py` | **Trap Simulation (Asymmetric)** - Physics simulation for ion trap eigenmodes with asymmetric endcap voltages. Calculates equilibrium positions, normal modes, and eigenfrequencies for mixed-species ion chains. |
| `eigenmodes/trap_sim.py` | **Trap Simulation (Symmetric)** - Simplified symmetric version |
| `eigenmodes/fit_Kappa_Chi_URF.py` | **Fit Kappa & Chi** - Fit trap efficiency parameters (kappa, chi) and RF voltage |
| `eigenmodes/sec_urf.py` | **Secular URF** - Secular frequency calculations |

### 8. Scripts (`scripts/`)

#### 8.1 Windows Scripts (`scripts/windows/`)

| File | Purpose |
|------|---------|
| `start_all.bat` | Start all services (Manager, Dashboard, Applet, Optimizer) |
| `start_manager.bat` | Start only Control Manager |
| `start_dashboard.bat` | Start only Main Flask Dashboard (Port 5000) |
| `start_applet.bat` | Start only Applet Flask Server (Port 5051) |
| `start_optimizer.bat` | Start only Optimizer Flask Server (Port 5050) |
| `run_auto_compensation.bat` | Run auto compensation experiment |
| `run_experiment.bat` | Run generic experiment |
| `run_trap_eigenmode.bat` | Run trap eigenmode calculation |

#### 8.2 Linux Scripts (`scripts/linux/`)

Same as Windows but with `.sh` extension for Linux/Mac environments.

#### 8.3 Setup Scripts (`scripts/setup/`)

| File | Purpose |
|------|---------|
| `setup_conda.bat` / `setup_conda.py` | Conda environment setup |
| `validate_setup.py` | Validate installation and dependencies |
| `environment.yml` | Conda environment specification |
| `setup_manager_pc.py` | Manager PC setup (creates E:/data directories) |
| `setup_data_directory.bat` | Create data directory structure |
| `start_servers.bat` | Legacy server startup |

#### 8.4 Maintenance (`scripts/maintenance/`)

| File | Purpose |
|------|---------|
| `cleanup_script.ps1` | Log cleanup and maintenance |

### 9. Tools (`tools/`)

| File | Purpose |
|------|---------|
| `check_server.py` | **Server Diagnostic** - Check Python version, YAML configuration, and all dependencies (OpenCV, NumPy, SciPy, PyYAML, PyZMQ, Flask, etc.) |
| `ControlManager.psm1` | PowerShell module for MLS management |
| `Setup-LabControl.ps1` | PowerShell setup script |

### 10. Configuration (`config/`)

| File | Purpose |
|------|---------|
| `config.yaml` | **Main Configuration** - Unified config with profiles for development/production. Contains all system settings. |
| `base.yaml` | Base configuration (fallback) |
| `hardware.yaml` | Hardware-specific settings |
| `services.yaml` | Service orchestration config |
| `README.md` | Configuration guide |

### 11. Tests (`tests/`)

| File | Purpose |
|------|---------|
| `test_connections.py` | **Connection Tests** - Test all hardware connections (ARTIQ, LabVIEW, Camera, Manager) |
| `test_config_example.yaml` | Example test configuration |

---

## Communication Protocol

### ZMQ Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 5555 | PUB/SUB | ARTIQ commands (Manager → ARTIQ) |
| 5556 | PUSH/PULL | ARTIQ data (ARTIQ → Manager) |
| 5557 | REQ/REP | Control Manager (main API) |
| 5558 | TCP | Camera Server |
| 5559 | TCP | LabVIEW/SMILE interface |

### HTTP Ports

| Port | Service | Description |
|------|---------|-------------|
| 5000 | Main Dashboard | Camera, telemetry, controls |
| 5050 | Optimizer UI | Bayesian optimization interface |
| 5051 | Applet Server | Experiment applets |

---

## Data Flow

### Image Data Flow
```
Hamamatsu CCD Camera → DCIMG file → camera_logic → JPG frames
                                      ↓
                              image_handler (ion detection)
                                      ↓
                    ┌─────────────────┼─────────────────┐
                    ↓                 ↓                 ↓
            jpg_frames/    jpg_frames_labelled/    ion_data/ (JSON)
```

### Telemetry Data Flow
```
LabVIEW VIs (Wavemeter, SMILE) → TCP 5559 → data_server.py
                                              ↓
                                    TelemetryBuffer (circular)
                                              ↓
                                    Flask Dashboard (real-time graphs)
```

### Optimization Data Flow
```
TwoPhaseController.ask() → Parameters → ARTIQ/hardware execution
                                              ↓
                                    Experiment results
                                              ↓
                         TwoPhaseController.tell(results) → Model update
```

---

## Safety Features

### Kill Switches (Multi-Level)

| Device | Time Limit | Enforced At |
|--------|------------|-------------|
| Piezo Output | 10 seconds | Flask, Manager, LabVIEW |
| E-Gun Output | 10 seconds (testing) | Flask, Manager, LabVIEW |

### System Modes

- **MANUAL**: Direct hardware control, no optimization
- **AUTO**: Automated optimization active
- **SAFE**: All outputs disabled, safe state

### Emergency Procedures

- `emergency_zero_exp.py` - ARTIQ experiment to zero all outputs
- Kill switch auto-shutdown on time limit exceeded
- Hardware-level protection in LabVIEW

---

## Key Algorithms

### 1. TuRBO (Trust Region Bayesian Optimization)

**Phase I optimization for individual components:**

```python
# Pseudocode
while not converged:
    # Adjust trust region
    if success_counter >= success_tolerance:
        length = min(length * 2, length_max)  # Expand
    elif failure_counter >= failure_tolerance:
        length = max(length / 2, length_min)  # Shrink
    
    # Fit GP within trust region
    gp.fit(X_trust_region, y_trust_region)
    
    # Optimize acquisition function
    x_next = maximize_ei(gp, trust_region_bounds)
    
    # Evaluate and update
    y_next = experiment(x_next)
    update_trust_region(y_next > best)
```

### 2. MOBO (Multi-Objective Bayesian Optimization)

**Phase II for system-level trade-offs:**

```python
# Pseudocode
while not converged:
    # Fit GP models for each objective
    for obj in objectives:
        gp_obj.fit(X, y_obj)
    
    # Compute qNEHVI (Noisy Expected Hypervolume Improvement)
    candidates = optimize_qnehvi(gp_models, pareto_front, ref_point)
    
    # Batch evaluation
    results = experiment_batch(candidates)
    
    # Update Pareto front
    for params, objs in zip(candidates, results):
        pareto_front.add(params, objs)
```

### 3. Ion Detection (Image Processing)

**Multi-scale peak detection with validation:**

```python
# Pseudocode
1. Background subtraction (adaptive thresholding)
2. Multi-scale LoG (Laplacian of Gaussian) filtering
3. Peak detection at multiple scales
4. 2D Gaussian fitting: I(x,y) = A * exp(-((x-x₀)²/2σₓ² + (y-y₀)²/2σᵧ²)) + B
5. Validation:
   - SNR check: A/σ_noise > threshold
   - Circularity check: σₓ/σᵧ ≈ 1
   - Size check: σ in valid range
```

---

## Usage Examples

### Start the System

```bash
# Option 1: Unified launcher
python -m src.launcher

# Option 2: Platform scripts
scripts\windows\start_all.bat    # Windows
./scripts/linux/start_all.sh     # Linux/Mac

# Option 3: Individual services
python -m src.server.manager.manager          # Manager only
python -m src.server.api.flask_server         # Dashboard only
```

### Run Experiments

```bash
# Auto compensation
python -m src.frontend.applet.auto_compensation
# or
scripts\windows\run_auto_compensation.bat

# Camera sweep with secular frequency
python -m src.frontend.applet.cam_sweep

# Trap eigenmode calculation
python -m src.frontend.applet.trap_eigenmode
```

### Switch Environment

```bash
# Show current environment
python scripts\switch_env.py

# Switch to development (laptop)
python scripts\switch_env.py dev

# Switch to production (manager PC)
python scripts\switch_env.py prod
```

### Use the Optimizer

```python
from src.optimizer import TwoPhaseController, Phase

# Initialize
controller = TwoPhaseController()
controller.start_phase(Phase.BE_LOADING_TURBO)

# Optimization loop
for i in range(max_iterations):
    # ASK: Get parameters
    params, metadata = controller.ask()
    
    # Run experiment with params
    result = run_experiment(params)
    
    # TELL: Register results
    controller.tell({
        "total_fluorescence": result["pmt_counts"],
        "cycle_time_ms": result["time"]
    })
```

---

## Hardware Requirements

### Manager PC
- **OS**: Windows 10/11
- **CPU**: Intel Core Ultra 9 (optimized for)
- **RAM**: 16GB+ recommended
- **GPU**: NVIDIA Quadro P400 (optional, for CUDA acceleration)
- **Storage**: SSD for data directory (E:/data)

### ARTIQ System
- **Hardware**: Kasli or similar FPGA board
- **Network**: Ethernet connection to Manager PC
- **Python**: ARTIQ environment with oitg.units

### Camera
- **Model**: Hamamatsu CCD (ORCA series)
- **Interface**: USB 3.0 or Camera Link
- **Software**: DCAM-API

### LabVIEW/SMILE
- **Software**: LabVIEW with SMILE framework
- **Hardware**: NI DAQ for analog outputs
- **Network**: TCP connection to Manager PC

---

## Dependencies

### Core
- Python 3.8+
- PyYAML - Configuration management
- PyZMQ - Distributed communication
- NumPy - Numerical computing
- SciPy - Optimization and fitting

### Web & Visualization
- Flask - Web servers
- Flask-CORS - Cross-origin requests
- OpenCV - Image processing
- Matplotlib - Plotting

### Bayesian Optimization
- BoTorch (optional) - For production MOBO
- GPyTorch (optional) - Gaussian processes
- scikit-optimize (fallback) - Basic BO

### Hardware
- dcam-api - Hamamatsu camera
- pyvisa - Lab instrument control

---

## Development Guidelines

### Code Organization
1. **Hardware code** goes in `src/hardware/`
2. **Experiment code** goes in `src/frontend/applet/`
3. **Analysis code** goes in `src/analysis/`
4. **Configuration** goes in `config/`
5. **Documentation** goes in `docs/`

### Adding New Experiments
1. Create class inheriting from `BaseExperiment` in `src/frontend/applet/`
2. Implement `run()` method
3. Add entry point script `run_<experiment>.py`
4. Add batch scripts in `scripts/windows/` and `scripts/linux/`

### Safety Checklist
- [ ] Kill switches tested for new hardware outputs
- [ ] Time limits configured appropriately
- [ ] Emergency stop procedures documented
- [ ] Hardware-level protection verified

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Camera not detected | Check DCAM-API installation, USB connection |
| ARTIQ connection failed | Verify ZMQ ports (5555, 5556) not blocked by firewall |
| LabVIEW not connecting | Check TCP port 5559, verify VI is running |
| Optimizer not converging | Check parameter bounds, increase initialization points |
| Image processing slow | Enable OpenCL/CUDA in OpenCV |

### Diagnostic Commands

```bash
# Check server configuration
python tools/check_server.py

# Test all connections
python tests/test_connections.py

# Check service status
python -m src.launcher --status

# View logs
tail -f logs/manager.log
tail -f logs/camera_server.log
```

---

## References

- **ARTIQ Documentation**: https://m-labs.hk/artiq/
- **DCAM-API Documentation**: Hamamatsu SDK
- **BoTorch**: https://botorch.org/ (Bayesian Optimization)
- **Ion Trap Physics**: See `docs/physics/`

---

**Version**: 2.0  
**Last Updated**: 2026-02-04  
**Authors**: MLS Development Team
