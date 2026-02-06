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

SAFETY CRITICAL:
- Piezo Output: Max 10 seconds ON time (kill switch enforced)
- E-Gun Output: Max 30 seconds ON time (kill switch enforced)
- Kill switches are enforced at Flask, Manager, and LabVIEW levels
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

from core import get_config, setup_logging, get_tracker, SystemMode, AlgorithmState


# =============================================================================
# KILL SWITCH MANAGER - SAFETY CRITICAL
# =============================================================================

class KillSwitchManager:
    """
    Manages safety kill switches for time-limited hardware outputs.

    Devices:
    - piezo: Max 10 seconds ON time
    - e_gun: Max 30 seconds ON time

    The kill switch monitors active outputs and automatically turns them off
    when time limits are exceeded. This is enforced at Flask level as a
    secondary protection (primary is in LabVIEW hardware).
    """

    TIME_LIMITS = {
        "piezo": 10.0,      # 10 seconds max for piezo output
        "e_gun": 10.0,      # 10 seconds max for e-gun (testing mode)
    }

    def __init__(self):
        self._active: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._running = True
        self.logger = logging.getLogger("kill_switch")

        # Start watchdog thread
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="KillSwitchWatchdog"
        )
        self._watchdog_thread.start()
        self.logger.info("Kill Switch Manager initialized")

    def register_on(self, device: str, set_voltage_callback: callable, zero_voltage_callback: callable):
        """
        Register a device as ON with kill switch protection.

        Args:
            device: Device name ('piezo' or 'e_gun')
            set_voltage_callback: Function to call with target voltage when ON
            zero_voltage_callback: Function to call to set voltage to 0
        """
        with self._lock:
            if device not in self.TIME_LIMITS:
                self.logger.warning(f"Unknown device for kill switch: {device}")
                return False

            self._active[device] = {
                "start_time": time.time(),
                "set_voltage_cb": set_voltage_callback,
                "zero_voltage_cb": zero_voltage_callback,
                "killed": False,
            }
            self.logger.info(f"Kill switch ARMED for {device} (max {self.TIME_LIMITS[device]}s)")
            return True

    def register_off(self, device: str):
        """Unregister a device (turned off safely by user)."""
        with self._lock:
            if device in self._active:
                elapsed = time.time() - self._active[device]["start_time"]
                self.logger.info(f"Kill switch DISARMED for {device} (was on for {elapsed:.1f}s)")
                del self._active[device]
                return True
            return False

    def is_active(self, device: str) -> bool:
        """Check if a device is currently active under kill switch monitoring."""
        with self._lock:
            return device in self._active

    def get_remaining_time(self, device: str) -> float:
        """Get remaining allowed ON time for a device."""
        with self._lock:
            if device not in self._active:
                return 0.0
            elapsed = time.time() - self._active[device]["start_time"]
            remaining = self.TIME_LIMITS[device] - elapsed
            return max(0.0, remaining)

    def trigger_kill(self, device: str, reason: str = "manual"):
        """
        Manually trigger kill switch for a device.

        Args:
            device: Device to kill
            reason: Reason for kill (for logging)
        """
        with self._lock:
            if device not in self._active:
                return False

            info = self._active[device]
            if info["killed"]:
                return False

            info["killed"] = True
            elapsed = time.time() - info["start_time"]

            self.logger.error(
                f"KILL SWITCH TRIGGERED for {device}: {reason} "
                f"(was on for {elapsed:.1f}s, limit was {self.TIME_LIMITS[device]}s)"
            )

            # Execute zero voltage callback
            try:
                info["zero_voltage_cb"]()
                self.logger.info(f"Kill switch executed for {device}")
            except Exception as e:
                self.logger.error(f"Kill switch callback failed for {device}: {e}")

            # Clean up
            del self._active[device]
            return True

    def _watchdog_loop(self):
        """Background thread that monitors active devices and enforces time limits."""
        while self._running:
            try:
                with self._lock:
                    now = time.time()
                    to_kill = []

                    for device, info in self._active.items():
                        elapsed = now - info["start_time"]
                        limit = self.TIME_LIMITS[device]

                        if elapsed > limit and not info["killed"]:
                            to_kill.append(device)

                    # Kill outside of lock to avoid deadlock
                    devices_to_kill = to_kill.copy()

                for device in devices_to_kill:
                    self.trigger_kill(device, f"TIME LIMIT EXCEEDED ({self.TIME_LIMITS[device]}s)")

                time.sleep(0.1)  # 10 Hz check rate

            except Exception as e:
                self.logger.error(f"Kill switch watchdog error: {e}")
                time.sleep(1)

    def get_status(self) -> Dict[str, Any]:
        """Get current kill switch status for all monitored devices."""
        with self._lock:
            status = {}
            for device, limit in self.TIME_LIMITS.items():
                if device in self._active:
                    info = self._active[device]
                    elapsed = time.time() - info["start_time"]
                    status[device] = {
                        "active": True,
                        "elapsed_seconds": round(elapsed, 2),
                        "remaining_seconds": round(limit - elapsed, 2),
                        "time_limit": limit,
                        "killed": info["killed"]
                    }
                else:
                    status[device] = {
                        "active": False,
                        "time_limit": limit,
                        "elapsed_seconds": 0,
                        "remaining_seconds": 0,
                        "killed": False
                    }
            return status

    def stop(self):
        """Stop the kill switch manager and kill all active devices."""
        self._running = False
        with self._lock:
            for device in list(self._active.keys()):
                self.trigger_kill(device, "SHUTDOWN")


# Global kill switch manager
kill_switch = KillSwitchManager()

# =============================================================================
# SETUP & CONFIGURATION
# =============================================================================

logger = setup_logging(component="flask")

# Import shared telemetry storage (Manager reads files, Flask displays)
# LabVIEW writes data files to E:/Data/, Manager reads them
try:
    from services.comms.data_server import (
        get_telemetry_data,
        get_data_sources
    )
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False
    logger.warning("Telemetry storage not available - no telemetry data will be displayed")
config = get_config()

# Network configuration
MANAGER_IP = config.get_network('master_ip') or "127.0.0.1"
MANAGER_PORT = config.client_port

# Camera configuration
CAMERA_HOST = config.get_camera_setting('host') or "127.0.0.1"
CAMERA_PORT = config.get_camera_setting('port') or 5555

# Camera frame paths - new unified structure
# Raw frames: E:/Data/jpg_frames/YYMMDD/
# Labelled frames: E:/Data/jpg_frames_labelled/YYMMDD/
LIVE_FRAMES_PATH = config.get_path('jpg_frames_labelled') if hasattr(config, 'get_path') else "E:/Data/jpg_frames_labelled"

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
        # RF Voltage (U_RF in volts, 0-200V)
        "u_rf_volts": 200.0,
        # Electrodes (range: -1V to 50V)
        "ec1": 0.0, "ec2": 0.0,
        "comp_h": 0.0, "comp_v": 0.0,
        # Toggles (0=off, 1=on)
        "bephi": 0, "b_field": 1, "be_oven": 0,
        # Laser & Electron
        "uv3": 0,
        # Piezo: setpoint voltage and output state (kill switch protected)
        "piezo": 2.4,           # Target voltage setpoint (default for HD valve)
        "piezo_output": 0,      # 0=off, 1=on
        # E-gun: kill switch protected (max 10s)
        "e_gun": 0,
        # HD Valve (0=off, 1=on)
        "hd_valve": 0,
        # DDS: LabVIEW controlled only (0-200 MHz)
        "dds_freq_mhz": 0.0,
    },
    "worker_alive": False,
    "camera_active": False,
}
state_lock = threading.RLock()

# Kill switch configuration exposed to clients
KILL_SWITCH_LIMITS = {
    "piezo": 10.0,   # 10 seconds max ON time
    "e_gun": 30.0,   # 10 seconds max ON time (testing mode)
}

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
    
    Logs all outgoing requests and incoming responses for debugging.

    Args:
        message: Request dictionary
        timeout_ms: Timeout in milliseconds

    Returns:
        Response dictionary
    """
    global manager_socket
    action = message.get("action", "UNKNOWN")
    source = message.get("source", "FLASK")
    
    # Log the outgoing request
    logger.info(f"[ZMQ OUT] action={action}, source={source}, params={message.get('params', message.get('device', 'N/A'))}")
    
    with zmq_lock:
        for attempt in range(2):  # Retry once
            try:
                sock = get_manager_socket()
                sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
                sock.send_json(message)
                response = sock.recv_json()
                # Log the incoming response
                resp_status = response.get("status", "unknown")
                if resp_status == "success":
                    logger.info(f"[ZMQ IN]  action={action} -> status=success")
                else:
                    logger.warning(f"[ZMQ IN]  action={action} -> status={resp_status}, message={response.get('message', 'N/A')}")
                return response
            except zmq.Again:
                logger.warning(f"[ZMQ] Manager request timeout (attempt {attempt + 1}/2) for action={action}")
                if manager_socket:
                    try:
                        manager_socket.close()
                    except:
                        pass
                    manager_socket = None
                if attempt == 0:
                    time.sleep(0.1)  # Brief delay before retry
                else:
                    logger.error(f"[ZMQ] Manager timeout for action={action} after 2 attempts")
                    return {"status": "error", "message": "Manager timeout", "code": "TIMEOUT"}
            except zmq.ZMQError as e:
                logger.error(f"[ZMQ] ZMQ error for action={action}: {e}")
                manager_socket = None
                if attempt == 0:
                    time.sleep(0.1)
                else:
                    return {"status": "error", "message": f"ZMQ error: {e}", "code": "ZMQ_ERROR"}
            except Exception as e:
                logger.error(f"[ZMQ] Manager request failed for action={action}: {e}")
                return {"status": "error", "message": str(e), "code": "EXCEPTION"}
        logger.error(f"[ZMQ] Max retries exceeded for action={action}")
        return {"status": "error", "message": "Max retries exceeded", "code": "MAX_RETRIES"}


def safe_shutdown() -> Dict[str, Any]:
    """
    Emergency shutdown: Stop Turbo algorithm and reset all hardware to safe defaults.
    This is called when the safety switch is engaged.

    Also triggers kill switches for time-limited devices.
    """
    logger.warning("SAFETY SHUTDOWN TRIGGERED - Stopping algorithm and resetting hardware")

    # Step 0: Trigger kill switches for all time-limited devices
    ks_results = {}
    for device in KILL_SWITCH_LIMITS.keys():
        ks_results[device] = kill_switch.trigger_kill(device, "SAFETY SHUTDOWN")

    # Step 1: Send STOP signal to manager
    stop_response = send_to_manager({
        "action": "STOP",
        "source": "FLASK_SAFETY",
        "reason": "Safety switch engaged"
    }, timeout_ms=3000)

    # Step 2: Reset all hardware voltages to safe defaults (0V)
    safe_params = {
        "u_rf_volts": 0.0,
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

    # Step 3: Turn off all toggles and outputs
    toggle_params = {
        "bephi": False,
        "b_field": False,
        "be_oven": False,
        "uv3": False,
        "e_gun": False,
        "piezo_output": False,
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
        message="SAFETY MODE ENGAGED: Algorithm stopped, hardware reset to defaults, kill switches triggered",
        iteration=None,
        delta=None
    )

    return {
        "status": "success" if stop_response.get("status") == "success" else "partial",
        "stop_result": stop_response,
        "reset_result": reset_response,
        "toggle_result": toggle_response,
        "kill_switch_triggered": ks_results
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
    Read the latest annotated frame from jpg_frames_labelled directory.

    Directory structure: E:/Data/jpg_frames_labelled/YYMMDD/*_labelled.jpg

    Returns:
        Tuple of (frame, timestamp, fit_params) or None if no frame available
    """
    try:
        from datetime import datetime

        # Get today's subdirectory
        current_date_str = datetime.now().strftime("%y%m%d")
        frame_path = Path(LIVE_FRAMES_PATH) / current_date_str

        if not frame_path.exists():
            return None

        # Find latest annotated frame file (*_labelled.jpg)
        frame_files = list(frame_path.glob("*_labelled.jpg"))
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

        # Try to extract fit parameters from filename or companion JSON
        fit_params = {}
        try:
            # Look for companion JSON in cam_json folder with matching timestamp
            json_folder = Path(LIVE_FRAMES_PATH).parent / current_date_str / "cam_json"

            if json_folder.exists():
                # Extract timestamp from filename (e.g., "14-32-15_123_labelled.jpg")
                filename = latest.stem  # "14-32-15_123_labelled"
                time_prefix = filename.replace("_labelled", "")  # "14-32-15_123"

                # Find JSON with matching timestamp prefix
                for json_file in json_folder.glob("*_data.json"):
                    if time_prefix in json_file.stem:
                        with open(json_file, 'r') as f:
                            data = json.load(f)
                            if data.get("atoms"):
                                # Use first atom's fit parameters
                                atom = data["atoms"][0]
                                fit_params = {
                                    "sig_x": atom.get("sigma_x", 0),
                                    "sig_y": atom.get("R_y", 0),
                                    "amp": atom.get("A_x", 0)
                                }
                        break
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

        # Try new path first (jpg_frames_labelled structure)
        json_folder = Path(LIVE_FRAMES_PATH).parent / current_date_str / "cam_json"

        # Fallback to legacy path
        if not json_folder.exists():
            json_folder = Path(f"E:/Data/{current_date_str}/cam_json")

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
                "sig_x": atom.get("sigma_x", 0),  # Gaussian width
                "sig_y": atom.get("R_y", 0),       # SHM turning point
                "amp": atom.get("A_x", 0)          # Amplitude
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
    cv2.putText(frame, "LIVE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, live_color, 2)

    # Latency display
    latency_color = (200, 200, 200) if latency_ms < 500 else (0, 0, 255)
    cv2.putText(frame, f"Latency: {latency_ms:.0f}ms", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, latency_color, 1)

    # High delay warning
    if latency_ms > 500:
        warning_text = "! HIGH DELAY"
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
                # No real data available - return empty frame (black)
                with camera_lock:
                    camera_state.is_live = False
                    latency = 0

                # Create black frame with "No Signal" text
                frame = np.zeros((600, 800, 3), dtype=np.uint8)
                
                # Display "No Signal" message
                cv2.putText(frame, "NO CAMERA SIGNAL", (280, 280),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2)
                cv2.putText(frame, "Waiting for camera feed...", (260, 320),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 80, 80), 1)

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
    Only returns real data from LabVIEW sources (no mock data).
    """
    now = time.time()
    cutoff = now - window_seconds
    result = {}

    # Get real data from DataIngestionServer (LabVIEW sources)
    if TELEMETRY_AVAILABLE:
        try:
            real_telemetry, real_lock = get_telemetry_data()
            with real_lock:
                for key, deque_data in real_telemetry.items():
                    points = [
                        {"t": ts, "v": val}
                        for ts, val in deque_data
                        if ts >= cutoff
                    ]
                    if points:
                        result[key] = points
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
            if TELEMETRY_AVAILABLE:
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


# Background simulation threads removed - no mock data


# =============================================================================
# FLASK ROUTES - HEALTH & STATUS
# =============================================================================

import time as time_module

# Server start time for uptime tracking
SERVER_START_TIME = time_module.time()


@app.route('/health')
def health_check():
    """
    Health check endpoint for monitoring and load balancers.

    Returns:
        - HTTP 200 if server is healthy
        - Basic status info (uptime, version, dependencies)

    This endpoint should be lightweight and fast - no blocking calls.
    """
    uptime_seconds = time_module.time() - SERVER_START_TIME

    # Check if manager socket is connected (non-blocking check)
    manager_connected = manager_socket is not None

    health_data = {
        "status": "healthy",
        "timestamp": time_module.time(),
        "uptime_seconds": round(uptime_seconds, 2),
        "uptime_formatted": format_uptime(uptime_seconds),
        "version": "1.0.0",
        "service": "smile-flask-server",
        "checks": {
            "server": "ok",
            "manager_connected": manager_connected,
            "telemetry_available": TELEMETRY_AVAILABLE,
            "camera_path_accessible": Path(LIVE_FRAMES_PATH).exists() if LIVE_FRAMES_PATH else False
        }
    }

    # Return 503 if critical components are down
    if not manager_connected:
        health_data["status"] = "degraded"
        return jsonify(health_data), 503

    return jsonify(health_data), 200


def format_uptime(seconds):
    """Format uptime seconds to human readable string."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    else:
        return f"{minutes}m {secs}s"


@app.route('/ready')
def readiness_check():
    """
    Readiness check for Kubernetes/container orchestration.

    Returns 200 when the server is ready to accept traffic.
    This checks if all required dependencies are available.
    """
    ready = True
    checks = {}

    # Check manager connection
    checks["manager"] = manager_socket is not None
    ready = ready and checks["manager"]

    # Check camera path
    checks["camera_path"] = Path(LIVE_FRAMES_PATH).exists() if LIVE_FRAMES_PATH else False

    if ready:
        return jsonify({"ready": True, "checks": checks}), 200
    else:
        return jsonify({"ready": False, "checks": checks}), 503


# =============================================================================
# FLASK ROUTES - STATIC PAGES
# =============================================================================

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/turbo')
def turbo_page():
    """TuRBO Algorithm Control and Monitoring page."""
    return render_template('turbo.html')


@app.route('/tools')
def tools_page():
    """Tools and Mini Functions page."""
    return render_template('tools.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    static_dir = Path(__file__).parent / 'static'
    return send_from_directory(str(static_dir), filename)


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
    """Get current system status including data sources and kill switch status."""
    logger.debug(f"[API] GET /api/status from {request.remote_addr}")
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
    if TELEMETRY_AVAILABLE:
        try:
            data_sources = get_data_sources()
        except Exception as e:
            logger.debug(f"Could not get data sources: {e}")

    # Get kill switch status
    ks_status = kill_switch.get_status()

    return jsonify({
        "mode": current_state["mode"],
        "params": current_state["params"],
        "worker_alive": current_state["worker_alive"],
        "camera": cam_info,
        "turbo": turbo_info,
        "data_sources": data_sources,
        "kill_switch": ks_status,
        "kill_switch_limits": KILL_SWITCH_LIMITS,
        "wavemeter": resp.get("wavemeter", {"available": False})
    })


@app.route('/api/wavemeter/status', methods=['GET'])
def get_wavemeter_status():
    """
    Get detailed wavemeter status and current frequency reading.
    
    Returns:
        - enabled: Whether wavemeter interface is enabled
        - connected: Whether connected to wavemeter PC
        - current_frequency_ghz: Current laser frequency in GHz
        - current_frequency_thz: Current laser frequency in THz
        - current_channel: Active measurement channel
        - reading_count: Total number of readings received
        - server: Wavemeter server address
    """
    resp = send_to_manager({"action": "STATUS", "source": "FLASK"})
    
    wavemeter_info = resp.get("wavemeter", {"available": False})
    
    return jsonify({
        "status": "success",
        "wavemeter": wavemeter_info
    })


@app.route('/api/wavemeter/frequency', methods=['GET'])
def get_wavemeter_frequency():
    """
    Get current laser frequency reading.
    
    Query parameters:
        - unit: 'ghz' (default) or 'thz'
    
    Returns:
        - frequency: Current frequency value
        - unit: Frequency unit
        - channel: Active measurement channel
        - timestamp: Last update timestamp
    """
    unit = request.args.get('unit', 'ghz').lower()
    
    resp = send_to_manager({"action": "STATUS", "source": "FLASK"})
    wavemeter_info = resp.get("wavemeter", {})
    
    if not wavemeter_info or not wavemeter_info.get("enabled"):
        return jsonify({
            "status": "error",
            "message": "Wavemeter not enabled",
            "available": False
        }), 503
    
    if not wavemeter_info.get("connected"):
        return jsonify({
            "status": "error",
            "message": "Wavemeter not connected",
            "available": True,
            "connected": False
        }), 503
    
    if unit == 'thz':
        freq = wavemeter_info.get("current_frequency_thz", 0)
    else:
        freq = wavemeter_info.get("current_frequency_ghz", 0)
    
    return jsonify({
        "status": "success",
        "frequency": freq,
        "unit": unit,
        "channel": wavemeter_info.get("current_channel", 1),
        "timestamp": wavemeter_info.get("last_update"),
        "reading_count": wavemeter_info.get("reading_count", 0)
    })


# =============================================================================
# FLASK ROUTES - CONTROL ENDPOINTS
# =============================================================================

@app.route('/api/control/electrodes', methods=['POST'])
def set_electrodes():
    """Set electrode voltages (EC1, EC2, Comp_H, Comp_V)."""
    logger.info(f"[API] POST /api/control/electrodes from {request.remote_addr}")
    try:
        data = request.get_json()
        if not data:
            logger.warning("[API] No JSON data provided")
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400

        params = {
            "ec1": float(data.get("ec1", 0)),
            "ec2": float(data.get("ec2", 0)),
            "comp_h": float(data.get("comp_h", 0)),
            "comp_v": float(data.get("comp_v", 0)),
        }
        logger.info(f"[API] Setting electrodes: {params}")

        # Validate ranges
        for name, value in params.items():
            if not -100 <= value <= 100:
                logger.warning(f"[API] Validation failed: {name}={value} out of range")
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
            logger.info(f"[API] Electrodes set successfully: {params}")
            return jsonify({"status": "success", "params": params})
        else:
            logger.error(f"[API] Failed to set electrodes: {resp.get('message')}")
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed"),
                "code": resp.get("code", "UNKNOWN")
            }), 400

    except ValueError as e:
        logger.warning(f"[API] Invalid value in electrode request: {e}")
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"[API] Electrode control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/rf', methods=['POST'])
def set_rf_voltage():
    """Set RF voltage (U_RF in volts, 0-200V)."""
    logger.info(f"[API] POST /api/control/rf from {request.remote_addr}")
    try:
        data = request.get_json()
        if not data:
            logger.warning("[API] No JSON data provided")
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400

        # Accept either 'u_rf_volts' (preferred) or 'u_rf' (legacy)
        u_rf_volts = float(data.get("u_rf_volts") or data.get("u_rf", 200))
        logger.info(f"[API] Setting RF voltage: {u_rf_volts}V")

        # Validate range (real voltage U_RF 0-200V)
        if not 0 <= u_rf_volts <= 200:
            logger.warning(f"[API] RF voltage {u_rf_volts}V out of range")
            return jsonify({
                "status": "error",
                "message": f"RF voltage {u_rf_volts} V out of range [0, 200]"
            }), 400

        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": {"u_rf_volts": u_rf_volts}
        })

        if resp.get("status") == "success":
            with state_lock:
                current_state["params"]["u_rf_volts"] = u_rf_volts
            logger.info(f"[API] RF voltage set to {u_rf_volts}V")
            return jsonify({"status": "success", "u_rf_volts": u_rf_volts})
        else:
            logger.error(f"[API] Failed to set RF voltage: {resp.get('message')}")
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed")
            }), 400

    except ValueError as e:
        logger.warning(f"[API] Invalid RF voltage value: {e}")
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"[API] RF control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def _apply_piezo_voltage(voltage: float):
    """Apply piezo voltage to hardware (internal helper)."""
    resp = send_to_manager({
        "action": "SET",
        "source": "FLASK_PIEZO",
        "params": {"piezo": voltage}
    })
    if resp.get("status") == "success":
        with state_lock:
            current_state["params"]["piezo_output_voltage"] = voltage
        return True
    else:
        logger.error(f"Failed to apply piezo voltage: {resp.get('message')}")
        return False


@app.route('/api/control/piezo/setpoint', methods=['POST'])
def set_piezo_setpoint():
    """
    Set piezo voltage setpoint (does NOT enable output).

    Request: {"voltage": 2.5}
    Response: {"status": "success", "setpoint": 2.5}
    """
    logger.info(f"[API] POST /api/control/piezo/setpoint from {request.remote_addr}")
    try:
        data = request.get_json()
        if not data:
            logger.warning("[API] No JSON data provided")
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400

        voltage = float(data.get("voltage", 0))
        logger.info(f"[API] Setting piezo setpoint: {voltage}V")

        # Validate range (0-4V as per original spec)
        if not 0 <= voltage <= 4:
            logger.warning(f"[API] Piezo setpoint {voltage}V out of range")
            return jsonify({
                "status": "error",
                "message": f"Piezo setpoint {voltage}V out of range [0, 4]"
            }), 400

        with state_lock:
            current_state["params"]["piezo"] = voltage

        # If output is currently on, update the voltage immediately
        with state_lock:
            output_on = current_state["params"].get("piezo_output", False)

        if output_on:
            _apply_piezo_voltage(voltage)

        logger.info(f"[API] Piezo setpoint updated to {voltage}V (output_active={output_on})")
        return jsonify({
            "status": "success",
            "setpoint": voltage,
            "output_active": output_on
        })

    except ValueError as e:
        logger.warning(f"[API] Invalid piezo setpoint value: {e}")
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"[API] Piezo setpoint error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/piezo/output', methods=['POST'])
def set_piezo_output():
    """
    Enable/disable piezo output with kill switch protection.

    When enabled: Applies the setpoint voltage
    When disabled: Sets voltage to 0V

    Kill switch: Auto-shutdown after 10 seconds

    Request: {"enable": true}
    Response: {"status": "success", "output": true, "kill_switch": {...}}
    """
    logger.info(f"[API] POST /api/control/piezo/output from {request.remote_addr}")
    try:
        data = request.get_json()
        if not data:
            logger.warning("[API] No JSON data provided")
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400

        enable = bool(data.get("enable", False))
        
        with state_lock:
            setpoint = current_state["params"].get("piezo", 0.0)

        if enable:
            logger.warning(f"[API] ENABLING PIEZO OUTPUT at {setpoint}V")
            # Enable output - apply setpoint voltage
            if _apply_piezo_voltage(setpoint):
                # Register with kill switch
                def set_voltage(v):
                    _apply_piezo_voltage(v)
                def zero_voltage():
                    _apply_piezo_voltage(0.0)
                    with state_lock:
                        current_state["params"]["piezo_output"] = False

                kill_switch.register_on("piezo", set_voltage, zero_voltage)

                with state_lock:
                    current_state["params"]["piezo_output"] = True

                logger.warning(f"[API] PIEZO OUTPUT ENABLED: {setpoint}V (kill switch: 10s max)")

                return jsonify({
                    "status": "success",
                    "output": True,
                    "voltage": setpoint,
                    "kill_switch": {
                        "armed": True,
                        "time_limit_seconds": KILL_SWITCH_LIMITS["piezo"],
                        "warning": "AUTO-SHUTOFF AFTER 10 SECONDS"
                    }
                })
            else:
                logger.error("[API] Failed to enable piezo output")
                return jsonify({
                    "status": "error",
                    "message": "Failed to enable piezo output"
                }), 500
        else:
            logger.info("[API] DISABLING PIEZO OUTPUT")
            # Disable output - set to 0V
            _apply_piezo_voltage(0.0)
            kill_switch.register_off("piezo")

            with state_lock:
                current_state["params"]["piezo_output"] = False

            logger.info("[API] Piezo output disabled")
            return jsonify({
                "status": "success",
                "output": False,
                "voltage": 0.0
            })

    except Exception as e:
        logger.error(f"[API] Piezo output control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def _apply_e_gun_state(state: bool):
    """Apply e-gun state to hardware (internal helper)."""
    resp = send_to_manager({
        "action": "SET",
        "source": "FLASK_EGUN",
        "params": {"e_gun": state}
    })
    if resp.get("status") == "success":
        return True
    else:
        logger.error(f"Failed to apply e-gun state: {resp.get('message')}")
        return False


@app.route('/api/control/toggle/<toggle_name>', methods=['POST'])
def set_toggle(toggle_name):
    """
    Set a toggle state (bephi, b_field, be_oven, uv3, e_gun).

    For e_gun: Kill switch protected (max 30 seconds ON time)
    """
    logger.info(f"[API] POST /api/control/toggle/{toggle_name} from {request.remote_addr}")
    try:
        data = request.get_json()
        state = bool(data.get("state", False))
        logger.info(f"[API] Setting toggle {toggle_name}={state}")

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
            logger.warning(f"[API] Unknown toggle: {toggle_name}")
            return jsonify({
                "status": "error",
                "message": f"Unknown toggle: {toggle_name}",
                "valid_toggles": list(param_map.keys())
            }), 400

        # Special handling for e-gun (kill switch protected)
        if toggle_name == "e_gun":
            if state:
                logger.warning("[API] ENABLING E-GUN")
                # Turn ON with kill switch
                if _apply_e_gun_state(True):
                    # Register with kill switch
                    def set_state(s):
                        send_to_manager({
                            "action": "SET",
                            "source": "FLASK_EGUN_KS",
                            "params": {"e_gun": s}
                        })
                    def zero_state():
                        send_to_manager({
                            "action": "SET",
                            "source": "FLASK_EGUN_KS",
                            "params": {"e_gun": False}
                        })
                        with state_lock:
                            current_state["params"]["e_gun"] = False

                    kill_switch.register_on("e_gun", set_state, zero_state)

                    with state_lock:
                        current_state["params"]["e_gun"] = True

                    logger.warning("[API] E-GUN ENABLED (kill switch: 30s max)")

                    return jsonify({
                        "status": "success",
                        "toggle": toggle_name,
                        "state": True,
                        "kill_switch": {
                            "armed": True,
                            "time_limit_seconds": KILL_SWITCH_LIMITS["e_gun"],
                            "warning": "AUTO-SHUTOFF AFTER 30 SECONDS"
                        }
                    })
                else:
                    logger.error("[API] Failed to enable e-gun")
                    return jsonify({
                        "status": "error",
                        "message": "Failed to enable e-gun"
                    }), 500
            else:
                logger.info("[API] DISABLING E-GUN")
                # Turn OFF
                _apply_e_gun_state(False)
                kill_switch.register_off("e_gun")

                with state_lock:
                    current_state["params"]["e_gun"] = False

                logger.info("[API] E-gun disabled")
                return jsonify({
                    "status": "success",
                    "toggle": toggle_name,
                    "state": False
                })

        # Standard toggles (no kill switch)
        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": {param_name: state}
        })

        if resp.get("status") == "success":
            with state_lock:
                current_state["params"][param_name] = state
            logger.info(f"[API] Toggle {toggle_name}={state} set successfully")
            return jsonify({
                "status": "success",
                "toggle": toggle_name,
                "state": state
            })
        else:
            logger.error(f"[API] Failed to set toggle {toggle_name}: {resp.get('message')}")
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed")
            }), 400

    except Exception as e:
        logger.error(f"[API] Toggle control error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/killswitch/status', methods=['GET'])
def get_killswitch_status():
    """Get kill switch status for all protected devices."""
    logger.debug(f"[API] GET /api/killswitch/status from {request.remote_addr}")
    return jsonify({
        "status": "success",
        "devices": kill_switch.get_status(),
        "limits": KILL_SWITCH_LIMITS
    })


@app.route('/api/killswitch/trigger', methods=['POST'])
def trigger_killswitch():
    """
    Manually trigger kill switch for a device.

    Request: {"device": "piezo"} or {"device": "e_gun"}
    """
    logger.warning(f"[API] POST /api/killswitch/trigger from {request.remote_addr}")
    try:
        data = request.get_json()
        device = data.get("device")

        if device not in KILL_SWITCH_LIMITS:
            logger.warning(f"[API] Unknown kill switch device: {device}")
            return jsonify({
                "status": "error",
                "message": f"Unknown device: {device}",
                "valid_devices": list(KILL_SWITCH_LIMITS.keys())
            }), 400

        logger.warning(f"[API] MANUAL KILL SWITCH TRIGGER for {device}")
        killed = kill_switch.trigger_kill(device, "MANUAL TRIGGER")

        if killed:
            logger.warning(f"[API] Kill switch triggered for {device}")
            return jsonify({
                "status": "success",
                "message": f"Kill switch triggered for {device}",
                "device": device
            })
        else:
            logger.warning(f"[API] Kill switch trigger: {device} was not active")
            return jsonify({
                "status": "warning",
                "message": f"Device {device} was not active",
                "device": device
            })

    except Exception as e:
        logger.error(f"[API] Kill switch trigger error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/dds', methods=['POST'])
def set_dds():
    """
    Set DDS frequency (LabVIEW controlled only).

    Protocol-compliant parameter names:
    - dds_freq_mhz: 0-200 (DDS frequency in MHz, LabVIEW only)

    Legacy aliases (for backwards compatibility):
    - freq_mhz -> dds_freq_mhz
    """
    try:
        data = request.get_json()
        params = {}

        # Handle frequency (protocol: dds_freq_mhz)
        # Accept dds_freq_mhz (protocol) or freq_mhz (legacy)
        freq_mhz = data.get("dds_freq_mhz") or data.get("dds_freq_Mhz") or data.get("freq_mhz")

        if freq_mhz is not None:
            freq_mhz = float(freq_mhz)
            if not 0 <= freq_mhz <= 200:  # 0-200 MHz (LabVIEW range)
                return jsonify({
                    "status": "error",
                    "message": f"DDS frequency {freq_mhz} MHz out of range [0, 200]"
                }), 400
            params["dds_freq_mhz"] = freq_mhz
        else:
            return jsonify({
                "status": "error",
                "message": "No valid parameter provided (dds_freq_mhz)"
            }), 400

        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": params
        })

        if resp.get("status") == "success":
            with state_lock:
                current_state["params"]["dds_freq_mhz"] = params["dds_freq_mhz"]

            return jsonify({
                "status": "success",
                "dds_freq_mhz": params["dds_freq_mhz"]
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


@app.route('/api/set', methods=['POST'])
def set_device():
    """
    Simplified unified control endpoint for all devices.

    New protocol format: {"device": "<name>", "value": <value>}

    Supported devices:
    - {"device": "u_rf", "value": 100.0}              # RF voltage U_RF (0-200V)
    - {"device": "trap", "value": [10, 10, 6, 37]}    # EC1, EC2, Comp_H, Comp_V
    - {"device": "ec1", "value": 10.0}                # Single electrode
    - {"device": "ec2", "value": 10.0}
    - {"device": "comp_h", "value": 6.0}
    - {"device": "comp_v", "value": 37.0}
    - {"device": "piezo", "value": 2.5}               # Piezo voltage (0-4V)
    - {"device": "dds", "value": 100.0}               # DDS frequency (0-200 MHz, LabVIEW only)
    - {"device": "b_field", "value": 1}               # 1=on, 0=off
    - {"device": "be_oven", "value": 1}               # 1=on, 0=off
    - {"device": "uv3", "value": 1}                   # 1=on, 0=off
    - {"device": "e_gun", "value": 1}                 # 1=on, 0=off
    - {"device": "bephi", "value": 1}                 # 1=on, 0=off

    Experiment commands:
    - {"device": "sweep", "value": [start, end, steps, ...]}
    """
    logger.info(f"[API] POST /api/set from {request.remote_addr}")
    try:
        data = request.get_json()
        if not data:
            logger.warning("[API] No JSON data provided")
            return jsonify({"status": "error", "message": "No JSON data provided"}), 400

        device = data.get("device")
        value = data.get("value")

        if not device:
            logger.warning("[API] Missing 'device' field")
            return jsonify({"status": "error", "message": "Missing 'device' field"}), 400

        logger.info(f"[API] Unified set device={device}, value={value}")

        # Build params based on device type
        params = {}

        # Single value devices
        single_value_devices = {
            "u_rf": "u_rf_volts",
            "ec1": "ec1",
            "ec2": "ec2",
            "comp_h": "comp_h",
            "comp_v": "comp_v",
            "piezo": "piezo",
            "dds": "dds_freq_mhz",  # LabVIEW controlled only, 0-200 MHz
        }

        # Toggle devices (0=off, 1=on)
        toggle_devices = {
            "b_field": "b_field",
            "be_oven": "be_oven",
            "uv3": "uv3",
            "e_gun": "e_gun",
            "bephi": "bephi",
            "hd_valve": "hd_valve",
        }

        if device in single_value_devices:
            param_name = single_value_devices[device]
            params[param_name] = float(value) if isinstance(value, (int, float, str)) else value

        elif device in toggle_devices:
            param_name = toggle_devices[device]
            # Convert to integer (0 or 1)
            if isinstance(value, (int, float)):
                params[param_name] = 1 if int(value) else 0
            else:
                params[param_name] = 1 if value else 0

        elif device == "trap":
            # Trap electrodes: [EC1, EC2, Comp_H, Comp_V]
            if isinstance(value, (list, tuple)) and len(value) >= 4:
                params["ec1"] = float(value[0])
                params["ec2"] = float(value[1])
                params["comp_h"] = float(value[2])
                params["comp_v"] = float(value[3])
            else:
                logger.warning(f"[API] Invalid trap value format: {value}")
                return jsonify({
                    "status": "error",
                    "message": "trap value must be [EC1, EC2, Comp_H, Comp_V]"
                }), 400

        elif device == "sweep":
            # Sweep command - forward to manager as action
            if isinstance(value, (list, tuple)):
                sweep_params = {
                    "target_frequency_khz": float(value[0]) if len(value) > 0 else 307.0,
                    "span_khz": float(value[1]) if len(value) > 1 else 40.0,
                    "steps": int(value[2]) if len(value) > 2 else 41,
                }
                # Add optional parameters if provided
                if len(value) > 3:
                    sweep_params["attenuation_db"] = float(value[3])
                if len(value) > 4:
                    sweep_params["on_time_ms"] = float(value[4])
                if len(value) > 5:
                    sweep_params["off_time_ms"] = float(value[5])
            else:
                sweep_params = {"target_frequency_khz": float(value)}

            logger.info(f"[API] Starting sweep with params: {sweep_params}")
            resp = send_to_manager({
                "action": "SWEEP",
                "source": "USER",
                "params": sweep_params
            })

            return jsonify({
                "status": resp.get("status", "error"),
                "exp_id": resp.get("exp_id"),
                "message": resp.get("message", resp.get("reason"))
            })

        else:
            logger.warning(f"[API] Unknown device: {device}")
            return jsonify({
                "status": "error",
                "message": f"Unknown device: {device}",
                "valid_devices": list(single_value_devices.keys()) + list(toggle_devices.keys()) + ["trap", "sweep"]
            }), 400

        # Send to manager
        resp = send_to_manager({
            "action": "SET",
            "source": "USER",
            "params": params
        })

        if resp.get("status") == "success":
            # Update local state
            with state_lock:
                current_state["params"].update(params)

            logger.info(f"[API] Device {device} set successfully: {params}")
            return jsonify({
                "status": "success",
                "device": device,
                "value": value,
                "params": params
            })
        else:
            logger.error(f"[API] Failed to set device {device}: {resp.get('message')}")
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed"),
                "code": resp.get("code", "UNKNOWN")
            }), 400

    except ValueError as e:
        logger.warning(f"[API] Invalid value in set device: {e}")
        return jsonify({"status": "error", "message": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"[API] Set device error: {e}")
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
    logger.info(f"[API] POST /api/safety/toggle from {request.remote_addr}")
    try:
        data = request.get_json()
        engage_safety = bool(data.get("engage", True))

        if engage_safety:
            logger.warning("[API] ENGAGING SAFETY MODE")
            # ENGAGE SAFE MODE
            result = safe_shutdown()
            logger.warning("[API] Safety mode engaged successfully")

            return jsonify({
                "status": "success",
                "mode": "SAFE",
                "message": "Safety mode engaged. Algorithm stopped, hardware reset.",
                "details": result
            })

        else:
            logger.info("[API] DISENGAGING SAFETY MODE - Switching to AUTO")
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

            logger.info("[API] Algorithm mode (AUTO) enabled")
            return jsonify({
                "status": "success",
                "mode": "AUTO",
                "message": "Algorithm mode enabled. Turbo optimization is running.",
                "manager_response": resp
            })

    except Exception as e:
        logger.error(f"[API] Safety toggle error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/safety/status', methods=['GET'])
def get_safety_status():
    """Get current safety status."""
    logger.debug(f"[API] GET /api/safety/status from {request.remote_addr}")
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
    if not TELEMETRY_AVAILABLE:
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
    if not TELEMETRY_AVAILABLE:
        return jsonify({"status": "error", "message": "Data server unavailable"}), 503

    try:
        from services.comms.data_server import DataIngestionServer

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
# FLASK ROUTES - CAMERA CONTROL
# =============================================================================

@app.route('/api/camera/start', methods=['POST'])
def start_camera():
    """
    Start camera recording.
    
    Request body:
    {
        "mode": "infinite",  # or "single" for DCIMG recording
        "trigger": true      # whether to send TTL trigger
    }
    """
    try:
        data = request.get_json() or {}
        mode = data.get("mode", "infinite")
        send_trigger = data.get("trigger", True)
        
        logger.info(f"Camera start requested: mode={mode}, trigger={send_trigger}")
        
        resp = send_to_manager({
            "action": "CAMERA_START",
            "source": "FLASK",
            "mode": "inf" if mode == "infinite" else "single",
            "trigger": send_trigger
        })
        
        if resp.get("status") == "success":
            with state_lock:
                current_state["camera_active"] = True
            
            return jsonify({
                "status": "success",
                "message": resp.get("message", "Camera started"),
                "mode": mode,
                "trigger_sent": resp.get("trigger_sent", False)
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed to start camera"),
                "code": resp.get("code", "CAMERA_ERROR")
            }), 400
            
    except Exception as e:
        logger.error(f"Camera start error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/camera/stop', methods=['POST'])
def stop_camera():
    """Stop camera recording."""
    try:
        logger.info("Camera stop requested")
        
        resp = send_to_manager({
            "action": "CAMERA_STOP",
            "source": "FLASK"
        })
        
        if resp.get("status") == "success":
            with state_lock:
                current_state["camera_active"] = False
            
            return jsonify({
                "status": "success",
                "message": resp.get("message", "Camera stopped")
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed to stop camera")
            }), 400
            
    except Exception as e:
        logger.error(f"Camera stop error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/camera/status', methods=['GET'])
def get_camera_status():
    """Get camera status."""
    try:
        resp = send_to_manager({
            "action": "CAMERA_STATUS",
            "source": "FLASK"
        })
        
        if resp.get("status") == "success":
            camera_data = resp.get("camera", {})
            
            # Merge with local state
            with state_lock:
                camera_data["flask_active"] = current_state.get("camera_active", False)
            
            return jsonify({
                "status": "success",
                "camera": camera_data
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed to get camera status")
            }), 400
            
    except Exception as e:
        logger.error(f"Camera status error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/camera/trigger', methods=['POST'])
def trigger_camera():
    """
    Send TTL trigger to camera.
    
    This triggers a single frame capture when the camera is already recording.
    """
    try:
        logger.info("Camera TTL trigger requested")
        
        resp = send_to_manager({
            "action": "CAMERA_TRIGGER",
            "source": "FLASK"
        })
        
        if resp.get("status") == "success":
            return jsonify({
                "status": "success",
                "message": resp.get("message", "Camera TTL trigger sent")
            })
        else:
            return jsonify({
                "status": "error",
                "message": resp.get("message", "Failed to trigger camera")
            }), 400
            
    except Exception as e:
        logger.error(f"Camera trigger error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/camera/settings', methods=['GET', 'POST'])
def camera_settings():
    """
    Get or set camera settings.
    
    GET: Returns current camera settings
    POST: Updates camera settings
    """
    if request.method == 'GET':
        try:
            # Return default/cached settings
            # In a full implementation, these would be fetched from the camera server
            return jsonify({
                "status": "success",
                "settings": {
                    "exposure_ms": 300,
                    "trigger_mode": "software",
                    "max_frames": 100,
                    "roi": {
                        "x_start": 180,
                        "x_finish": 220,
                        "y_start": 425,
                        "y_finish": 495
                    },
                    "filter_radius": 6
                }
            })
        except Exception as e:
            logger.error(f"Camera settings get error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    else:  # POST
        try:
            data = request.get_json() or {}
            logger.info(f"Camera settings update: {data}")
            
            # In a full implementation, these would be sent to the camera server
            return jsonify({
                "status": "success",
                "message": "Camera settings updated",
                "settings": data
            })
            
        except Exception as e:
            logger.error(f"Camera settings update error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/ion_data/latest', methods=['GET'])
def get_latest_ion_data():
    """
    Get the latest ion position and fit data.
    
    Returns JSON data in the format:
    {
        "timestamp": "2026-02-02T14:30:15.123456",
        "ions": {
            "ion_1": {"pos_x": 320.5, "pos_y": 240.3, "sig_x": 15.2, "R_y": 8.7}
        }
    }
    """
    try:
        # Try to read from ion_data directory
        from datetime import datetime
        today_str = datetime.now().strftime("%y%m%d")
        ion_data_path = Path(f"E:/Data/ion_data/{today_str}")
        
        if not ion_data_path.exists():
            return jsonify({
                "status": "success",
                "data": None,
                "message": "No ion data available yet"
            })
        
        # Get most recent JSON file
        json_files = sorted(ion_data_path.glob("ion_data_*.json"))
        if not json_files:
            return jsonify({
                "status": "success",
                "data": None,
                "message": "No ion data available yet"
            })
        
        latest = json_files[-1]
        with open(latest, 'r') as f:
            data = json.load(f)
        
        return jsonify({
            "status": "success",
            "data": data,
            "source": str(latest.name)
        })
        
    except Exception as e:
        logger.error(f"Get ion data error: {e}")
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
        logger.info("[STARTUP] Flask Dashboard Server Starting...")
        logger.info("=" * 60)
        logger.info(f"[STARTUP] Manager ZMQ endpoint: {MANAGER_IP}:{MANAGER_PORT}")
        logger.info(f"[STARTUP] Flask HTTP server: http://0.0.0.0:5000")
        logger.info(f"[STARTUP] Camera frames path: {LIVE_FRAMES_PATH}")
        logger.info(f"[STARTUP] Kill switch limits: Piezo={KILL_SWITCH_LIMITS['piezo']}s, E-Gun={KILL_SWITCH_LIMITS['e_gun']}s")
        logger.info("[STARTUP] All API endpoints registered")
        logger.info("[STARTUP] Ready to accept connections")
        logger.info("-" * 60)
        
        print(f"=" * 60)
        print(f"Dashboard running at http://0.0.0.0:5000")
        print(f"Connected to manager at {MANAGER_IP}:{MANAGER_PORT}")
        print(f"Streaming annotated frames from: {LIVE_FRAMES_PATH}")
        print(f"Scientific Dashboard - Turbo Algorithm Control")
        print(f"=" * 60)

        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] Shutdown requested by user")
    except Exception as e:
        logger.error(f"[FATAL] Fatal error: {e}", exc_info=True)
        raise
    finally:
        cleanup()
