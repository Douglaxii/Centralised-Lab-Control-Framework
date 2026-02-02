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

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from app import main

if __name__ == "__main__":
    main()
