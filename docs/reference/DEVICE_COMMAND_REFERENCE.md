# ARTIQ Device & Command Reference

## Hardware Devices

### Core Device
| Device Name | Type | Description |
|-------------|------|-------------|
| core | CoreDevice | ARTIQ core device (required by all) |

### DAC Devices (Zotino)
| Device Name | Type | Description | Channels |
|-------------|------|-------------|----------|
| zotino0 | Zotino | 16-channel DAC | EC: 4,5 / Comp: 0-3 |

### DDS Devices (Urukul)
| Device Name | Type | Description |
|-------------|------|-------------|
| urukul0_ch0 | AD9910 | Axial secular frequency |
| urukul0_ch1 | AD9910 | Radial secular frequency |
| urukul0_ch2 | AD9910 | Raman beam 0 |
| urukul0_ch3 | AD9910 | Raman beam 1 |

### TTL Devices
| Device Name | Type | Description |
|-------------|------|-------------|
| ttl0_counter | TTLInOut | PMT counter input |
| ttl4 | TTLOut | Camera trigger output |

---

## ZMQ Commands (Artiq_Worker)

| Command | Payload | Description |
|---------|---------|-------------|
| SET_DC | ec1, ec2, comp_h, comp_v | Set DC voltages (Volts) |
| SET_COOLING | amp0, amp1, sw0, sw1 | Set Raman beam params |
| RUN_SWEEP | target_frequency_khz, span_khz, steps, att_db, on_time_ms, off_time_ms | Run frequency sweep |
| CAMERA_TRIGGER | - | Trigger camera once |
| START_CAMERA_INF | - | Start camera infinity mode |
| STOP_CAMERA | - | Stop camera |
| PMT_MEASURE | duration_ms | Measure PMT counts |
| CAM_SWEEP | - | Camera sweep (not implemented) |
| SECULAR_SWEEP | - | Secular sweep (not implemented) |
| EMERGENCY_ZERO | - | Emergency shutdown |
| PING | - | Health check |
| STOP_WORKER | - | Graceful shutdown |

---

## Fragment Classes

### ec.py (Endcaps - Zotino ch 4,5)
```python
set_ec(v1: TFloat, v2: TFloat)           # Set EC1, EC2 voltages
set_params(v1: TFloat, v2: TFloat)       # Alias for set_ec
```

### comp.py (Compensation - Zotino ch 0-3)
```python
set_comp(v0, v1, v2, v3: TFloat)         # Set all 4 channels
set_hor_ver(u_hor, u_ver: TFloat)        # Set H/V compensation
```

### raman_control.py (Urukul ch 2,3)
```python
set_beams(amp0, amp1: TFloat, sw0, sw1: TInt32)   # Set beams
set_frequency(freq0_mhz, freq1_mhz: TFloat)       # Set freq
set_att(att0_db, att1_db: TFloat)                 # Set attenuation
```

### dds_controller.py (Single DDS channel)
```python
set_frequency(freq_hz: TFloat)           # Set frequency
set_amplitude(amplitude: TFloat)         # Set amplitude (0-1)
set_att(att_db: TFloat)                  # Set attenuation (dB)
cfg_sw(enable: TBool)                    # Enable/disable RF
pulse(duration_ms: TFloat)               # Output pulse
```

### pmt_counter.py (TTL input)
```python
count(duration_ms: TFloat) -> TInt32     # Count photons
count_with_timeout(duration_ms, timeout_ms) -> TInt32
gate_open()                              # Open gate
gate_close() -> TInt32                   # Close gate & return count
```

### camera_trigger.py (TTL output)
```python
trigger(duration_ms: TFloat)             # Send pulse (ms)
trigger_us(duration_us: TFloat)          # Send pulse (us)
on()                                     # Set high
off()                                    # Set low
trigger_multiple(n, delay_ms, pulse_ms)  # Multiple triggers
```

### sweeping.py (Orchestrator)
```python
sweep_point(freq_hz, on_ms, off_ms) -> TInt32           # Sweep point
sweep_point_with_cam(freq_hz, on_ms, off_ms) -> TInt32  # With camera
pmt_measure(duration_ms) -> TInt32                      # Simple PMT
```

**Sub-fragments**:
- dds_axial: urukul0_ch0
- dds_radial: urukul0_ch1
- pmt: ttl0_counter
- cam: ttl4

---

## Phase 3A Experiments

### SetDCExp
- Parameters: ec1, ec2, comp_h, comp_v (Volts)
- Submit: `submit_set_dc(scheduler, ec1=5.0, ec2=5.0, ...)`

### SecularSweepExp
- Parameters: target_freq_khz, span_khz, steps, att_db, on_time_ms, off_time_ms
- Results: pmt_counts, frequency_khz
- Submit: `submit_sweep(scheduler, target_freq_khz=400.0, ...)`

### PMTMeasureExp
- Parameters: duration_ms, num_samples
- Results: counts, counts_std
- Submit: `submit_pmt_measure(scheduler, duration_ms=100.0, ...)`

### EmergencyZeroExp
- No parameters - immediate safety shutdown
- Submit: `submit_emergency_zero(scheduler, priority=100)`

---

## Device Mapping

```
Zotino0 (DAC)
├── Ch 0: Comp Horizontal Coarse
├── Ch 1: Comp Horizontal Fine
├── Ch 2: Comp Vertical Coarse
├── Ch 3: Comp Vertical Fine
├── Ch 4: Endcap 1 (EC1)
└── Ch 5: Endcap 2 (EC2)

Urukul0 (DDS)
├── Ch 0: Axial secular
├── Ch 1: Radial secular
├── Ch 2: Raman beam 0
└── Ch 3: Raman beam 1

TTL
├── ttl0_counter: PMT input
└── ttl4: Camera trigger
```

---

## Quick Examples

### Set DC
```python
# Experiment
from experiments.set_dc_exp import submit_set_dc
submit_set_dc(scheduler, ec1=5.0, ec2=5.0)

# ZMQ
{"type": "SET_DC", "values": {"ec1": 5.0, "ec2": 5.0}}

# Direct
self.ec.set_ec(5.0 * V, 5.0 * V)
```

### Sweep
```python
# Experiment
from experiments.secular_sweep_exp import submit_sweep
submit_sweep(scheduler, target_freq_khz=400.0, steps=41)

# ZMQ
{"type": "RUN_SWEEP", "values": {"target_frequency_khz": 400.0, ...}}
```

### PMT
```python
# Experiment
from experiments.pmt_measure_exp import submit_pmt_measure
submit_pmt_measure(scheduler, duration_ms=100.0)

# Direct
counts = self.pmt.count(100.0)
```

---

*Phase 3 Complete - 2024-02-03*
