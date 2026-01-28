# Lab PC Deployment Package

**Target System:** Lab PC (Windows with LabVIEW)  
**Purpose:** LabVIEW integration for data sending (SMILE, Wavemeter)

## Contents

```
deploy_lab_pc/
├── labview/            # LabVIEW VIs and Python interface
│   ├── SMILE_Data_Sender.vi
│   ├── Wavemeter_Data_Sender.vi
│   └── mock_labview_sender.py
├── core/               # Shared utilities (config, logging, ZMQ)
├── config/             # Configuration files
├── tests/              # Unit tests
├── docs/               # Documentation
├── lab_comms.py        # Communication library
└── requirements.txt    # Python dependencies
```

## Quick Start

### 1. Clone to Lab PC

Copy this `deploy_lab_pc/` folder to your Lab PC (e.g., `C:\LabControl\`)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Edit `config/settings.yaml` with your network settings:
- `master_ip`: IP of the Master/Server PC
- `labview_port`: Port for LabVIEW communication

### 4. Run LabVIEW VIs

Open in LabVIEW:
- `labview/SMILE_Data_Sender.vi` - Send SMILE spectrometer data
- `labview/Wavemeter_Data_Sender.vi` - Send wavemeter data

Or use the Python mock sender for testing:
```bash
python labview/mock_labview_sender.py
```

## Main Components

| File | Purpose |
|------|---------|
| `labview/SMILE_Data_Sender.vi` | Send SMILE spectrometer readings |
| `labview/Wavemeter_Data_Sender.vi` | Send laser wavemeter data |
| `labview/mock_labview_sender.py` | Python mock for testing |
| `lab_comms.py` | Communication library |

## Network Requirements

- Must be able to reach Master PC on ZMQ ports
- LabVIEW must have TCP/IP support enabled

## See Also

- LabVIEW Integration: `docs/LABVIEW_INTEGRATION.md`
- Main project: `../README.md`
