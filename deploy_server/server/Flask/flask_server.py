"""
Flask Web UI Server for Lab Control Framework - Scientific Dashboard

Provides web interface for:
- CCD Camera streaming with position overlays (Top-Left)
- Control Cockpit (Bottom-Left): Voltages, Hardware Toggles, Lasers
- Real-time Telemetry Stack - 7 graphs (Top-Right)
- Turbo Algorithm Status & Safety Switch (Bottom-Right)

Layout (2 Columns):
- Left Column (50%): Camera Feed (75%) + Controls (25%)
- Right Column (50%): Telemetry Stack (80%) + Safety/Turbo Log (20%)

Theme: Flat, Lightweight, Scientific
Palette: Off-white background (#F9FAFB), White cards (#FFFFFF), 1px borders (#E5E7EB)
Typography: Inter/Roboto for UI, Fira Code for data/logs
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from flask import Flask, render_template, jsonify, Response, request, send_from_directory
import zmq
import json
import time
import threading
import cv2
import numpy as np
import logging
from collections import deque
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from core import get_config, setup_logging, get_tracker
from core.enums import SystemMode, AlgorithmState

# Import data ingestion server (shared telemetry storage)
try:
    from server.communications.data_server import (
        get_telemetry_data, 
        get_data_sources,
        DataIngestionServer
    )
    DATA_SERVER_AVAILABLE = True
except ImportError:
    DATA_SERVER_AVAILABLE = False
    logger.warning("DataIngestionServer not available - will use simulated data only")

# =============================================================================
# SETUP & CONFIGURATION
# =============================================================================

logger = setup_logging(component="flask")
config = get_config()

# Network configuration
MANAGER_IP = config.get_network('master_ip') or "127.0.0.1"
MANAGER_PORT = config.client_port

# Camera configuration
CAMERA_HOST = config.get_camera_setting('host') or "127.0.0.1"
CAMERA_PORT = config.get_camera_setting('port') or 5555
LIVE_FRAMES_PATH = config.get_path('live_frames') if hasattr(config, 'get_path') else Path(__file__).parent / "live_frames"

app = Flask(__name__)

# =============================================================================
# DATA STRUCTURES & STATE MANAGEMENT
# =============================================================================

# SystemMode and AlgorithmState now imported from core.enums

@dataclass
class TurboAlgorithmLog:
    """Structured log entry for Turbo algorithm."""
    timestamp: float
    formatted_time: str
    level: str  # INFO, WARNING, ERROR, ITERATION
    message: str
    iteration: Optional[int] = None
    delta: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "time": self.formatted_time,
            "level": self.level,
            "message": self.message,
            "iteration": self.iteration,
            "delta": self.delta
        }


@dataclass 
class CameraState:
    """Camera feed state with latency tracking and fit parameters."""
    last_frame_time: float = 0.0
    last_frame_timestamp: float = 0.0
    fps: float = 0.0
    latency_ms: float = 0.0
    is_live: bool = False
    high_delay_warning: bool = False
    frame_count: int = 0
    ion_position: Dict[str, Any] = field(default_factory=lambda: {"x": 0, "y": 0, "found": False})
    
    def update_latency(self, frame_timestamp: float):
        """Update latency metrics based on frame timestamp."""
        now = time.time()
        self.last_frame_time = now
        self.last_frame_timestamp = frame_timestamp
        self.latency_ms = (now - frame_timestamp) * 1000
        self.high_delay_warning = self.latency_ms > 500
        self.frame_count += 1
        self.is_live = True
    
    def update_ion_position(self, x: float, y: float, found: bool, **fit_params):
        """Update ion position and fit parameters."""
        self.ion_position = {"x": x, "y": y, "found": found, **fit_params}


# =============================================================================
# THREAD-SAFE DATA STORES
# =============================================================================

# Telemetry data: 300 seconds rolling window at 1Hz = 300 points
# Stored as (timestamp, value) tuples for accurate time-window rendering
TELEMETRY_WINDOW_SECONDS = 300
TELEMETRY_MAX_POINTS = 1000  # Extra buffer for higher frequency data

telemetry_data: Dict[str, deque] = {
    "pos_x": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pos_y": deque(maxlen=TELEMETRY_MAX_POINTS),
    "sig_x": deque(maxlen=TELEMETRY_MAX_POINTS),
    "sig_y": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pressure": deque(maxlen=TELEMETRY_MAX_POINTS),
    "laser_freq": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pmt": deque(maxlen=TELEMETRY_MAX_POINTS),
}
telemetry_lock = threading.RLock()

# Turbo algorithm logs (structured)
turbo_algorithm_logs: deque = deque(maxlen=500)
turbo_logs_lock = threading.RLock()

# Turbo algorithm state
turbo_state = {
    "status": AlgorithmState.IDLE.value,
    "current_iteration": 0,
    "convergence_delta": 0.0,
    "target_parameter": None,
    "start_time": None,
    "safety_engaged": True,  # Default to safe mode
}
turbo_state_lock = threading.Lock()

# Camera state
camera_state = CameraState()
camera_lock = threading.Lock()

# Current hardware state
current_state = {
    "mode": SystemMode.MANUAL.value,
    "params": {
        # RF Voltage
        "u_rf": 500.0,
        # Electrodes
        "ec1": 0.0, "ec2": 0.0,
        "comp_h": 0.0, "comp_v": 0.0,
        # Toggles
        "bephi": False, "b_field": True, "be_oven": False,
        # Laser & Electron
        "uv3": False, "e_gun": False,
        "piezo": 0.0,
        # DDS
        "dds_profile": 0,
    },
    "worker_alive": False,
    "camera_active": False,
}
state_lock = threading.RLock()

# =============================================================================
# ZMQ COMMUNICATION
# =============================================================================

zmq_ctx = zmq.Context()
manager_socket: Optional[zmq.Socket] = None
zmq_lock = threading.Lock()


def get_manager_socket() -> zmq.Socket:
    """Get or create ZMQ socket to manager with connection pooling."""
    global manager_socket
    if manager_socket is None:
        manager_socket = zmq_ctx.socket(zmq.REQ)
        manager_socket.connect(f"tcp://{MANAGER_IP}:{MANAGER_PORT}")
        manager_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
        manager_socket.setsockopt(zmq.LINGER, 0)  # Don't wait on close
        logger.info(f"Connected to manager at {MANAGER_IP}:{MANAGER_PORT}")
    return manager_socket


def send_to_manager(message: Dict[str, Any], timeout_ms: int = 5000) -> Dict[str, Any]:
    """
    Send request to manager and return response with retry logic.
    
    Args:
        message: Request dictionary
        timeout_ms: Timeout in milliseconds
        
    Returns:
        Response dictionary
    """
    with zmq_lock:
        for attempt in range(2):  # Retry once
            try:
                sock = get_manager_socket()
                sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
                sock.send_json(message)
                return sock.recv_json()
            except zmq.Again:
                logger.warning(f"Manager request timeout (attempt {attempt + 1})")
                global manager_socket
                if manager_socket:
                    manager_socket.close()
                    manager_socket = None
                if attempt == 0:
                    time.sleep(0.1)  # Brief delay before retry
                else:
                    return {"status": "error", "message": "Manager timeout", "code": "TIMEOUT"}
            except zmq.ZMQError as e:
                logger.error(f"ZMQ error: {e}")
                manager_socket = None
                if attempt == 0:
                    time.sleep(0.1)
                else:
                    return {"status": "error", "message": f"ZMQ error: {e}", "code": "ZMQ_ERROR"}
            except Exception as e:
                logger.error(f"Manager request failed: {e}")
                return {"status": "error", "message": str(e), "code": "EXCEPTION"}
        return {"status": "error", "message": "Max retries exceeded", "code": "MAX_RETRIES"}


def safe_shutdown() -> Dict[str, Any]:
    """
    Emergency shutdown: Stop Turbo algorithm and reset all hardware to safe defaults.
    This is called when the safety switch is engaged.
    """
    logger.warning("SAFETY SHUTDOWN TRIGGERED - Stopping algorithm and resetting hardware")
    
    # Step 1: Send STOP signal to manager
    stop_response = send_to_manager({
        "action": "STOP",
        "source": "FLASK_SAFETY",
        "reason": "Safety switch engaged"
    }, timeout_ms=3000)
    
    # Step 2: Reset all hardware voltages to safe defaults (0V)
    safe_params = {
        "u_rf": 0.0,
        "ec1": 0.0, "ec2": 0.0,
        "comp_h": 0.0, "comp_v": 0.0,
        "piezo": 0.0,
    }
    
    reset_response = send_to_manager({
        "action": "SET",
        "source": "FLASK_SAFETY",
        "params": safe_params,
        "reason": "Safety shutdown"
    }, timeout_ms=5000)
    
    # Step 3: Turn off all toggles
    toggle_params = {
        "bephi": False,
        "b_field": False, 
        "be_oven": False,
        "uv3": False,
        "e_gun": False,
    }
    
    toggle_response = send_to_manager({
        "action": "SET",
        "source": "FLASK_SAFETY",
        "params": toggle_params,
        "reason": "Safety shutdown"
    }, timeout_ms=5000)
    
    # Update local state
    with state_lock:
        current_state["params"].update(safe_params)
        current_state["params"].update(toggle_params)
        current_state["mode"] = SystemMode.SAFE.value
    
    with turbo_state_lock:
        turbo_state["status"] = AlgorithmState.STOPPED.value
        turbo_state["safety_engaged"] = True
    
    # Log the safety event
    add_turbo_log(
        level="ERROR",
        message="SAFETY MODE ENGAGED: Algorithm stopped, hardware reset to defaults",
        iteration=None,
        delta=None
    )
    
    return {
        "status": "success" if stop_response.get("status") == "success" else "partial",
        "stop_result": stop_response,
        "reset_result": reset_response,
        "toggle_result": toggle_response
    }


# =============================================================================
# TURBO ALGORITHM LOGGING
# =============================================================================

def add_turbo_log(level: str, message: str, iteration: Optional[int] = None, delta: Optional[float] = None):
    """Add a structured log entry for the Turbo algorithm."""
    with turbo_logs_lock:
        now = time.time()
        log_entry = TurboAlgorithmLog(
            timestamp=now,
            formatted_time=datetime.fromtimestamp(now).strftime("%H:%M:%S"),
            level=level,
            message=message,
            iteration=iteration,
            delta=delta
        )
        turbo_algorithm_logs.append(log_entry)
    
    # Also log to system logger for persistence
    if level == "ERROR":
        logger.error(f"[Turbo] {message}")
    elif level == "WARNING":
        logger.warning(f"[Turbo] {message}")
    else:
        logger.info(f"[Turbo] {message}")


def update_turbo_state(status: str, iteration: Optional[int] = None, 
                       delta: Optional[float] = None, target: Optional[str] = None):
    """Update the Turbo algorithm state."""
    with turbo_state_lock:
        turbo_state["status"] = status
        if iteration is not None:
            turbo_state["current_iteration"] = iteration
        if delta is not None:
            turbo_state["convergence_delta"] = delta
        if target is not None:
            turbo_state["target_parameter"] = target
        if status == AlgorithmState.RUNNING.value and turbo_state["start_time"] is None:
            turbo_state["start_time"] = time.time()


# =============================================================================
# CAMERA STREAMING
# =============================================================================

def read_frame_from_disk() -> Optional[Tuple[np.ndarray, float, Dict[str, Any]]]:
    """
    Read the latest frame from disk and associated fit parameters.
    
    Returns:
        Tuple of (frame, timestamp, fit_params) or None if no frame available
    """
    try:
        frame_path = Path(LIVE_FRAMES_PATH)
        if not frame_path.exists():
            return None
            
        # Find latest frame file
        frame_files = list(frame_path.glob("frame*.jpg"))
        if not frame_files:
            return None
            
        latest = max(frame_files, key=lambda p: p.stat().st_mtime)
        
        # Check if frame is fresh (within last 5 seconds)
        mtime = latest.stat().st_mtime
        if time.time() - mtime > 5.0:
            return None  # Stale frame
            
        frame = cv2.imread(str(latest))
        if frame is None:
            return None
        
        # Try to find matching JSON with fit parameters
        fit_params = {}
        try:
            # Look for JSON files in the cam_json folder
            from datetime import datetime
            current_date_str = datetime.now().strftime("%y%m%d")
            json_folder = Path(f"Y:/Xi/Data/{current_date_str}/cam_json")
            
            if json_folder.exists():
                # Find JSON files close in time to the frame
                json_files = list(json_folder.glob("*_data.json"))
                if json_files:
                    # Get the most recent JSON
                    latest_json = max(json_files, key=lambda p: p.stat().st_mtime)
                    json_mtime = latest_json.stat().st_mtime
                    
                    # Only use if recent (within 2 seconds of frame)
                    if abs(json_mtime - mtime) < 2.0:
                        with open(latest_json, 'r') as f:
                            data = json.load(f)
                            if data.get("atoms"):
                                # Use first atom's fit parameters
                                atom = data["atoms"][0]
                                fit_params = {
                                    "sig_x": atom.get("sig_x", 0),
                                    "sig_y": atom.get("sig_y", 0),
                                    "theta": atom.get("theta", 0),
                                    "amp": atom.get("amp", 0)
                                }
        except Exception:
            pass  # No fit params available
            
        return frame, mtime, fit_params
        
    except Exception as e:
        logger.debug(f"Frame read failed: {e}")
        return None


def update_ion_position_from_file():
    """
    Update camera_state ion position and fit parameters from latest JSON file.
    Called periodically to sync with image handler output.
    """
    try:
        from datetime import datetime
        current_date_str = datetime.now().strftime("%y%m%d")
        json_folder = Path(f"Y:/Xi/Data/{current_date_str}/cam_json")
        
        if not json_folder.exists():
            return
            
        json_files = list(json_folder.glob("*_data.json"))
        if not json_files:
            return
            
        # Get most recent JSON
        latest_json = max(json_files, key=lambda p: p.stat().st_mtime)
        
        # Check if fresh (within last 3 seconds)
        if time.time() - latest_json.stat().st_mtime > 3.0:
            return
            
        with open(latest_json, 'r') as f:
            data = json.load(f)
            
        if not data.get("atoms"):
            return
            
        # Use first atom for display
        atom = data["atoms"][0]
        
        with camera_lock:
            camera_state.ion_position = {
                "x": atom.get("x0", 0),
                "y": atom.get("y0", 0),
                "found": True,
                "sig_x": atom.get("sig_x", 0),
                "sig_y": atom.get("sig_y", 0),
                "theta": atom.get("theta", 0),
                "amp": atom.get("amp", 0)
            }
            
    except Exception:
        pass


def add_overlay_to_frame(frame: np.ndarray, pos: Dict[str, Any], latency_ms: float) -> np.ndarray:
    """
    Add position markers and status overlays to frame.
    Displays only a thin outer circle (no crosshair) and fit parameters.
    
    Args:
        frame: Input image
        pos: Ion position dict with 'x', 'y', 'found', and optional fit params
        latency_ms: Current latency in milliseconds
        
    Returns:
        Frame with overlays
    """
    h, w = frame.shape[:2]
    
    # Add position marker if ion found
    if pos.get("found", False):
        x, y = int(pos["x"]), int(pos["y"])
        # Ensure within bounds
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        
        # SINGLE THIN OUTER CIRCLE ONLY (no crosshair, no center dot)
        marker_color = (0, 255, 0)  # Neon green
        cv2.circle(frame, (x, y), 20, marker_color, 1)  # Thin line (thickness=1)
        
        # DISPLAY FIT PARAMETERS
        params_text = []
        
        # Show sigma values if available
        if "sig_x" in pos and "sig_y" in pos:
            sig_x = pos["sig_x"]
            sig_y = pos["sig_y"]
            params_text.append(f"sx:{sig_x:.1f} sy:{sig_y:.1f}")
        
        # Show theta if available
        if "theta" in pos:
            theta_deg = np.degrees(pos["theta"]) % 180
            params_text.append(f"th:{theta_deg:.0f}")
        
        # Show amplitude if available
        if "amp" in pos:
            amp = pos["amp"]
            params_text.append(f"A:{amp:.1f}")
        
        # Draw parameter text next to ion
        if params_text:
            text = " | ".join(params_text)
            text_x = x + 25  # Offset to right of circle
            text_y = y - 15  # Slightly above
            
            # Ensure text stays within frame
            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)[0]
            if text_x + text_size[0] > w:
                text_x = x - 25 - text_size[0]  # Move to left side
            if text_y < text_size[1]:
                text_y = y + 25  # Move below if too high
            
            # Draw text with dark background for readability
            cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.35, (0, 0, 0), 2)  # Black outline
            cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.35, marker_color, 1)  # Green text
    
    # LIVE indicator in corner
    live_color = (0, 255, 0) if latency_ms < 500 else (0, 165, 255)
    cv2.putText(frame, "● LIVE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                0.7, live_color, 2)
    
    # Latency display
    latency_color = (200, 200, 200) if latency_ms < 500 else (0, 0, 255)
    cv2.putText(frame, f"Latency: {latency_ms:.0f}ms", (10, 60), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, latency_color, 1)
    
    # High delay warning
    if latency_ms > 500:
        warning_text = "⚠ HIGH DELAY"
        cv2.putText(frame, warning_text, (10, h - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    
    return frame


def generate_simulated_frame(t: float) -> np.ndarray:
    """Generate a simulated camera frame for demo/development."""
    frame = np.zeros((600, 800, 3), dtype=np.uint8)
    
    # Gradient background
    for i in range(600):
        frame[i, :] = [245, 248, 250]  # Off-white scientific background
    
    # Add subtle noise
    noise = np.random.randint(0, 5, (600, 800, 3), dtype=np.uint8)
    frame = cv2.add(frame, noise)
    
    # Simulated ion motion
    x = 400 + int(30 * np.sin(t * 0.5))
    y = 300 + int(20 * np.cos(t * 0.7))
    
    # Draw ion spot with glow
    cv2.circle(frame, (x, y), 15, (200, 200, 255), -1)
    cv2.circle(frame, (x, y), 10, (220, 220, 255), -1)
    cv2.circle(frame, (x, y), 5, (255, 255, 255), -1)
    
    return frame


def generate_frames():
    """
    Generate MJPEG video stream frames.
    
    Yields:
        MJPEG frame data for HTTP multipart response
    """
    frame_interval = 1.0 / 30.0  # Target 30 FPS
    last_yield_time = 0
    last_json_check = 0
    
    while True:
        try:
            loop_start = time.time()
            
            # Periodically update ion position from JSON files
            if loop_start - last_json_check > 0.5:  # Check every 500ms
                update_ion_position_from_file()
                last_json_check = loop_start
            
            # Try to read from disk first
            result = read_frame_from_disk()
            
            if result is not None:
                frame, timestamp, fit_params = result
                
                # Update camera state
                with camera_lock:
                    camera_state.update_latency(timestamp)
                    # Merge fit params into ion_position if available
                    if fit_params:
                        camera_state.ion_position.update(fit_params)
                    pos = camera_state.ion_position.copy()
                    latency = camera_state.latency_ms
                    
                # Add overlays
                frame = add_overlay_to_frame(frame, pos, latency)
                
            else:
                # Fallback to simulated frame
                frame = generate_simulated_frame(time.time())
                
                with camera_lock:
                    camera_state.is_live = False
                    pos = camera_state.ion_position.copy()
                    latency = 999  # Indicate simulation
                    
                # Add overlays to simulated frame
                frame = add_overlay_to_frame(frame, pos, latency)
                
                # Add simulation indicator
                cv2.putText(frame, "SIMULATED CAMERA FEED", (250, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 1)
            
            # Encode and yield frame
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Cache-Control: no-cache\r\n\r\n' + 
                       buffer.tobytes() + b'\r\n')
            
            # Frame rate limiting
            elapsed = time.time() - loop_start
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
                
        except Exception as e:
            logger.error(f"Frame generation error: {e}")
            time.sleep(0.1)


# =============================================================================
# TELEMETRY STREAMING
# =============================================================================

def get_telemetry_for_time_window(window_seconds: float = 300.0) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get telemetry data for specified time window.
    
    Returns data points with timestamps for accurate time-based rendering.
    Merges simulated data with real data from LabVIEW sources.
    """
    now = time.time()
    cutoff = now - window_seconds
    result = {}
    
    # Get simulated/camera data
    with telemetry_lock:
        for key, deque_data in telemetry_data.items():
            points = [
                {"t": ts, "v": val} 
                for ts, val in deque_data 
                if ts >= cutoff
            ]
            result[key] = points
    
    # Get real data from DataIngestionServer (LabVIEW sources)
    if DATA_SERVER_AVAILABLE:
        try:
            real_telemetry, real_lock = get_telemetry_data()
            with real_lock:
                for key, deque_data in real_telemetry.items():
                    if key in result:
                        # Merge real data with simulated, prioritizing real
                        real_points = [
                            {"t": ts, "v": val}
                            for ts, val in deque_data
                            if ts >= cutoff
                        ]
                        if real_points:
                            # Use real data if available
                            result[key] = real_points
                    else:
                        result[key] = [
                            {"t": ts, "v": val}
                            for ts, val in deque_data
                            if ts >= cutoff
                        ]
        except Exception as e:
            logger.debug(f"Could not get real telemetry data: {e}")
    
    return result


def telemetry_generator():
    """
    Generate Server-Sent Events for real-time telemetry.
    
    Sends 300-second rolling window data at 2Hz.
    Includes data from LabVIEW sources (Wavemeter, SMILE).
    """
    while True:
        try:
            data = get_telemetry_for_time_window(TELEMETRY_WINDOW_SECONDS)
            data["timestamp"] = time.time()
            
            # Add camera state
            with camera_lock:
                data["camera"] = {
                    "latency_ms": camera_state.latency_ms,
                    "is_live": camera_state.is_live,
                    "high_delay_warning": camera_state.high_delay_warning,
                    "fps": camera_state.fps
                }
            
            # Add turbo state
            with turbo_state_lock:
                data["turbo"] = {
                    "status": turbo_state["status"],
                    "iteration": turbo_state["current_iteration"],
                    "delta": turbo_state["convergence_delta"],
                    "target": turbo_state["target_parameter"],
                    "safety_engaged": turbo_state["safety_engaged"]
                }
            
            # Add data source status (LabVIEW connections)
            if DATA_SERVER_AVAILABLE:
                try:
                    data["data_sources"] = get_data_sources()
                except:
                    data["data_sources"] = {}
            
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(0.5)  # 2 Hz update rate
            
        except Exception as e:
            logger.error(f"Telemetry generator error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            time.sleep(1)


def turbo_log_generator():
    """
    Generate Server-Sent Events for Turbo algorithm logs.
    
    Streams new log entries as they arrive.
    """
    last_len = 0
    heartbeat_interval = 5.0
    last_heartbeat = time.time()
    
    while True:
        try:
            with turbo_logs_lock:
                current_len = len(turbo_algorithm_logs)
                logs_list = [log.to_dict() for log in turbo_algorithm_logs]
            
            now = time.time()
            
            if current_len != last_len:
                # New entries available
                data = {
                    "logs": logs_list,
                    "new_count": current_len - last_len if current_len > last_len else 0,
                    "total_count": current_len
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_len = current_len
                last_heartbeat = now
                
            elif now - last_heartbeat >= heartbeat_interval:
                # Send heartbeat
                yield f"data: {json.dumps({'heartbeat': True, 'total_count': current_len})}\n\n"
                last_heartbeat = now
            
            time.sleep(0.1)  # 10 Hz check rate
            
        except Exception as e:
            logger.error(f"Turbo log generator error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            time.sleep(1)


# =============================================================================
# BACKGROUND SIMULATION (for development/demo)
# =============================================================================

def simulate_telemetry():
    """Background thread to simulate telemetry data."""
    t = 0
    while True:
        try:
            now = time.time()
            
            with telemetry_lock:
                # Pos x: Micro-motion oscillation
                telemetry_data["pos_x"].append((now, 320 + 10 * np.sin(t * 0.5) + 2 * np.random.randn()))
                
                # Pos y: Discrete position steps
                y_positions = [200, 250, 300, 350]
                telemetry_data["pos_y"].append((now, y_positions[int(t / 50) % 4] + np.random.randn()))
                
                # Sig x: Fluorescence peak (Gaussian)
                sig_x_base = 15 + 5 * np.exp(-((t % 100 - 50) / 20) ** 2)
                telemetry_data["sig_x"].append((now, sig_x_base + np.random.randn()))
                
                # Sig y: Fluorescence width/background
                sig_y_base = 25 + 8 * np.exp(-((t % 100 - 50) / 30) ** 2)
                telemetry_data["sig_y"].append((now, sig_y_base + np.random.randn()))
                
                # Pressure: Chamber pressure readout
                pressure_base = 1.2e-10
                if 200 < (t % 400) < 300:
                    pressure_base = 5.0e-10
                telemetry_data["pressure"].append((now, pressure_base + np.random.randn() * 1e-11))
                
                # Laser Frequency: Lock stability/drift
                freq_base = 212.5
                phase = t % 300
                if 50 < phase < 250:
                    freq_base = 213.2 + np.random.randn() * 0.02
                telemetry_data["laser_freq"].append((now, freq_base))
                
                # PMT: Photon counts
                pmt_base = 100
                phase = t % 400
                if 50 < phase < 100:
                    pmt_base = 100 + (phase - 50) * 20 + np.random.randn() * 50
                elif 100 <= phase < 300:
                    pmt_base = 1100 + np.random.randn() * 100
                    if 180 < phase < 190:  # Spike
                        pmt_base += 800
                else:
                    pmt_base = 100 + np.random.randn() * 30
                telemetry_data["pmt"].append((now, max(0, pmt_base)))
            
            # Update simulated ion position with fit parameters
            with camera_lock:
                camera_state.ion_position = {
                    "x": 320 + 10 * np.sin(t * 0.5),
                    "y": 300 + 5 * np.cos(t * 0.3),
                    "found": True,
                    "sig_x": 3.0 + 0.5 * np.sin(t * 0.2),
                    "sig_y": 6.0 + 0.8 * np.cos(t * 0.15),
                    "theta": 0.1 * np.sin(t * 0.1),
                    "amp": 15.0 + 2 * np.random.randn()
                }
            
            t += 1
            time.sleep(1.0)  # 1 Hz data rate
            
        except Exception as e:
            logger.error(f"Telemetry simulation error: {e}")
            time.sleep(1)


def simulate_turbo_algorithm():
    """Background thread to simulate Turbo algorithm execution and logging."""
    iteration = 0
    target_params = ["Pos_x", "Pos_y", "Sig_x", "Sig_y", "Pressure", "Laser_Freq"]
    target_idx = 0
    
    while True:
        try:
            with turbo_state_lock:
                is_running = not turbo_state["safety_engaged"]
            
            if is_running:
                iteration += 1
                target = target_params[target_idx % len(target_params)]
                
                # Simulate convergence
                delta = max(0.001, 0.1 * np.exp(-iteration / 50) + np.random.randn() * 0.01)
                
                if iteration % 10 == 0:
                    # Switch optimization target
                    target_idx += 1
                    add_turbo_log(
                        level="INFO",
                        message=f"Turbo: Optimizing {target}...",
                        iteration=iteration,
                        delta=delta
                    )
                    update_turbo_state(AlgorithmState.OPTIMIZING.value, iteration, delta, target)
                
                elif iteration % 5 == 0:
                    add_turbo_log(
                        level="ITERATION",
                        message=f"Iteration {iteration}: Convergence delta {delta:.4f}",
                        iteration=iteration,
                        delta=delta
                    )
                
                # Random error simulation
                if np.random.random() < 0.02:  # 2% chance
                    add_turbo_log(
                        level="ERROR",
                        message="ERROR: Optimization diverging. Resetting weights.",
                        iteration=iteration
                    )
                    update_turbo_state(AlgorithmState.DIVERGING.value, iteration, delta)
                    iteration = max(0, iteration - 10)  # Roll back
                
                if delta < 0.01:
                    update_turbo_state(AlgorithmState.CONVERGED.value, iteration, delta, target)
            
            time.sleep(2.0)  # Log every 2 seconds when running
            
        except Exception as e:
            logger.error(f"Turbo simulation error: {e}")
            time.sleep(1)


# Start background simulation threads
threading.Thread(target=simulate_telemetry, daemon=True, name="TelemetrySim").start()
threading.Thread(target=simulate_turbo_algorithm, daemon=True, name="TurboSim").start()


# =============================================================================
# FLASK ROUTES - STATIC PAGES
# =============================================================================

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory('static', filename)


# =============================================================================
# FLASK ROUTES - VIDEO STREAMING
# =============================================================================

@app.route('/video_feed')
def video_feed():
    """Video streaming route for CCD Footage."""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


# =============================================================================
# FLASK ROUTES - API ENDPOINTS
# =============================================================================

@app.route('/api/telemetry/stream')
def telemetry_stream():
    """Server-sent events for real-time telemetry data."""
    return Response(
        telemetry_generator(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering
        }
    )


@app.route('/api/turbo/logs/stream')
def turbo_logs_stream():
    """Server-sent events for Turbo algorithm log streaming."""
    return Response(
        turbo_log_generator(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/status')
def get_status():
    """Get current system status including data sources."""
    # Query manager for fresh state
    resp = send_to_manager({"action": "STATUS", "source": "FLASK"})
    
    with state_lock:
        if resp.get("status") == "success":
            current_state["mode"] = resp.get("mode", current_state["mode"])
            current_state["params"].update(resp.get("params", {}))
            current_state["worker_alive"] = resp.get("worker_alive", False)
    
    with camera_lock:
        cam_info = {
            "latency_ms": camera_state.latency_ms,
            "is_live": camera_state.is_live,
            "high_delay_warning": camera_state.high_delay_warning,
            "fps": camera_state.fps,
            "ion_position": camera_state.ion_position
        }
    
    with turbo_state_lock:
        turbo_info = {
            "status": turbo_state["status"],
            "iteration": turbo_state["current_iteration"],
            "convergence_delta": turbo_state["convergence_delta"],
            "target_parameter": turbo_state["target_parameter"],
            "safety_engaged": turbo_state["safety_engaged"]
        }
    
    # Get data source status (LabVIEW connections)
    data_sources = {}
    if DATA_SERVER_AVAILABLE:
        try:
            data_sources = get_data_sources()
        except Exception as e:
            logger.debug(f"Could not get data sources: {e}")
    
    return jsonify({
        "mode": current_state["mode"],
        "params": current_state["params"],
        "worker_alive": current_state["worker_alive"],
        "camera": cam_info,
        "turbo": turbo_info,
        "data_sources": data_sources
    })


# =============================================================================
# FLASK ROUTES - CONTROL ENDPOINTS
# =============================================================================

@app.route('/api/control/electrodes', methods=['POST'])
def set_electrodes():
    """Set electrode voltages (EC1, EC2, Comp_H, Comp_V)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400
        
        params = {
            "ec1": float(data.get("ec1", 0)),
            "ec2": float(data.get("ec2", 0)),
            "comp_h": float(data.get("comp_h", 0)),
            "comp_v": float(data.get("comp_v", 0)),
        }
        
        # Validate ranges
        for name, value in params.items():
            if not -100 <= value <= 100:
                return jsonify({
                    "status": "error", 
                    "message": f"{name} value {value} out of range [-100, 100]"
                }), 400
        
        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": params
        })
        
        if resp.get("status") == "success":
            with state_lock:
                current_state["params"].update(params)
            return jsonify({"status": "success", "params": params})
        else:
            return jsonify({
                "status": "error", 
                "message": resp.get("message", "Failed"),
                "code": resp.get("code", "UNKNOWN")
            }), 400
            
    except ValueError as e:
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"Electrode control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/rf', methods=['POST'])
def set_rf_voltage():
    """Set RF voltage (U_RF in volts)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400
            
        # Accept either 'u_rf_volts' (preferred) or 'u_rf' (legacy)
        u_rf_volts = float(data.get("u_rf_volts") or data.get("u_rf", 200))
        
        # Validate range (real voltage 0-500V)
        if not 0 <= u_rf_volts <= 500:
            return jsonify({
                "status": "error",
                "message": f"RF voltage {u_rf_volts} V out of range [0, 500]"
            }), 400
        
        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": {"u_rf_volts": u_rf_volts}
        })
        
        if resp.get("status") == "success":
            with state_lock:
                current_state["params"]["u_rf_volts"] = u_rf_volts
            return jsonify({"status": "success", "u_rf_volts": u_rf_volts})
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed")
            }), 400
            
    except ValueError as e:
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"RF control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/piezo', methods=['POST'])
def set_piezo():
    """Set piezo voltage."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400
            
        piezo = float(data.get("piezo", 0))
        
        # Validate range
        if not -10 <= piezo <= 10:
            return jsonify({
                "status": "error",
                "message": f"Piezo voltage {piezo} out of range [-10, 10]"
            }), 400
        
        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": {"piezo": piezo}
        })
        
        if resp.get("status") == "success":
            with state_lock:
                current_state["params"]["piezo"] = piezo
            return jsonify({"status": "success", "piezo": piezo})
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed")
            }), 400
            
    except ValueError as e:
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"Piezo control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/toggle/<toggle_name>', methods=['POST'])
def set_toggle(toggle_name):
    """Set a toggle state (bephi, b_field, be_oven, uv3, e_gun)."""
    try:
        data = request.get_json()
        state = bool(data.get("state", False))
        
        # Map frontend names to parameter names
        param_map = {
            "bephi": "bephi",
            "b_field": "b_field",
            "be_oven": "be_oven",
            "uv3": "uv3",
            "e_gun": "e_gun"
        }
        
        param_name = param_map.get(toggle_name)
        if not param_name:
            return jsonify({
                "status": "error",
                "message": f"Unknown toggle: {toggle_name}",
                "valid_toggles": list(param_map.keys())
            }), 400
        
        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": {param_name: state}
        })
        
        if resp.get("status") == "success":
            with state_lock:
                current_state["params"][param_name] = state
            return jsonify({
                "status": "success",
                "toggle": toggle_name,
                "state": state
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed")
            }), 400
            
    except Exception as e:
        logger.error(f"Toggle control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/dds', methods=['POST'])
def set_dds():
    """Set DDS profile and/or frequency."""
    try:
        data = request.get_json()
        params = {}
        
        # Handle profile
        profile = data.get("profile")
        if profile is not None:
            profile = int(profile)
            if not 0 <= profile <= 7:
                return jsonify({
                    "status": "error",
                    "message": f"DDS profile {profile} out of range [0, 7]"
                }), 400
            params["dds_profile"] = profile
        
        # Handle frequency (0-500 kHz)
        freq_khz = data.get("freq_khz")
        if freq_khz is not None:
            freq_khz = float(freq_khz)
            if not 0 <= freq_khz <= 500:
                return jsonify({
                    "status": "error",
                    "message": f"DDS frequency {freq_khz} kHz out of range [0, 500]"
                }), 400
            params["dds_freq_khz"] = freq_khz
        
        if not params:
            return jsonify({
                "status": "error",
                "message": "No valid parameters provided (profile or freq_khz)"
            }), 400
        
        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": params
        })
        
        if resp.get("status") == "success":
            with state_lock:
                if "dds_profile" in params:
                    current_state["params"]["dds_profile"] = params["dds_profile"]
                if "dds_freq_khz" in params:
                    current_state["params"]["dds_freq_khz"] = params["dds_freq_khz"]
            return jsonify({
                "status": "success", 
                "dds_profile": params.get("dds_profile"),
                "dds_freq_khz": params.get("dds_freq_khz")
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed")
            }), 400
            
    except ValueError as e:
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"DDS control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# FLASK ROUTES - SAFETY & ALGORITHM CONTROL
# =============================================================================

@app.route('/api/safety/toggle', methods=['POST'])
def toggle_safety():
    """
    Master Safety Switch toggle.
    
    When engaging safe mode:
    - Sends immediate STOP signal to manager
    - Resets all hardware voltages to safe defaults (0V)
    - Halts Turbo algorithm
    
    When disengaging (algorithm mode):
    - Allows Turbo algorithm to run
    """
    try:
        data = request.get_json()
        engage_safety = bool(data.get("engage", True))
        
        if engage_safety:
            # ENGAGE SAFE MODE
            result = safe_shutdown()
            
            return jsonify({
                "status": "success",
                "mode": "SAFE",
                "message": "Safety mode engaged. Algorithm stopped, hardware reset.",
                "details": result
            })
            
        else:
            # DISENGAGE SAFE MODE - Allow algorithm to run
            with turbo_state_lock:
                turbo_state["safety_engaged"] = False
                turbo_state["status"] = AlgorithmState.IDLE.value
                turbo_state["start_time"] = None
                turbo_state["current_iteration"] = 0
            
            # Notify manager
            resp = send_to_manager({
                "action": "MODE",
                "source": "USER",
                "mode": "AUTO"
            })
            
            with state_lock:
                current_state["mode"] = SystemMode.AUTO.value
            
            add_turbo_log(
                level="INFO",
                message="ALGORITHM RUNNING: Turbo optimization enabled"
            )
            
            return jsonify({
                "status": "success",
                "mode": "AUTO",
                "message": "Algorithm mode enabled. Turbo optimization is running.",
                "manager_response": resp
            })
            
    except Exception as e:
        logger.error(f"Safety toggle error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/safety/status', methods=['GET'])
def get_safety_status():
    """Get current safety status."""
    with turbo_state_lock:
        return jsonify({
            "safety_engaged": turbo_state["safety_engaged"],
            "algorithm_status": turbo_state["status"],
            "current_iteration": turbo_state["current_iteration"],
            "convergence_delta": turbo_state["convergence_delta"],
            "target_parameter": turbo_state["target_parameter"]
        })


@app.route('/api/turbo/logs', methods=['GET'])
def get_turbo_logs():
    """Get Turbo algorithm logs (REST API)."""
    try:
        limit = min(int(request.args.get('limit', 100)), 500)
        level_filter = request.args.get('level', None)
        
        with turbo_logs_lock:
            logs = list(turbo_algorithm_logs)
            if level_filter:
                logs = [log for log in logs if log.level == level_filter.upper()]
            logs = logs[-limit:]
            
        return jsonify({
            "logs": [log.to_dict() for log in logs],
            "count": len(logs),
            "total": len(turbo_algorithm_logs)
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# FLASK ROUTES - MODE & EXPERIMENT
# =============================================================================

@app.route('/api/mode', methods=['POST'])
def set_mode():
    """Set system mode (MANUAL/AUTO/SAFE)."""
    try:
        data = request.get_json()
        new_mode = data.get("mode", "MANUAL")
        
        logger.info(f"Mode change request: {new_mode}")
        
        resp = send_to_manager({
            "action": "MODE",
            "source": "USER",
            "mode": new_mode
        })
        
        if resp.get("status") == "success":
            with state_lock:
                current_state["mode"] = resp.get("mode", new_mode)
            
            # Update safety state based on mode
            with turbo_state_lock:
                if new_mode == "SAFE":
                    turbo_state["safety_engaged"] = True
                    turbo_state["status"] = AlgorithmState.STOPPED.value
                elif new_mode == "AUTO":
                    turbo_state["safety_engaged"] = False
                    turbo_state["status"] = AlgorithmState.RUNNING.value
                else:  # MANUAL
                    turbo_state["safety_engaged"] = True
                    turbo_state["status"] = AlgorithmState.IDLE.value
            
            return jsonify({"status": "success", "mode": current_state["mode"]})
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed to change mode")
            }), 400
            
    except Exception as e:
        logger.error(f"Mode change error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/sweep', methods=['POST'])
def trigger_sweep():
    """Trigger a sweep experiment."""
    try:
        data = request.get_json()
        logger.info(f"Sweep trigger received: {data}")
        
        resp = send_to_manager({
            "action": "SWEEP",
            "source": "USER",
            "params": data.get("params", {})
        })
        
        if resp.get("status") in ("started", "success"):
            return jsonify({
                "status": "success",
                "exp_id": resp.get("exp_id")
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("reason", "Failed to start sweep")
            }), 400
            
    except Exception as e:
        logger.error(f"Sweep trigger error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/compare', methods=['POST'])
def trigger_secular_compare():
    """
    Trigger secular frequency comparison.
    
    Request body:
    {
        "ec1": 10.0,        # Endcap 1 voltage (V)
        "ec2": 10.0,        # Endcap 2 voltage (V)
        "comp_h": 6.0,      # Horizontal compensation (V)
        "comp_v": 37.0,     # Vertical compensation (V)
        "u_rf_mV": 1400,    # RF voltage on SMILE interface (mV)
        "mass_numbers": [9, 3]  # Ion masses (optional, default [9, 3])
    }
    """
    try:
        data = request.get_json()
        logger.info(f"Secular comparison trigger received: {data}")
        
        # Build comparison parameters
        compare_params = {
            "ec1": float(data.get("ec1", 10.0)),
            "ec2": float(data.get("ec2", 10.0)),
            "comp_h": float(data.get("comp_h", 6.0)),
            "comp_v": float(data.get("comp_v", 37.0)),
            "u_rf_mV": float(data.get("u_rf_mV", 1400)),
            "mass_numbers": data.get("mass_numbers", [9, 3])
        }
        
        resp = send_to_manager({
            "action": "COMPARE",
            "source": "USER",
            "params": compare_params
        })
        
        if resp.get("status") == "started":
            return jsonify({
                "status": "success",
                "exp_id": resp.get("exp_id"),
                "message": resp.get("message"),
                "predicted_freq_kHz": resp.get("predicted_freq_kHz"),
                "target_mode": resp.get("target_mode")
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed to start comparison"),
                "code": resp.get("code", "UNKNOWN_ERROR")
            }), 400
            
    except Exception as e:
        logger.error(f"Secular comparison trigger error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/experiment', methods=['GET'])
def get_experiment_status():
    """Get current experiment status."""
    try:
        exp_id = request.args.get('id')
        
        resp = send_to_manager({
            "action": "EXPERIMENT_STATUS",
            "source": "FLASK",
            "exp_id": exp_id
        })
        
        return jsonify(resp)
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/experiments', methods=['GET'])
def list_experiments():
    """List recent experiments."""
    try:
        tracker = get_tracker()
        experiments = tracker.list_experiments()
        
        return jsonify({
            "experiments": [
                {
                    "id": e.exp_id,
                    "status": e.status,
                    "phase": e.phase,
                    "duration": e.duration_seconds
                }
                for e in experiments[-10:]  # Last 10
            ]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/data/sources', methods=['GET'])
def get_data_sources_status():
    """Get data source status (LabVIEW connections)."""
    if not DATA_SERVER_AVAILABLE:
        return jsonify({
            "status": "unavailable",
            "message": "Data ingestion server not enabled"
        })
    
    try:
        sources = get_data_sources()
        return jsonify({
            "status": "ok",
            "sources": sources
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/data/recent/<channel>', methods=['GET'])
def get_recent_channel_data(channel):
    """Get recent data for a specific telemetry channel."""
    if not DATA_SERVER_AVAILABLE:
        return jsonify({"status": "error", "message": "Data server unavailable"}), 503
    
    try:
        from server.communications.data_server import DataIngestionServer
        
        window = min(float(request.args.get('window', 300)), 3600)  # Max 1 hour
        
        # Get real data
        real_telemetry, real_lock = get_telemetry_data()
        with real_lock:
            if channel not in real_telemetry:
                return jsonify({"status": "error", "message": f"Unknown channel: {channel}"}), 400
            
            cutoff = time.time() - window
            points = [
                {"timestamp": ts, "value": val}
                for ts, val in real_telemetry[channel]
                if ts >= cutoff
            ]
        
        return jsonify({
            "status": "ok",
            "channel": channel,
            "count": len(points),
            "data": points
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# CLEANUP
# =============================================================================

def cleanup():
    """Cleanup ZMQ resources on shutdown."""
    global manager_socket, zmq_ctx
    logger.info("Cleaning up Flask server resources...")
    try:
        if manager_socket:
            try:
                manager_socket.close()
            except:
                pass
            manager_socket = None
        if zmq_ctx and not zmq_ctx.closed:
            try:
                zmq_ctx.term()
            except:
                pass
    except Exception as e:
        logger.debug(f"Cleanup error (non-critical): {e}")
    logger.info("Cleanup complete")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    try:
        logger.info("=" * 60)
        logger.info("Flask Dashboard Server Starting...")
        logger.info(f"Manager: {MANAGER_IP}:{MANAGER_PORT}")
        logger.info(f"Camera frames path: {LIVE_FRAMES_PATH}")
        print(f"🌍 Dashboard running at http://0.0.0.0:5000")
        print(f"📊 Connected to manager at {MANAGER_IP}:{MANAGER_PORT}")
        print(f"🔬 Scientific Dashboard - Turbo Algorithm Control")
        
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        cleanup()
