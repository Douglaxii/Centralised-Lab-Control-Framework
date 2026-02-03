#!/bin/bash
# Start only the Optimizer Flask Server

cd "$(dirname "$0")/../.."
python3 -m src.launcher --service optimizer
