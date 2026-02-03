#!/bin/bash
# Run Trap Eigenmode Experiment
# Usage: ./run_trap_eigenmode.sh -u 200 -e1 10 -e2 10 -m 9 3

cd "$(dirname "$0")/../.."
python3 -m src.applet.trap_eigenmode "$@"
