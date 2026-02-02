#!/bin/bash
# One-line command to run Auto Compensation Experiment
# Usage: ./run_auto_compensation.sh [options]

cd "$(dirname "$0")"
python3 server/applet/run_auto_comp.py "$@"
