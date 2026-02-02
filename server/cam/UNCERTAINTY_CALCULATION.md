# Ion Fit Uncertainty Calculation

This document describes how uncertainties (errors) are calculated for ion fit parameters.

## Overview

Uncertainties are calculated for the following parameters:
- `pos_x_err`: Uncertainty in X position (pixels)
- `pos_y_err`: Uncertainty in Y position (pixels)
- `sig_x_err`: Uncertainty in Gaussian sigma X (pixels)
- `R_y_err`: Uncertainty in R_y (SHM turning point in Y) (pixels)

## Calculation Methods

### 1. Simple Moments-Based Fitting (Default)

When `curve_fit` is not available or fails, the algorithm falls back to moments-based fitting.

#### Position Uncertainty (pos_x_err, pos_y_err)

```python
pos_x_err = sig_x / (snr + 1e-6)
pos_y_err = sig_y / (snr + 1e-6)
```

**Theory**: The position uncertainty is inversely proportional to the signal-to-noise ratio. A higher SNR means better precision in determining the centroid.

- `sig_x`, `sig_y`: Gaussian width (standard deviation) in x and y
- `snr`: Signal-to-noise ratio = amplitude / noise

**Physical interpretation**: The uncertainty scales with the spot size divided by the signal quality. A larger spot with low SNR has higher uncertainty.

#### Width Uncertainty (sig_x_err, R_y_err)

```python
N_eff = max(1, np.sum(region > background + noise))
sig_x_err = sig_x / np.sqrt(2 * N_eff)
R_y_err = sig_y * 2.355 / np.sqrt(2 * N_eff)
```

**Theory**: The width uncertainty follows from Gaussian statistics where the relative uncertainty in variance estimation scales as 1/√(2N), where N is the number of effective pixels.

- `N_eff`: Effective number of pixels contributing to the signal (pixels above background + noise)
- `2.355`: Conversion factor from sigma to FWHM (R_y = σ_y × 2.355)

**Physical interpretation**: More pixels contributing to the ion signal means better statistics and lower uncertainty in the width measurement.

### 2. Full 2D Gaussian Fitting (When SciPy Available)

When `scipy.optimize.curve_fit` is available and succeeds:

```python
popt, pcov = curve_fit(gaussian_2d, (x_indices, y_indices), region.ravel(), p0=p0)
perr = np.sqrt(np.diag(pcov))
x0_err, y0_err, sx_err, sy_err = perr[1], perr[2], perr[3], perr[4]
```

**Theory**: The covariance matrix (`pcov`) from least-squares fitting provides direct uncertainty estimates based on the fit residuals and the Jacobian of the model.

The diagonal elements of the covariance matrix represent the variance of each fitted parameter. Taking the square root gives the standard deviation (1σ uncertainty).

**Advantages**:
- Accounts for correlations between parameters
- Based on actual fit residuals
- More accurate for non-ideal Gaussian profiles

## Typical Values

From test data with good quality ions (SNR ~ 200-250):

| Parameter | Typical Value | Typical Uncertainty |
|-----------|---------------|---------------------|
| pos_x | ~133 pixels | ±0.05 pixels |
| pos_y | ~133 pixels | ±0.05 pixels |
| sig_x | ~13 pixels | ±0.3 pixels |
| R_y | ~31 pixels | ±0.7 pixels |

## Factors Affecting Uncertainty

1. **Signal-to-Noise Ratio (SNR)**: Higher SNR → Lower uncertainty
2. **Ion Spot Size**: Larger spots have inherently higher position uncertainty
3. **Number of Pixels**: More pixels in the ROI → Better statistics → Lower uncertainty
4. **Background Level**: Higher background → Lower effective SNR → Higher uncertainty

## Usage in Analysis

The uncertainties can be used for:
- Weighted averaging of ion positions across multiple frames
- Tracking ion drift with proper error bars
- Determining if two ions are resolvable
- Quality control (reject fits with excessive uncertainty)

## File Output

Uncertainties are saved in a separate JSON file in the `ion_uncertainty/` folder:

```json
{
  "timestamp": "2026-02-02T16:53:59.185973",
  "frame_number": 0,
  "image_name": "2024_08_09_4_frame_1.jpg",
  "ions": {
    "ion_1": {
      "pos_x": 133.62,
      "pos_y": 133.19,
      "sig_x": 13.44,
      "R_y": 31.20,
      "pos_x_err": 0.053,
      "pos_y_err": 0.053,
      "sig_x_err": 0.288,
      "R_y_err": 0.669,
      "snr": 252.0
    }
  }
}
```

## References

1. Numerical Recipes in C, Chapter 15: Modeling of Data
2. Bevington & Robinson, Data Reduction and Error Analysis for the Physical Sciences
3. scipy.optimize.curve_fit documentation: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html
