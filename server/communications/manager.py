"""
Control Manager - Central coordinator for the lab control framework.

Manages communication between:
- Web UI (Flask) via REQ/REP on port 5557
- ARTIQ Worker via PUB/SUB on port 5555 (commands)
- Data collection via PULL on port 5556 (worker feedback)
- Turbo Algorithm optimization process
- LabVIEW hardware interface

Features:
- Mode management (MANUAL / AUTO / SAFE)
- Experiment tracking
- Safety interlocks with KILL SWITCHES
- Structured logging
- Turbo algorithm coordination

SAFETY CRITICAL:
- Piezo Output: Max 10 seconds ON time (manager-level kill switch)
- E-Gun Output: Max 30 seconds ON time (manager-level kill switch)
"""

import zmq
import time
import json
import threading
import logging
import socket
from typing import Optional, Dict, Any, Set, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass, field

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core import (
    get_config,
    setup_logging,
    get_tracker,
    log_safety_trigger,
)
from core.exceptions import ConnectionError, SafetyError
from core.enums import (
    SystemMode, AlgorithmState, CommandType,
    smile_mv_to_real_volts
)


# =============================================================================
# CAMERA INTERFACE - Direct control of CCD camera
# =============================================================================

class CameraInterface:
    """
    Direct interface to the camera server.
    
    Provides simplified camera control without going through Flask.
    Communicates directly with camera_server via TCP.
    
    This eliminates the messy chain:
    ARTIQ -> Flask -> TCP -> camera_server -> camera_logic
    
    And replaces it with:
    Manager -> camera_server (direct TCP)
    ARTIQ TTL trigger -> camera (hardware trigger)
    """
    
    def __init__(self, host: str = '127.0.0.1', port: Optional[int] = None):
        """
        Initialize camera interface.
        
        Args:
            host: Camera server host (default: localhost)
            port: Camera server port (default from config or 5558)
        """
        self.logger = logging.getLogger("camera_interface")
        
        # Load configuration
        config = get_config()
        self.host = host
        self.port = port or config.get('network.camera_port', 5558)
        self.timeout = 5.0
        
        # Camera state
        self.is_recording = False
        self.lock = threading.RLock()
        
        self.logger.info(f"Camera Interface initialized ({self.host}:{self.port})")
    
    def _send_command(self, command: str) -> Tuple[bool, str]:
        """
        Send command to camera server.
        
        Args:
            command: Command string (START, START_INF, STOP, STATUS)
            
        Returns:
            Tuple of (success, response_message)
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect((self.host, self.port))
                s.sendall(command.encode() + b'\n')
                response = s.recv(1024).decode().strip()
                
                if response.startswith("OK:"):
                    return True, response
                else:
                    return False, response
                    
        except socket.timeout:
            self.logger.error(f"Camera server timeout")
            return False, "Timeout"
        except ConnectionRefusedError:
            self.logger.error(f"Camera server not available at {self.host}:{self.port}")
            return False, "Connection refused"
        except Exception as e:
            self.logger.error(f"Camera communication error: {e}")
            return False, str(e)
    
    def start_recording(self, mode: str = "inf", exp_id: Optional[str] = None) -> bool:
        """
        Start camera recording.
        
        Args:
            mode: Recording mode - "inf" for infinite capture, "single" for DCIMG recording
            exp_id: Optional experiment ID for metadata
            
        Returns:
            True if successful
        """
        with self.lock:
            if mode == "inf":
                success, msg = self._send_command("START_INF")
            else:
                success, msg = self._send_command("START")
            
            if success:
                self.is_recording = True
                self.logger.info(f"Camera recording started ({mode} mode)")
                
                # Send experiment ID if provided
                if exp_id:
                    self._send_command(f"EXP_ID:{exp_id}")
            else:
                self.logger.error(f"Failed to start camera: {msg}")
            
            return success
    
    def stop_recording(self) -> bool:
        """
        Stop camera recording.
        
        Returns:
            True if successful
        """
        with self.lock:
            success, msg = self._send_command("STOP")
            
            if success:
                self.is_recording = False
                self.logger.info("Camera recording stopped")
            else:
                self.logger.error(f"Failed to stop camera: {msg}")
            
            return success
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get camera status.
        
        Returns:
            Dictionary with status information
        """
        success, msg = self._send_command("STATUS")
        
        with self.lock:
            return {
                "connected": success,
                "recording": self.is_recording,
                "status_message": msg if success else "Unknown",
                "server": f"{self.host}:{self.port}"
            }


# =============================================================================
# KILL SWITCH MANAGER - MANAGER LEVEL SAFETY
# =============================================================================

class ManagerKillSwitch:
    """
    Manager-level kill switch for time-limited hardware outputs.
    
    This provides an additional layer of safety beyond Flask-level kill switches.
    Time limits:
    - piezo: 10 seconds max
    - e_gun: 30 seconds max
    
    On timeout: Automatically commands LabVIEW to set voltage to 0V.
    """
    
    TIME_LIMITS = {
        "piezo": 10.0,   # 10 seconds
        "e_gun": 10.0,   # 10 seconds (testing mode)
    }
    
    def __init__(self):
        self._active: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._running = True
        self._callbacks: Dict[str, Callable] = {}
        self.logger = logging.getLogger("manager_kill_switch")
        
        # Start watchdog
        self._watchdog = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="ManagerKillSwitch"
        )
        self._watchdog.start()
        self.logger.info("Manager Kill Switch initialized")
    
    def register_callback(self, device: str, kill_callback: Callable):
        """Register a callback to be called when kill switch triggers."""
        self._callbacks[device] = kill_callback
    
    def arm(self, device: str, metadata: Dict[str, Any] = None):
        """Arm the kill switch for a device."""
        with self._lock:
            if device not in self.TIME_LIMITS:
                self.logger.warning(f"Unknown device: {device}")
                return False
            
            self._active[device] = {
                "start_time": time.time(),
                "metadata": metadata or {},
                "killed": False,
            }
            self.logger.warning(
                f"KILL SWITCH ARMED for {device} "
                f"(limit: {self.TIME_LIMITS[device]}s)"
            )
            return True
    
    def disarm(self, device: str):
        """Disarm the kill switch (safe turn-off by user)."""
        with self._lock:
            if device in self._active:
                elapsed = time.time() - self._active[device]["start_time"]
                self.logger.info(
                    f"Kill switch disarmed for {device} "
                    f"(was active for {elapsed:.1f}s)"
                )
                del self._active[device]
                return True
            return False
    
    def is_armed(self, device: str) -> bool:
        """Check if kill switch is armed for a device."""
        with self._lock:
            return device in self._active and not self._active[device].get("killed", False)
    
    def trigger(self, device: str, reason: str = "manual") -> bool:
        """
        Manually trigger the kill switch.
        
        Returns True if device was killed, False if not armed.
        """
        with self._lock:
            if device not in self._active:
                return False
            
            info = self._active[device]
            if info.get("killed"):
                return False
            
            info["killed"] = True
            elapsed = time.time() - info["start_time"]
            
            self.logger.error(
                f"KILL SWITCH TRIGGERED for {device}: {reason} "
                f"(was on for {elapsed:.1f}s)"
            )
            
            # Execute callback if registered
            if device in self._callbacks:
                try:
                    self._callbacks[device]()
                except Exception as e:
                    self.logger.error(f"Kill switch callback failed: {e}")
            
            del self._active[device]
            return True
    
    def _watchdog_loop(self):
        """Monitor active devices and enforce time limits."""
        while self._running:
            try:
                with self._lock:
                    now = time.time()
                    to_kill = []
                    
                    for device, info in self._active.items():
                        if info.get("killed"):
                            continue
                        elapsed = now - info["start_time"]
                        limit = self.TIME_LIMITS[device]
                        
                        if elapsed > limit:
                            to_kill.append(device)
                
                for device in to_kill:
                    self.trigger(device, f"TIME LIMIT EXCEEDED ({self.TIME_LIMITS[device]}s)")
                
                time.sleep(0.1)  # 10 Hz check rate
                
            except Exception as e:
                self.logger.error(f"Kill switch watchdog error: {e}")
                time.sleep(1)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current kill switch status."""
        with self._lock:
            status = {}
            for device, limit in self.TIME_LIMITS.items():
                if device in self._active:
                    info = self._active[device]
                    elapsed = time.time() - info["start_time"]
                    status[device] = {
                        "armed": True,
                        "elapsed": elapsed,
                        "remaining": max(0, limit - elapsed),
                        "limit": limit,
                        "killed": info.get("killed", False),
                    }
                else:
                    status[device] = {
                        "armed": False,
                        "limit": limit,
                    }
            return status
    
    def shutdown(self):
        """Shutdown kill switch and trigger all active devices."""
        self._running = False
        with self._lock:
            for device in list(self._active.keys()):
                self.trigger(device, "SHUTDOWN")


# =============================================================================
# LABVIEW FILE READER - Reads data files written by LabVIEW to Y:\Xi\Data\
# =============================================================================

class LabVIEWFileReader:
    """
    Reads data files written by LabVIEW to shared drive and stores in telemetry.
    
    Expected directory structure:
        E:/Data/telemetry/
        ├── wavemeter/*.dat      - CSV: timestamp,frequency_mhz
        ├── smile/pmt/*.dat      - CSV: timestamp,pmt_counts
        ├── smile/pressure/*.dat - CSV: timestamp,pressure_mbar
        └── camera/*.json        - JSON: pos_x, pos_y, sig_x, sig_y
    
    This runs in a background thread polling for new files.
    """
    
    def __init__(self, base_path: str = "E:/Data/telemetry", poll_interval: float = 1.0):
        self.logger = logging.getLogger("labview_file_reader")
        self.base_path = Path(base_path)
        self.poll_interval = poll_interval
        
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.known_files: Dict[str, set] = {}  # subdir -> set of filenames
        
        # Track stats per source
        self.stats = {
            "wavemeter": {"count": 0, "last_value": None},
            "smile_pmt": {"count": 0, "last_value": None},
            "smile_pressure": {"count": 0, "last_value": None},
            "camera": {"count": 0, "last_value": None},
        }
    
    def start(self):
        """Start the file reader thread."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name="LabVIEWFileReader"
        )
        self.thread.start()
        self.logger.info(f"LabVIEWFileReader started - watching {self.base_path}")
    
    def stop(self):
        """Stop the file reader."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.logger.info("LabVIEWFileReader stopped")
    
    def _read_loop(self):
        """Main loop - poll directories and read new files."""
        # Initialize known files
        for subdir in ["wavemeter", "smile/pmt", "smile/pressure", "camera"]:
            path = self.base_path / subdir
            if path.exists():
                self.known_files[subdir] = set(p.name for p in path.glob("*"))
            else:
                self.known_files[subdir] = set()
        
        while self.running:
            try:
                self._check_wavemeter()
                self._check_smile_pmt()
                self._check_smile_pressure()
                self._check_camera()
                
                time.sleep(self.poll_interval)
            except Exception as e:
                self.logger.error(f"File read error: {e}")
                time.sleep(self.poll_interval)
    
    def _check_wavemeter(self):
        """Check for new wavemeter files."""
        watch_dir = self.base_path / "wavemeter"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.dat"))
        new_files = current_files - self.known_files.get("wavemeter", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                timestamp, value = self._read_csv_file(filepath)
                if timestamp and value is not None:
                    store_data_point("laser_freq", value, timestamp)
                    update_data_source("wavemeter", timestamp)
                    self.stats["wavemeter"]["count"] += 1
                    self.stats["wavemeter"]["last_value"] = value
            except Exception as e:
                self.logger.debug(f"Failed to read {fname}: {e}")
        
        self.known_files["wavemeter"] = current_files
    
    def _check_smile_pmt(self):
        """Check for new SMILE PMT files."""
        watch_dir = self.base_path / "smile" / "pmt"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.dat"))
        new_files = current_files - self.known_files.get("smile/pmt", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                timestamp, value = self._read_csv_file(filepath)
                if timestamp and value is not None:
                    store_data_point("pmt", value, timestamp)
                    update_data_source("smile", timestamp)
                    self.stats["smile_pmt"]["count"] += 1
                    self.stats["smile_pmt"]["last_value"] = value
            except Exception as e:
                self.logger.debug(f"Failed to read {fname}: {e}")
        
        self.known_files["smile/pmt"] = current_files
    
    def _check_smile_pressure(self):
        """Check for new SMILE pressure files."""
        watch_dir = self.base_path / "smile" / "pressure"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.dat"))
        new_files = current_files - self.known_files.get("smile/pressure", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                timestamp, value = self._read_csv_file(filepath)
                if timestamp and value is not None:
                    store_data_point("pressure", value, timestamp)
                    update_data_source("smile", timestamp)
                    self.stats["smile_pressure"]["count"] += 1
                    self.stats["smile_pressure"]["last_value"] = value
            except Exception as e:
                self.logger.debug(f"Failed to read {fname}: {e}")
        
        self.known_files["smile/pressure"] = current_files
    
    def _check_camera(self):
        """Check for new camera JSON files."""
        watch_dir = self.base_path / "camera"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.json"))
        new_files = current_files - self.known_files.get("camera", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                data = self._read_json_file(filepath)
                if data:
                    timestamp = data.get("timestamp", time.time())
                    
                    # Store position data
                    for key in ["pos_x", "pos_y", "sig_x", "sig_y"]:
                        if key in data:
                            store_data_point(key, data[key], timestamp)
                    
                    update_data_source("camera", timestamp)
                    self.stats["camera"]["count"] += 1
            except Exception as e:
                self.logger.debug(f"Failed to read {fname}: {e}")
        
        self.known_files["camera"] = current_files
    
    def _read_csv_file(self, filepath: Path) -> tuple:
        """Read CSV file: timestamp,value."""
        try:
            with open(filepath, 'r') as f:
                line = f.readline().strip()
                if ',' in line:
                    parts = line.split(',')
                    timestamp = float(parts[0])
                    value = float(parts[1])
                    return timestamp, value
        except Exception:
            pass
        return None, None
    
    def _read_json_file(self, filepath: Path) -> dict:
        """Read JSON file."""
        try:
            import json
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def get_stats(self) -> dict:
        """Get reader statistics."""
        return {
            "running": self.running,
            "base_path": str(self.base_path),
            "stats": self.stats.copy(),
            "known_files": {k: len(v) for k, v in self.known_files.items()}
        }


# Import LabVIEW interface
try:
    from .labview_interface import LabVIEWInterface, LabVIEWCommandType
    LABVIEW_AVAILABLE = True
except ImportError:
    LABVIEW_AVAILABLE = False

# Import shared telemetry storage (LabVIEW writes files, Manager reads them)
try:
    from .data_server import (
        store_data_point, 
        update_data_source, 
        get_data_sources,
        get_statistics as get_telemetry_stats
    )
    TELEMETRY_STORAGE_AVAILABLE = True
except ImportError:
    TELEMETRY_STORAGE_AVAILABLE = False


@dataclass
class TurboAlgorithmState:
    """State tracking for Turbo algorithm."""
    status: AlgorithmState = AlgorithmState.IDLE
    current_iteration: int = 0
    convergence_delta: float = 0.0
    target_parameter: Optional[str] = None
    start_time: Optional[float] = None
    last_update: Optional[float] = None
    error_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "iteration": self.current_iteration,
            "convergence_delta": self.convergence_delta,
            "target_parameter": self.target_parameter,
            "start_time": self.start_time,
            "runtime_seconds": time.time() - self.start_time if self.start_time else 0
        }


class ControlManager:
    """
    Central control manager for coordinating lab components.
    
    Attributes:
        mode: Current system mode (MANUAL/AUTO/SAFE)
        current_exp: Currently active experiment context
        params: Unified parameter state
        turbo_state: Turbo algorithm execution state
    """
    
    # Valid parameter names for validation
    VALID_PARAMS: Set[str] = {
        # RF Voltage (real voltage in volts)
        "u_rf_volts",
        # Electrodes
        "ec1", "ec2", "comp_h", "comp_v",
        # Cooling parameters
        "freq0", "amp0", "freq1", "amp1", "sw0", "sw1",
        # Toggles
        "bephi", "b_field", "be_oven", "uv3", "e_gun",
        # Laser & Piezo
        "piezo",
        # DDS
        "dds_profile",
        "dds_freq_khz"
    }
    
    # Parameter ranges for safety validation
    PARAM_RANGES: Dict[str, tuple] = {
        "u_rf_volts": (0, 500),   # Real RF voltage 0-500V (500V max for safety)
        "ec1": (-100, 100),       # Electrode voltages +/-100V
        "ec2": (-100, 100),
        "comp_h": (-100, 100),
        "comp_v": (-100, 100),
        "freq0": (200, 220),      # Raman frequency range (MHz)
        "freq1": (200, 220),
        "amp0": (0, 1),           # Raman amplitude range
        "amp1": (0, 1),
        "piezo": (0, 4),          # Piezo 0-4V
        "dds_profile": (0, 7),    # DDS profiles 0-7
        "dds_freq_khz": (0, 500), # DDS frequency 0-500 kHz
    }
    
    def __init__(self):
        """Initialize the control manager."""
        # Setup logging
        self.logger = setup_logging(component="manager")
        self.logger.info("=" * 60)
        self.logger.info("Control Manager Starting...")
        
        # Load configuration
        self.config = get_config()
        self.cmd_port = self.config.cmd_port
        self.data_port = self.config.data_port
        self.client_port = self.config.client_port
        
        # Initialize ZMQ context
        self.ctx = zmq.Context()
        
        # Setup sockets
        self._setup_sockets()
        
        # System state
        self.mode = SystemMode.MANUAL
        self.lock = threading.RLock()
        self.running = True
        
        # Turbo algorithm state
        self.turbo_state = TurboAlgorithmState()
        self.turbo_lock = threading.Lock()
        
        # Unified Parameter State
        defaults = self.config.get_all_hardware_defaults()
        self.params = {
            # RF Voltage (real voltage in volts)
            "u_rf_volts": defaults.get("u_rf_volts", 200.0),
            # DC Electrodes
            "ec1": defaults.get("ec1", 0.0),
            "ec2": defaults.get("ec2", 0.0),
            "comp_h": defaults.get("comp_h", 0.0),
            "comp_v": defaults.get("comp_v", 0.0),
            # Cooling parameters
            "freq0": defaults.get("freq0", 212.5),
            "amp0": defaults.get("amp0", 0.05),
            "freq1": defaults.get("freq1", 212.5),
            "amp1": defaults.get("amp1", 0.05),
            "sw0": defaults.get("sw0", False),
            "sw1": defaults.get("sw1", False),
            # Toggles
            "bephi": defaults.get("bephi", False),
            "b_field": defaults.get("b_field", True),
            "be_oven": defaults.get("be_oven", False),
            "uv3": defaults.get("uv3", False),
            "e_gun": defaults.get("e_gun", False),
            # Laser & Piezo
            "piezo": defaults.get("piezo", 0.0),
            # DDS
            "dds_profile": defaults.get("dds_profile", 0),
            "dds_freq_khz": defaults.get("dds_freq_khz", 0),
        }
        
        # Experiment tracking
        self.tracker = get_tracker()
        self.current_exp: Optional[Any] = None
        
        # Component health tracking
        self.last_worker_heartbeat = time.time()
        self.worker_alive = False
        self.worker_lock = threading.Lock()
        
        # Safety tracking
        self.safety_triggered = False
        
        # Kill Switch Manager
        self.kill_switch = ManagerKillSwitch()
        
        # LabVIEW Interface
        self.labview: Optional[LabVIEWInterface] = None
        self._init_labview()
        
        # Register kill switch callbacks after LabVIEW is initialized
        self._setup_kill_switch_callbacks()
        
        # LabVIEW file reader (reads data files from Y:\Xi\Data\)
        self.labview_data_reader = LabVIEWFileReader()
        self.labview_data_reader.start()
        
        # Camera Interface (direct control, bypassing Flask)
        self.camera: Optional[CameraInterface] = None
        self._init_camera()
        
        # Start background threads
        self._start_background_threads()
        
        self.logger.info("Manager Online. Ready for ARTIQ & Turbo Algorithm.")
        if self.labview and self.labview.is_connected():
            self.logger.info("LabVIEW interface connected")
        elif self.labview:
            self.logger.warning("LabVIEW interface available but not connected")
    
    def _init_labview(self):
        """Initialize LabVIEW interface if available."""
        if not LABVIEW_AVAILABLE:
            self.logger.info("LabVIEW interface not available (module not found)")
            return
        
        try:
            config = get_config()
            enabled = config.get('labview.enabled', True)
            
            if not enabled:
                self.logger.info("LabVIEW interface disabled in config")
                return
            
            self.labview = LabVIEWInterface()
            
            # Register pressure alert callback for immediate notification
            self.labview.set_pressure_alert_callback(self._on_pressure_alert)
            
            self.labview.start()
            
            # Try initial connection
            if self.labview.connect():
                self.logger.info(f"Connected to LabVIEW at {self.labview.host}:{self.labview.port}")
            else:
                self.logger.warning(f"LabVIEW not available at {self.labview.host}:{self.labview.port}")
                self.logger.warning("Will retry connection in background")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize LabVIEW interface: {e}")
            self.labview = None
    
    def _init_camera(self):
        """Initialize camera interface for direct control."""
        try:
            self.camera = CameraInterface()
            self.logger.info("Camera interface initialized")
            
            # Test connection
            status = self.camera.get_status()
            if status["connected"]:
                self.logger.info("Camera server connection verified")
            else:
                self.logger.warning("Camera server not available (will retry on demand)")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize camera interface: {e}")
            self.camera = None
    
    def _on_pressure_alert(self, pressure: float, threshold: float, timestamp: float, action: str):
        """
        Handle pressure alert from LabVIEW pressure monitor.
        
        This is called IMMEDIATELY when pressure exceeds threshold.
        The piezo and e-gun are already being killed by the LabVIEW kill switch.
        Here we handle manager-level notifications and logging.
        
        Args:
            pressure: Current pressure reading (mbar)
            threshold: Threshold that was exceeded (mbar)
            timestamp: When the alert occurred
            action: Action taken (e.g., "KILL_PIEZO_EGUN")
        """
        self.logger.error(
            f"🚨 MANAGER RECEIVED PRESSURE ALERT: {pressure:.2e} mbar > {threshold:.2e} mbar! "
            f"Action={action}"
        )
        
        # Update internal state
        self.params["piezo"] = 0.0
        self.params["e_gun"] = False
        
        # Publish emergency commands to ARTIQ workers
        self._publish_emergency_zero("piezo")
        self._publish_emergency_zero("e_gun")
        
        # Store in experiment context if active
        if self.current_exp:
            self.current_exp.add_result("pressure_alert", {
                "pressure_mbar": pressure,
                "threshold_mbar": threshold,
                "timestamp": timestamp,
                "action": action,
                "phase": self.current_exp.phase
            })
        
        # Set safety flag
        self.safety_triggered = True
        
        # Note: The actual hardware kill is handled by LabVIEW kill switch
        # This is just for manager-level coordination and logging
    
    def _setup_kill_switch_callbacks(self):
        """
        Setup kill switch callbacks that command LabVIEW to zero outputs on timeout.
        
        This provides manager-level protection independent of Flask-level kill switches.
        """
        def kill_piezo():
            """Kill piezo output - set to 0V via LabVIEW."""
            self.logger.error("MANAGER KILL SWITCH: Zeroing piezo voltage")
            if self.labview:
                try:
                    self.labview.set_piezo_voltage(0.0)
                except Exception as e:
                    self.logger.error(f"Failed to kill piezo via LabVIEW: {e}")
            # Also publish to ARTIQ workers
            self._publish_emergency_zero("piezo")
        
        def kill_e_gun():
            """Kill e-gun - turn off via LabVIEW."""
            self.logger.error("MANAGER KILL SWITCH: Turning off e-gun")
            if self.labview:
                try:
                    self.labview.set_e_gun(False)
                except Exception as e:
                    self.logger.error(f"Failed to kill e-gun via LabVIEW: {e}")
            # Update internal state
            self.params["e_gun"] = False
            # Also publish to ARTIQ workers
            self._publish_emergency_zero("e_gun")
        
        self.kill_switch.register_callback("piezo", kill_piezo)
        self.kill_switch.register_callback("e_gun", kill_e_gun)
        self.logger.info("Kill switch callbacks registered")
    
    def _publish_emergency_zero(self, device: str):
        """Publish emergency zero command to all workers."""
        msg = {
            "type": "EMERGENCY_ZERO",
            "device": device,
            "reason": "kill_switch_triggered",
            "timestamp": time.time(),
        }
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.warning(f"Published emergency zero for {device}")
    
    def _setup_sockets(self):
        """Setup ZMQ sockets."""
        # 1. Client socket (Flask/TuRBO) - REQ/REP pattern
        self.client_socket = self.ctx.socket(zmq.REP)
        self.client_socket.bind(f"tcp://*:{self.client_port}")
        self.client_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout for responsive shutdown
        self.logger.info(f"Client socket bound to port {self.client_port}")
        
        # 2. Command socket to workers - PUB pattern
        self.pub_socket = self.ctx.socket(zmq.PUB)
        self.pub_socket.bind(f"tcp://*:{self.cmd_port}")
        self.logger.info(f"Command socket bound to port {self.cmd_port}")
        
        # 3. Data socket from workers - PULL pattern (receives PUSH from workers)
        self.pull_socket = self.ctx.socket(zmq.PULL)
        self.pull_socket.bind(f"tcp://*:{self.data_port}")
        # Set timeout for periodic checks
        timeout_ms = int(self.config.get_network('receive_timeout') * 1000)
        self.pull_socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.logger.info(f"Data socket bound to port {self.data_port} (PULL)")
    
    def _start_background_threads(self):
        """Start background worker threads."""
        # Worker data listener
        self.listen_thread = threading.Thread(
            target=self._listen_for_worker_data, 
            daemon=True,
            name="WorkerListener"
        )
        self.listen_thread.start()
        
        # Health monitor
        self.health_thread = threading.Thread(
            target=self._health_monitor,
            daemon=True,
            name="HealthMonitor"
        )
        self.health_thread.start()
        
        # Turbo algorithm coordinator
        self.turbo_thread = threading.Thread(
            target=self._turbo_coordinator,
            daemon=True,
            name="TurboCoordinator"
        )
        self.turbo_thread.start()
    
    def run(self):
        """Main loop: Handle Client Requests (Flask/TuRBO)."""
        self.logger.info("Entering main request loop...")
        
        while self.running:
            try:
                req = self.client_socket.recv_json()
                resp = self.handle_request(req)
                self.client_socket.send_json(resp)
            except zmq.Again:
                # No request pending, continue loop
                continue
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                try:
                    self.client_socket.send_json({
                        "status": "error",
                        "message": str(e),
                        "code": "INTERNAL_ERROR"
                    })
                except:
                    pass
    
    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming requests from clients.
        
        Args:
            req: Request dictionary with 'action', 'source', etc.
            
        Returns:
            Response dictionary
        """
        action = req.get("action")
        source = req.get("source", "UNKNOWN")
        exp_id = req.get("exp_id")
        
        self.logger.info(f"Request from {source}: {action}")
        
        with self.lock:
            # Handle STOP action immediately (highest priority)
            if action == "STOP":
                return self._handle_stop(req)
            
            # Safety Logic: Block TuRBO if in MANUAL or SAFE
            if source == "TURBO" and self.mode != SystemMode.AUTO:
                return {
                    "status": "rejected",
                    "reason": f"System is in {self.mode.value} mode"
                }
            
            # Auto-switch to MANUAL if User acts
            if source == "USER" and self.mode == SystemMode.AUTO:
                self.mode = SystemMode.MANUAL
                with self.turbo_lock:
                    self.turbo_state.status = AlgorithmState.IDLE
                self.logger.info("User override -> Switched to MANUAL")
            
            # Route to appropriate handler
            if action == "SET":
                return self._handle_set(req)
            elif action == "GET":
                return self._handle_get(req)
            elif action == "SWEEP":
                return self._handle_sweep(req)
            elif action == "COMPARE":
                return self._handle_compare(req)
            elif action == "MODE":
                return self._handle_mode_change(req)
            elif action == "EXPERIMENT_START":
                return self._handle_experiment_start(req)
            elif action == "EXPERIMENT_STATUS":
                return self._handle_experiment_status(req)
            elif action == "STATUS":
                return self._handle_status(req)
            elif action == "TURBO_STATUS":
                return self._handle_turbo_status(req)
            elif action == "TURBO_CONTROL":
                return self._handle_turbo_control(req)
            elif action == "CAMERA_START":
                return self._handle_camera_start(req)
            elif action == "CAMERA_STOP":
                return self._handle_camera_stop(req)
            elif action == "CAMERA_STATUS":
                return self._handle_camera_status(req)
            elif action == "CAMERA_TRIGGER":
                return self._handle_camera_trigger(req)
            else:
                return {"status": "error", "message": f"Unknown action: {action}", "code": "UNKNOWN_ACTION"}
    
    def _validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """
        Validate parameter names and values.
        
        Returns:
            Error message if invalid, None if valid
        """
        # Check for invalid parameter names
        invalid = set(params.keys()) - self.VALID_PARAMS
        if invalid:
            return f"Invalid parameters: {invalid}"
        
        # Check parameter ranges
        for name, value in params.items():
            if name in self.PARAM_RANGES:
                min_val, max_val = self.PARAM_RANGES[name]
                if not isinstance(value, (int, float)):
                    return f"Parameter {name} must be numeric"
                if not min_val <= value <= max_val:
                    return f"Parameter {name}={value} out of range [{min_val}, {max_val}]"
        
        return None
    
    def _handle_set(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle SET command.
        
        Kill switch handling:
        - e_gun=True: Arms kill switch (30s max)
        - e_gun=False: Disarms kill switch
        """
        new_params = req.get("params", {})
        source = req.get("source", "UNKNOWN")
        reason = req.get("reason", "")
        
        # Validate parameters
        error = self._validate_params(new_params)
        if error:
            return {"status": "error", "message": error, "code": "VALIDATION_ERROR"}
        
        # Handle kill switch arming for e_gun
        if "e_gun" in new_params:
            if new_params["e_gun"]:
                # Arming e-gun - start kill switch
                self.kill_switch.arm("e_gun", {"source": source, "voltage": self.params.get("e_gun_voltage", 0)})
            else:
                # Disarming e-gun
                self.kill_switch.disarm("e_gun")
        
        # Update internal state
        self.params.update(new_params)
        
        # Determine what changed and publish updates
        dc_changed = any(k in new_params for k in ["ec1", "ec2", "comp_h", "comp_v"])
        cooling_changed = any(k in new_params for k in ["freq0", "amp0", "freq1", "amp1", "sw0", "sw1"])
        rf_changed = "u_rf" in new_params
        piezo_changed = "piezo" in new_params
        toggle_changed = any(k in new_params for k in ["bephi", "b_field", "be_oven", "uv3", "e_gun"])
        dds_changed = "dds_profile" in new_params
        dds_freq_changed = "dds_freq_khz" in new_params
        
        if dc_changed:
            self._publish_dc_update()
        if cooling_changed:
            self._publish_cooling_update()
        if rf_changed:
            self._publish_rf_update()
        if piezo_changed:
            self._publish_piezo_update()
        if toggle_changed:
            self._publish_toggle_update(new_params)
        if dds_changed:
            self._publish_dds_update()
        if dds_freq_changed:
            # Convert kHz to MHz for LabVIEW
            freq_mhz = new_params["dds_freq_khz"] / 1000.0
            self._publish_dds_frequency(freq_mhz)
        
        # Update experiment context if exists
        if self.current_exp:
            self.current_exp.parameters.update(new_params)
        
        # Log if from safety system
        if "SAFETY" in source:
            self.logger.warning(f"Safety SET applied: {new_params} (reason: {reason})")
        
        return {
            "status": "success",
            "mode": self.mode.value,
            "params": {k: v for k, v in self.params.items() if k in new_params}
        }
    
    def _handle_get(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle GET command."""
        param_names = req.get("params", list(self.params.keys()))
        values = {k: self.params.get(k) for k in param_names if k in self.params}
        
        return {
            "status": "success",
            "values": values
        }
    
    def _handle_stop(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle STOP command - Emergency stop from safety system.
        
        Immediately:
        - Stop Turbo algorithm
        - Reset hardware to safe defaults
        - Trigger all kill switches
        - Enter SAFE mode
        """
        source = req.get("source", "UNKNOWN")
        reason = req.get("reason", "Emergency stop")
        
        self.logger.warning(f"STOP command from {source}: {reason}")
        
        with self.turbo_lock:
            self.turbo_state.status = AlgorithmState.STOPPED
            self.turbo_state.target_parameter = None
        
        # Enter SAFE mode
        self.mode = SystemMode.SAFE
        self.safety_triggered = True
        
        # Trigger all kill switches
        ks_triggered = {}
        for device in self.kill_switch.TIME_LIMITS.keys():
            ks_triggered[device] = self.kill_switch.trigger(device, f"STOP from {source}")
        
        # Apply safety defaults
        self._apply_safety_defaults(notify=False)  # Don't publish, just log
        
        return {
            "status": "success",
            "message": "STOP executed. Algorithm halted, safe defaults applied, kill switches triggered.",
            "mode": self.mode.value,
            "kill_switches_triggered": ks_triggered
        }
    
    def _handle_sweep(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SWEEP command."""
        sweep_params = req.get("params", {})
        exp_id = req.get("exp_id")
        
        # Create or use existing experiment
        if exp_id:
            self.current_exp = self.tracker.get_experiment(exp_id)
        
        if not self.current_exp:
            self.current_exp = self.tracker.create_experiment(parameters={
                "type": "sweep",
                **sweep_params
            })
        
        self.current_exp.start()
        self.current_exp.transition_to("sweep")
        
        # Publish sweep command
        self._publish_sweep_command(sweep_params, self.current_exp.exp_id)
        
        self.logger.info(f"Started sweep experiment {self.current_exp.exp_id}")
        
        return {
            "status": "started",
            "exp_id": self.current_exp.exp_id
        }
    
    def _handle_compare(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle COMPARE command for secular frequency comparison.
        
        Workflow:
        1. Set electrodes (EC1, EC2, Comp_H, Comp_V) via ARTIQ
        2. Set RF voltage via SMILE/LabVIEW
        3. Calculate theoretical secular frequencies
        4. Run secular scan around predicted frequency
        5. Fit Lorentzian and compare to prediction
        6. Return results
        """
        params = req.get("params", {})
        exp_id = req.get("exp_id")
        
        # Default comparison parameters
        compare_params = {
            'ec1': params.get('ec1', 10.0),
            'ec2': params.get('ec2', 10.0),
            'comp_h': params.get('comp_h', 6.0),
            'comp_v': params.get('comp_v', 37.0),
            'u_rf_mV': params.get('u_rf_mV', 1400),
            'mass_numbers': params.get('mass_numbers', [9, 3]),
            'scan_range_kHz': params.get('scan_range_kHz', 20.0),
            'scan_points': params.get('scan_points', 41),
        }
        
        self.logger.info(f"Starting secular comparison with params: {compare_params}")
        
        # Create experiment context
        if exp_id:
            self.current_exp = self.tracker.get_experiment(exp_id)
        
        if not self.current_exp:
            self.current_exp = self.tracker.create_experiment(parameters={
                "type": "secular_compare",
                **compare_params
            })
        
        self.current_exp.start()
        self.current_exp.transition_to("secular_compare")
        
        try:
            # Step 1: Set electrodes via ARTIQ
            self.logger.info("Step 1: Setting electrode voltages...")
            self.params.update({
                'ec1': compare_params['ec1'],
                'ec2': compare_params['ec2'],
                'comp_h': compare_params['comp_h'],
                'comp_v': compare_params['comp_v'],
            })
            self._publish_dc_update()
            
            # Step 2: Set RF voltage via SMILE/LabVIEW
            self.logger.info("Step 2: Setting RF voltage...")
            if self.labview:
                # Convert SMILE mV to real volts using calibrated scale
                # 700mV on SMILE = 100V real RF
                u_rf_real = smile_mv_to_real_volts(compare_params['u_rf_mV'])
                success = self.labview.set_rf_voltage(u_rf_real)
                if not success:
                    self.logger.warning("Failed to set RF voltage via LabVIEW")
            
            # Step 3: Calculate theoretical frequencies
            self.logger.info("Step 3: Calculating theoretical frequencies...")
            try:
                from server.analysis.secular_comparison import SecularFrequencyComparator
                comparator = SecularFrequencyComparator()
                
                predicted_freqs, smallest_freq, mode_name = comparator.calculate_theoretical_freqs(
                    compare_params, compare_params['mass_numbers']
                )
                
                self.logger.info(f"Predicted frequencies: {predicted_freqs}")
                self.logger.info(f"Target mode: {smallest_freq:.3f} kHz ({mode_name})")
                
                # Step 4: Publish command to ARTIQ for secular sweep
                self.logger.info("Step 4: Running secular sweep...")
                sweep_params = {
                    "target_frequency_khz": smallest_freq,
                    "span_khz": compare_params['scan_range_kHz'],
                    "steps": compare_params['scan_points'],
                    "attenuation_db": 25.0,
                    "on_time_ms": 300.0,
                    "off_time_ms": 300.0,
                    "compare_mode": True,  # Flag for comparison mode
                    "predicted_freq_kHz": smallest_freq,
                }
                self._publish_sweep_command(sweep_params, self.current_exp.exp_id)
                
                # Store comparison state for later analysis
                self.current_exp.add_result("secular_compare_theory", {
                    "predicted_freqs_kHz": predicted_freqs,
                    "smallest_freq_kHz": smallest_freq,
                    "target_mode": mode_name,
                    "params": compare_params
                })
                
                return {
                    "status": "started",
                    "exp_id": self.current_exp.exp_id,
                    "message": "Secular comparison started",
                    "predicted_freq_kHz": smallest_freq,
                    "target_mode": mode_name
                }
                
            except Exception as e:
                self.logger.error(f"Failed to calculate theoretical frequencies: {e}")
                return {
                    "status": "error",
                    "message": f"Theory calculation failed: {e}",
                    "code": "THEORY_ERROR"
                }
                
        except Exception as e:
            self.logger.error(f"Compare command failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "code": "COMPARE_ERROR"
            }
    
    def _handle_mode_change(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MODE change command."""
        new_mode = req.get("mode", "MANUAL")
        
        try:
            self.mode = SystemMode(new_mode)
            self.logger.info(f"Mode changed to {self.mode.value}")
            
            # Update Turbo state based on mode
            with self.turbo_lock:
                if self.mode == SystemMode.SAFE:
                    self.turbo_state.status = AlgorithmState.STOPPED
                elif self.mode == SystemMode.AUTO:
                    self.turbo_state.status = AlgorithmState.RUNNING
                else:  # MANUAL
                    self.turbo_state.status = AlgorithmState.IDLE
            
            # If entering SAFE mode, apply safety defaults
            if self.mode == SystemMode.SAFE:
                self._apply_safety_defaults()
            
            return {"status": "success", "mode": self.mode.value}
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid mode: {new_mode}",
                "code": "INVALID_MODE"
            }
    
    def _handle_experiment_start(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle EXPERIMENT_START command."""
        params = req.get("params", {})
        
        self.current_exp = self.tracker.create_experiment(parameters=params)
        self.current_exp.start()
        
        self.logger.info(f"Started experiment {self.current_exp.exp_id}")
        
        return {
            "status": "success",
            "exp_id": self.current_exp.exp_id
        }
    
    def _handle_experiment_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle EXPERIMENT_STATUS query."""
        exp_id = req.get("exp_id")
        
        if exp_id:
            exp = self.tracker.get_experiment(exp_id)
        else:
            exp = self.current_exp
        
        if not exp:
            return {"status": "error", "message": "No active experiment", "code": "NO_EXPERIMENT"}
        
        return {
            "status": "success",
            "exp_id": exp.exp_id,
            "phase": exp.phase,
            "status": exp.status,
            "duration": exp.duration_seconds,
            "results": exp.results
        }
    
    def _handle_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle general STATUS query including kill switch and camera status."""
        with self.worker_lock:
            worker_alive = self.worker_alive
        
        with self.turbo_lock:
            turbo_dict = self.turbo_state.to_dict()
        
        # Get camera status if available
        camera_status = None
        if self.camera:
            try:
                camera_status = self.camera.get_status()
            except:
                camera_status = {"available": False}
        
        return {
            "status": "success",
            "mode": self.mode.value,
            "worker_alive": worker_alive,
            "current_exp": self.current_exp.exp_id if self.current_exp else None,
            "params": self.params,
            "turbo": turbo_dict,
            "safety_triggered": self.safety_triggered,
            "kill_switch": self.kill_switch.get_status(),
            "camera": camera_status
        }
    
    def _handle_turbo_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle TURBO_STATUS query."""
        with self.turbo_lock:
            return {
                "status": "success",
                "turbo": self.turbo_state.to_dict()
            }
    
    def _handle_turbo_control(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle TURBO_CONTROL commands:
        - start: Start optimization
        - stop: Stop optimization
        - reset: Reset algorithm state
        """
        command = req.get("command")
        
        if command == "start":
            if self.mode != SystemMode.AUTO:
                return {"status": "rejected", "reason": f"System in {self.mode.value} mode"}
            
            with self.turbo_lock:
                self.turbo_state.status = AlgorithmState.RUNNING
                self.turbo_state.start_time = time.time()
                self.turbo_state.current_iteration = 0
            
            self.logger.info("Turbo algorithm started")
            return {"status": "success", "message": "Turbo algorithm started"}
        
        elif command == "stop":
            with self.turbo_lock:
                self.turbo_state.status = AlgorithmState.STOPPED
                self.turbo_state.target_parameter = None
            
            self.logger.info("Turbo algorithm stopped")
            return {"status": "success", "message": "Turbo algorithm stopped"}
        
        elif command == "reset":
            with self.turbo_lock:
                self.turbo_state = TurboAlgorithmState()
            
            self.logger.info("Turbo algorithm reset")
            return {"status": "success", "message": "Turbo algorithm reset"}
        
        else:
            return {"status": "error", "message": f"Unknown turbo command: {command}"}
    
    def _handle_camera_start(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start camera recording with optional TTL trigger.
        
        Simplified workflow:
        1. Start camera recording (direct TCP to camera_server)
        2. Optionally send TTL trigger command to ARTIQ
        
        Args:
            req: Request with optional 'trigger' flag and 'mode' (inf/single)
        """
        mode = req.get("mode", "inf")  # "inf" for infinite, "single" for DCIMG
        send_trigger = req.get("trigger", True)  # Whether to send TTL trigger
        exp_id = req.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        self.logger.info(f"Camera start requested: mode={mode}, trigger={send_trigger}")
        
        # Check camera interface
        if not self.camera:
            return {"status": "error", "message": "Camera interface not available", "code": "CAMERA_NOT_AVAILABLE"}
        
        try:
            # Step 1: Start camera recording
            success = self.camera.start_recording(mode=mode, exp_id=exp_id)
            if not success:
                return {"status": "error", "message": "Failed to start camera recording", "code": "CAMERA_START_FAILED"}
            
            # Step 2: Send TTL trigger command to ARTIQ if requested
            if send_trigger:
                self._publish_camera_trigger(exp_id)
                self.logger.info("Camera TTL trigger command sent to ARTIQ")
            
            return {
                "status": "success",
                "message": f"Camera started ({mode} mode)",
                "mode": mode,
                "trigger_sent": send_trigger
            }
            
        except Exception as e:
            self.logger.error(f"Camera start failed: {e}")
            return {"status": "error", "message": str(e), "code": "CAMERA_ERROR"}
    
    def _handle_camera_stop(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Stop camera recording."""
        self.logger.info("Camera stop requested")
        
        if not self.camera:
            return {"status": "error", "message": "Camera interface not available", "code": "CAMERA_NOT_AVAILABLE"}
        
        try:
            success = self.camera.stop_recording()
            if success:
                return {"status": "success", "message": "Camera stopped"}
            else:
                return {"status": "error", "message": "Failed to stop camera", "code": "CAMERA_STOP_FAILED"}
        except Exception as e:
            self.logger.error(f"Camera stop failed: {e}")
            return {"status": "error", "message": str(e), "code": "CAMERA_ERROR"}
    
    def _handle_camera_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Get camera status."""
        if not self.camera:
            return {"status": "error", "message": "Camera interface not available", "code": "CAMERA_NOT_AVAILABLE"}
        
        try:
            status = self.camera.get_status()
            return {"status": "success", "camera": status}
        except Exception as e:
            self.logger.error(f"Camera status check failed: {e}")
            return {"status": "error", "message": str(e), "code": "CAMERA_ERROR"}
    
    def _handle_camera_trigger(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send TTL trigger command to ARTIQ for camera.
        This is used when you want to trigger the camera without starting recording.
        """
        exp_id = req.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        self.logger.info("Camera TTL trigger requested")
        
        try:
            self._publish_camera_trigger(exp_id)
            return {"status": "success", "message": "Camera TTL trigger command sent to ARTIQ"}
        except Exception as e:
            self.logger.error(f"Camera trigger failed: {e}")
            return {"status": "error", "message": str(e), "code": "TRIGGER_ERROR"}
    
    def _publish_camera_trigger(self, exp_id: Optional[str] = None):
        """
        Publish camera TTL trigger command to ARTIQ worker.
        
        The ARTIQ worker will execute the actual TTL pulse on the hardware.
        """
        msg = {
            "type": "CAMERA_TRIGGER",
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.debug(f"Published camera trigger command for exp {exp_id}")
    
    # ==========================================================================
    # PUBLISH COMMANDS TO WORKERS
    # ==========================================================================
    
    def _publish_dc_update(self):
        """Send DC parameter update to workers and LabVIEW."""
        msg = {
            "type": "SET_DC",
            "values": {
                "ec1": self.params["ec1"],
                "ec2": self.params["ec2"],
                "comp_h": self.params["comp_h"],
                "comp_v": self.params["comp_v"]
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.debug(f"Published DC update: {msg['values']}")
        
        # Send to LabVIEW (electrodes)
        if self.labview:
            # LabVIEW handles electrodes separately or as part of RF system
            pass  # Electrodes not directly controlled by SMILE LabVIEW in current spec
    
    def _publish_cooling_update(self):
        """Send cooling parameter update to workers."""
        msg = {
            "type": "SET_COOLING",
            "values": {
                "freq0": self.params["freq0"],
                "amp0": self.params["amp0"],
                "freq1": self.params["freq1"],
                "amp1": self.params["amp1"],
                "sw0": self.params["sw0"],
                "sw1": self.params["sw1"]
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.debug(f"Published cooling update: {msg['values']}")
    
    def _publish_rf_update(self):
        """Send RF voltage update to workers and LabVIEW."""
        u_rf_volts = self.params["u_rf_volts"]
        
        msg = {
            "type": "SET_RF",
            "values": {
                "u_rf_volts": u_rf_volts
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.debug(f"Published RF update: U_RF={u_rf_volts} V")
        
        # Send to LabVIEW (convert volts to SMILE mV)
        if self.labview:
            from core.enums import real_volts_to_smile_mv
            smile_mv = real_volts_to_smile_mv(u_rf_volts)
            success = self.labview.set_rf_voltage(smile_mv)
            if not success:
                self.logger.warning("Failed to set RF voltage in LabVIEW")
    
    def _publish_piezo_update(self):
        """Send piezo voltage update to workers and LabVIEW."""
        msg = {
            "type": "SET_PIEZO",
            "values": {
                "piezo": self.params["piezo"]
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.debug(f"Published piezo update: {self.params['piezo']}")
        
        # Send to LabVIEW
        if self.labview:
            success = self.labview.set_piezo_voltage(self.params["piezo"])
            if not success:
                self.logger.warning("Failed to set piezo voltage in LabVIEW")
    
    def _publish_toggle_update(self, toggles: Dict[str, Any]):
        """Send toggle state updates to workers and LabVIEW."""
        # Map of parameter names to LabVIEW setter methods
        labview_setters = {
            "be_oven": lambda v: self.labview.set_be_oven(v) if self.labview else False,
            "b_field": lambda v: self.labview.set_b_field(v) if self.labview else False,
            "bephi": lambda v: self.labview.set_bephi(v) if self.labview else False,
            "uv3": lambda v: self.labview.set_uv3(v) if self.labview else False,
            "e_gun": lambda v: self.labview.set_e_gun(v) if self.labview else False,
        }
        
        for name, value in toggles.items():
            msg = {
                "type": f"SET_{name.upper()}",
                "value": value,
                "exp_id": self.current_exp.exp_id if self.current_exp else None
            }
            self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
            self.pub_socket.send_json(msg)
            self.logger.debug(f"Published toggle update: {name}={value}")
            
            # Send to LabVIEW
            if name in labview_setters and self.labview:
                success = labview_setters[name](value)
                if not success:
                    self.logger.warning(f"Failed to set {name} in LabVIEW")
    
    def _publish_dds_update(self):
        """Send DDS profile update to workers and LabVIEW."""
        msg = {
            "type": "SET_DDS",
            "values": {
                "profile": self.params["dds_profile"]
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.debug(f"Published DDS update: profile={self.params['dds_profile']}")
        
        # Note: DDS profile selection is typically handled by ARTIQ
        # LabVIEW may control DDS frequency directly via _publish_dds_frequency
    
    def _publish_dds_frequency(self, freq_mhz: float):
        """Send DDS frequency update to LabVIEW."""
        if self.labview:
            success = self.labview.set_dds_frequency(freq_mhz)
            if success:
                self.logger.debug(f"Set DDS frequency to {freq_mhz} MHz in LabVIEW")
            else:
                self.logger.warning(f"Failed to set DDS frequency in LabVIEW")
    
    def _publish_sweep_command(self, params: Dict[str, Any], exp_id: str):
        """Send sweep command to ARTIQ worker."""
        msg = {
            "type": "RUN_SWEEP",
            "values": params,
            "exp_id": exp_id
        }
        self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.info(f"Published sweep command for exp {exp_id}")
    
    # ==========================================================================
    # BACKGROUND THREADS
    # ==========================================================================
    
    def _listen_for_worker_data(self):
        """Background thread to catch data from Worker."""
        self.logger.info("Worker data listener started")
        
        while self.running:
            try:
                packet = self.pull_socket.recv_json()
                
                # Extract packet info
                category = packet.get("category", "UNKNOWN")
                source = packet.get("source", "UNKNOWN")
                payload = packet.get("payload", {})
                exp_id = packet.get("exp_id")
                
                # Update worker health
                if source == "ARTIQ":
                    with self.worker_lock:
                        self.last_worker_heartbeat = time.time()
                        self.worker_alive = True
                
                # Handle different categories
                if category == "HEARTBEAT":
                    self.logger.debug(f"Heartbeat from {source}")
                    
                elif category == "DATA":
                    self.logger.debug(f"Data from {source}: {payload}")
                    
                elif category == "SWEEP_COMPLETE":
                    self._handle_sweep_complete(packet)
                    
                elif category == "STATUS":
                    self.logger.info(f"Status from {source}: {payload}")
                    
                elif category == "ERROR":
                    self.logger.error(f"Error from {source}: {payload}")
                    
            except zmq.Again:
                # Timeout, continue loop
                continue
            except Exception as e:
                self.logger.error(f"Data listener error: {e}")
    
    def _handle_sweep_complete(self, packet: Dict[str, Any]):
        """Handle SWEEP_COMPLETE message from worker."""
        exp_id = packet.get("exp_id")
        payload = packet.get("payload", {})
        
        self.logger.info(f"✅ ARTIQ finished sweep for exp {exp_id}")
        
        # Update experiment context
        if exp_id and self.current_exp and self.current_exp.exp_id == exp_id:
            self.current_exp.transition_to("analysis")
            self.current_exp.add_result("artiq_sweep", payload)
        
        # Trigger analysis (could call H5 analysis script here)
        self._trigger_analysis(exp_id, payload)
    
    def _trigger_analysis(self, exp_id: str, sweep_data: Dict[str, Any]):
        """Trigger post-sweep analysis."""
        self.logger.info(f"Triggering analysis for exp {exp_id}")
        # Here you would:
        # 1. Call analyze_sweep.py on the H5 file
        # 2. Wait for camera images
        # 3. Run image analysis
        pass
    
    def _health_monitor(self):
        """Monitor component health."""
        timeout = self.config.get_network('watchdog_timeout')
        
        while self.running:
            time.sleep(1)
            
            # Check worker heartbeat
            with self.worker_lock:
                time_since_heartbeat = time.time() - self.last_worker_heartbeat
                if time_since_heartbeat > timeout:
                    if self.worker_alive:
                        self.logger.error(f"WORKER TIMEOUT: No heartbeat for {time_since_heartbeat:.1f}s")
                        self.worker_alive = False
                        
                        # Trigger safety if in AUTO mode
                        if self.mode == SystemMode.AUTO:
                            self.logger.warning("Entering SAFE mode due to worker timeout")
                            self.mode = SystemMode.SAFE
                            self._apply_safety_defaults()
    
    def _turbo_coordinator(self):
        """
        Background thread to coordinate Turbo algorithm execution.
        
        In a real implementation, this would:
        1. Interface with the actual Turbo/Bayesian optimization library
        2. Manage optimization iterations
        3. Handle parameter suggestions from the algorithm
        4. Feed back measurement results
        """
        self.logger.info("Turbo coordinator started")
        
        while self.running:
            try:
                with self.turbo_lock:
                    state = self.turbo_state.status
                
                if state == AlgorithmState.RUNNING:
                    # Placeholder: In real implementation, this would
                    # communicate with the Turbo optimization process
                    pass
                
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Turbo coordinator error: {e}")
                time.sleep(1)
    
    # ==========================================================================
    # SAFETY
    # ==========================================================================
    
    def _apply_safety_defaults(self, notify: bool = True):
        """
        Apply safety defaults to hardware (workers + LabVIEW).
        
        Args:
            notify: If True, publish updates to workers
        """
        self.logger.warning("Applying safety defaults!")
        
        # Update params to safe values
        self.params.update({
            "u_rf_volts": 0.0,
            "ec1": 0.0,
            "ec2": 0.0,
            "comp_h": 0.0,
            "comp_v": 0.0,
            "piezo": 0.0,
            "sw0": False,
            "sw1": False,
            "bephi": False,
            "b_field": False,
            "be_oven": False,
            "e_gun": False,
            "uv3": False,
        })
        
        if notify:
            # Publish safety commands to workers
            self._publish_dc_update()
            self._publish_cooling_update()
            self._publish_rf_update()
            self._publish_piezo_update()
        
        # Apply to LabVIEW
        if self.labview:
            self.logger.info("Applying safety defaults to LabVIEW...")
            results = self.labview.apply_safety_defaults()
            failed = [k for k, v in results.items() if not v]
            if failed:
                self.logger.warning(f"Failed to apply safety defaults to LabVIEW devices: {failed}")
            else:
                self.logger.info("Safety defaults applied to LabVIEW successfully")
        
        # Log safety event
        log_safety_trigger(
            self.logger,
            trigger_type="manager_safety",
            previous_state=self.params,
            safety_state=self.params,
            exp_id=self.current_exp.exp_id if self.current_exp else None
        )
    
    def shutdown(self):
        """Graceful shutdown."""
        self.logger.info("Shutting down Control Manager...")
        self.running = False
        
        # Stop camera recording if active
        if self.camera:
            self.logger.info("Stopping camera recording...")
            try:
                self.camera.stop_recording()
            except Exception as e:
                self.logger.warning(f"Error stopping camera: {e}")
        
        # Stop LabVIEW file reader
        if hasattr(self, 'labview_data_reader') and self.labview_data_reader:
            self.logger.info("Stopping LabVIEW file reader...")
            self.labview_data_reader.stop()
        
        # Stop LabVIEW interface
        if self.labview:
            self.labview.stop()
        
        # Close sockets
        self.client_socket.close()
        self.pub_socket.close()
        self.pull_socket.close()
        self.ctx.term()
        
        self.logger.info("Control Manager stopped")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    try:
        mgr = ControlManager()
        mgr.run()
    except KeyboardInterrupt:
        mgr.shutdown()
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        raise
