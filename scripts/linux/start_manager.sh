#!/bin/bash
echo "Starting MLS Control Manager..."
cd "$(dirname "$0")/../.."
python -m src.server.manager.manager
