#!/bin/bash
echo "Usage: run_experiment.sh <experiment_name>"
if [ -z "$1" ]; then
    echo "Please provide an experiment name"
    exit 1
fi
cd "$(dirname "$0")/../.."
python -m src.applet.run_$1
