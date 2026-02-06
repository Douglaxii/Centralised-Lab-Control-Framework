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
import re
import struct
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
    ConnectionError,
    SafetyError,
    SystemMode,
    AlgorithmState,
    CommandType,
    u_rf_mv_to_U_RF_V
)

# Import optimizer controller
try:
    from services.optimizer.optimizer_controller import OptimizerController, OptimizerState
    OPTIMIZER_AVAILABLE = True
except ImportError:
    OPTIMIZER_AVAILABLE = False


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
# WAVEMETER INTERFACE - HighFinesse/Angstrom WS7 Wavemeter TCP Client
# =============================================================================

class WavemeterInterface:
    """
    Interface to HighFinesse/Angstrom WS7 Wavemeter via TCP broadcast.
    
    Connects to the LabVIEW server running on the wavemeter PC and receives
    real-time frequency measurements. The data stream contains:
    - Frequency data as ASCII text (in THz)
    - Channel ID as binary double precision
    - Temperature and pressure readings (filtered out)
    
    Frequency values are converted from THz to GHz and stored in telemetry.
    """
    
    # Default connection settings
    DEFAULT_HOST = '134.99.120.141'  # Wavemeter PC IP
    DEFAULT_PORT = 1790               # LabVIEW TCP broadcast port
    
    # Frequency filtering ranges (in THz)
    UV_RANGE = (900, 980)        # UV frequency range ~957 THz
    FUNDAMENTAL_RANGE = (200, 260)  # Fundamental range ~239 THz
    TEMP_RANGE = (20, 35)        # Temperature ~27°C (filter out)
    PRESSURE_RANGE = (900, 1100) # Pressure ~985 mBar (filter out)
    
    # Channel detection
    CHANNEL_RANGE = (1.0, 8.0)   # Valid channel IDs
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, 
                 divider: float = 4.0, enabled: bool = True):
        """
        Initialize wavemeter interface.
        
        Args:
            host: Wavemeter PC IP address (default from config or DEFAULT_HOST)
            port: TCP port (default from config or DEFAULT_PORT)
            divider: Divider for UV->Fundamental conversion (4.0 for UV, 1.0 for raw)
            enabled: Whether to enable the interface (default True)
        """
        self.logger = logging.getLogger("wavemeter_interface")
        
        # Load configuration
        config = get_config()
        self.host = host or config.get('wavemeter.host', self.DEFAULT_HOST)
        self.port = port or config.get('wavemeter.port', self.DEFAULT_PORT)
        self.divider = divider or config.get('wavemeter.divider', 4.0)
        self.enabled = config.get('wavemeter.enabled', enabled)
        
        # Connection settings
        self.timeout = 5.0
        self.reconnect_delay = 3.0
        
        # State
        self.running = False
        self.connected = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        
        # Current readings
        self.current_channel = 1
        self.current_freq_ghz = 0.0
        self.current_freq_thz = 0.0
        self.last_update_time: Optional[float] = None
        self.reading_count = 0
        
        # Statistics
        self.stats = {
            "connections": 0,
            "readings": 0,
            "errors": 0,
            "start_time": None
        }
        
        # Regex for finding frequency values in text
        self.freq_pattern = re.compile(r'(\d{3,}\.\d+)')
        
        if self.enabled:
            self.logger.info(f"Wavemeter Interface initialized ({self.host}:{self.port})")
        else:
            self.logger.info("Wavemeter Interface disabled")
    
    def start(self):
        """Start the wavemeter data collection thread."""
        if not self.enabled:
            self.logger.info("Wavemeter Interface disabled, not starting")
            return False
        
        if self.running:
            return True
        
        self.running = True
        self.stats["start_time"] = time.time()
        self.thread = threading.Thread(
            target=self._data_collection_loop,
            daemon=True,
            name="WavemeterInterface"
        )
        self.thread.start()
        self.logger.info("Wavemeter data collection started")
        return True
    
    def stop(self):
        """Stop the wavemeter data collection."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.connected = False
        self.logger.info("Wavemeter Interface stopped")
    
    def _data_collection_loop(self):
        """Main data collection loop - connects and reads wavemeter data."""
        while self.running:
            try:
                self._connect_and_read()
            except Exception as e:
                self.logger.error(f"Wavemeter connection error: {e}")
                self.stats["errors"] += 1
            
            if self.running:
                self.logger.warning(f"Reconnecting in {self.reconnect_delay}s...")
                time.sleep(self.reconnect_delay)
    
    def _connect_and_read(self):
        """Connect to wavemeter and read data stream."""
        self.logger.info(f"Connecting to wavemeter at {self.host}:{self.port}")
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            
            self.connected = True
            self.stats["connections"] += 1
            self.logger.info("Connected to wavemeter!")
            
            buffer = b""
            
            while self.running:
                try:
                    # Receive data chunk
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    
                    buffer += chunk
                    
                    # Process buffer for channel and frequency data
                    buffer = self._process_buffer(buffer)
                    
                    # Prevent buffer overflow
                    if len(buffer) > 8192:
                        buffer = buffer[-2048:]
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    self.logger.error(f"Read error: {e}")
                    self.stats["errors"] += 1
                    break
        
        self.connected = False
        self.logger.warning("Wavemeter connection closed")
    
    def _process_buffer(self, buffer: bytes) -> bytes:
        """
        Process received buffer for channel and frequency data.
        
        Args:
            buffer: Current byte buffer
            
        Returns:
            Updated buffer (may be truncated)
        """
        # --- A. DETECT CHANNEL (Binary Search) ---
        c_idx = buffer.find(b'channelId')
        if c_idx != -1 and len(buffer) > c_idx + 30:
            for offset in range(9, 25):
                try:
                    candidate = buffer[c_idx + offset:c_idx + offset + 8]
                    if len(candidate) < 8:
                        break
                    val = struct.unpack('>d', candidate)[0]
                    if self.CHANNEL_RANGE[0] <= val <= self.CHANNEL_RANGE[1] and val.is_integer():
                        self.current_channel = int(val)
                        break
                except:
                    pass
            # Clear buffer up to here to stay fresh
            buffer = buffer[c_idx + 20:]
        
        # --- B. DETECT FREQUENCY (Text Search) ---
        try:
            text_view = buffer.decode('utf-8', errors='ignore')
            matches = self.freq_pattern.findall(text_view)
            
            for m in matches:
                val_thz = float(m)
                valid_reading = False
                final_freq_ghz = 0.0
                
                # Filter: UV Range (~957 THz)
                if self.UV_RANGE[0] < val_thz < self.UV_RANGE[1]:
                    final_freq_ghz = (val_thz * 1000.0) / self.divider
                    valid_reading = True
                
                # Filter: Fundamental Range (~239 THz)
                elif self.FUNDAMENTAL_RANGE[0] < val_thz < self.FUNDAMENTAL_RANGE[1]:
                    final_freq_ghz = val_thz * 1000.0
                    valid_reading = True
                
                # Filter out temperature and pressure readings
                elif self.TEMP_RANGE[0] < val_thz < self.TEMP_RANGE[1]:
                    continue  # Temperature reading, skip
                elif self.PRESSURE_RANGE[0] < val_thz < self.PRESSURE_RANGE[1]:
                    continue  # Pressure reading, skip
                
                if valid_reading:
                    self._store_reading(final_freq_ghz, val_thz)
                    # Clear buffer to prevent reprocessing
                    return b""
        
        except Exception:
            pass
        
        return buffer
    
    def _store_reading(self, freq_ghz: float, raw_thz: float):
        """
        Store a valid frequency reading.
        
        Args:
            freq_ghz: Converted frequency in GHz
            raw_thz: Raw frequency reading in THz
        """
        timestamp = time.time()
        
        with self.lock:
            self.current_freq_ghz = freq_ghz
            self.current_freq_thz = raw_thz
            self.last_update_time = timestamp
            self.reading_count += 1
            self.stats["readings"] += 1
        
        # Store in telemetry (laser_freq is the channel name in data_server)
        if TELEMETRY_STORAGE_AVAILABLE:
            try:
                store_data_point("laser_freq", freq_ghz, timestamp)
                update_data_source("wavemeter", timestamp)
            except Exception as e:
                self.logger.debug(f"Failed to store telemetry: {e}")
        
        # Log periodically (every 5 seconds)
        if int(timestamp) % 5 == 0:
            self.logger.debug(f"CH {self.current_channel} | {freq_ghz:.4f} GHz ({raw_thz:.4f} THz)")
    
    def get_current_reading(self) -> Dict[str, Any]:
        """
        Get the current frequency reading.
        
        Returns:
            Dictionary with current reading information
        """
        with self.lock:
            return {
                "channel": self.current_channel,
                "frequency_ghz": self.current_freq_ghz,
                "frequency_thz": self.current_freq_thz,
                "last_update": self.last_update_time,
                "connected": self.connected,
                "reading_count": self.reading_count
            }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get interface status.
        
        Returns:
            Dictionary with status information
        """
        with self.lock:
            uptime = time.time() - self.stats["start_time"] if self.stats["start_time"] else 0
            return {
                "enabled": self.enabled,
                "connected": self.connected,
                "running": self.running,
                "server": f"{self.host}:{self.port}",
                "current_channel": self.current_channel,
                "current_frequency_ghz": self.current_freq_ghz,
                "last_update": self.last_update_time,
                "reading_count": self.reading_count,
                "stats": self.stats.copy(),
                "uptime_seconds": uptime
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
        "e_gun": 30.0,   # 10 seconds (testing mode)
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
        # RF Voltage (real voltage U_RF in volts, after amplifier)
        "u_rf_volts",
        # Electrodes (range: -1V to 50V)
        "ec1", "ec2", "comp_h", "comp_v",
        # Cooling parameters (freq0/freq1 are constants 215.5 MHz, backend only)
        "amp0", "amp1", "sw0", "sw1",
        # Toggles (0=off, 1=on)
        "bephi", "b_field", "be_oven", "uv3", "e_gun", "hd_valve",
        # Laser & Piezo
        "piezo",
        # DDS (LabVIEW controlled only, 0-200 MHz)
        "dds_freq_mhz",
    }
    
    # Parameter ranges for safety validation
    PARAM_RANGES: Dict[str, tuple] = {
        "u_rf_volts": (0, 200),   # Real RF voltage U_RF 0-200V (1400mV u_rf / 7)
        "ec1": (-1, 50),          # Electrode voltages -1V to 50V
        "ec2": (-1, 50),
        "comp_h": (-1, 50),
        "comp_v": (-1, 50),
        "amp0": (0, 1),           # Raman amplitude range
        "amp1": (0, 1),
        "sw0": (0, 1),            # Shutter switches (0=off, 1=on)
        "sw1": (0, 1),
        "bephi": (0, 1),          # Toggles (0=off, 1=on)
        "b_field": (0, 1),
        "be_oven": (0, 1),
        "uv3": (0, 1),
        "e_gun": (0, 1),
        "hd_valve": (0, 1),       # HD valve (0=off, 1=on)
        "piezo": (0, 4),          # Piezo 0-4V
        "dds_freq_mhz": (0, 200), # DDS frequency 0-200 MHz (LabVIEW only)
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
            # RF Voltage (real voltage U_RF in volts, after amplifier)
            "u_rf_volts": defaults.get("u_rf_volts", 200.0),
            # DC Electrodes (range: -1V to 50V)
            "ec1": defaults.get("ec1", 0.0),
            "ec2": defaults.get("ec2", 0.0),
            "comp_h": defaults.get("comp_h", 0.0),
            "comp_v": defaults.get("comp_v", 0.0),
            # Cooling parameters (freq0/freq1 are constants 215.5 MHz, backend only)
            "amp0": defaults.get("amp0", 0.05),
            "amp1": defaults.get("amp1", 0.05),
            # Shutter switches (0=off, 1=on)
            "sw0": defaults.get("sw0", 0),
            "sw1": defaults.get("sw1", 0),
            # Toggles (0=off, 1=on)
            "bephi": defaults.get("bephi", 0),
            "b_field": defaults.get("b_field", 1),
            "be_oven": defaults.get("be_oven", 0),
            "uv3": defaults.get("uv3", 0),
            "e_gun": defaults.get("e_gun", 0),
            "hd_valve": defaults.get("hd_valve", 0),
            # Laser & Piezo
            "piezo": defaults.get("piezo", 0.0),
            # DDS frequency in MHz (LabVIEW controlled, 0-200 MHz)
            "dds_freq_mhz": defaults.get("dds_freq_mhz", 0.0),
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
        
        # Wavemeter Interface (HighFinesse WS7 frequency data)
        self.wavemeter: Optional[WavemeterInterface] = None
        self._init_wavemeter()
        
        # Optimizer Controller (Bayesian optimization)
        self.optimizer_controller: Optional[OptimizerController] = None
        self._init_optimizer()
        
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
                
                # Auto-start camera if configured
                self._auto_start_camera()
            else:
                self.logger.warning("Camera server not available (will retry on demand)")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize camera interface: {e}")
            self.camera = None
    
    def _auto_start_camera(self):
        """
        Auto-start camera recording if configured.
        
        This method is called during manager initialization if:
        1. Camera interface is successfully initialized
        2. Camera server connection is verified
        3. camera.auto_start is True in configuration
        
        Flow:
        1. Start camera in infinite mode (via TCP to camera server)
        2. Send START_CAMERA_INF command to ARTIQ worker
        3. ARTIQ worker acknowledges and is ready for TTL triggers
        """
        try:
            config = get_config()
            auto_start = config.get('camera.auto_start', True)
            
            if not auto_start:
                self.logger.info("Camera auto-start disabled in config")
                return
            
            if not self.camera:
                self.logger.warning("Cannot auto-start camera: interface not available")
                return
            
            self.logger.info("Auto-starting camera recording...")
            
            # Step 1: Start camera infinite mode
            mode = config.get('camera.mode', 'inf')  # 'inf' or 'single'
            exp_id = f"auto_start_{int(time.time())}"
            
            success = self.camera.start_recording(mode=mode, exp_id=exp_id)
            if not success:
                self.logger.error("Failed to auto-start camera recording")
                return
            
            self.logger.info(f"Camera recording started in {mode} mode")
            
            # Step 2: Signal ARTIQ worker to prepare for camera triggers
            self._publish_camera_inf_start(exp_id)
            
            # Step 3: Optionally send initial TTL trigger
            send_trigger = config.get('camera.send_initial_trigger', True)
            if send_trigger:
                time.sleep(1)  # Brief delay for camera to stabilize
                self._publish_camera_trigger(exp_id)
                self.logger.info("Initial camera TTL trigger sent")
            
            self.logger.info("Camera auto-start completed successfully")
            
        except Exception as e:
            self.logger.error(f"Camera auto-start failed: {e}")
    
    def _publish_camera_inf_start(self, exp_id: Optional[str] = None):
        """
        Publish START_CAMERA_INF command to ARTIQ worker.
        
        This notifies the ARTIQ worker that camera infinite mode is active,
        so it can prepare for TTL trigger commands.
        """
        msg = {
            "type": "START_CAMERA_INF",
            "values": {},
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        self.logger.debug(f"Published START_CAMERA_INF for exp {exp_id}")
    
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
        self.logger.info("=" * 60)
        self.logger.info("Manager main request loop started")
        self.logger.info(f"Listening on port {self.client_port}")
        self.logger.info("=" * 60)
        
        while self.running:
            try:
                req = self.client_socket.recv_json()
                resp = self.handle_request(req)
                self.client_socket.send_json(resp)
            except zmq.Again:
                # No request pending, continue loop
                continue
            except Exception as e:
                self.logger.error(f"[ERROR] Error in main loop: {e}", exc_info=True)
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
        params = req.get("params", {})
        
        # Log the incoming request
        if params:
            self.logger.info(f"[REQUEST] From={source} | Action={action} | Params={params}")
        else:
            self.logger.info(f"[REQUEST] From={source} | Action={action}")
        
        with self.lock:
            # Handle STOP action immediately (highest priority)
            if action == "STOP":
                self.logger.warning(f"[STOP] Emergency stop requested by {source}")
                return self._handle_stop(req)
            
            # Safety Logic: Block TuRBO if in MANUAL or SAFE
            if source == "TURBO" and self.mode != SystemMode.AUTO:
                self.logger.warning(f"[REJECTED] TuRBO request blocked: System is in {self.mode.value} mode")
                return {
                    "status": "rejected",
                    "reason": f"System is in {self.mode.value} mode"
                }
            
            # Auto-switch to MANUAL if User acts
            if source == "USER" and self.mode == SystemMode.AUTO:
                self.mode = SystemMode.MANUAL
                with self.turbo_lock:
                    self.turbo_state.status = AlgorithmState.IDLE
                self.logger.info(f"[MODE] User override: Switched from AUTO to MANUAL")
            
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
            elif action == "CAMERA_SETTINGS":
                return self._handle_camera_settings(req)
            
            # Optimizer commands
            elif action == "OPTIMIZE_START":
                return self._handle_optimize_start(req)
            elif action == "OPTIMIZE_STOP":
                return self._handle_optimize_stop(req)
            elif action == "OPTIMIZE_RESET":
                return self._handle_optimize_reset(req)
            elif action == "OPTIMIZE_STATUS":
                return self._handle_optimize_status(req)
            elif action == "OPTIMIZE_SUGGESTION":
                return self._handle_optimize_suggestion(req)
            elif action == "OPTIMIZE_RESULT":
                return self._handle_optimize_result(req)
            elif action == "OPTIMIZE_CONFIG":
                return self._handle_optimize_config(req)
            
            elif action == "PMT_MEASURE":
                return self._handle_pmt_measure(req)
            elif action == "CAM_SWEEP":
                return self._handle_cam_sweep(req)
            elif action == "SECULAR_SWEEP":
                return self._handle_secular_sweep(req)
            
            else:
                self.logger.error(f"[ERROR] Unknown action '{action}' from {source}")
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
        
        self.logger.debug(f"[SET] Processing from {source}: {new_params}")
        
        # Validate parameters
        error = self._validate_params(new_params)
        if error:
            self.logger.warning(f"[SET] Validation failed: {error}")
            return {"status": "error", "message": error, "code": "VALIDATION_ERROR"}
        
        # Handle kill switch arming for e_gun
        if "e_gun" in new_params:
            if new_params["e_gun"]:
                # Arming e-gun - start kill switch
                self.logger.warning(f"[KILL SWITCH] Arming e_gun from source={source}")
                self.kill_switch.arm("e_gun", {"source": source, "voltage": self.params.get("e_gun_voltage", 0)})
            else:
                # Disarming e-gun
                self.logger.info(f"[KILL SWITCH] Disarming e_gun from source={source}")
                self.kill_switch.disarm("e_gun")
        
        # Update internal state
        self.params.update(new_params)
        
        # Determine what changed and publish updates
        dc_changed = any(k in new_params for k in ["ec1", "ec2", "comp_h", "comp_v"])
        # Note: freq0 and freq1 are constants (215.5 MHz), not adjustable
        cooling_changed = any(k in new_params for k in ["amp0", "amp1", "sw0", "sw1"])
        rf_changed = "u_rf_volts" in new_params
        piezo_changed = "piezo" in new_params
        toggle_changed = any(k in new_params for k in ["bephi", "b_field", "be_oven", "uv3", "e_gun", "hd_valve"])
        dds_changed = "dds_freq_mhz" in new_params
        
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
        
        # Update experiment context if exists
        if self.current_exp:
            self.current_exp.parameters.update(new_params)
        
        # Log if from safety system
        if "SAFETY" in source:
            self.logger.warning(f"[SAFETY] Safety SET applied: {new_params} (reason: {reason})")
        
        # Log parameter changes
        changed = list(new_params.keys())
        if len(changed) <= 3:
            self.logger.info(f"[SET] Success - Changed: {changed}")
        else:
            self.logger.info(f"[SET] Success - Changed {len(changed)} parameters")
        
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
        
        self.logger.warning("=" * 60)
        self.logger.warning(f"[STOP] EMERGENCY STOP from {source}: {reason}")
        self.logger.warning("=" * 60)
        
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
                # u_rf_mV is the SMILE interface value in millivolts (0-1400mV)
                # set_rf_voltage() expects mV, so pass it directly
                u_rf_mv = compare_params['u_rf_mV']
                success = self.labview.set_rf_voltage(u_rf_mv)
                if not success:
                    self.logger.warning("Failed to set RF voltage via LabVIEW")
            
            # Step 3: Calculate theoretical frequencies
            self.logger.info("Step 3: Calculating theoretical frequencies...")
            try:
                from services.analysis.secular_comparison import SecularFrequencyComparator
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
        """Handle general STATUS query including kill switch, camera, and wavemeter status."""
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
        
        # Get wavemeter status if available
        wavemeter_status = None
        if self.wavemeter:
            try:
                wavemeter_status = self.wavemeter.get_status()
            except:
                wavemeter_status = {"available": False}
        
        return {
            "status": "success",
            "mode": self.mode.value,
            "worker_alive": worker_alive,
            "current_exp": self.current_exp.exp_id if self.current_exp else None,
            "params": self.params,
            "turbo": turbo_dict,
            "safety_triggered": self.safety_triggered,
            "kill_switch": self.kill_switch.get_status(),
            "camera": camera_status,
            "wavemeter": wavemeter_status
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
    
    def _handle_camera_settings(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle CAMERA_SETTINGS command.
        
        Configures camera parameters (n_frames, exposure, trigger_mode, etc.)
        before starting a recording.
        
        Request format:
        {
            "action": "CAMERA_SETTINGS",
            "params": {
                "n_frames": 41,
                "exposure_ms": 300.0,
                "trigger_mode": "extern",
                "analysis_roi": {
                    "xstart": 180, "xfinish": 220,
                    "ystart": 425, "yfinish": 495,
                    "radius": 6
                }
            }
        }
        """
        params = req.get("params", {})
        
        self.logger.info(f"Camera settings update: {params}")
        
        # Forward settings to camera server if available
        if self.camera:
            try:
                # Store settings for later use
                self._camera_settings = params
                
                # TODO: Implement actual camera settings update
                # This would communicate with camera_server to set parameters
                # before starting recording
                
                return {
                    "status": "success",
                    "message": "Camera settings configured",
                    "settings": params
                }
            except Exception as e:
                self.logger.error(f"Failed to configure camera settings: {e}")
                return {
                    "status": "error",
                    "message": str(e),
                    "code": "CAMERA_SETTINGS_ERROR"
                }
        else:
            return {
                "status": "error",
                "message": "Camera interface not available",
                "code": "CAMERA_NOT_AVAILABLE"
            }
    
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
        self.logger.info(f"[PUB->ARTIQ] SET_DC: ec1={self.params['ec1']:.2f}, ec2={self.params['ec2']:.2f}, "
                        f"comp_h={self.params['comp_h']:.2f}, comp_v={self.params['comp_v']:.2f}")
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        
        # Send to LabVIEW (electrodes)
        if self.labview:
            # LabVIEW handles electrodes separately or as part of RF system
            pass  # Electrodes not directly controlled by SMILE LabVIEW in current spec
    
    def _publish_cooling_update(self):
        """Send cooling parameter update to workers."""
        # Note: freq0 and freq1 are constants (215.5 MHz) and not sent
        msg = {
            "type": "SET_COOLING",
            "values": {
                "amp0": self.params["amp0"],
                "amp1": self.params["amp1"],
                "sw0": self.params["sw0"],  # 0=off, 1=on
                "sw1": self.params["sw1"]   # 0=off, 1=on
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.logger.info(f"[PUB->ARTIQ] SET_COOLING: amp0={self.params['amp0']:.3f}, amp1={self.params['amp1']:.3f}, "
                        f"sw0={self.params['sw0']}, sw1={self.params['sw1']}")
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
    
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
        self.logger.info(f"[PUB->ARTIQ] SET_RF: U_RF={u_rf_volts:.1f}V")
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        
        # Send to LabVIEW (convert U_RF volts to u_rf millivolts)
        if self.labview:
            from core import U_RF_V_to_u_rf_mv
            u_rf_mv = U_RF_V_to_u_rf_mv(u_rf_volts)
            self.logger.info(f"[LABVIEW] Setting RF voltage: {u_rf_mv:.1f}mV (U_RF={u_rf_volts:.1f}V)")
            success = self.labview.set_rf_voltage(u_rf_mv)
            if not success:
                self.logger.warning("[LABVIEW] Failed to set RF voltage")
    
    def _publish_piezo_update(self):
        """Send piezo voltage update to workers and LabVIEW."""
        piezo_v = self.params["piezo"]
        msg = {
            "type": "SET_PIEZO",
            "values": {
                "piezo": piezo_v
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.logger.info(f"[PUB->ARTIQ] SET_PIEZO: {piezo_v:.3f}V")
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        
        # Send to LabVIEW
        if self.labview:
            self.logger.info(f"[LABVIEW] Setting piezo voltage: {piezo_v:.3f}V")
            success = self.labview.set_piezo_voltage(piezo_v)
            if not success:
                self.logger.warning("[LABVIEW] Failed to set piezo voltage")
    
    def _publish_toggle_update(self, toggles: Dict[str, Any]):
        """Send toggle state updates to workers and LabVIEW."""
        # Map of parameter names to LabVIEW setter methods
        # All toggles are integers: 0=off, 1=on
        labview_setters = {
            "be_oven": lambda v: self.labview.set_be_oven(v) if self.labview else False,
            "b_field": lambda v: self.labview.set_b_field(v) if self.labview else False,
            "bephi": lambda v: self.labview.set_bephi(v) if self.labview else False,
            "uv3": lambda v: self.labview.set_uv3(v) if self.labview else False,
            "e_gun": lambda v: self.labview.set_e_gun(v) if self.labview else False,
            "hd_valve": lambda v: self.labview.set_hd_valve(v) if self.labview else False,
        }
        
        for name, value in toggles.items():
            # Ensure value is integer (0 or 1)
            int_value = int(1 if value else 0)
            msg = {
                "type": f"SET_{name.upper()}",
                "value": int_value,
                "exp_id": self.current_exp.exp_id if self.current_exp else None
            }
            state_str = "ON" if int_value else "OFF"
            self.logger.info(f"[PUB->ARTIQ] SET_{name.upper()}: {state_str}")
            self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
            self.pub_socket.send_json(msg)
            
            # Send to LabVIEW
            if name in labview_setters and self.labview:
                self.logger.info(f"[LABVIEW] Setting {name}={state_str}")
                success = labview_setters[name](int_value)
                if not success:
                    self.logger.warning(f"[LABVIEW] Failed to set {name}")
    
    def _publish_dds_update(self):
        """Send DDS frequency update to LabVIEW (LabVIEW controlled only, 0-200 MHz)."""
        dds_freq = self.params.get("dds_freq_mhz", 0.0)
        msg = {
            "type": "SET_DDS",
            "values": {
                "dds_freq_mhz": dds_freq
            },
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.logger.info(f"[PUB->ARTIQ] SET_DDS: freq={dds_freq:.2f}MHz")
        self.pub_socket.send_string("ALL", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        
        # Send to LabVIEW
        if self.labview:
            self.logger.info(f"[LABVIEW] Setting DDS frequency: {dds_freq:.2f}MHz")
            success = self.labview.set_dds_frequency(dds_freq)
            if not success:
                self.logger.warning("[LABVIEW] Failed to set DDS frequency")
    
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
        target_freq = params.get('target_frequency_khz', 'unknown')
        steps = params.get('steps', 'unknown')
        self.logger.info(f"[PUB->ARTIQ] RUN_SWEEP: exp={exp_id}, target={target_freq}kHz, steps={steps}")
        self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
    
    # ==========================================================================
    # BACKGROUND THREADS
    # ==========================================================================
    
    def _listen_for_worker_data(self):
        """Background thread to catch data from Worker."""
        self.logger.info("[LISTENER] Worker data listener started")
        
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
                    self.logger.debug(f"[LISTENER] Heartbeat from {source}")
                    
                elif category == "DATA":
                    self.logger.debug(f"[LISTENER] Data from {source}: {payload}")
                    
                elif category == "SWEEP_COMPLETE":
                    self.logger.info(f"[LISTENER] SWEEP_COMPLETE from {source} for exp={exp_id}")
                    self._handle_sweep_complete(packet)
                    
                elif category == "STATUS":
                    self.logger.info(f"[LISTENER] Status from {source}: {payload}")
                    
                elif category == "ERROR":
                    self.logger.error(f"[LISTENER] Error from {source}: {payload}")
                    
                elif category == "PMT_MEASURE_RESULT":
                    counts = payload.get('counts', 'unknown')
                    self.logger.info(f"[LISTENER] PMT_MEASURE_RESULT from {source}: {counts} counts")
                    
                elif category == "CAM_SWEEP_COMPLETE":
                    self.logger.info(f"[LISTENER] CAM_SWEEP_COMPLETE from {source} for exp={exp_id}")
                    
                elif category == "CAM_SWEEP_ERROR":
                    error_msg = payload.get('error', 'unknown error')
                    self.logger.error(f"[LISTENER] CAM_SWEEP_ERROR from {source}: {error_msg}")
                    
                elif category == "SECULAR_SWEEP_COMPLETE":
                    self.logger.info(f"[LISTENER] SECULAR_SWEEP_COMPLETE from {source} for exp={exp_id}")
                    
                elif category == "SECULAR_SWEEP_ERROR":
                    error_msg = payload.get('error', 'unknown error')
                    self.logger.error(f"[LISTENER] SECULAR_SWEEP_ERROR from {source}: {error_msg}")
                    
                else:
                    self.logger.debug(f"[LISTENER] {category} from {source}")
                    
            except zmq.Again:
                # Timeout, continue loop
                continue
            except Exception as e:
                self.logger.error(f"[LISTENER] Data listener error: {e}")
    
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
        
        self.logger.info(f"[HEALTH] Health monitor started (watchdog timeout: {timeout}s)")
        
        while self.running:
            time.sleep(1)
            
            # Check worker heartbeat
            with self.worker_lock:
                time_since_heartbeat = time.time() - self.last_worker_heartbeat
                if time_since_heartbeat > timeout:
                    if self.worker_alive:
                        self.logger.error(f"[HEALTH] WORKER TIMEOUT: No heartbeat for {time_since_heartbeat:.1f}s")
                        self.worker_alive = False
                        
                        # Trigger safety if in AUTO mode
                        if self.mode == SystemMode.AUTO:
                            self.logger.warning("[HEALTH] Entering SAFE mode due to worker timeout")
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
        # All toggles are integers: 0=off, 1=on
        self.params.update({
            "u_rf_volts": 0.0,
            "ec1": 0.0,
            "ec2": 0.0,
            "comp_h": 0.0,
            "comp_v": 0.0,
            "piezo": 0.0,
            "sw0": 0,
            "sw1": 0,
            "bephi": 0,
            "b_field": 0,
            "be_oven": 0,
            "e_gun": 0,
            "uv3": 0,
            "hd_valve": 0,
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
    
    def _init_wavemeter(self):
        """Initialize wavemeter interface for frequency data collection."""
        try:
            config = get_config()
            enabled = config.get('wavemeter.enabled', True)
            
            if not enabled:
                self.logger.info("Wavemeter interface disabled in config")
                return
            
            self.wavemeter = WavemeterInterface()
            
            # Start the wavemeter data collection
            if self.wavemeter.start():
                self.logger.info(f"Wavemeter interface started ({self.wavemeter.host}:{self.wavemeter.port})")
            else:
                self.logger.warning("Wavemeter interface failed to start")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize wavemeter interface: {e}")
            self.wavemeter = None
    
    # ==========================================================================
    # OPTIMIZER INTEGRATION - Bayesian Optimization for Ion Loading
    # ==========================================================================
    
    def _init_optimizer(self):
        """Initialize optimizer controller if available."""
        if not OPTIMIZER_AVAILABLE:
            self.logger.info("Optimizer controller not available")
            return
        
        try:
            self.optimizer_controller = OptimizerController(control_manager=self)
            self.logger.info("Optimizer controller initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize optimizer: {e}")
            self.optimizer_controller = None
    
    def _handle_optimize_start(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle OPTIMIZE_START command.
        
        Starts Bayesian optimization for ion loading.
        
        Request format:
        {
            "action": "OPTIMIZE_START",
            "target_be_count": 1,
            "target_hd_present": false,
            "max_iterations": 100,
            ...
        }
        """
        if not self.optimizer_controller:
            return {
                "status": "error",
                "message": "Optimizer controller not available",
                "code": "OPTIMIZER_NOT_AVAILABLE"
            }
        
        # Must be in AUTO mode for optimization
        if self.mode != SystemMode.AUTO:
            return {
                "status": "rejected",
                "reason": f"System must be in AUTO mode (currently {self.mode.value})"
            }
        
        # Extract configuration from request
        config_overrides = {
            k: v for k, v in req.items()
            if k not in ['action', 'source', 'exp_id']
        }
        
        try:
            success = self.optimizer_controller.start(**config_overrides)
            
            if success:
                # Create experiment context for optimization
                self.current_exp = self.tracker.create_experiment(parameters={
                    "type": "optimization",
                    **config_overrides
                })
                self.current_exp.start()
                
                self.logger.info(f"Optimization started: {config_overrides}")
                
                return {
                    "status": "success",
                    "message": "Optimization started",
                    "exp_id": self.current_exp.exp_id,
                    "config": config_overrides
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to start optimization"
                }
                
        except Exception as e:
            self.logger.error(f"Error starting optimization: {e}")
            return {
                "status": "error",
                "message": str(e),
                "code": "OPTIMIZER_ERROR"
            }
    
    def _handle_optimize_stop(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_STOP command."""
        if not self.optimizer_controller:
            return {
                "status": "error",
                "message": "Optimizer controller not available"
            }
        
        success = self.optimizer_controller.stop()
        
        return {
            "status": "success" if success else "error",
            "message": "Optimization stopped" if success else "Failed to stop"
        }
    
    def _handle_optimize_reset(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_RESET command."""
        if not self.optimizer_controller:
            return {
                "status": "error",
                "message": "Optimizer controller not available"
            }
        
        success = self.optimizer_controller.reset()
        
        return {
            "status": "success" if success else "error",
            "message": "Optimization reset" if success else "Failed to reset"
        }
    
    def _handle_optimize_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_STATUS command."""
        if not self.optimizer_controller:
            return {
                "status": "error",
                "message": "Optimizer controller not available"
            }
        
        status = self.optimizer_controller.get_status()
        
        return {
            "status": "success",
            "data": status.to_dict()
        }
    
    def _handle_optimize_suggestion(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle OPTIMIZE_SUGGESTION request.
        
        Returns the next suggested parameters for the optimizer.
        ControlManager calls this to get parameters, then executes the experiment.
        """
        if not self.optimizer_controller:
            return {
                "status": "error",
                "message": "Optimizer controller not available"
            }
        
        suggestion = self.optimizer_controller.get_next_suggestion()
        
        if suggestion is None:
            return {
                "status": "no_suggestion",
                "message": "No suggestion available (optimizer not running or pending result)"
            }
        
        return {
            "status": "success",
            "data": suggestion
        }
    
    def _handle_optimize_result(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle OPTIMIZE_RESULT command.
        
        Register experimental results from optimizer experiment.
        
        Request format:
        {
            "action": "OPTIMIZE_RESULT",
            "measurements": {
                "ion_count": 1,
                "secular_freq": 307.0,
                "sweep_peak_freq": 277.0,
                ...
            }
        }
        """
        if not self.optimizer_controller:
            return {
                "status": "error",
                "message": "Optimizer controller not available"
            }
        
        measurements = req.get("measurements", {})
        
        if not measurements:
            return {
                "status": "error",
                "message": "No measurements provided"
            }
        
        try:
            status = self.optimizer_controller.register_result(measurements)
            
            # Update experiment context
            if self.current_exp:
                self.current_exp.add_result("optimization", {
                    "iteration": status.iteration,
                    "cost": status.current_cost,
                    "measurements": measurements
                })
            
            return {
                "status": "success",
                "data": status.to_dict()
            }
            
        except Exception as e:
            self.logger.error(f"Error registering optimization result: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _handle_pmt_measure(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle PMT_MEASURE command - Request gated PMT count from ARTIQ.
        
        This follows the approach used in PMT_beam_finder.py:
        - Send PMT_MEASURE command to ARTIQ worker
        - ARTIQ opens ttl0_counter gate for specified duration
        - Returns the count value
        
        Request format:
        {
            "action": "PMT_MEASURE",
            "duration_ms": 100.0  # Measurement duration in milliseconds
        }
        
        Response format:
        {
            "status": "success",
            "counts": 1234,
            "duration_ms": 100.0
        }
        """
        duration_ms = req.get("duration_ms", 100.0)
        exp_id = req.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        self.logger.info(f"PMT measure requested: duration={duration_ms}ms")
        
        # Publish PMT_MEASURE command to ARTIQ worker
        # The worker will execute the measurement and return results via PULL socket
        msg = {
            "type": "PMT_MEASURE",
            "duration_ms": duration_ms,
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        
        self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        
        # Wait for response with timeout
        # The ARTIQ worker will send back results via the PULL socket
        timeout = duration_ms / 1000.0 + 2.0  # measurement time + 2s buffer
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Set temporary timeout for this check
                self.pull_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms chunks
                packet = self.pull_socket.recv_json()
                
                # Check if this is our PMT measurement response
                if packet.get("category") == "PMT_MEASURE_RESULT" and packet.get("exp_id") == exp_id:
                    payload = packet.get("payload", {})
                    counts = payload.get("counts", 0)
                    self.logger.info(f"PMT measurement complete: {counts} counts in {duration_ms}ms")
                    return {
                        "status": "success",
                        "counts": counts,
                        "duration_ms": duration_ms
                    }
                    
            except zmq.Again:
                # No message yet, continue waiting
                continue
            except Exception as e:
                self.logger.error(f"Error waiting for PMT measure result: {e}")
                break
        
        # If we get here, we timed out
        self.logger.warning(f"PMT measurement timeout after {timeout:.1f}s")
        return {
            "status": "error",
            "message": "PMT measurement timeout",
            "code": "PMT_TIMEOUT"
        }
    
    def _handle_cam_sweep(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle CAM_SWEEP command - Run secular sweep with synchronized camera capture.
        
        Workflow:
        1. Stop camera infinity mode (if running)
        2. Configure camera for N frames with external trigger
        3. Send CAM_SWEEP command to ARTIQ worker
        4. ARTIQ runs sweep: for each frequency point:
           - Set DDS frequency
           - Enable DDS output
           - Gate PMT counter
           - Trigger camera via TTL
           - Record PMT counts
        5. Collect sweep data from ARTIQ
        6. Return data to caller (ion positions read separately from ion_data files)
        
        Request format:
        {
            "action": "CAM_SWEEP",
            "params": {
                "target_frequency_khz": 400.0,
                "span_khz": 40.0,
                "steps": 41,
                "on_time_ms": 100.0,
                "off_time_ms": 100.0,
                "attenuation_db": 25.0
            }
        }
        
        Response format:
        {
            "status": "success",
            "sweep_data": {
                "frequencies_khz": [...],
                "pmt_counts": [...]
            }
        }
        """
        params = req.get("params", {})
        exp_id = req.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        # Extract sweep parameters
        target_freq = params.get("target_frequency_khz", 400.0)
        span_khz = params.get("span_khz", 40.0)
        steps = int(params.get("steps", 41))
        on_time_ms = params.get("on_time_ms", 100.0)
        off_time_ms = params.get("off_time_ms", 100.0)
        att_db = params.get("attenuation_db", 25.0)
        
        self.logger.info(f"CAM_SWEEP requested: {target_freq}kHz ± {span_khz/2}kHz, "
                        f"{steps} steps, {on_time_ms}ms on/{off_time_ms}ms off")
        
        # Stop camera infinity mode first
        if self.camera and self.camera.is_recording:
            self.logger.info("Stopping camera infinity mode for sweep...")
            self.camera.stop_recording()
            time.sleep(1.0)  # Wait for camera to stop
        
        # Publish CAM_SWEEP command to ARTIQ worker
        # The worker will execute the sweep and return results via PULL socket
        msg = {
            "type": "CAM_SWEEP",
            "params": {
                "target_frequency_khz": target_freq,
                "span_khz": span_khz,
                "steps": steps,
                "on_time_ms": on_time_ms,
                "off_time_ms": off_time_ms,
                "attenuation_db": att_db
            },
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        
        self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        
        # Calculate timeout: sweep time + buffer
        sweep_duration = (on_time_ms + off_time_ms) * steps / 1000.0  # seconds
        timeout = sweep_duration + 10.0  # sweep time + 10s buffer
        start_time = time.time()
        
        self.logger.info(f"Waiting for sweep completion (timeout: {timeout:.1f}s)...")
        
        # Wait for sweep completion
        while time.time() - start_time < timeout:
            try:
                # Set temporary timeout for this check
                self.pull_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms chunks
                packet = self.pull_socket.recv_json()
                
                # Check if this is our sweep response
                if packet.get("category") == "CAM_SWEEP_COMPLETE" and packet.get("exp_id") == exp_id:
                    payload = packet.get("payload", {})
                    frequencies = payload.get("frequencies_khz", [])
                    pmt_counts = payload.get("pmt_counts", [])
                    
                    self.logger.info(f"CAM_SWEEP complete: {len(frequencies)} points")
                    
                    return {
                        "status": "success",
                        "sweep_data": {
                            "frequencies_khz": frequencies,
                            "pmt_counts": pmt_counts
                        },
                        "exp_id": exp_id
                    }
                
                elif packet.get("category") == "CAM_SWEEP_ERROR" and packet.get("exp_id") == exp_id:
                    error_msg = packet.get("payload", {}).get("error", "Unknown error")
                    self.logger.error(f"CAM_SWEEP failed: {error_msg}")
                    return {
                        "status": "error",
                        "message": error_msg,
                        "code": "SWEEP_ERROR"
                    }
                    
            except zmq.Again:
                # No message yet, continue waiting
                continue
            except Exception as e:
                self.logger.error(f"Error waiting for CAM_SWEEP result: {e}")
                break
        
        # If we get here, we timed out
        self.logger.warning(f"CAM_SWEEP timeout after {timeout:.1f}s")
        return {
            "status": "error",
            "message": "Camera sweep timeout",
            "code": "SWEEP_TIMEOUT"
        }
    
    def _handle_secular_sweep(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle SECULAR_SWEEP command - Run secular frequency sweep.
        
        Similar to CAM_SWEEP but without camera triggering, and supports
        both axial (urukul0_ch0) and radial (urukul0_ch1) sweeps.
        
        Request format:
        {
            "action": "SECULAR_SWEEP",
            "params": {
                "target_frequency_khz": 400.0,
                "span_khz": 40.0,
                "steps": 41,
                "on_time_ms": 100.0,
                "off_time_ms": 100.0,
                "attenuation_db": 25.0,
                "dds_choice": "axial"  # or "radial"
            }
        }
        
        Response format:
        {
            "status": "success",
            "sweep_data": {
                "frequencies_khz": [...],
                "pmt_counts": [...]
            }
        }
        """
        params = req.get("params", {})
        exp_id = req.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        # Extract sweep parameters
        target_freq = params.get("target_frequency_khz", 400.0)
        span_khz = params.get("span_khz", 40.0)
        steps = int(params.get("steps", 41))
        on_time_ms = params.get("on_time_ms", 100.0)
        off_time_ms = params.get("off_time_ms", 100.0)
        att_db = params.get("attenuation_db", 25.0)
        dds_choice = params.get("dds_choice", "axial")  # "axial" or "radial"
        
        self.logger.info(f"SECULAR_SWEEP requested: {target_freq}kHz ± {span_khz/2}kHz, "
                        f"{steps} steps, DDS={dds_choice}")
        
        # Publish SECULAR_SWEEP command to ARTIQ worker
        msg = {
            "type": "SECULAR_SWEEP",
            "params": {
                "target_frequency_khz": target_freq,
                "span_khz": span_khz,
                "steps": steps,
                "on_time_ms": on_time_ms,
                "off_time_ms": off_time_ms,
                "attenuation_db": att_db,
                "dds_choice": dds_choice
            },
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        
        self.pub_socket.send_string("ARTIQ", flags=zmq.SNDMORE)
        self.pub_socket.send_json(msg)
        
        # Calculate timeout: sweep time + buffer
        sweep_duration = (on_time_ms + off_time_ms) * steps / 1000.0  # seconds
        timeout = sweep_duration + 10.0  # sweep time + 10s buffer
        start_time = time.time()
        
        self.logger.info(f"Waiting for secular sweep completion (timeout: {timeout:.1f}s)...")
        
        # Wait for sweep completion
        while time.time() - start_time < timeout:
            try:
                # Set temporary timeout for this check
                self.pull_socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms chunks
                packet = self.pull_socket.recv_json()
                
                # Check if this is our sweep response
                if packet.get("category") == "SECULAR_SWEEP_COMPLETE" and packet.get("exp_id") == exp_id:
                    payload = packet.get("payload", {})
                    frequencies = payload.get("frequencies_khz", [])
                    pmt_counts = payload.get("pmt_counts", [])
                    
                    self.logger.info(f"SECULAR_SWEEP complete: {len(frequencies)} points")
                    
                    return {
                        "status": "success",
                        "sweep_data": {
                            "frequencies_khz": frequencies,
                            "pmt_counts": pmt_counts
                        },
                        "exp_id": exp_id
                    }
                
                elif packet.get("category") == "SECULAR_SWEEP_ERROR" and packet.get("exp_id") == exp_id:
                    error_msg = packet.get("payload", {}).get("error", "Unknown error")
                    self.logger.error(f"SECULAR_SWEEP failed: {error_msg}")
                    return {
                        "status": "error",
                        "message": error_msg,
                        "code": "SWEEP_ERROR"
                    }
                    
            except zmq.Again:
                # No message yet, continue waiting
                continue
            except Exception as e:
                self.logger.error(f"Error waiting for SECULAR_SWEEP result: {e}")
                break
        
        # If we get here, we timed out
        self.logger.warning(f"SECULAR_SWEEP timeout after {timeout:.1f}s")
        return {
            "status": "error",
            "message": "Secular sweep timeout",
            "code": "SWEEP_TIMEOUT"
        }
    
    def _handle_optimize_config(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_CONFIG get/set."""
        if not self.optimizer_controller:
            return {
                "status": "error",
                "message": "Optimizer controller not available"
            }
        
        method = req.get("method", "GET")
        
        if method == "GET":
            config = self.optimizer_controller.config
            return {
                "status": "success",
                "data": {
                    "target_be_count": config.target_be_count,
                    "target_hd_present": config.target_hd_present,
                    "max_iterations": config.max_iterations,
                    "convergence_threshold": config.convergence_threshold,
                    "n_initial_points": config.n_initial_points,
                    "enable_be_loading": config.enable_be_loading,
                    "enable_be_ejection": config.enable_be_ejection,
                    "enable_hd_loading": config.enable_hd_loading,
                }
            }
        else:  # POST
            config_updates = req.get("config", {})
            for key, value in config_updates.items():
                if hasattr(self.optimizer_controller.config, key):
                    setattr(self.optimizer_controller.config, key, value)
            
            return {
                "status": "success",
                "message": "Configuration updated"
            }
    
    def execute_optimization_step(self) -> Optional[Dict[str, Any]]:
        """
        Execute one step of optimization (called by main loop or worker).
        
        This is the integration point where ControlManager:
        1. Gets suggestion from optimizer
        2. Executes experiment with suggested parameters
        3. Collects measurements
        4. Registers result with optimizer
        
        Returns:
            Status dictionary or None if not running
        """
        if not self.optimizer_controller or not self.optimizer_controller.is_running():
            return None
        
        # Check if we need a new suggestion
        if self.optimizer_controller.has_suggestion_pending():
            return None  # Waiting for result
        
        # Get suggestion
        suggestion = self.optimizer_controller.get_next_suggestion()
        if suggestion is None:
            return None
        
        # Extract parameters for SET command
        params = {k: v for k, v in suggestion.items() if not k.startswith('_')}
        
        # Execute SET command
        set_result = self._handle_set({
            "params": params,
            "source": "OPTIMIZER",
            "reason": f"Optimization iteration {self.optimizer_controller.iteration}"
        })
        
        if set_result.get("status") != "success":
            self.logger.error(f"Failed to set optimizer parameters: {set_result}")
            return None
        
        # Note: The experiment execution and measurement collection
        # would be handled by the worker (ARTIQ) or camera
        # For now, we return the suggestion for external execution
        
        return {
            "status": "suggestion_ready",
            "params": suggestion,
            "phase": self.optimizer_controller.phase.value,
            "iteration": self.optimizer_controller.iteration
        }
    
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
        
        # Stop wavemeter interface
        if hasattr(self, 'wavemeter') and self.wavemeter:
            self.logger.info("Stopping wavemeter interface...")
            self.wavemeter.stop()
        
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
    mgr = None
    try:
        print("=" * 60)
        print("[STARTUP] MLS Control Manager Starting...")
        print("=" * 60)
        mgr = ControlManager()
        print("-" * 60)
        print("[STARTUP] Control Manager initialized successfully")
        print("[STARTUP] Entering main request loop...")
        print("=" * 60)
        mgr.run()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] KeyboardInterrupt received")
        if mgr:
            mgr.shutdown()
    except Exception as e:
        logging.error(f"[FATAL] Fatal error: {e}", exc_info=True)
        print(f"[FATAL] Fatal error: {e}")
        raise
    finally:
        print("=" * 60)
        print("[SHUTDOWN] Control Manager stopped")
        print("=" * 60)
