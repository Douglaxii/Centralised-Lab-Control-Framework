#!/usr/bin/env python3
"""
One-line command to run Auto Compensation Experiment.

Usage:
    python run_auto_comp.py                    # Run with defaults
    python run_auto_comp.py --host localhost --port 5557
    python -m applet.run_auto_comp             # As module

This is a thin wrapper around experiments.auto_compensation.main()
"""

import sys
from pathlib import Path

# Add applet to path
sys.path.insert(0, str(Path(__file__).parent))

from experiments.auto_compensation import main

if __name__ == "__main__":
    sys.exit(main())
