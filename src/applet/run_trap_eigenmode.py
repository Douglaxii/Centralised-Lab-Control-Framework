#!/usr/bin/env python3
"""
One-line command to run Trap Eigenmode Experiment.

Usage:
    python run_trap_eigenmode.py -u 200 -e1 10 -e2 10 -m 9 3
    python -m applet.run_trap_eigenmode -u 350 --masses 9 9 3
    
This is a thin wrapper around experiments.trap_eigenmode.main()
"""

import sys
from pathlib import Path

# Add applet to path
sys.path.insert(0, str(Path(__file__).parent))

from experiments.trap_eigenmode import main

if __name__ == "__main__":
    sys.exit(main())
