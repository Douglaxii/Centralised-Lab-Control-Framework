# Secular Frequency Comparison System

This document describes the automated secular frequency comparison system that validates trap calibration by comparing measured secular frequencies with theoretical predictions.

## Overview

The secular comparison system automates the process of:
1. Setting trap parameters (electrodes and RF voltage)
2. Calculating theoretical secular frequencies using `trap_sim_asy`
3. Performing a secular frequency scan around the predicted frequency
4. Fitting a Lorentzian to the measured data
5. Comparing the fitted center to the theoretical prediction
6. Uploading results for analysis or Turbo algorithm feedback

## System Architecture

```
[User/Flask] ──COMPARE──> [Manager]
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   [ARTIQ Worker]      [SMILE/LabVIEW]      [Analysis Module]
        │                     │                     │
   Set EC1/EC2          Set U_RF (1400mV)    Calculate theory
   Set Comp_H/V                               ↓
        │                     │            367.3 kHz
        └──────────┬──────────┘               │
                   │                         │
                   ▼                         │
            Run Secular Scan <───────────────┘
                   │
                   ▼
            [Lorentzian Fit]
                   │
                   ▼
            [Compare & Upload]
```

## Workflow Details

### 1. Command Initiation

Send COMPARE command from Flask dashboard or external script:

```bash
curl -X POST http://localhost:5000/api/compare \
  -H "Content-Type: application/json" \
  -d '{
    "ec1": 10.0,
    "ec2": 10.0,
    "comp_h": 6.0,
    "comp_v": 37.0,
    "u_rf_mV": 1400,
    "mass_numbers": [9, 3]
  }'
```

### 2. Parameter Setup

**Default Parameters:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| EC1 | 10.0 V | Endcap 1 voltage |
| EC2 | 10.0 V | Endcap 2 voltage |
| Comp_H | 6.0 V | Horizontal compensation |
| Comp_V | 37.0 V | Vertical compensation |
| U_RF | 1400 mV | RF voltage on SMILE interface |

**RF Voltage Scaling:**
- 700 mV on SMILE → 100 V real RF
- 1400 mV on SMILE → 200 V real RF
- Scale factor: 100/700 = 0.1429 V/mV

### 3. Theoretical Calculation

The system uses `trap_sim_asy.py` to calculate normal modes:

```python
from server.analysis.secular_comparison import SecularFrequencyComparator

comparator = SecularFrequencyComparator()
predicted_freqs, smallest_freq, mode_name = comparator.calculate_theoretical_freqs(
    params={'ec1': 10, 'ec2': 10, 'comp_h': 6, 'comp_v': 37, 'u_rf_mV': 1400},
    mass_numbers=[9, 3]  # Be+ ions
)

# Result: 367.3 kHz (Axial in-phase mode)
```

### 4. Secular Scan

Scan parameters:
- **Center**: Predicted frequency (e.g., 367.3 kHz)
- **Range**: ±20 kHz
- **Points**: 41 (1 kHz resolution)
- **Dwell**: 300 ms ON / 300 ms OFF per point

### 5. Lorentzian Fitting

The fit model is:
```
L(f) = A × Γ² / [(f - f₀)² + Γ²] + BG
```

Where:
- `f₀`: Center frequency (the fitted secular frequency)
- `Γ`: Half-width at half-maximum (HWHM)
- `A`: Amplitude
- `BG`: Background
- `FWHM = 2Γ`

Fit quality metrics:
- **χ² (chi-squared)**: Reduced chi-square of fit
- **SNR**: Signal-to-noise ratio (peak / RMS noise)

### 6. Comparison and Classification

**Match Quality Criteria:**

| Quality | Frequency Diff | χ² | Description |
|---------|---------------|-----|-------------|
| Excellent | < 1% | < 3 | Perfect agreement |
| Good | < 5% | < 5 | Acceptable agreement |
| Poor | < 10% | - | Marginal agreement |
| Mismatch | > 10% | - | Significant deviation |

## API Reference

### Manager API

#### COMPARE Command

```json
{
  "action": "COMPARE",
  "source": "USER",
  "params": {
    "ec1": 10.0,
    "ec2": 10.0,
    "comp_h": 6.0,
    "comp_v": 37.0,
    "u_rf_mV": 1400,
    "mass_numbers": [9, 3],
    "scan_range_kHz": 20.0,
    "scan_points": 41
  }
}
```

**Response:**
```json
{
  "status": "started",
  "exp_id": "EXP_123456_...",
  "message": "Secular comparison started",
  "predicted_freq_kHz": 367.330,
  "target_mode": "Axial in-phase"
}
```

### Flask API

#### Trigger Comparison

```bash
POST /api/compare
Content-Type: application/json

{
  "ec1": 10.0,
  "ec2": 10.0,
  "comp_h": 6.0,
  "comp_v": 37.0,
  "u_rf_mV": 1400
}
```

#### Get Comparison Results

```bash
GET /api/data/recent/secular_fitted?window=3600
```

**Response:**
```json
{
  "status": "ok",
  "channel": "secular_fitted",
  "count": 5,
  "data": [
    {"timestamp": 1706380800.1, "value": 369.8},
    ...
  ]
}
```

## Data Channels

The following telemetry channels are updated during comparison:

| Channel | Source | Description |
|---------|--------|-------------|
| `secular_fitted` | Analysis | Fitted secular frequency (kHz) |
| `secular_predicted` | Theory | Predicted frequency (kHz) |
| `secular_diff` | Analysis | Difference: fitted - predicted (kHz) |
| `secular_snr` | Analysis | Signal-to-noise ratio |

## Python Module Usage

### Basic Comparison

```python
from server.analysis.secular_comparison import SecularFrequencyComparator

comparator = SecularFrequencyComparator()

# Run full comparison with simulated data
result = comparator.run_comparison(
    params={
        'ec1': 10.0,
        'ec2': 10.0,
        'comp_h': 6.0,
        'comp_v': 37.0,
        'u_rf_mV': 1400
    },
    mass_numbers=[9, 3],
    scan_results=(frequencies, counts)  # From ARTIQ sweep
)

print(f"Predicted: {result.smallest_freq_kHz:.3f} kHz")
print(f"Fitted: {result.fitted_center_kHz:.3f} kHz")
print(f"Difference: {result.frequency_difference_kHz:.3f} kHz")
print(f"Quality: {result.match_quality}")
```

### Upload Results

```python
# Upload to data server for dashboard/Turbo
comparator.upload_to_data_server(result)
```

### Lorentzian Fitting Only

```python
from server.analysis.secular_comparison import LorentzianFitter
import numpy as np

fitter = LorentzianFitter()

# Generate data
freqs = np.linspace(350, 390, 41)
counts = 100 + 1000 * np.exp(-(freqs - 368)**2 / 10) + np.random.normal(0, 20, 41)

# Fit
success, result = fitter.fit(freqs, counts)

if success:
    print(f"Center: {result['x0']:.3f} ± {result['x0_err']:.3f} kHz")
    print(f"FWHM: {result['fwhm']:.3f} kHz")
    print(f"χ²: {result['chi2']:.2f}")
```

## Command Line Testing

### Theory Only

```bash
python server/analysis/secular_comparison.py \
  --ec1 10 --ec2 10 --comp-h 6 --comp-v 37 --u-rf 1400
```

### With Simulated Fit

```bash
python server/analysis/secular_comparison.py \
  --ec1 10 --ec2 10 --comp-h 6 --comp-v 37 --u-rf 1400 \
  --test-fit
```

## Error Handling

### No Signal Detected

**Cause:**
- Ions not loaded
- Secular frequency far from prediction
- RF voltage not applied correctly
- Detection system malfunction

**Response:**
```json
{
  "signal_detected": false,
  "error_message": "no_signal",
  "snr": 1.2
}
```

### Fit Failure

**Cause:**
- Multiple peaks in scan range
- Asymmetric lineshape
- Insufficient data points
- Poor SNR

**Response:**
```json
{
  "signal_detected": true,
  "fit_success": false,
  "error_message": "fit_failed",
  "chi2": 15.7
}
```

### Theory Calculation Failure

**Cause:**
- Invalid trap parameters
- Numerical convergence issues
- Mass numbers incompatible

**Response:**
```json
{
  "status": "error",
  "message": "Theory calculation failed: ...",
  "code": "THEORY_ERROR"
}
```

## Integration with Turbo Algorithm

The comparison results can be used by the Turbo algorithm for automated trap optimization:

```python
# Turbo receives comparison results
if result.match_quality in ["excellent", "good"]:
    # Use measured frequency to refine model
    turbo.update_calibration(
        predicted=result.smallest_freq_kHz,
        measured=result.fitted_center_kHz
    )
else:
    # Trigger re-optimization
    turbo.flag_mismatch(result)
```

## File Output

Comparison results are saved to:
```
Y:/Xi/Data/<date>/secular_compare/
  EXP_123456_comparison.json
  EXP_123456_scan_data.csv
  EXP_123456_fit_plot.png
```

**JSON Format:**
```json
{
  "ec1": 10.0,
  "ec2": 10.0,
  ...
  "predicted_freqs_kHz": [367.33, 1003.70, ...],
  "smallest_freq_kHz": 367.33,
  "target_mode": "Axial in-phase",
  "signal_detected": true,
  "fit_success": true,
  "fitted_center_kHz": 369.85,
  "fitted_fwhm_kHz": 5.2,
  "frequency_difference_kHz": 2.52,
  "relative_difference_percent": 0.69,
  "match_quality": "excellent",
  "timestamp": 1706380800.123
}
```

## Calibration Procedure

1. **Load ions** in standard trap configuration
2. **Set default parameters** via COMPARE command
3. **Run comparison** and check match quality
4. **If mismatch > 5%:**
   - Check electrode voltages with multimeter
   - Verify RF voltage calibration
   - Inspect ion position (should be centered)
5. **Iterate** until match quality is "good" or "excellent"

## Performance Specifications

| Metric | Specification |
|--------|--------------|
| Theory accuracy | < 0.1% (numerical) |
| Fit accuracy | ±0.5 kHz typical |
| Scan time | ~25 seconds (41 points × 600 ms) |
| Total comparison time | < 30 seconds |
| Minimum SNR | 2:1 |
| Maximum frequency offset | ±20 kHz |

## Troubleshooting

### Comparison Always Returns Mismatch

1. **Verify electrode voltages:**
   ```python
   # Check actual voltages at trap
   actual_ec1 = read_multimeter("EC1")
   assert abs(actual_ec1 - 10.0) < 0.1
   ```

2. **Check RF calibration:**
   - Compare SMILE mV reading to HV probe measurement
   - Recalibrate if 700mV ≠ 100V

3. **Inspect ion crystal:**
   - Should be centered in trap
   - Check for RF heating (excess micromotion)

4. **Verify mass numbers:**
   - Ensure correct isotope (⁹Be⁺)
   - Check for contaminant ions

### Lorentzian Fit Fails

1. **Increase scan range:** Try ±30 kHz instead of ±20 kHz
2. **Increase dwell time:** Use 500 ms instead of 300 ms
3. **Check for multiple peaks:** May need to identify correct mode
4. **Verify PMT gain:** Ensure sufficient signal level

### Theory Calculation Diverges

1. **Check electrode signs:** EC1 and EC2 should be positive for positive ions
2. **Verify compensation signs:** May need negative voltages
3. **Check RF frequency:** Should match trap resonance (~35.85 MHz)
