"""
Camera Sweep Experiment - CLI Entry Point.

Usage:
    python run_cam_sweep.py -f 400 -s 40 -n 41
    python run_cam_sweep.py --frequency 350 --span 20 --steps 21
    python run_cam_sweep.py -f 400 --on-time 150 --off-time 150 --exposure 200
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from experiments.cam_sweep import main

if __name__ == "__main__":
    sys.exit(main())
