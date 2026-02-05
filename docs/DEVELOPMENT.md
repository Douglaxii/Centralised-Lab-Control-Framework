# MLS Development Guide

Guide for developers contributing to the Multi-Ion Lab System.

---

## Table of Contents

1. [Setup](#setup)
2. [Naming Conventions](#naming-conventions)
3. [Code Style](#code-style)
4. [Testing](#testing)
5. [Project Structure](#project-structure)

---

## Setup

### Prerequisites

- Python 3.11+
- Conda (recommended)
- VS Code (recommended)

### Development Environment

```bash
# Create environment
conda env create -f scripts/setup/environment.yml
conda activate mls

# Install dev dependencies
pip install -r requirements-dev.txt
```

### VS Code Configuration

Recommended extensions:
- Python (Pylance)
- Black Formatter
- Pylint
- MyPy Type Checker

Debug configurations are in `.vscode/launch.json`:
- Python: Flask Server
- Python: Manager
- Python: Camera Server
- Python: Launcher (All Services)

---

## Naming Conventions

### Files

| Type | Convention | Example |
|------|------------|---------|
| Python files | `lowercase_with_underscores.py` | `camera_control.py` |
| Config files | `lowercase_with_underscores.yaml` | `settings.yaml` |
| Documentation | `UPPERCASE.md` or `lowercase.md` | `README.md`, `guide.md` |

### Python Code

| Element | Convention | Example |
|---------|------------|---------|
| Classes | `PascalCase` | `CameraController` |
| Functions | `snake_case` | `set_camera_params()` |
| Variables | `snake_case` | `exposure_time_ms` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_EXPOSURE_MS` |
| Private | `_leading_underscore` | `_internal_buffer` |

### Hardware Variables

| Device | Variable | Unit | Range |
|--------|----------|------|-------|
| Endcap 1 | `ec1_voltage` | V | -1 to 50 |
| Endcap 2 | `ec2_voltage` | V | -1 to 50 |
| Comp H | `comp_h_voltage` | V | -1 to 50 |
| Comp V | `comp_v_voltage` | V | -1 to 50 |
| RF (SMILE) | `u_rf_mv` | mV | 0-1400 |
| RF (Real) | `U_rf_v` | V | 0-200 |

---

## Code Style

### Imports

Order imports as follows:
1. Standard library
2. Third-party
3. Local application

```python
# 1. Standard library
import os
import json
from pathlib import Path

# 2. Third-party
import numpy as np
import zmq

# 3. Local application
from src.core.config import get_config
from src.hardware.camera import Camera
```

### Type Hints

Use type hints for function signatures:

```python
def calculate_voltage(
    u_rf_mv: float, 
    v_end: float
) -> tuple[float, float]:
    """Calculate DAC voltages."""
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def set_rf_voltage(self, voltage_v: float) -> bool:
    """Set RF voltage.
    
    Args:
        voltage_v: Target voltage in volts (0-200V)
        
    Returns:
        True if successful, False otherwise
        
    Raises:
        ValueError: If voltage out of range
    """
    pass
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test
pytest tests/test_camera.py -v

# Run with coverage
pytest --cov=src tests/
```

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── test_camera.py        # Camera tests
├── test_manager.py       # Manager tests
└── test_integration.py   # Integration tests
```

### Writing Tests

```python
import pytest
from src.hardware.camera import Camera

def test_camera_initialization():
    """Test camera initializes correctly."""
    camera = Camera()
    assert camera.is_connected is False

def test_exposure_bounds():
    """Test exposure time validation."""
    camera = Camera()
    
    with pytest.raises(ValueError):
        camera.set_exposure(0)  # Too low
    
    with pytest.raises(ValueError):
        camera.set_exposure(20000)  # Too high
```

---

## Project Structure

```
mls/
├── config/              # Configuration files
│   ├── config.yaml     # Main config
│   ├── hardware.yaml   # Hardware settings
│   └── environments/   # Environment configs
│
├── src/                # Source code
│   ├── core/           # Shared utilities
│   │   ├── config/     # Configuration management
│   │   ├── exceptions/ # Custom exceptions
│   │   ├── logging/    # Logging utilities
│   │   └── utils/      # General utilities
│   │
│   ├── server/         # Server components
│   │   ├── api/        # Flask REST API
│   │   ├── comms/      # Communication (ZMQ/TCP)
│   │   └── manager/    # ControlManager
│   │
│   ├── hardware/       # Hardware interfaces
│   │   └── camera/     # Camera system
│   │       ├── camera_server.py
│   │       ├── camera_client.py
│   │       └── image_handler.py
│   │
│   ├── optimizer/      # Bayesian optimization
│   │   ├── turbo.py
│   │   ├── mobo.py
│   │   └── flask_optimizer/
│   │
│   └── frontend/       # User interfaces
│       └── applet/     # Flask applets
│
├── artiq/              # ARTIQ experiments
│   ├── experiments/    # Experiment classes
│   └── fragments/      # Hardware fragments
│
├── scripts/            # Utility scripts
│   ├── setup/          # Setup scripts
│   └── windows/        # Windows batch files
│
├── tests/              # Test suite
├── logs/               # Log files
├── data/               # Data storage
└── docs/               # Documentation
```

---

## Contributing

1. **Follow naming conventions** - Check with `pylint`
2. **Add tests** - For new features
3. **Update docs** - Keep documentation current
4. **Run linting** - Before committing

```bash
# Format code
black .

# Lint code
pylint src/

# Type check
mypy src/
```

---

## Debugging

### Logging

Logs are in `logs/` directory:
- `manager.log` - ControlManager
- `flask.log` - Flask server
- `camera.log` - Camera server

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Import errors | Check PYTHONPATH includes project root |
| ZMQ errors | Verify ports not in use |
| Camera errors | Check USB connection |

---

*Last Updated: 2026-02-05*
