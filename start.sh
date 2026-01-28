#!/bin/bash
# Start Lab Control System (Linux/Mac)
# Usage: ./start.sh [interactive|daemon|status|stop|restart]

set -e

MODE="${1:-interactive}"
cd "$(dirname "$0")"

echo "=========================================="
echo "Lab Control System - Starting in $MODE mode"
echo "=========================================="

case "$MODE" in
    interactive)
        python3 launcher.py --interactive
        ;;
    daemon)
        nohup python3 launcher.py --daemon > /dev/null 2>&1 &
        echo "Started in background (PID: $!)"
        echo "Check logs/launcher.log for status"
        ;;
    status)
        python3 launcher.py --status
        ;;
    stop)
        python3 launcher.py --stop
        ;;
    restart)
        python3 launcher.py --restart
        ;;
    *)
        echo "Usage: $0 [interactive|daemon|status|stop|restart]"
        echo ""
        echo "  interactive  - Start with interactive console (default)"
        echo "  daemon       - Start in background"
        echo "  status       - Show service status"
        echo "  stop         - Stop all services"
        echo "  restart      - Restart all services"
        exit 1
        ;;
esac
