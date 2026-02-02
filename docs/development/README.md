# Development Documentation

Resources for MLS developers and contributors.

## Contents

| Document | Description |
|----------|-------------|
| [Naming Conventions](naming_conventions.md) | Code style and naming standards |
| [Testing](testing.md) | Test procedures and calibration |

## Development Setup

### Prerequisites

- Python 3.11+
- Conda (recommended)
- VS Code (recommended)

### Environment Setup

```bash
# Create conda environment
conda env create -f environment.yml
conda activate mls

# Verify installation
python -c "import flask, zmq, numpy, cv2; print('All OK!')"
```

### VS Code Configuration

VS Code is the recommended IDE with these features:
- Full IntelliSense for Python with Pylance
- Auto-import suggestions
- Type checking enabled
- Black formatter (formats on save)
- Pylint linting
- MyPy type checking
- Multi-process debugging

## Project Structure

```
MLS/
├── artiq/                  # ARTIQ experiments and fragments
│   ├── experiments/
│   └── fragments/
├── server/                 # Python server components
│   ├── communications/     # ZMQ/TCP communication
│   ├── Flask/             # Web UI
│   ├── cam/               # Camera server
│   └── optimizer/         # Bayesian optimization
├── core/                   # Core utilities
├── tests/                  # Test suite
├── config/                 # Configuration files
└── docs/                   # Documentation
```

## Code Style

All code must follow the [Naming Conventions](naming_conventions.md):

- **Files:** `lowercase_with_underscores.py`
- **Classes:** `PascalCase`
- **Functions:** `snake_case`
- **Variables:** `snake_case`
- **Constants:** `UPPER_SNAKE_CASE`

## Testing

```bash
# Run all tests
pytest tests/

# Run calibration tests
python tests/calibration_test.py --all

# Test pressure safety
python tests/test_pressure_safety.py
```

## Debugging

### VS Code Launch Configurations

- **Python: Flask Server** - Debug Flask with auto-reload
- **Python: Manager** - Debug the manager
- **Python: Camera Server** - Debug camera server
- **Python: Launcher (All Services)** - Debug launcher
- **Launch All Services** - Compound config for all services

### Logging

Check logs in the `logs/` directory:
- `manager.log`
- `flask_server.log`
- `artiq_worker.log`
- `optimizer.log`

## Contributing

1. Follow naming conventions
2. Add tests for new features
3. Update documentation
4. Run linting before commit

```bash
# Format code
black .

# Lint code
pylint server/ core/
```
