# Phase 3 Migration Guide

## Overview

Phase 3 introduces three major improvements:

1. **Phase 3A**: Command-specific experiments (ARTIQ-native approach)
2. **Phase 3B**: Async communication patterns (better performance)
3. **Phase 3C**: External configuration (YAML-based, no code changes)

## Quick Start

### 1. Copy New Files

```bash
# Create directories
mkdir -p /home/artiq/.../repository/experiments
mkdir -p /home/artiq/.../repository/utils
mkdir -p /home/artiq/.../repository/config/artiq

# Copy Phase 3A: Experiments
cp MLS/artiq/experiments/*.py /home/artiq/.../repository/experiments/
cp MLS/artiq/experiments/__init__.py /home/artiq/.../repository/experiments/

# Copy Phase 3B+C: Utils
cp MLS/artiq/utils/*.py /home/artiq/.../repository/utils/
cp MLS/artiq/utils/__init__.py /home/artiq/.../repository/utils/

# Copy Phase 3C: Config
cp MLS/config/artiq/*.yaml /home/artiq/.../repository/config/artiq/

# Copy Phase 2: Updated fragments
cp MLS/artiq/dds_controller.py /home/artiq/.../repository/
cp MLS/artiq/pmt_counter.py /home/artiq/.../repository/
cp MLS/artiq/camera_trigger.py /home/artiq/.../repository/
cp MLS/artiq/sweeping.py /home/artiq/.../repository/
cp MLS/artiq/raman_control.py /home/artiq/.../repository/
```

### 2. Update IP Configuration

Edit `config/artiq/artiq_config.yaml`:

```yaml
network:
  master_ip: "192.168.56.101"  # Your ARTIQ VM IP
```

### 3. Test Repository Scan

```bash
artiq_master
```

Check that no `WorkerWatchdogTimeout` errors appear.

## Architecture Comparison

### Phase 1/2: ZMQ Worker (Monolithic)

```
Manager → ZMQ → Artiq_Worker.py
                     ├── ec.py
                     ├── comp.py
                     ├── raman_control.py
                     └── sweeping.py (heavy)
```

### Phase 3A: Command-Specific Experiments

```
Manager → Scheduler → experiments/SetDCExp.py
                    ├── experiments/SecularSweepExp.py
                    ├── experiments/PMTMeasureExp.py
                    └── experiments/EmergencyZeroExp.py
                            
Each experiment imports only what it needs:
    SetDCExp → ec.py + comp.py
    SecularSweepExp → dds_controller.py + pmt_counter.py
```

## Usage Examples

### Option 1: Use New Experiments (Recommended)

From ARTIQ dashboard:
1. Open ARTIQ dashboard
2. Find experiments in repository list:
   - `experiments.set_dc_exp.SetDCExpScan`
   - `experiments.secular_sweep_exp.SecularSweepExpScan`
   - `experiments.pmt_measure_exp.PMTMeasureExpScan`
3. Set parameters and submit

From Python code:
```python
from experiments.set_dc_exp import submit_set_dc
from experiments.secular_sweep_exp import submit_sweep

# Submit DC setting
rid = submit_set_dc(scheduler, ec1=5.0, ec2=5.0, comp_h=0.0, comp_v=0.0)

# Submit sweep
rid = submit_sweep(
    scheduler,
    target_freq_khz=400.0,
    span_khz=40.0,
    steps=41,
    dds_choice="axial"
)
```

### Option 2: Use Unified Submitter

```python
from utils.experiment_submitter import ExperimentSubmitter

submitter = ExperimentSubmitter(mode="experiments", scheduler=scheduler)
await submitter.connect()

# Submit any experiment type
result = await submitter.submit_set_dc(ec1=5.0, ec2=5.0)
result = await submitter.submit_sweep(target_freq_khz=400.0, span_khz=40.0)
result = await submitter.submit_pmt_measure(duration_ms=100.0)

if result.success:
    print(f"Experiment RID: {result.rid}")
```

### Option 3: Keep Using ZMQ (Legacy)

```python
from utils.experiment_submitter import ExperimentSubmitter

submitter = ExperimentSubmitter(mode="zmq")
await submitter.connect()

# Same API, but uses ZMQ instead of scheduler
result = await submitter.submit_set_dc(ec1=5.0, ec2=5.0)
```

## Configuration System (Phase 3C)

### File Hierarchy

```
config/artiq/
├── artiq_config.yaml          # Base configuration
├── artiq_config_development.yaml  # Development overrides
├── artiq_config_production.yaml   # Production overrides
└── artiq_config_local.yaml    # Local machine (not in git)
```

### Loading Order

1. `artiq_config.yaml` (base)
2. `artiq_config_{environment}.yaml` (environment-specific)
3. `artiq_config_local.yaml` (local machine)

Later files override earlier ones.

### Usage

```python
from utils.config_loader import get_artiq_config, get_config_value, config

# Get full config
config = get_artiq_config()
ip = config['network']['master_ip']

# Get specific value
cmd_port = get_config_value('network.cmd_port', default=5555)

# Use shortcuts
print(config.master_ip)      # 192.168.56.101
print(config.cmd_port)       # 5555
print(config.dds_devices)    # {'axial': 'urukul0_ch0', ...}
```

### Changing IP Address

Edit `config/artiq/artiq_config_local.yaml`:

```yaml
network:
  master_ip: "192.168.56.101"  # Your ARTIQ IP
```

No code changes needed!

## Async Communication (Phase 3B)

### Basic Async Client

```python
from utils.async_comm import AsyncZMQClient

client = AsyncZMQClient()
await client.connect()

# Non-blocking send
await client.send_command({
    "type": "SET_DC",
    "values": {"ec1": 5.0, "ec2": 5.0}
})

# Non-blocking receive with timeout
data = await client.receive_data(timeout=5.0)
if data:
    print(f"Received: {data}")
```

### Connection Pool (High Throughput)

```python
from utils.async_comm import ZMQConnectionPool

pool = ZMQConnectionPool(pool_size=3)
await pool.connect()

# Get client from pool
async with pool.acquire() as client:
    await client.send_command({...})
    data = await client.receive_data()
```

### One-Shot Commands

```python
from utils.async_comm import send_command_simple

# Simple one-shot command
response = await send_command_simple(
    {"type": "PMT_MEASURE", "duration_ms": 100.0},
    timeout=5.0
)
```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'experiments'`

**Solution**: Add to Python path or use absolute imports:
```python
import sys
sys.path.insert(0, "/home/artiq/.../repository")
```

### YAML Not Available

**Problem**: `ImportError: No module named 'yaml'`

**Solution**: Install PyYAML:
```bash
pip install pyyaml
```

Or use JSON config instead (rename to `.json`).

### ZMQ Not Available

**Problem**: `ImportError: No module named 'zmq'`

**Solution**: Install pyzmq:
```bash
pip install pyzmq
```

### Repository Scan Still Slow

**Problem**: `WorkerWatchdogTimeout` still occurs

**Solution**: 
1. Check that lazy loading is in `Artiq_Worker.py`
2. Verify fragments are NOT imported at module level
3. Use command-specific experiments instead

## Migration Checklist

- [ ] Copy all new files to repository
- [ ] Update IP in `config/artiq/artiq_config_local.yaml`
- [ ] Install dependencies: `pip install pyyaml pyzmq`
- [ ] Test repository scan: `artiq_master`
- [ ] Test individual experiments from dashboard
- [ ] Test ZMQ worker (if still needed)
- [ ] Update Manager code to use new submitter (optional)
- [ ] Verify all hardware control works
- [ ] Update documentation

## Rollback

If you need to rollback:

```bash
# Restore original files from backup
cp backup/Artiq_Worker.py /home/artiq/.../repository/
cp backup/sweeping.py /home/artiq/.../repository/

# Remove Phase 3 files
rm -rf /home/artiq/.../repository/experiments/
rm -rf /home/artiq/.../repository/utils/
rm -rf /home/artiq/.../repository/config/artiq/
```

## Support

For issues:
1. Check logs in `logs/artiq_worker.log`
2. Verify configuration with `config_loader.py` test
3. Test individual components separately
4. Compare with working backup
