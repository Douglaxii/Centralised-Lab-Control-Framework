"""
Applet Flask Server

Provides web interface and API for running experimental scripts.
Default port: 5051

Endpoints:
    /               - Main dashboard
    /api/experiments        - List available experiments
    /api/experiments/start  - Start experiment
    /api/experiments/stop   - Stop experiment
    /api/experiments/status - Get status
    /api/experiments/stream - SSE stream of progress
"""

import sys
import json
import time
import logging
from pathlib import Path
from typing import Generator

from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("applet.server")

# Create Flask app
template_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

app = Flask(
    __name__,
    template_folder=str(template_dir),
    static_folder=str(static_dir)
)
CORS(app)

# Import controller
from controllers import controller
from experiments import ExperimentStatus

# SSE clients
sse_clients: list = []


def broadcast_progress(progress: float):
    """Broadcast progress to all SSE clients."""
    message = f'data: {{"type": "progress", "value": {progress}}}\n\n'
    for client in sse_clients[:]:
        try:
            client.put(message)
        except:
            pass


def broadcast_status(status: ExperimentStatus):
    """Broadcast status to all SSE clients."""
    message = f'data: {{"type": "status", "value": "{status.value}"}}\n\n'
    for client in sse_clients[:]:
        try:
            client.put(message)
        except:
            pass


# Register callbacks
controller.register_progress_callback(broadcast_progress)
controller.register_status_callback(broadcast_status)


# ==================== HTML Routes ====================

@app.route("/")
def index():
    """Main dashboard."""
    experiments = controller.list_experiments()
    return render_template("index.html", experiments=experiments)


# ==================== API Routes ====================

@app.route("/api/experiments", methods=["GET"])
def list_experiments():
    """List available experiments."""
    return jsonify({
        "status": "success",
        "experiments": controller.list_experiments()
    })


@app.route("/api/experiments/start", methods=["POST"])
def start_experiment():
    """
    Start an experiment.
    
    Request body:
        {
            "experiment": "auto_compensation",
            "config": {  # optional
                "manager_host": "localhost",
                "manager_port": 5557
            }
        }
    """
    data = request.get_json() or {}
    exp_id = data.get("experiment")
    config = data.get("config", {})
    
    if not exp_id:
        return jsonify({
            "status": "error",
            "message": "Missing 'experiment' field"
        }), 400
    
    result = controller.start(exp_id, config)
    return jsonify(result)


@app.route("/api/experiments/stop", methods=["POST"])
def stop_experiment():
    """Stop current experiment."""
    result = controller.stop()
    return jsonify(result)


@app.route("/api/experiments/pause", methods=["POST"])
def pause_experiment():
    """Pause current experiment."""
    result = controller.pause()
    return jsonify(result)


@app.route("/api/experiments/resume", methods=["POST"])
def resume_experiment():
    """Resume paused experiment."""
    result = controller.resume()
    return jsonify(result)


@app.route("/api/experiments/status", methods=["GET"])
def get_status():
    """Get current experiment status."""
    return jsonify({
        "status": "success",
        **controller.get_status()
    })


@app.route("/api/experiments/stream")
def stream():
    """SSE stream for real-time updates."""
    def event_stream():
        import queue
        q = queue.Queue()
        sse_clients.append(q)
        
        try:
            # Send initial status
            status = controller.get_status()
            yield f'data: {{"type": "init", "data": {json.dumps(status)}}}\n\n'
            
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    # Send heartbeat
                    yield ': heartbeat\n\n'
        finally:
            if q in sse_clients:
                sse_clients.remove(q)
    
    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500


# ==================== Main Entry Point ====================

def main():
    """Run the Applet Flask Server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Applet Flask Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5051, help="Port to bind to (default: 5051)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              Applet Flask Server                             ║
╠══════════════════════════════════════════════════════════════╣
║  URL: http://{args.host}:{args.port:<5}                            ║
║                                                              ║
║  Available Experiments:                                      ║
{"║    - trap_eigenmode":<63}║
{"║    - auto_compensation":<63}║
{"║    - cam_sweep":<63}║
{"║    - sim_calibration":<63}║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    logger.info(f"Starting Applet Server on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
