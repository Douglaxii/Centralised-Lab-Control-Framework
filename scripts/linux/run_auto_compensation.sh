#!/bin/bash
# Run Auto Compensation Experiment
# Usage: ./run_auto_compensation.sh [options]

cd "$(dirname "$0")/../.."
python3 -m src.applet.auto_compensation "$@"
