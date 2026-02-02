# Bayesian Optimization Guide

Complete guide to using the automated ion loading optimization system.

## Overview

The optimizer uses **SAASBO** (Sparse Axis-Aligned Subspace Bayesian Optimization) to automatically find optimal parameters for:

1. **Be+ Loading** - Load exactly N ions with minimal UV exposure
2. **Be+ Ejection** - Remove excess ions surgically
3. **HD+ Loading** - Load dark HD+ ions efficiently

## Quick Start

### Via Web Interface

1. Open http://localhost:5050 (Optimizer Flask UI)
2. Set targets on **Parameters** page:
   - Target Be+ Count: 1
   - Load HD+: ✓ (checked)
3. Click **Start** on Overview page
4. Monitor progress on **Dashboard** page

### Via Python API

```python
import zmq
import json

# Connect to ControlManager
ctx = zmq.Context()
socket = ctx.socket(zmq.REQ)
socket.connect("tcp://localhost:5557")

# Start optimization
socket.send_json({
    "action": "OPTIMIZE_START",
    "source": "USER",
    "target_be_count": 1,
    "target_hd_present": True,
    "max_iterations": 50
})

response = socket.recv_json()
print(f"Started: {response}")

# Monitor status
while True:
    socket.send_json({"action": "OPTIMIZE_STATUS"})
    status = socket.recv_json()
    
    data = status.get("data", {})
    print(f"Phase: {data.get('phase')}, "
          f"Iter: {data.get('iteration')}, "
          f"Cost: {data.get('best_cost', 0):.2f}")
    
    if data.get("phase") == "complete":
        break
    
    time.sleep(2)
```

## Three-Phase Workflow

### Phase I: Be+ Loading

**Goal**: Load exactly `N` Be+ ions

**Parameters Optimized**:
- `be_oven_duration_ms` - How long oven is on
- `be_pi_laser_start_ms` - When PI laser turns on
- `be_pi_laser_duration_ms` - **KEY PARAMETER** (minimize this)
- `piezo` - Laser frequency tuning
- `cooling_power_mw` - 397nm cooling power
- `u_rf_volts` - RF voltage

**Success Criteria**:
- `ion_count == target_be_count`
- `secular_freq` within 5% of target

**Why Minimize PI Duration?**
The 235nm PI laser causes patch charges on electrodes. Shorter exposure = more stable trap.

### Phase II: Be+ Ejection (Conditional)

**Triggered when**: `ion_count > target_be_count`

**Parameters Optimized**:
- `tickle_amplitude` - Pulse strength
- `tickle_duration_ms` - Pulse length
- `tickle_freq_khz` - Secular resonance frequency

**Success Criteria**:
- `ion_count == target_be_count` (not 0!)

**Note**: This phase is skipped if initial loading succeeds or produces fewer ions than target.

### Phase III: HD+ Loading

**Goal**: Add HD+ ion to existing Be+ crystal

**Parameters Optimized**:
- `hd_valve_duration_ms` - HD gas exposure (minimize)
- `hd_egun_duration_ms` - Electron gun firing time (minimize)
- `piezo` - Must overlap with HD flux

**Verification Method**: Secular frequency sweep
- Success: Peak at coupled Be-HD frequency (~277 kHz)
- Failure: Peak remains at single Be+ frequency (~307 kHz)

**Success Criteria**:
- `sweep_peak_freq` matches HD+ target
- `ion_count` unchanged (still have Be+)

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_be_count` | 1 | Target number of Be+ ions |
| `target_hd_present` | False | Whether to load HD+ |
| `max_iterations` | 100 | Max iterations per phase |
| `n_initial_points` | 5 | Random exploration before BO |
| `convergence_threshold` | 0.01 | Stop when delta < threshold |
| `enable_be_loading` | True | Enable Phase I |
| `enable_be_ejection` | True | Enable Phase II |
| `enable_hd_loading` | True | Enable Phase III |

## Understanding the Algorithm

### SAASBO Explained

**Problem**: Standard Bayesian Optimization fails in high dimensions (20+ parameters).

**Solution**: SAASBO identifies that only 3-5 parameters matter at any given time.

**How it works**:
1. **Gaussian Process** models the cost function
2. **ARD Kernel** learns length scales for each parameter
3. **Small length scale** = important parameter
4. **Focus search** on important subspace

### Cost Functions

**Be+ Loading**:
```
Cost = Accuracy_Penalty + Stability + Time + Cooling_Power + PI_Duration

Where:
- Accuracy: 0 if correct count, high penalty if empty
- PI_Duration: Weighted heavily (KEY METRIC)
```

**HD+ Loading**:
```
Cost = -1000 if HD+ detected (reward)
       +200 if no HD+ (penalty)
       + Piezo_Efficiency + Egun_Efficiency
```

### Expected Improvement

The algorithm suggests parameters that:
1. **Exploit** - Try regions with low cost (good performance)
2. **Explore** - Try uncertain regions (high variance)

Balance controlled by `xi` parameter (exploration weight).

## Monitoring Optimization

### Key Metrics

| Metric | Good Value | Description |
|--------|------------|-------------|
| Cost | Decreasing | Lower is better |
| Convergence Delta | < 0.01 | Variation in recent costs |
| Active Dimensions | 3-5 | Number of important parameters |
| Iteration | Progress | Current iteration count |

### Dashboard Views

**Overview Page**:
- Current phase and state
- Best cost achieved
- Quick controls (start/stop/reset)

**Dashboard Page**:
- Real-time cost plot
- Parameter trends
- Recent iteration log

**History Page**:
- Complete optimization log
- Cost evolution chart
- Export to JSON

## Profiles

### What are Profiles?

Saved optimal configurations for specific targets:
- `be_1`: 1 Be+ ion, no HD+
- `be_1_hd`: 1 Be+ ion + HD+
- `be_2`: 2 Be+ ions, no HD+

### Using Profiles

**Warm Starting**:
When you start optimization with a saved profile, the optimizer uses it as the first suggestion.

**Loading Profiles**:
```python
# Via web UI
Profiles page → Click profile → "Load Profile"

# Via API
socket.send_json({
    "action": "OPTIMIZE_CONFIG",
    "method": "POST",
    "config": {
        "target_be_count": 1,
        "target_hd_present": True
    }
})
```

## Troubleshooting

### Optimization Won't Start

**Check**:
1. System mode is AUTO (not MANUAL or SAFE)
2. ControlManager is running
3. No pending suggestion (check status)

### Stuck on Phase I

**Symptoms**: Many iterations, no success

**Solutions**:
- Check oven is working
- Verify PI laser alignment
- Check secular frequency detection
- Increase `max_iterations`
- Widen parameter bounds

### Empty Trap After Ejection

**Cause**: Tickle pulse too strong

**Solution**: Algorithm learns this automatically, but you can:
- Skip to Phase I manually
- Start with lower tickle amplitude

### HD+ Not Detected

**Symptoms**: Sweep shows Be+ peak only (~307 kHz)

**Checks**:
- HD valve opening?
- E-gun firing?
- Piezo overlapping with HD flux?
- Pressure in correct range?

**Solutions**:
- Verify `piezo` is set during HD loading
- Check `hd_valve_duration_ms` is non-zero
- Manually optimize piezo voltage

### High Cost Not Decreasing

**Causes**:
1. Parameter bounds too narrow
2. Hardware not responding
3. Measurement noise too high

**Solutions**:
- Reset and widen bounds
- Check hardware connections
- Increase `n_initial_points` for more exploration

## Advanced Usage

### Custom Objective Weights

Edit `server/optimizer/objectives.py`:

```python
BeLoadingObjective(
    w_accuracy=100.0,   # Increase for strict count
    w_pi=50.0,          # Increase to minimize UV exposure
    w_time=0.5,         # Decrease if speed less important
)
```

### Skipping Phases

```python
# Skip directly to HD+ loading
socket.send_json({
    "action": "OPTIMIZE_CONTROL",
    "command": "skip_phase",
    "phase": "hd_loading"
})
```

### Manual Parameter Injection

```python
# Force specific parameters
socket.send_json({
    "action": "OPTIMIZE_CONTROL",
    "command": "inject_params",
    "params": {
        "piezo": 2.0,
        "be_pi_laser_duration_ms": 300
    }
})
```

## Best Practices

1. **Start Simple**: Try Be+ loading only first (target_hd_present=False)

2. **Monitor Costs**: If cost not decreasing after 20 iterations, reset

3. **Save Good Profiles**: When optimization succeeds, profile is auto-saved

4. **Check Active Dims**: If >10 dimensions active, hardware may be noisy

5. **Regular Validation**: Periodically verify profiles still work

6. **Pressure Safety**: Always monitor pressure during HD+ loading

## Performance Tuning

### Faster Convergence

- Reduce `max_iterations` to 30-50
- Decrease `n_initial_points` to 3
- Increase `convergence_threshold` to 0.05

### Better Results

- Increase `max_iterations` to 100-200
- Increase `n_initial_points` to 10
- Decrease `convergence_threshold` to 0.001

### Parallel Execution

Currently not supported. Sequential experiments only.

## Safety Considerations

⚠️ **Automatic operations can be dangerous**:

1. **Kill Switches**: Still active during optimization
2. **Mode Changes**: Switching to MANUAL pauses optimizer
3. **Pressure**: Auto-kill if pressure spikes
4. **Emergency Stop**: STOP command halts everything

**Always** have someone monitoring when optimization is running.

## API Reference

See [API Reference](../api/reference.md) for complete command reference.

## Related Documentation

- [BO Architecture](bo_architecture.md) - Technical optimizer design
- [API Reference](../api/reference.md) - Complete API documentation

## Support

For issues or questions about optimization:
1. Check this guide
2. Review logs in `logs/optimizer.log`
3. Contact development team
