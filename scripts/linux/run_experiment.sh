#!/bin/bash
# Run any applet experiment
# Usage: ./run_experiment.sh [experiment_name] [options]
# Example: ./run_experiment.sh auto_compensation

cd "$(dirname "$0")/../.."
EXPERIMENT="$1"
shift
python3 -m "src.applet.run_${EXPERIMENT}" "$@"
