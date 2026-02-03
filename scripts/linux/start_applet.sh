#!/bin/bash
# Start only the Applet Flask Server

cd "$(dirname "$0")/../.."
python3 -m src.launcher --service applet
