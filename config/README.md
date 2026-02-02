# MLS Configuration System

This directory contains the configuration files for the MLS (Multi-Level System) lab control framework. The configuration uses a modular, layered approach that separates concerns and makes it easy to manage different environments.

## Directory Structure

```
MLS/config/
├── README.md                    # This file
├── base.yaml                    # Base configuration (shared defaults)
├── services.yaml                # Service orchestration settings
├── hardware.yaml                # Hardware-specific parameters
├── environments/                # Environment-specific overrides
│   ├── development.yaml         # Development environment
│   ├── production.yaml          # Production/lab environment
│   └── local.yaml               # Local machine overrides (gitignored)
└── schemas/                     # Pydantic validation schemas
    ├── __init__.py
    └── config_schema.py
```

## Configuration Philosophy

The configuration system follows these principles:

1. **Modularity**: Separate configs for different aspects (network, hardware, services)
2. **Layering**: Base config + environment overrides
3. **Validation**: Pydantic schemas ensure type safety
4. **Flexibility**: Easy to add new environments or modify settings

## Configuration Files

### base.yaml
Core configuration shared across all environments. Contains:
- Network settings (IP addresses, ports, timeouts)
- Data paths (ARTIQ, LabVIEW, camera, analysis)
- Hardware defaults (worker settings, camera parameters)
- LabVIEW integration settings
- Telemetry configuration
- Camera control settings
- Logging configuration
- Analysis parameters

### services.yaml
Service orchestration configuration:
- Camera server settings
- Manager service settings
- Flask web server settings
- Health monitoring
- Performance optimization
- Service dependencies

### hardware.yaml
Hardware-specific settings:
- System identification
- RF system configuration
- Vacuum system parameters
- Camera hardware specs
- Laser system settings
- Electrode configuration
- Device mappings
- Calibration data

### environments/*.yaml
Environment-specific overrides that modify base settings:
- **development.yaml**: Local testing with localhost, disabled hardware
- **production.yaml**: Lab setup with network drives, real hardware
- **local.yaml**: User-specific overrides (not committed to git)

## Environment Selection

Set the `MLS_ENV` environment variable to choose the active configuration:

```bash
# Windows
set MLS_ENV=development

# Linux/macOS
export MLS_ENV=production
```

Available environments:
- `development`: Local testing with simulated hardware
- `production`: Full lab setup with real hardware
- `local`: Your personal overrides (create from local.yaml.example)

## Usage

### Basic Usage

```python
from MLS.core.config import get_config

# Load configuration (uses MLS_ENV or defaults to 'development')
config = get_config()

# Access settings via properties
print(config.master_ip)      # '134.99.120.40' (production)
print(config.cmd_port)       # 5555
print(config.flask_port)     # 5000

# Access nested settings via get()
exposure = config.get('hardware.camera.exposure_default')  # 0.3

# Get paths (auto-resolves relative paths)
output_path = config.get_path('output_base')
camera_path = config.get_path('camera_frames')
```

### Environment-Specific Loading

```python
# Force a specific environment
config = get_config(environment='production')

# Check current environment
print(config.environment)    # 'production'
```

### Using Pydantic Validation

```python
from MLS.config.schemas import load_config, AppConfig

# Load with full Pydantic validation
config: AppConfig = load_config('development')

# Access with IDE autocomplete and type checking
print(config.network.master_ip)
print(config.hardware.camera.target_temperature)
print(config.paths.output_base)
```

### Reloading Configuration

```python
config = get_config()

# ... modify config files ...

# Reload from disk
config.reload()
```

## Configuration Merging

The system merges configurations in this order:

1. **base.yaml** - Foundation settings
2. **services.yaml** - Service orchestration
3. **environments/{MLS_ENV}.yaml** - Environment overrides

Later files override earlier ones. For example, if `base.yaml` sets:

```yaml
network:
  master_ip: "134.99.120.40"
```

And `environments/development.yaml` sets:

```yaml
network:
  master_ip: "127.0.0.1"
```

The development environment will use `127.0.0.1`.

## Adding a New Environment

1. Create a new file in `environments/`:

```yaml
# environments/staging.yaml
environment: staging

network:
  master_ip: "10.0.1.100"

paths:
  output_base: "/mnt/staging/data"

labview:
  enabled: true
  host: "10.0.1.50"
```

2. Set the environment variable:

```bash
export MLS_ENV=staging
```

3. Use it in your code:

```python
config = get_config()  # Automatically loads staging
```

## Validation

The `schemas/config_schema.py` file contains Pydantic models that validate:
- Port numbers (1024-65535)
- IP address formats
- Path existence (optional)
- Value ranges (e.g., voltages, temperatures)
- Required fields

Validation errors provide helpful messages:

```python
from MLS.config.schemas import load_config

try:
    config = load_config('production')
except ValidationError as e:
    print(e)  # Shows exactly which field failed validation
```

## Path Handling

Paths in configuration can be:
- **Absolute**: `Y:/Xi/Data` (used as-is)
- **Relative**: `./data` (resolved relative to project root)

The `get_path()` method handles resolution:

```python
# In config: output_base: "./data"
path = config.get_path('output_base')
# Returns: "/path/to/MLS/data"
```

## Backward Compatibility

The system maintains compatibility with legacy code that expects the old `settings.yaml` format:

```python
# Legacy style still works
from MLS.core.config import get_config

config = get_config("config/settings.yaml")  # Legacy file
value = config.get('network.master_ip')
```

## Best Practices

1. **Use environment variables**: Set `MLS_ENV` instead of hardcoding paths
2. **Keep secrets in local.yaml**: Don't commit passwords or API keys
3. **Validate changes**: Run `python -m MLS.config.schemas` to validate configs
4. **Document overrides**: Comment why an environment differs from base
5. **Use Pydantic models**: For new code, import from `schemas` for type safety

## Troubleshooting

### Config not found
```
FileNotFoundError: Could not find configuration directory
```
Ensure `MLS/config/base.yaml` exists and you're running from the project root.

### Port conflicts
```
ValidationError: port must be between 1024 and 65535
```
Check that port numbers in your config are valid (not < 1024 or > 65535).

### Path resolution issues
```python
# Debug path resolution
print(config.get('paths.output_base'))  # Raw value
print(config.get_path('output_base'))   # Resolved path
```

## Migration from Old Structure

If you're migrating from the old single-file `settings.yaml`:

1. Settings are now split across multiple files
2. Use `base.yaml` for most settings
3. Move environment-specific overrides to `environments/`
4. Service settings go in `services.yaml`
5. Hardware specs go in `hardware.yaml`

The old `settings.yaml` is still supported for backward compatibility but new development should use the modular structure.
