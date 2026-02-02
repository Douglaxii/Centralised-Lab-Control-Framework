"""
SIM Calibration Experiment - CLI Entry Point.

Usage:
    python run_sim_calibration.py --host localhost --port 5557
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from experiments.sim_calibration import main

if __name__ == "__main__":
    sys.exit(main())
