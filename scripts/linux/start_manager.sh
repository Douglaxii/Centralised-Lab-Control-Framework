#!/bin/bash
# Start only the Control Manager

cd "$(dirname "$0")/../.."
python3 -m src.launcher --service manager
