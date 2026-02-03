"""
Launcher for the Applet Flask Server.

Usage:
    python launcher.py
    python launcher.py --port 5051
    python launcher.py --debug
"""

import sys
import argparse
import logging
from pathlib import Path

# Add project root to path for absolute imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Also add src directory to path
src_dir = project_root / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from applet.app import main

if __name__ == "__main__":
    main()
