# Mixed-Species Loading System (MLS)

A distributed control system for automated mixed-species ion trap experiments, featuring Two-Phase Bayesian optimization for ion loading.

## Overview

MLS coordinates multiple hardware subsystems for loading and manipulating Beryllium (Be+) and Hydrogen-Deuteride (HD+) ions in a Paul trap:

- **ARTIQ** - Pulse sequencing, DC electrodes, cooling lasers
- **LabVIEW/SMILE** - High voltage RF, piezo, oven, e-gun
- **Camera** - Ion imaging and counting
- **Two-Phase Optimizer** - TuRBO (Phase I) + MOBO (Phase II) Bayesian optimization

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start all services
python launcher.py

# Access dashboards
http://localhost:5000    # Main control interface
```

## Architecture

### Smart Master Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                           │
│  ┌──────────────┐  ┌──────────────────────┐                    │
│  │  Main Flask  │  │   Direct ZMQ/CLI     │                    │
│  │  (Port 5000) │  │                      │                    │
│  └──────┬───────┘  └──────────┬───────────┘                    │
└─────────┼─────────────────────┼────────────────────────────────┘
          │                     │
          └─────────────────────┘
                    │
                    ▼ ZMQ REQ/REP (Port 5557)
┌─────────────────────────────────────────────────────────────────┐
│                    CONTROL MANAGER (Smart Master)                │
│                           Port 5557 (ZMQ)                        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              REQUEST HANDLERS                            │   │
│  │  SET | GET | SWEEP | OPTIMIZE_* | CAMERA_* | STATUS     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│  ┌─────────────────────────┼─────────────────────────────┐     │
│  │              TWO-PHASE OPTIMIZER                        │     │
│  │         (TuRBO Phase I → MOBO Phase II)                 │     │
│  └─────────────────────────┼─────────────────────────────┘     │
│                            │                                     │
│  ┌─────────────────────────┼─────────────────────────────┐     │
│  │              HARDWARE INTERFACES                        │     │
│  │  Camera | LabVIEW | ARTIQ | Kill Switches              │     │
│  └─────────────────────────┼─────────────────────────────┘     │
└────────────────────────────┼────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   ARTIQ      │    │   LabVIEW    │    │   Camera     │
│   Worker     │    │   /SMILE     │    │   Server     │
│  (ZMQ 5555)  │    │  (TCP 5559)  │    │  (TCP 5558)  │
└──────────────┘    └──────────────┘    └──────────────┘
```

### Key Design Principles

1. **ControlManager is Central** - All commands flow through ControlManager
2. **Two-Phase Optimization** - TuRBO for component tuning, MOBO for global optimization
3. **ASK-TELL Interface** - Clean separation between optimizer and hardware
4. **Warm Start** - Phase I data seeds Phase II for faster convergence
5. **Safety First** - Kill switches and mode-based protection

## Two-Phase Bayesian Optimization

### Phase I: Component-Level (TuRBO)

Rapidly optimize individual experimental stages using Trust Region Bayesian Optimization:

| Module | Goal | Algorithm | Metric |
|--------|------|-----------|--------|
| Be+ Loading | Maximize fluorescence | TuRBO-1 | Total PMT/Camera counts |
| Be+ Ejection | Minimize residual ions | TuRBO-1 | Residual fluorescence |
| HD+ Loading | Maximize yield | TuRBO-1 | Dark ion dip depth |

### Phase II: System-Level (MOBO)

Multi-objective optimization balancing yield vs speed with constraints:

- **Objective 1 (Yield)**: Maximize HD+ count
- **Objective 2 (Speed)**: Minimize total cycle time
- **Constraint 1 (Purity)**: Be+ residual ≤ threshold
- **Constraint 2 (Stability)**: Trap heating ≤ limit

### ASK-TELL Interface

```python
from server.optimizer import TwoPhaseController, Phase

# Initialize
controller = TwoPhaseController()
controller.start_phase(Phase.BE_LOADING_TURBO)

# Optimization loop
for i in range(max_iterations):
    # ASK: Get parameters
    params, metadata = controller.ask()
    
    # ... run experiment with params ...
    
    # TELL: Register results
    controller.tell({
        "total_fluorescence": measured_fluorescence,
        "cycle_time_ms": measured_time
    })
```

See [docs/BO.md](docs/BO.md) for complete architecture documentation.

## Project Structure

```
MLS/
├── launcher.py                 # Unified service launcher
├── requirements.txt            # Python dependencies
├── config/
│   └── settings.yaml          # System configuration
│
├── core/                      # Shared utilities
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── enums.py               # Enumerations and constants
│   ├── exceptions.py          # Custom exceptions
│   ├── experiment.py          # Experiment tracking
│   ├── logger.py              # Logging utilities
│   └── zmq_utils.py           # ZMQ helper functions
│
├── server/                    # Server components
│   ├── communications/
│   │   ├── manager.py         # ControlManager (main coordinator)
│   │   ├── labview_interface.py
│   │   └── data_server.py
│   │
│   ├── cam/                   # Camera system
│   │   ├── camera_server.py
│   │   ├── camera_logic.py
│   │   └── image_handler.py
│   │
│   ├── Flask/                 # Main web interface (Port 5000)
│   │   └── flask_server.py
│   │
│   ├── hardware/              # Hardware abstraction layer
│   │   └── __init__.py
│   │
│   └── optimizer/             # Bayesian optimization
│       ├── two_phase_controller.py  # Main controller
│       ├── turbo.py                 # TuRBO optimizer (Phase I)
│       ├── mobo.py                  # MOBO optimizer (Phase II)
│       ├── parameters.py            # Parameter spaces
│       ├── objectives.py            # Cost functions
│       └── storage.py               # Profile storage
│
├── artiq/                     # ARTIQ hardware control
│   ├── experiments/
│   └── fragments/
│
├── tests/                     # Test suite
│   ├── test_core.py
│   ├── test_optimizer.py
│   ├── test_two_phase_optimizer.py
│   └── ...
│
├── tools/                     # Diagnostic tools
│   └── control.ps1           # PowerShell control interface
│
└── docs/                      # Documentation
    ├── ARCHITECTURE.md
    ├── BO.md
    ├── API_REFERENCE.md
    └── ...
```

## Features

### Two-Phase Bayesian Optimization

Automated optimization for mixed-species ion loading:

1. **Phase I - Component Optimization**: TuRBO rapidly tunes individual stages
2. **Phase II - Global Optimization**: MOBO balances yield vs speed with constraints
3. **Warm Start**: Phase I results seed Phase II for faster convergence
4. **Pareto Front**: Multiple optimal configurations for different trade-offs

### Safety Systems

| Feature | Description |
|---------|-------------|
| Kill Switches | Auto-shutdown: Piezo (10s), E-gun (30s) |
| Mode Protection | Must be in AUTO mode for optimization |
| Pressure Monitor | Auto-kill if pressure > 5×10⁻⁹ mbar |
| Emergency Stop | Hardware and software STOP commands |

### Data Flow

1. **Experiment Control**: ControlManager → ARTIQ/LabVIEW → Hardware
2. **Telemetry**: LabVIEW → Files → ControlManager → Flask Charts
3. **Optimization**: ASK → Experiment → TELL → Update Model

## API Reference

### ControlManager Commands

```python
# Start Phase I optimization
{
    "action": "OPTIMIZE_START",
    "target_be_count": 1,
    "target_hd_present": True
}

# Get next parameters (ASK)
{"action": "OPTIMIZE_SUGGESTION"}

# Register results (TELL)
{
    "action": "OPTIMIZE_RESULT",
    "measurements": {
        "total_fluorescence": 100.0,
        "cycle_time_ms": 5000
    }
}

# Set parameters
{
    "action": "SET",
    "params": {"piezo": 2.5, "be_oven": 1}
}

# Get status
{"action": "OPTIMIZE_STATUS"}
```

See [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for complete API.

### PowerShell Control Interface

```powershell
# Import the control module
. .\tools\control.ps1

# Get system status
Get-SystemStatus

# Start optimization
Start-Optimization -targetBe 1 -targetHd $true

# Get parameters
$params = Get-Parameters

# Set parameters
Set-Parameter -name "piezo" -value 2.5

# Stop optimization
Stop-Optimization
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run optimizer tests only
python -m pytest tests/test_optimizer.py tests/test_two_phase_optimizer.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

## Configuration

Edit `config/settings.yaml`:

```yaml
network:
  master_ip: "134.99.120.40"
  cmd_port: 5555        # ControlManager commands
  data_port: 5556       # Worker feedback
  client_port: 5557     # Flask/Client requests
  camera_port: 5558     # Camera server

labview:
  host: "172.17.1.217"
  port: 5559
  
hardware:
  worker_defaults:
    u_rf_volts: 200.0
    piezo: 0.0

optimization:
  turbo_max_iterations: 50
  turbo_n_init: 10
  mobo_max_iterations: 30
  mobo_n_init: 5
```

## Safety ⚠️

**CRITICAL**: This system controls high-voltage hardware (up to 200V RF).

1. **Always** verify kill switches function before experiments
2. **Always** test emergency STOP procedures
3. **Never** disable safety features in production
4. **Always** monitor pressure when using e-gun or piezo

## Documentation

- [Bayesian Optimization Architecture](docs/BO.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API_REFERENCE.md)
- [Data Integration](docs/DATA_INTEGRATION.md)
- [LabVIEW Integration](docs/LABVIEW_INTEGRATION.md)

## Migration from Legacy SAASBO

The legacy SAASBO optimizer has been replaced with the Two-Phase optimizer:

| Legacy (SAASBO) | New (Two-Phase) |
|-----------------|-----------------|
| `OptimisationManager` | `TwoPhaseController` |
| `OptimisationPhase` | `Phase` |
| `get_suggestion()` | `ask()` |
| `register_result()` | `tell()` |
| Single-phase | Phase I (TuRBO) → Phase II (MOBO) |

## License

Proprietary - See LICENSE file

## Support

For issues or questions, contact the development team.
