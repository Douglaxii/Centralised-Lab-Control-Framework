#!/bin/bash
# Start the Applet Flask Server
# Usage: ./start_applet_server.sh [options]

cd "$(dirname "$0")"
python3 server/applet/launcher.py "$@"
