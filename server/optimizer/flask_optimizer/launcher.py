"""
Launcher for the Optimizer Flask Server.

This can be run independently or integrated into the main launcher.
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from server.optimizer.flask_optimizer import OptimizerWebServer

def main():
    parser = argparse.ArgumentParser(description="Optimizer Flask Server Launcher")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5050, help="Port to bind to (default: 5050)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              Optimizer Flask Server                          ║
╠══════════════════════════════════════════════════════════════╣
║  URL: http://{args.host}:{args.port:<5}                            ║
║  Dashboard: http://{args.host}:{args.port}/dashboard              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    server = OptimizerWebServer(host=args.host, port=args.port, debug=args.debug)
    
    try:
        server.start(blocking=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop()

if __name__ == "__main__":
    main()
