#!/bin/bash
# One-line command to run Trap Eigenmode Experiment
# Usage: ./run_trap_eigenmode.sh -u 200 -e1 10 -e2 10 -m 9 3

cd "$(dirname "$0")"
python3 server/applet/run_trap_eigenmode.py "$@"
