#!/bin/bash
# MLS Unified Launcher - Start all services
# Usage: ./start_all.sh [options]

cd "$(dirname "$0")/../.."

echo "=========================================="
echo "MLS Lab Control System"
echo "=========================================="

if [ $# -eq 0 ]; then
    echo "Starting all services..."
    echo ""
    echo "Services:"
    echo "  - Manager      (ZMQ)     Port 5557"
    echo "  - Dashboard    (Flask)   Port 5000  http://localhost:5000"
    echo "  - Applet       (Flask)   Port 5051  http://localhost:5051"
    echo "  - Optimizer    (Flask)   Port 5050  http://localhost:5050"
    echo ""
    python3 -m src.launcher
elif [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    python3 -m src.launcher --help
else
    python3 -m src.launcher "$@"
fi
