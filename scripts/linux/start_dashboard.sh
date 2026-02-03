#!/bin/bash
# Start only the Dashboard Flask Server

cd "$(dirname "$0")/../.."
python3 -m src.launcher --service flask
