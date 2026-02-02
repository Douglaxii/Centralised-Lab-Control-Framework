"""
Flask application for optimization monitoring - ControlManager Client.

This Flask server does NOT directly control the optimizer. Instead, it:
1. Sends commands to ControlManager via HTTP/ZMQ
2. Displays status and results from ControlManager
3. Provides a web UI for monitoring only

Architecture:
    User  ←→  Flask Optimizer UI  ←→  ControlManager  ←→  OptimizerController
                                              ↑
                                         ARTIQ/LabVIEW
"""

import os
import sys
import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("optimizer.flask")


class ControlManagerClient:
    """
    Client for communicating with ControlManager.
    
    This client sends commands to ControlManager and receives responses.
    It does NOT directly access the optimizer - all commands go through
    the ControlManager.
    
    Also maintains local state for visualization purposes, including
    optimization history for the score plot.
    """
    
    def __init__(self, host: str = "localhost", port: int = 5557):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        
        # For ZMQ communication (direct to ControlManager)
        self.zmq_enabled = True
        self._zmq_context = None
        self._zmq_socket = None
        self._zmq_lock = threading.Lock()
        
        # Local state for visualization (accumulated from status polling)
        self._history: List[Dict[str, Any]] = []
        self._history_lock = threading.Lock()
        self._current_params: Optional[Dict[str, Any]] = None
        self._status_cache: Optional[Dict[str, Any]] = None
        self._status_cache_time: float = 0
        self._status_cache_ttl: float = 1.0  # Cache TTL in seconds
        
        logger.info(f"ControlManager client initialized: {host}:{port}")
    
    def _get_zmq_socket(self):
        """Get or create ZMQ socket with connection pooling."""
        import zmq
        
        with self._zmq_lock:
            if self._zmq_socket is None:
                self._zmq_context = zmq.Context()
                self._zmq_socket = self._zmq_context.socket(zmq.REQ)
                self._zmq_socket.connect(f"tcp://{self.host}:{self.port}")
                self._zmq_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
                self._zmq_socket.setsockopt(zmq.LINGER, 0)
                logger.info(f"ZMQ socket connected to {self.host}:{self.port}")
            return self._zmq_socket
    
    def _send_request(self, action: str, data: dict = None) -> dict:
        """
        Send request to ControlManager via ZMQ.
        
        Uses connection pooling for efficiency.
        """
        import zmq
        
        try:
            socket = self._get_zmq_socket()
            
            request_data = {
                "action": action,
                "source": "OPTIMIZER_FLASK",
                "timestamp": time.time()
            }
            if data:
                request_data.update(data)
            
            socket.send_json(request_data)
            response = socket.recv_json()
            
            return response
            
        except zmq.Again:
            # Timeout - recreate socket for next request
            logger.warning("ZMQ request timeout, recreating socket")
            with self._zmq_lock:
                if self._zmq_socket:
                    try:
                        self._zmq_socket.close()
                    except:
                        pass
                    self._zmq_socket = None
            return {
                "status": "error",
                "message": "Request timeout - ControlManager not responding"
            }
        except Exception as e:
            logger.error(f"ZMQ request failed: {e}")
            # Reset socket on error
            with self._zmq_lock:
                if self._zmq_socket:
                    try:
                        self._zmq_socket.close()
                    except:
                        pass
                    self._zmq_socket = None
            return {
                "status": "error",
                "message": f"Failed to communicate with ControlManager: {e}"
            }
    
    def close(self):
        """Close ZMQ socket and context."""
        with self._zmq_lock:
            if self._zmq_socket:
                try:
                    self._zmq_socket.close()
                except:
                    pass
                self._zmq_socket = None
            if self._zmq_context:
                try:
                    self._zmq_context.term()
                except:
                    pass
                self._zmq_context = None
    
    # Optimizer commands
    def optimize_start(self, **config) -> dict:
        """Start optimization via ControlManager."""
        return self._send_request("OPTIMIZE_START", config)
    
    def optimize_stop(self) -> dict:
        """Stop optimization via ControlManager."""
        return self._send_request("OPTIMIZE_STOP")
    
    def optimize_reset(self) -> dict:
        """Reset optimization via ControlManager."""
        return self._send_request("OPTIMIZE_RESET")
    
    def optimize_status(self) -> dict:
        """Get optimization status from ControlManager."""
        return self._send_request("OPTIMIZE_STATUS")
    
    def optimize_config(self, method: str = "GET", config: dict = None) -> dict:
        """Get/set optimization config via ControlManager."""
        return self._send_request("OPTIMIZE_CONFIG", {
            "method": method,
            "config": config
        })
    
    def optimize_suggestion(self) -> dict:
        """Get next suggestion from ControlManager."""
        return self._send_request("OPTIMIZE_SUGGESTION")
    
    def optimize_result(self, measurements: dict) -> dict:
        """Register result via ControlManager."""
        return self._send_request("OPTIMIZE_RESULT", {
            "measurements": measurements
        })
    
    # General ControlManager commands
    def get_system_status(self) -> dict:
        """Get general system status."""
        return self._send_request("STATUS")
    
    def get_params(self) -> dict:
        """Get current parameters."""
        return self._send_request("GET")
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get accumulated optimization history."""
        with self._history_lock:
            return self._history.copy()
    
    def clear_history(self):
        """Clear optimization history."""
        with self._history_lock:
            self._history = []
    
    def update_from_status(self, status: Dict[str, Any]):
        """
        Update local state from status response.
        Accumulates history for visualization.
        """
        if not status or not isinstance(status, dict):
            return
        
        data = status.get("data", status)  # Handle both wrapped and unwrapped
        
        # Update current params
        if "current_params" in data:
            self._current_params = data["current_params"]
        
        # Accumulate history if we have iteration and cost
        iteration = data.get("iteration")
        cost = data.get("best_value") or data.get("cost")
        phase = data.get("phase", "idle")
        
        if iteration is not None and cost is not None:
            with self._history_lock:
                # Check if we already have this iteration
                existing = next(
                    (h for h in self._history if h.get("iteration") == iteration),
                    None
                )
                if existing:
                    # Update existing entry
                    existing["cost"] = cost
                    existing["phase"] = phase
                    existing["params"] = data.get("current_params", existing.get("params"))
                else:
                    # Add new entry
                    self._history.append({
                        "iteration": iteration,
                        "phase": phase,
                        "cost": cost,
                        "params": data.get("current_params"),
                        "timestamp": time.time()
                    })
                    # Keep only last 1000 iterations to prevent memory issues
                    if len(self._history) > 1000:
                        self._history = self._history[-1000:]


# Global client instance
control_manager_client = ControlManagerClient()


def create_app() -> Flask:
    """Create Flask application."""
    
    template_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"
    
    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir)
    )
    
    # Enable CORS
    CORS(app)
    
    # Register routes
    register_routes(app)
    
    return app


def register_routes(app: Flask):
    """Register all Flask routes."""
    
    # ========================================================================
    # HTML Pages
    # ========================================================================
    
    @app.route("/")
    def index():
        """Main dashboard."""
        return render_template("index.html")
    
    @app.route("/dashboard")
    def dashboard():
        """Optimization dashboard."""
        return render_template("dashboard.html")
    
    @app.route("/parameters")
    def parameters_page():
        """Parameter configuration page."""
        return render_template("parameters.html")
    
    @app.route("/history")
    def history_page():
        """Optimization history page."""
        return render_template("history.html")
    
    @app.route("/profiles")
    def profiles_page():
        """Saved profiles page."""
        return render_template("profiles.html")
    
    # ========================================================================
    # API Routes - Status (Proxied to ControlManager)
    # ========================================================================
    
    @app.route("/api/status")
    def api_status():
        """
        Get current state of the optimization loop.
        
        Response format per documentation:
        {
          "phase": "PHASE_I_BE_LOADING",
          "iteration": 12,
          "current_params": { ... },
          "config": { ... }
        }
        """
        # Check cache first
        now = time.time()
        if (control_manager_client._status_cache and 
            now - control_manager_client._status_cache_time < control_manager_client._status_cache_ttl):
            cache_data = control_manager_client._status_cache.copy()
            cache_data["cached"] = True
            return jsonify(cache_data)
        
        # Get fresh status from ControlManager
        response = control_manager_client.optimize_status()
        
        # Update local history tracking
        if isinstance(response, dict):
            control_manager_client.update_from_status(response)
            
            # Cache the response
            control_manager_client._status_cache = response
            control_manager_client._status_cache_time = now
        
        return jsonify(response)
    
    @app.route("/api/history")
    def api_history():
        """
        Get optimization history for the Score plot.
        
        Returns accumulated cost values over iterations.
        """
        history = control_manager_client.get_history()
        return jsonify({
            "status": "success",
            "data": history,
            "count": len(history)
        })
    
    @app.route("/api/best")
    def api_best():
        """Get best parameters from ControlManager."""
        # Get from status
        status = control_manager_client.optimize_status()
        if status.get("status") == "success":
            return jsonify({
                "status": "success",
                "data": status.get("data", {}).get("best_params")
            })
        return jsonify(status)
    
    # ========================================================================
    # API Routes - Control (Proxied to ControlManager)
    # ========================================================================
    
    @app.route("/api/control/start", methods=["POST"])
    def api_start():
        """Start optimization via ControlManager."""
        data = request.get_json() or {}
        response = control_manager_client.optimize_start(**data)
        return jsonify(response)
    
    @app.route("/api/control/stop", methods=["POST"])
    def api_stop():
        """Stop optimization via ControlManager."""
        response = control_manager_client.optimize_stop()
        return jsonify(response)
    
    @app.route("/api/control/reset", methods=["POST"])
    def api_reset():
        """Reset optimization via ControlManager."""
        # Clear local history on reset
        control_manager_client.clear_history()
        response = control_manager_client.optimize_reset()
        return jsonify(response)
    
    @app.route("/api/control/skip/<phase>", methods=["POST"])
    def api_skip_phase(phase: str):
        """Skip to a specific phase."""
        # This would need to be implemented in ControlManager
        return jsonify({
            "status": "error",
            "message": "Phase skip not yet implemented"
        }), 501
    
    # ========================================================================
    # API Routes - Configuration (Proxied to ControlManager)
    # ========================================================================
    
    @app.route("/api/config", methods=["GET"])
    def api_get_config():
        """Get configuration from ControlManager."""
        response = control_manager_client.optimize_config(method="GET")
        return jsonify(response)
    
    @app.route("/api/config", methods=["POST"])
    def api_set_config():
        """Update configuration via ControlManager."""
        data = request.get_json() or {}
        response = control_manager_client.optimize_config(
            method="POST",
            config=data
        )
        return jsonify(response)
    
    # ========================================================================
    # API Routes - Profiles (Local storage)
    # ========================================================================
    
    @app.route("/api/profiles")
    def api_profiles():
        """Get all saved profiles."""
        try:
            from server.optimizer.storage import ProfileStorage
            storage = ProfileStorage()
            profiles = storage.list_profiles()
            return jsonify({
                "status": "success",
                "data": profiles,
                "count": len(profiles)
            })
        except Exception as e:
            logger.error(f"Error listing profiles: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            })
    
    @app.route("/api/profiles/<key>")
    def api_profile_detail(key: str):
        """Get specific profile."""
        try:
            from server.optimizer.storage import ProfileStorage
            storage = ProfileStorage()
            
            # Parse key like "be_1" or "be_1_hd"
            parts = key.split("_")
            if len(parts) < 2:
                return jsonify({
                    "status": "error",
                    "message": "Invalid profile key format"
                }), 400
            
            try:
                be_count = int(parts[1])
            except (IndexError, ValueError):
                return jsonify({
                    "status": "error",
                    "message": "Invalid Be+ count in profile key"
                }), 400
            
            hd_present = "hd" in parts
            
            profile = storage.get_profile(be_count, hd_present)
            
            if profile is None:
                return jsonify({
                    "status": "error",
                    "message": "Profile not found"
                }), 404
            
            return jsonify({
                "status": "success",
                "data": profile
            })
        except Exception as e:
            logger.error(f"Error loading profile: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            })
    
    # ========================================================================
    # API Routes - Parameter Spaces (Local - static info)
    # ========================================================================
    
    @app.route("/api/parameters/spaces")
    def api_parameter_spaces():
        """Get parameter space definitions."""
        try:
            from server.optimizer.parameters import (
                create_be_loading_space,
                create_be_ejection_space,
                create_hd_loading_space
            )
            
            spaces = {}
            
            for name, create_fn in [
                ("be_loading", create_be_loading_space),
                ("be_ejection", create_be_ejection_space),
                ("hd_loading", create_hd_loading_space)
            ]:
                try:
                    space = create_fn()
                    spaces[name] = {
                        "n_dims": space.get_n_dims(),
                        "parameters": {
                            name: {
                                "type": param.param_type.value,
                                "bounds": param.bounds,
                                "default": param.default,
                                "unit": param.unit,
                                "description": param.description
                            }
                            for name, param in space.parameters.items()
                        }
                    }
                except Exception as e:
                    logger.error(f"Error creating space {name}: {e}")
            
            return jsonify({
                "status": "success",
                "data": spaces
            })
        except Exception as e:
            logger.error(f"Error loading parameter spaces: {e}")
            return jsonify({
                "status": "error",
                "message": str(e)
            })
    
    # ========================================================================
    # Static Files
    # ========================================================================
    
    @app.route("/static/<path:filename>")
    def static_files(filename):
        """Serve static files."""
        return send_from_directory(app.static_folder, filename)
    
    # ========================================================================
    # Error Handlers
    # ========================================================================
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "status": "error",
            "message": "Not found"
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500


class OptimizerWebServer:
    """
    Wrapper class for running the Flask optimizer server.
    
    Usage:
        server = OptimizerWebServer(host='0.0.0.0', port=5050)
        server.start()
        # ... run in background ...
        server.stop()
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5050,
        debug: bool = False,
        control_manager_host: str = "localhost",
        control_manager_port: int = 5557
    ):
        self.host = host
        self.port = port
        self.debug = debug
        
        # Update global client
        global control_manager_client
        control_manager_client = ControlManagerClient(
            host=control_manager_host,
            port=control_manager_port
        )
        
        self.app = create_app()
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self, blocking: bool = False):
        """Start the server."""
        if self._running:
            logger.warning("Server already running")
            return
        
        self._running = True
        
        if blocking:
            logger.info(f"Starting Optimizer Flask server on {self.host}:{self.port}")
            self.app.run(host=self.host, port=self.port, debug=self.debug, threaded=True)
        else:
            self._thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name="OptimizerFlaskServer"
            )
            self._thread.start()
            logger.info(f"Optimizer Flask server started on {self.host}:{self.port}")
    
    def _run_server(self):
        """Run server in thread."""
        try:
            self.app.run(host=self.host, port=self.port, debug=False, threaded=True)
        except Exception as e:
            logger.error(f"Flask server error: {e}")
            self._running = False
    
    def stop(self):
        """Stop the server."""
        self._running = False
        # Close ZMQ connections
        control_manager_client.close()
        logger.info("Optimizer Flask server stopped")
    
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running


# Main entry point
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Optimizer Flask Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5050, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--cm-host", default="localhost", help="ControlManager host")
    parser.add_argument("--cm-port", type=int, default=5557, help="ControlManager port")
    
    args = parser.parse_args()
    
    server = OptimizerWebServer(
        host=args.host,
        port=args.port,
        debug=args.debug,
        control_manager_host=args.cm_host,
        control_manager_port=args.cm_port
    )
    
    server.start(blocking=True)
