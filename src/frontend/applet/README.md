# Applet Flask Server

Modular experimental script controller for the ion trap control system.

## Quick Start

### Start the Server

```bash
# Windows
start_applet_server.bat

# Linux/Mac
./start_applet_server.sh

# Or directly
python server/applet/launcher.py
```

The server runs on port 5051 by default.

### Run Experiments

**Trap Eigenmode:**
```bash
# Windows
run_trap_eigenmode.bat -u 200 -e1 10 -e2 10 -m 9 3

# Linux/Mac
./run_trap_eigenmode.sh -u 200 -e1 10 -e2 10 -m 9 3

# Or directly
python server/applet/run_trap_eigenmode.py -u 350 --masses 9 9 3
```

**Auto Compensation:**
```bash
# Windows
run_auto_compensation.bat

# Linux/Mac
./run_auto_compensation.sh

# Or directly
python server/applet/run_auto_comp.py
```

**Camera Sweep:**
```bash
# Windows
run_cam_sweep.bat -f 400 -s 40 -n 41

# Linux/Mac
./run_cam_sweep.sh -f 400 -s 40 -n 41

# Or directly
python server/applet/run_cam_sweep.py -f 400 --span 40 --steps 41
```

**SIM Calibration:**
```bash
# Windows
run_sim_calibration.bat

# Linux/Mac
./run_sim_calibration.sh

# Or directly
python server/applet/run_sim_calibration.py --host localhost --port 5557
```

## Available Experiments

### Trap Eigenmode (`trap_eigenmode`)

Calculates normal modes of trapped ions:

**Inputs:**
- `u_rf`: RF voltage [V]
- `ec1`: Endcap 1 voltage [V]
- `ec2`: Endcap 2 voltage [V]
- `masses`: List of ion mass numbers (e.g., `[9, 3]`)

**Outputs:**
- Eigenfrequencies (Hz)
- Mass-weighted eigenvectors
- Equilibrium positions
- Eigenmode table (CSV)
- Visualization plot (PNG)

**Usage:**
```bash
# CLI
python run_trap_eigenmode.py -u 200 -e1 10 -e2 10 -m 9 3
python run_trap_eigenmode.py -u 350 --masses 9 9 3 --theta 5.0

# Or via batch script
run_trap_eigenmode.bat -u 200 -e1 10 -e2 10 -m 9 3
```

### Auto Compensation (`auto_compensation`)

Automatically calibrates compensation voltages:

1. **Reference Recording** (Progress 5%)
   - Sets u_rf = 200V
   - Records pos_y as reference

2. **Horizontal Calibration** (Progress 10%)
   - Sets u_rf = 100V
   - Calibrates comp_h to match reference pos_y
   - Uses proportional feedback control

3. **Vertical Scan** (Progress 30-80%)
   - Scans comp_v from 30V to 50V in 1V steps
   - Random sequence to avoid systematic effects
   - Records PMT signal at each point

4. **Cubic Fit & Optimization** (Progress 80-95%)
   - Fits: PMT = a·comp_v³ + b·comp_v² + c·comp_v + d
   - Finds extremas: f'(comp_v) = 0
   - Selects middle extrema in valid range [0V, 50V]

5. **Apply Result** (Progress 95-100%)
   - Sets optimal comp_v
   - Records final PMT signal

### Camera Sweep (`cam_sweep`)

Performs secular frequency sweep with synchronized camera capture and Lorentzian fitting:

**Workflow:**
1. **Read Ion Position** (Progress 2%)
   - Reads ion position from last frame of infinity mode
   - Calculates ROI centered on ion position
   - Ensures single-ion tracking regardless of size/brightness

2. **Pause Infinity Mode** (Progress 5%)
   - Stops camera infinity recording

3. **Configure Camera** (Progress 15%)
   - Sets N frames = number of sweep steps
   - Sets ROI centered on detected ion position
   - Configures external trigger mode
   - Forces single-ion detection mode

4. **Execute Sweep** (Progress 30-70%)
   - ARTIQ runs secular sweep
   - For each frequency point:
     - Sets DDS frequency
     - Gates PMT counter
     - Triggers camera via TTL
     - Records PMT counts

5. **Perform Lorentzian Fits** (Progress 70-85%)
   - Fits Lorentzian to PMT vs frequency
   - Fits Lorentzian to sig_x vs frequency
   - Fits Lorentzian to R_y vs frequency
   - Detects poor fit quality (low R²)

6. **Save Results** (Progress 85-95%)
   - Saves sweep data with all fit parameters
   - Includes uncertainties for all fit parameters

7. **Restart Infinity Mode** (Progress 95-100%)
   - Restarts camera infinity recording

**Inputs:**
- `target_frequency_khz`: Center frequency [kHz] (default: 400)
- `span_khz`: Sweep span [kHz] (default: 40)
- `steps`: Number of frequency points (default: 41)
- `on_time_ms`: PMT gate time [ms] (default: 100)
- `off_time_ms`: Delay between points [ms] (default: 100)
- `attenuation_db`: DDS attenuation [dB] (default: 25)
- `exposure_ms`: Camera exposure [ms] (default: 300)
- `roi_size`: ROI half-size around ion [pixels] (default: 60)

**Outputs:**
- Sweep data JSON: `cam_sweep_result/cam_sweep_FREQkHz_YYYYMMDD_HHMMSS.json`
- Contains: frequency, PMT counts, sig_x, r_y for each point
- Contains: Lorentzian fit results with uncertainties for all three quantities

**Fit Quality Detection:**
- **good**: R² > 0.7, clear Lorentzian shape
- **poor**: R² > 0.3, weak or noisy signal
- **failed**: R² < 0.3 or fit did not converge

**Usage:**
```bash
# CLI
python run_cam_sweep.py -f 400 -s 40 -n 41
python run_cam_sweep.py -f 350 --span 20 --steps 21 --exposure 200 --roi-size 80

# Or via batch script
run_cam_sweep.bat -f 400 -s 40 -n 41
```

**Data Format:**
```json
{
  "timestamp": "20250130_143052",
  "ion_position": [200.5, 450.3],
  "sweep_params": {
    "target_frequency_khz": 400,
    "span_khz": 40,
    "steps": 41
  },
  "data_points": [
    {
      "frequency_khz": 380.0,
      "pmt_counts": 1250,
      "sig_x": 4.52,
      "r_y": 9.04,
      "frame_number": 0
    },
    ...
  ],
  "fits": {
    "pmt_fit": {
      "f0_kHz": 400.5,
      "f0_err_kHz": 0.8,
      "FWHM_kHz": 12.3,
      "FWHM_err_kHz": 1.2,
      "r_squared": 0.95,
      "fit_quality": "good"
    },
    "sig_x_fit": { ... },
    "r_y_fit": { ... }
  }
}
```

### SIM Calibration (`sim_calibration`)

Calibrates trap geometry parameters (kappa, chi) by measuring secular frequencies across a range of RF and endcap voltages.

**Workflow:**
1. **Load Reference Data** (Progress 5%)
   - Reads reference eigenfrequencies from `reference_eigenfrequencies.md`
   - CSV format: U_RF, V_end=10V wx, wy, V_end=20V wx, wy, ...

2. **Measure Secular Frequencies** (Progress 10-80%)
   - For each (U_RF, V_end) combination:
     - Set trap voltages via Manager
     - Measure radial X frequency (urukul0_ch1)
     - Measure radial Y frequency (urukul0_ch1)
   - Updates reference file after each measurement

3. **Run Fit** (Progress 85%)
   - Calls `fit_Kappa_Chi_URF.fit_chi_kappa_multi()`
   - Fits measured frequencies to trap model
   - Calculates chi_x, chi_y, kappa_x, kappa_y, kappa_z

4. **Update Config** (Progress 95%)
   - Saves calibrated parameters with uncertainties
   - Stores in `data/sim_calibration/sim_calibration_config.json`

**Inputs:**
- `u_rf_values`: List of RF voltages [V] (default: [57.1, 71.4, ..., 200.0])
- `v_end_values`: List of endcap voltages [V] (default: [10, 20, 30])
- `ion_masses`: Ion mass numbers (default: [9] for Be+)
- `sweep_span_khz`: Frequency sweep span [kHz] (default: 40)
- `sweep_steps`: Points per sweep (default: 41)

**Outputs:**
- Updated reference file: `reference_eigenfrequencies.md`
- Measurement data: `sim_calibration_YYYYMMDD_HHMMSS.json`
- Calibrated config: `sim_calibration_config.json`

**Usage:**
```bash
# CLI
python run_sim_calibration.py --host localhost --port 5557

# Or via batch script
run_sim_calibration.bat
```

**Axial vs Radial DDS Selection:**
- **Axial** (`urukul0_ch0`): Used for secular frequencies along the trap axis (z-direction)
- **Radial** (`urukul0_ch1`): Used for secular frequencies in the radial plane (x, y directions)

The SIM calibration primarily measures radial modes (wx, wy) as these are most sensitive to the kappa and chi parameters.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/api/experiments` | GET | List available experiments |
| `/api/experiments/start` | POST | Start experiment |
| `/api/experiments/stop` | POST | Stop experiment |
| `/api/experiments/pause` | POST | Pause experiment |
| `/api/experiments/resume` | POST | Resume experiment |
| `/api/experiments/status` | GET | Get current status |
| `/api/experiments/stream` | GET | SSE stream for real-time updates |

### Start Experiment Example

```json
POST /api/experiments/start
{
    "experiment": "auto_compensation",
    "config": {
        "manager_host": "localhost",
        "manager_port": 5557,
        "data_dir": "data/experiments"
    }
}
```

## Directory Structure

```
applet/
├── app.py                          # Flask application
├── launcher.py                     # Server entry point
├── run_auto_comp.py               # CLI entry point (auto compensation)
├── run_cam_sweep.py               # CLI entry point (camera sweep)
├── run_sim_calibration.py         # CLI entry point (SIM calibration)
├── controllers/
│   ├── __init__.py
│   └── experiment_controller.py   # Experiment management
├── experiments/
│   ├── __init__.py
│   ├── base_experiment.py         # Base class
│   ├── auto_compensation.py       # Auto compensation script
│   ├── cam_sweep.py               # Camera sweep script
│   └── sim_calibration.py         # SIM calibration script
├── templates/
│   └── index.html                 # Web dashboard
└── README.md                      # This file
```

## Adding New Experiments

1. Create a new file in `experiments/`:

```python
# experiments/my_experiment.py
from .base_experiment import BaseExperiment, ExperimentResult

class MyExperiment(BaseExperiment):
    def run(self) -> ExperimentResult:
        self.set_status(ExperimentStatus.RUNNING)
        
        # Your experiment logic
        self.set_progress(50)
        self.record_data("key", value)
        
        return ExperimentResult(
            success=True,
            data=self.data,
            message="Experiment complete"
        )
```

2. Register in `controllers/experiment_controller.py`:

```python
from experiments.my_experiment import MyExperiment

self._experiments = {
    "auto_compensation": AutoCompensationExperiment,
    "my_experiment": MyExperiment,  # Add here
}
```

## Configuration

Command-line options:

```bash
# Applet Server
python launcher.py --host 0.0.0.0 --port 5051 --debug

# Auto Compensation
python run_auto_comp.py --host localhost --port 5557 --data-dir data/experiments
```

## Data Output

Results are saved to `data/experiments/`:
- `auto_compensation_YYYYMMDD_HHMMSS.json` - Experiment data
- `auto_compensation_YYYYMMDD_HHMMSS.png` - Fit plot

Results are saved to `data/cam_sweep_result/`:
- `cam_sweep_FREQkHz_YYYYMMDD_HHMMSS.json` - Sweep data with Lorentzian fits (frequency, PMT, sig_x, r_y, fit parameters with uncertainties)

Results are saved to `data/sim_calibration/`:
- `sim_calibration_YYYYMMDD_HHMMSS.json` - Measurement data
- `sim_calibration_config.json` - Calibrated kappa/chi parameters
- Updates `reference_eigenfrequencies.md` with new measurements
