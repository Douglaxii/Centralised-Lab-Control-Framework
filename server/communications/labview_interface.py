"""
LabVIEW Interface Module - TCP Communication with SMILE LabVIEW Program

Provides bidirectional communication between the Python Control Manager and
the SMILE LabVIEW program for hardware control.

Supported Controls:
- U_RF (RF voltage)
- Piezo voltage (kill switch protected: 10s max)
- Be+ Oven (on/off)
- B-field (on/off)
- Bephi (on/off)
- UV3 (on/off)
- E-gun (on/off) (kill switch protected: 30s max)
- HD Valve Shutters (on/off)
- DDS Frequency

Protocol: JSON over TCP

SAFETY CRITICAL:
- Piezo output is limited to 10 seconds maximum by worker-level kill switch
- E-gun output is limited to 30 seconds maximum by worker-level kill switch
- These are the FINAL safety layer before hardware
"""

import socket
import json
import time
import threading
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core import get_config


# =============================================================================
# LABVIEW WORKER KILL SWITCH - FINAL SAFETY LAYER
# =============================================================================

class LabVIEWKillSwitch:
    """
    Worker-level kill switch for LabVIEW hardware outputs.
    
    This is the FINAL safety layer before hardware. Time limits:
    - piezo: 10 seconds max
    - e_gun: 30 seconds max
    
    On timeout: Immediately commands LabVIEW to set voltage to 0V.
    """
    
    TIME_LIMITS = {
        "piezo": 10.0,   # 10 seconds
        "e_gun": 30.0,   # 30 seconds max
    }
    
    # Pressure safety threshold (mbar) - immediate kill if exceeded
    PRESSURE_THRESHOLD_MBAR = 5e-10  # 5e-9 mbar threshold
    
    def __init__(self, labview_interface: 'LabVIEWInterface'):
        self._labview = labview_interface
        self._active: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._running = True
        self.logger = logging.getLogger("labview_kill_switch")
        
        # Start watchdog
        self._watchdog = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="LabVIEWKillSwitch"
        )
        self._watchdog.start()
        self.logger.info("LabVIEW Kill Switch initialized")
    
    def arm(self, device: str, metadata: Dict[str, Any] = None) -> bool:
        """Arm the kill switch for a device."""
        with self._lock:
            if device not in self.TIME_LIMITS:
                return False
            
            self._active[device] = {
                "start_time": time.time(),
                "metadata": metadata or {},
                "killed": False,
            }
            self.logger.warning(
                f"LABVIEW KILL SWITCH ARMED for {device} "
                f"(limit: {self.TIME_LIMITS[device]}s)"
            )
            return True
    
    def disarm(self, device: str) -> bool:
        """Disarm the kill switch (safe turn-off)."""
        with self._lock:
            if device in self._active:
                elapsed = time.time() - self._active[device]["start_time"]
                self.logger.info(
                    f"LabVIEW kill switch disarmed for {device} "
                    f"(was active for {elapsed:.1f}s)"
                )
                del self._active[device]
                return True
            return False
    
    def is_armed(self, device: str) -> bool:
        """Check if kill switch is armed."""
        with self._lock:
            return device in self._active and not self._active[device].get("killed", False)
    
    def _kill_device(self, device: str, reason: str):
        """Execute kill - set device to safe state (0V/off)."""
        self.logger.error(
            f"LABVIEW KILL SWITCH EXECUTING for {device}: {reason}"
        )
        
        try:
            if device == "piezo":
                self._labview.set_piezo_voltage(0.0, bypass_kill_switch=True)
            elif device == "e_gun":
                self._labview.set_e_gun(False, bypass_kill_switch=True)
            self.logger.info(f"LabVIEW kill switch executed for {device}")
        except Exception as e:
            self.logger.error(f"LabVIEW kill switch execution failed: {e}")
    
    def trigger(self, device: str, reason: str = "manual") -> bool:
        """Manually trigger the kill switch."""
        with self._lock:
            if device not in self._active:
                return False
            
            info = self._active[device]
            if info.get("killed"):
                return False
            
            info["killed"] = True
            elapsed = time.time() - info["start_time"]
            
            self.logger.error(
                f"LABVIEW KILL SWITCH TRIGGERED for {device}: {reason} "
                f"(was on for {elapsed:.1f}s)"
            )
            
            # Execute kill
            self._kill_device(device, reason)
            
            del self._active[device]
            return True
    
    def _watchdog_loop(self):
        """Monitor active devices."""
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
                    self.trigger(device, f"TIME LIMIT ({self.TIME_LIMITS[device]}s)")
                
                time.sleep(0.05)  # 20 Hz check rate (faster at hardware level)
                
            except Exception as e:
                self.logger.error(f"LabVIEW kill switch watchdog error: {e}")
                time.sleep(1)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
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
                    }
                else:
                    status[device] = {"armed": False, "limit": limit}
            return status
    
    def trigger_pressure_alert(self, pressure: float, threshold: float):
        """
        Trigger immediate kill due to pressure threshold exceeded.
        This is called when pressure exceeds safe limits.
        
        Args:
            pressure: Current pressure reading (mbar)
            threshold: Threshold that was exceeded (mbar)
        """
        self.logger.error(
            f"PRESSURE ALERT: {pressure:.2e} mbar exceeds threshold {threshold:.2e} mbar! "
            f"Immediately killing piezo and e-gun!"
        )
        
        # Kill piezo immediately
        if "piezo" not in self._active or not self._active.get("piezo", {}).get("killed", False):
            self._kill_device("piezo", f"PRESSURE_ALERT: {pressure:.2e} mbar")
        
        # Kill e-gun immediately
        if "e_gun" not in self._active or not self._active.get("e_gun", {}).get("killed", False):
            self._kill_device("e_gun", f"PRESSURE_ALERT: {pressure:.2e} mbar")
    
    def shutdown(self):
        """Shutdown and kill all devices."""
        self._running = False
        with self._lock:
            for device in list(self._active.keys()):
                self.trigger(device, "SHUTDOWN")


class LabVIEWCommandType(Enum):
    """Types of commands that can be sent to LabVIEW."""
    SET_VOLTAGE = "set_voltage"           # U_RF, Piezo
    SET_TOGGLE = "set_toggle"             # Oven, B-field, Bephi, UV3, E-gun
    SET_SHUTTER = "set_shutter"           # HD Valve shutters
    SET_FREQUENCY = "set_frequency"       # DDS Frequency
    GET_STATUS = "get_status"             # Query current state
    EMERGENCY_STOP = "emergency_stop"     # Immediate stop
    PING = "ping"                         # Keepalive
    PRESSURE_ALERT = "pressure_alert"     # Pressure threshold exceeded


class PressureMonitor:
    """
    Real-time pressure monitor with immediate safety response.
    
    Monitors pressure data from SMILE/LabVIEW via file system (E:/Data/telemetry/)
    and triggers immediate kill switch when threshold is exceeded.
    
    Features:
    - Ultra-low latency response (< 50ms from detection to action)
    - Immediate piezo and e-gun shutdown on pressure spike
    - Server notification via callback
    - Configurable thresholds
    - Hysteresis to prevent oscillation
    """
    
    # Default pressure threshold (mbar) - vacuum is typically 1e-10 to 1e-9
    DEFAULT_THRESHOLD_MBAR = 5e-9
    
    # Hysteresis factor (threshold must drop to threshold/hysteresis before reset)
    HYSTERESIS = 2.0
    
    # Check interval (seconds) - high frequency for safety
    CHECK_INTERVAL = 0.05  # 20 Hz check rate
    
    def __init__(
        self,
        labview_interface: 'LabVIEWInterface',
        threshold_mbar: float = None,
        pressure_file_path: str = None,
        alert_callback: Optional[Callable] = None,
        check_interval: float = None
    ):
        """
        Initialize pressure monitor.
        
        Args:
            labview_interface: LabVIEW interface for triggering kill switch
            threshold_mbar: Pressure threshold in mbar (default: 5e-9)
            pressure_file_path: Path to pressure data file (optional, uses telemetry dir)
            alert_callback: Callback function(pressure, threshold, timestamp) for server notification
            check_interval: Check interval in seconds (default: 0.05 = 20Hz)
        """
        self.logger = logging.getLogger("pressure_monitor")
        self.labview = labview_interface
        
        # Get config values
        config = get_config()
        
        self.threshold = threshold_mbar or config.get('labview.pressure_threshold_mbar', self.DEFAULT_THRESHOLD_MBAR)
        self.check_interval = check_interval or config.get('labview.pressure_check_interval', self.CHECK_INTERVAL)
        self.alert_callback = alert_callback
        
        # Get pressure file path from config or use default
        output_base = config.get_path('output_base') if config else "E:/Data"
        self.pressure_dir = Path(pressure_file_path or f"{output_base}/telemetry/smile/pressure")
        
        # State
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.alert_active = False
        self.last_pressure: Optional[float] = None
        self.last_read_time: Optional[float] = None
        self.known_files: set = set()
        
        # Statistics
        self.stats = {
            "checks": 0,
            "alerts_triggered": 0,
            "last_alert_time": None,
            "max_pressure_seen": 0.0,
        }
        
        self.logger.info(
            f"PressureMonitor initialized (threshold: {self.threshold:.2e} mbar, "
            f"check interval: {self.check_interval}s)"
        )
    
    def start(self):
        """Start pressure monitoring thread."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="PressureMonitor"
        )
        self.thread.start()
        self.logger.info(f"Pressure monitoring started (watching: {self.pressure_dir})")
    
    def stop(self):
        """Stop pressure monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.logger.info("Pressure monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop - runs at high frequency."""
        while self.running:
            try:
                loop_start = time.time()
                
                # Read latest pressure
                pressure = self._read_latest_pressure()
                
                if pressure is not None:
                    self.last_pressure = pressure
                    self.stats["checks"] += 1
                    
                    # Track max pressure
                    if pressure > self.stats["max_pressure_seen"]:
                        self.stats["max_pressure_seen"] = pressure
                    
                    # Check threshold
                    self._check_threshold(pressure)
                
                # Maintain check interval
                elapsed = time.time() - loop_start
                sleep_time = max(0, self.check_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                self.logger.error(f"Pressure monitor error: {e}")
                time.sleep(0.1)  # Brief pause on error
    
    def _read_latest_pressure(self) -> Optional[float]:
        """
        Read the most recent pressure value from telemetry files.
        
        Returns:
            Pressure in mbar, or None if no data available
        """
        try:
            if not self.pressure_dir.exists():
                return None
            
            # Find most recent .dat file
            dat_files = list(self.pressure_dir.glob("*.dat"))
            if not dat_files:
                return None
            
            latest_file = max(dat_files, key=lambda p: p.stat().st_mtime)
            
            # Read the file (CSV format: timestamp,pressure_mbar)
            with open(latest_file, 'r') as f:
                line = f.readline().strip()
                if ',' in line:
                    parts = line.split(',')
                    if len(parts) >= 2:
                        timestamp = float(parts[0])
                        pressure = float(parts[1])
                        
                        # Check if data is fresh (within last 5 seconds)
                        if time.time() - timestamp < 5.0:
                            self.last_read_time = timestamp
                            return pressure
                        
        except Exception as e:
            self.logger.debug(f"Failed to read pressure: {e}")
        
        return None
    
    def _check_threshold(self, pressure: float):
        """
        Check pressure against threshold and trigger alert if needed.
        
        Uses hysteresis to prevent rapid on/off cycling:
        - Alert triggers when pressure > threshold
        - Alert resets when pressure < threshold / hysteresis
        """
        if pressure > self.threshold:
            if not self.alert_active:
                # Pressure just crossed threshold - TRIGGER ALERT
                self._trigger_alert(pressure)
        elif self.alert_active:
            # Check hysteresis for reset
            reset_threshold = self.threshold / self.HYSTERESIS
            if pressure < reset_threshold:
                # Pressure dropped enough - reset alert
                self._reset_alert(pressure)
    
    def _trigger_alert(self, pressure: float):
        """Trigger pressure alert - immediate action required."""
        alert_time = time.time()
        self.alert_active = True
        self.stats["alerts_triggered"] += 1
        self.stats["last_alert_time"] = alert_time
        
        self.logger.error(
            f"🚨 PRESSURE ALERT TRIGGERED: {pressure:.2e} mbar > {self.threshold:.2e} mbar threshold! "
            f"Immediately killing piezo and e-gun!"
        )
        
        # IMMEDIATE ACTION: Kill piezo and e-gun via kill switch
        if self.labview and self.labview.kill_switch:
            self.labview.kill_switch.trigger_pressure_alert(pressure, self.threshold)
        
        # Notify server via callback
        if self.alert_callback:
            try:
                self.alert_callback(
                    pressure=pressure,
                    threshold=self.threshold,
                    timestamp=alert_time,
                    action="KILL_PIEZO_EGUN"
                )
            except Exception as e:
                self.logger.error(f"Alert callback failed: {e}")
    
    def _reset_alert(self, pressure: float):
        """Reset pressure alert when pressure returns to safe levels."""
        self.alert_active = False
        self.logger.info(
            f"Pressure alert reset: {pressure:.2e} mbar returned to safe levels "
            f"(threshold: {self.threshold:.2e} mbar)"
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get current monitor status."""
        return {
            "running": self.running,
            "alert_active": self.alert_active,
            "threshold_mbar": self.threshold,
            "check_interval_seconds": self.check_interval,
            "last_pressure_mbar": self.last_pressure,
            "last_read_time": self.last_read_time,
            "pressure_age_seconds": time.time() - self.last_read_time if self.last_read_time else None,
            "stats": self.stats.copy(),
            "pressure_dir": str(self.pressure_dir)
        }
    
    def set_threshold(self, threshold_mbar: float):
        """Update pressure threshold."""
        old_threshold = self.threshold
        self.threshold = threshold_mbar
        self.logger.info(f"Pressure threshold updated: {old_threshold:.2e} -> {threshold_mbar:.2e} mbar")


class LabVIEWCommandType(Enum):
    """Types of commands that can be sent to LabVIEW."""
    SET_VOLTAGE = "set_voltage"           # U_RF, Piezo
    SET_TOGGLE = "set_toggle"             # Oven, B-field, Bephi, UV3, E-gun
    SET_SHUTTER = "set_shutter"           # HD Valve shutters
    SET_FREQUENCY = "set_frequency"       # DDS Frequency
    GET_STATUS = "get_status"             # Query current state
    EMERGENCY_STOP = "emergency_stop"     # Immediate stop
    PING = "ping"                         # Keepalive
    PRESSURE_ALERT = "pressure_alert"     # Pressure threshold exceeded


@dataclass
class LabVIEWCommand:
    """Command structure for LabVIEW communication."""
    command: str
    device: str
    value: Any
    timestamp: float
    request_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "device": self.device,
            "value": self.value,
            "timestamp": self.timestamp,
            "request_id": self.request_id
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class LabVIEWResponse:
    """Response structure from LabVIEW."""
    request_id: str
    status: str  # "ok", "error", "busy"
    device: str
    value: Any
    message: Optional[str] = None
    timestamp: Optional[float] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LabVIEWResponse':
        return cls(
            request_id=data.get("request_id", ""),
            status=data.get("status", "error"),
            device=data.get("device", ""),
            value=data.get("value"),
            message=data.get("message"),
            timestamp=data.get("timestamp")
        )


class LabVIEWInterface:
    """
    TCP Interface to SMILE LabVIEW Program with integrated kill switch protection.
    
    Handles connection management, command queuing, and response handling.
    Thread-safe for use with the Control Manager.
    
    SAFETY: Provides FINAL safety layer for time-limited outputs.
    """
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """
        Initialize LabVIEW interface.
        
        Args:
            host: LabVIEW host IP (default from config)
            port: LabVIEW TCP port (default from config)
        """
        self.logger = logging.getLogger("labview_interface")
        
        # Load configuration
        config = get_config()
        self.host = host or config.get('labview.host') or '127.0.0.1'
        self.port = port or config.get('labview.port') or 5559
        self.timeout = config.get('labview.timeout') or 5.0
        self.retry_delay = config.get('labview.retry_delay') or 1.0
        self.max_retries = config.get('labview.max_retries') or 3
        
        # Connection state
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.lock = threading.RLock()
        
        # Command queue for async operations
        self.command_queue: list = []
        self.queue_lock = threading.Lock()
        
        # Callback for status updates from LabVIEW
        self.status_callback: Optional[Callable] = None
        
        # Background threads
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.request_counter = 0
        self.request_lock = threading.Lock()
        
        # Kill switch - FINAL safety layer
        self.kill_switch = LabVIEWKillSwitch(self)
        
        # Pressure monitor - IMMEDIATE safety response for vacuum protection
        self.pressure_monitor: Optional[PressureMonitor] = None
        self._pressure_alert_callback: Optional[Callable] = None
        
        self.logger.info(f"LabVIEW Interface initialized ({self.host}:{self.port})")
    
    def start(self):
        """Start the interface and connection monitor."""
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._connection_monitor,
            daemon=True,
            name="LabVIEWMonitor"
        )
        self.monitor_thread.start()
        
        # Start pressure monitoring (safety critical)
        self._start_pressure_monitor()
        
        self.logger.info("LabVIEW Interface started")
    
    def stop(self):
        """Stop the interface and close connection."""
        self.running = False
        # Stop pressure monitoring
        self._stop_pressure_monitor()
        # Shutdown kill switch (will zero all outputs)
        self.kill_switch.shutdown()
        self.disconnect()
        self.logger.info("LabVIEW Interface stopped")
    
    def _start_pressure_monitor(self):
        """Initialize and start pressure monitoring."""
        try:
            config = get_config()
            threshold = config.get('labview.pressure_threshold_mbar', 5e-9)
            
            self.pressure_monitor = PressureMonitor(
                labview_interface=self,
                threshold_mbar=threshold,
                alert_callback=self._on_pressure_alert
            )
            self.pressure_monitor.start()
            self.logger.info(f"Pressure monitoring started (threshold: {threshold:.2e} mbar)")
        except Exception as e:
            self.logger.error(f"Failed to start pressure monitoring: {e}")
    
    def _stop_pressure_monitor(self):
        """Stop pressure monitoring."""
        if self.pressure_monitor:
            self.pressure_monitor.stop()
            self.logger.info("Pressure monitoring stopped")
    
    def _on_pressure_alert(self, pressure: float, threshold: float, timestamp: float, action: str):
        """
        Handle pressure alert - notify server and trigger safety actions.
        
        This is called by PressureMonitor when threshold is exceeded.
        """
        self.logger.error(
            f"Pressure alert callback triggered: {pressure:.2e} mbar > {threshold:.2e} mbar, "
            f"action={action}"
        )
        
        # Notify via status callback if registered
        if self.status_callback:
            try:
                self.status_callback({
                    "type": "PRESSURE_ALERT",
                    "pressure_mbar": pressure,
                    "threshold_mbar": threshold,
                    "timestamp": timestamp,
                    "action_taken": action,
                    "source": "LabVIEW_PressureMonitor"
                })
            except Exception as e:
                self.logger.error(f"Status callback error: {e}")
    
    def set_pressure_alert_callback(self, callback: Callable):
        """
        Set callback for pressure alerts.
        
        Args:
            callback: Function(pressure, threshold, timestamp, action) to call on alert
        """
        self._pressure_alert_callback = callback
        if self.pressure_monitor:
            self.pressure_monitor.alert_callback = callback
        self.logger.info("Pressure alert callback registered")
    
    def set_pressure_threshold(self, threshold_mbar: float):
        """
        Update pressure threshold.
        
        Args:
            threshold_mbar: New threshold in mbar (e.g., 5e-9 for 5x10^-9 mbar)
        """
        if self.pressure_monitor:
            self.pressure_monitor.set_threshold(threshold_mbar)
        else:
            self.logger.warning("Pressure monitor not running, cannot set threshold")
    
    def get_pressure_status(self) -> Dict[str, Any]:
        """Get current pressure monitoring status."""
        if self.pressure_monitor:
            return self.pressure_monitor.get_status()
        return {"running": False, "error": "Pressure monitor not initialized"}
    
    def connect(self) -> bool:
        """
        Establish TCP connection to LabVIEW.
        
        Returns:
            True if connected, False otherwise
        """
        with self.lock:
            if self.connected and self.socket:
                return True
            
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                self.socket.connect((self.host, self.port))
                self.connected = True
                self.logger.info(f"Connected to LabVIEW at {self.host}:{self.port}")
                return True
                
            except socket.error as e:
                self.logger.warning(f"Failed to connect to LabVIEW: {e}")
                self.socket = None
                self.connected = False
                return False
    
    def disconnect(self):
        """Close TCP connection."""
        with self.lock:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            self.connected = False
            self.logger.info("Disconnected from LabVIEW")
    
    def _connection_monitor(self):
        """Background thread to maintain connection."""
        while self.running:
            if not self.connected:
                self.connect()
            
            # Send periodic ping to keep connection alive
            if self.connected:
                try:
                    self._send_ping()
                except:
                    self.connected = False
            
            time.sleep(5.0)  # Check every 5 seconds
    
    def _send_ping(self):
        """Send keepalive ping."""
        ping_cmd = LabVIEWCommand(
            command=LabVIEWCommandType.PING.value,
            device="system",
            value=None,
            timestamp=time.time(),
            request_id=self._generate_request_id()
        )
        self._send_command_raw(ping_cmd)
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        with self.request_lock:
            self.request_counter += 1
            return f"REQ_{self.request_counter:06d}_{int(time.time() * 1000)}"
    
    def _send_command_raw(self, command: LabVIEWCommand) -> Optional[LabVIEWResponse]:
        """
        Send a command to LabVIEW and wait for response.
        
        Note: This method assumes LabVIEW sends one response per command
        and uses newline delimiter. LabVIEW must handle TCP fragmentation
        by buffering data until newline is received.
        
        Args:
            command: Command to send
            
        Returns:
            Response from LabVIEW or None if failed
        """
        with self.lock:
            if not self.connected:
                if not self.connect():
                    return None
            
            try:
                # Send command with newline terminator
                # IMPORTANT: LabVIEW must buffer TCP data and wait for \n
                # to handle TCP fragmentation correctly
                message = command.to_json() + "\n"
                self.socket.sendall(message.encode('utf-8'))
                
                # Wait for response (blocking read)
                # LabVIEW should send response with \n terminator
                response_data = self.socket.recv(4096).decode('utf-8').strip()
                
                if not response_data:
                    return None
                
                response_dict = json.loads(response_data)
                return LabVIEWResponse.from_dict(response_dict)
                
            except socket.timeout:
                self.logger.warning("LabVIEW response timeout")
                self.connected = False
                return None
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON response: {e}")
                return None
            except Exception as e:
                self.logger.error(f"Communication error: {e}")
                self.connected = False
                return None
    
    def send_command(self, command_type: LabVIEWCommandType, device: str, 
                     value: Any, retries: Optional[int] = None) -> bool:
        """
        Send a command to LabVIEW with retry logic.
        
        Args:
            command_type: Type of command
            device: Device name
            value: Value to set
            retries: Number of retries (default from config)
            
        Returns:
            True if successful, False otherwise
        """
        if retries is None:
            retries = self.max_retries
        
        command = LabVIEWCommand(
            command=command_type.value,
            device=device,
            value=value,
            timestamp=time.time(),
            request_id=self._generate_request_id()
        )
        
        for attempt in range(retries + 1):
            response = self._send_command_raw(command)
            
            if response and response.status == "ok":
                if attempt > 0:
                    self.logger.info(f"Command succeeded after {attempt + 1} attempts")
                return True
            
            if attempt < retries:
                self.logger.warning(f"Command failed, retrying ({attempt + 1}/{retries})...")
                time.sleep(self.retry_delay)
        
        self.logger.error(f"Command failed after {retries + 1} attempts")
        return False
    
    # ==================================================================
    # CONVENIENCE METHODS FOR SPECIFIC HARDWARE
    # ==================================================================
    
    def set_rf_voltage(self, voltage: float) -> bool:
        """
        Set U_RF voltage.
        
        Args:
            voltage: Voltage in volts (0-1000)
            
        Returns:
            True if successful
        """
        return self.send_command(
            LabVIEWCommandType.SET_VOLTAGE,
            "U_RF",
            round(voltage, 3)
        )
    
    def set_piezo_voltage(self, voltage: float, bypass_kill_switch: bool = False) -> bool:
        """
        Set piezo voltage with kill switch protection.
        
        When voltage > 0: Arms kill switch (10s max)
        When voltage = 0: Disarms kill switch
        
        Args:
            voltage: Voltage in volts (0 to 4)
            bypass_kill_switch: If True, bypass kill switch arming (for kill switch callbacks)
            
        Returns:
            True if successful
        """
        # Handle kill switch
        if not bypass_kill_switch:
            if voltage > 0:
                self.kill_switch.arm("piezo", {"voltage": voltage})
            else:
                self.kill_switch.disarm("piezo")
        
        return self.send_command(
            LabVIEWCommandType.SET_VOLTAGE,
            "piezo",
            round(voltage, 3)
        )
    
    def set_be_oven(self, state: bool) -> bool:
        """Control Be+ oven (True=on, False=off)."""
        return self.send_command(
            LabVIEWCommandType.SET_TOGGLE,
            "be_oven",
            bool(state)
        )
    
    def set_b_field(self, state: bool) -> bool:
        """Control B-field (True=on, False=off)."""
        return self.send_command(
            LabVIEWCommandType.SET_TOGGLE,
            "b_field",
            bool(state)
        )
    
    def set_bephi(self, state: bool) -> bool:
        """Control Bephi (True=on, False=off)."""
        return self.send_command(
            LabVIEWCommandType.SET_TOGGLE,
            "bephi",
            bool(state)
        )
    
    def set_uv3(self, state: bool) -> bool:
        """Control UV3 laser (True=on, False=off)."""
        return self.send_command(
            LabVIEWCommandType.SET_TOGGLE,
            "uv3",
            bool(state)
        )
    
    def set_e_gun(self, state: bool, bypass_kill_switch: bool = False) -> bool:
        """
        Control electron gun with kill switch protection (30s max).
        
        When state=True: Arms kill switch
        When state=False: Disarms kill switch
        
        Args:
            state: True to turn on, False to turn off
            bypass_kill_switch: If True, bypass kill switch (for callbacks)
        """
        # Handle kill switch
        if not bypass_kill_switch:
            if state:
                self.kill_switch.arm("e_gun", {})
            else:
                self.kill_switch.disarm("e_gun")
        
        return self.send_command(
            LabVIEWCommandType.SET_TOGGLE,
            "e_gun",
            bool(state)
        )
    
    def set_hd_shutter(self, shutter_id: str, state: bool) -> bool:
        """
        Control HD valve shutter.
        
        Args:
            shutter_id: Shutter identifier (e.g., "shutter_1", "shutter_2")
            state: True=open, False=close
            
        Returns:
            True if successful
        """
        return self.send_command(
            LabVIEWCommandType.SET_SHUTTER,
            f"hd_{shutter_id}",
            bool(state)
        )
    
    def set_dds_frequency(self, frequency_mhz: float) -> bool:
        """
        Set DDS frequency.
        
        Args:
            frequency_mhz: Frequency in MHz
            
        Returns:
            True if successful
        """
        return self.send_command(
            LabVIEWCommandType.SET_FREQUENCY,
            "dds",
            round(frequency_mhz, 6)
        )
    
    def emergency_stop(self) -> bool:
        """
        Send emergency stop command.
        
        Also triggers all kill switches at LabVIEW level.
        
        Returns:
            True if successful
        """
        # Trigger kill switches first
        self.logger.error("Emergency stop: triggering kill switches")
        self.kill_switch.trigger("piezo", "EMERGENCY_STOP")
        self.kill_switch.trigger("e_gun", "EMERGENCY_STOP")
        
        return self.send_command(
            LabVIEWCommandType.EMERGENCY_STOP,
            "all",
            None,
            retries=1  # Only try once for emergency
        )
    
    def get_status(self) -> Optional[Dict[str, Any]]:
        """
        Query current status from LabVIEW.
        
        Returns:
            Status dictionary or None if failed
        """
        command = LabVIEWCommand(
            command=LabVIEWCommandType.GET_STATUS.value,
            device="all",
            value=None,
            timestamp=time.time(),
            request_id=self._generate_request_id()
        )
        
        response = self._send_command_raw(command)
        if response and response.status == "ok":
            return {
                "device": response.device,
                "value": response.value,
                "timestamp": response.timestamp
            }
        return None
    
    # ==================================================================
    # BATCH OPERATIONS
    # ==================================================================
    
    def apply_safety_defaults(self) -> Dict[str, bool]:
        """
        Apply safety defaults to all controllable hardware.
        
        Returns:
            Dictionary of device -> success status
        """
        results = {}
        
        # Voltages to 0
        results["U_RF"] = self.set_rf_voltage(0.0)
        results["piezo"] = self.set_piezo_voltage(0.0)
        
        # Toggles off
        results["be_oven"] = self.set_be_oven(False)
        results["b_field"] = self.set_b_field(False)
        results["bephi"] = self.set_bephi(False)
        results["uv3"] = self.set_uv3(False)
        results["e_gun"] = self.set_e_gun(False)
        
        self.logger.info(f"Safety defaults applied: {results}")
        return results
    
    def apply_state(self, params: Dict[str, Any]) -> Dict[str, bool]:
        """
        Apply multiple parameters at once.
        
        Args:
            params: Dictionary of parameter name -> value
            
        Returns:
            Dictionary of parameter -> success status
        """
        results = {}
        
        # Map internal parameter names to LabVIEW devices
        device_map = {
            "u_rf": ("U_RF", self.set_rf_voltage),
            "piezo": ("piezo", self.set_piezo_voltage),
            "be_oven": ("be_oven", self.set_be_oven),
            "b_field": ("b_field", self.set_b_field),
            "bephi": ("bephi", self.set_bephi),
            "uv3": ("uv3", self.set_uv3),
            "e_gun": ("e_gun", self.set_e_gun),
        }
        
        for param, value in params.items():
            if param in device_map:
                device_name, setter = device_map[param]
                try:
                    results[param] = setter(value)
                except Exception as e:
                    self.logger.error(f"Failed to set {param}: {e}")
                    results[param] = False
            elif param.startswith("hd_shutter_"):
                shutter_id = param.replace("hd_shutter_", "")
                results[param] = self.set_hd_shutter(shutter_id, value)
            elif param == "dds_freq":
                results[param] = self.set_dds_frequency(value)
        
        return results
    
    def is_connected(self) -> bool:
        """Check if connected to LabVIEW."""
        return self.connected
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information."""
        info = {
            "host": self.host,
            "port": self.port,
            "connected": self.connected,
            "timeout": self.timeout
        }
        
        # Add pressure monitoring status
        pressure_status = self.get_pressure_status()
        info["pressure_monitor"] = pressure_status
        
        return info


# ==============================================================================
# STANDALONE TEST
# ==============================================================================

if __name__ == "__main__":
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )
    
    # Create interface
    lv = LabVIEWInterface()
    lv.start()
    
    try:
        print("LabVIEW Interface Test")
        print("Commands: rf <voltage>, piezo <voltage>, oven <0/1>, bfield <0/1>")
        print("          uv3 <0/1>, egun <0/1>, status, quit")
        
        while True:
            cmd = input("> ").strip().lower().split()
            
            if not cmd:
                continue
                
            if cmd[0] == "quit":
                break
                
            elif cmd[0] == "status":
                info = lv.get_connection_info()
                print(f"Connection: {info}")
                status = lv.get_status()
                print(f"LabVIEW Status: {status}")
                
            elif cmd[0] == "rf" and len(cmd) == 2:
                success = lv.set_rf_voltage(float(cmd[1]))
                print(f"Set RF voltage: {'OK' if success else 'FAILED'}")
                
            elif cmd[0] == "piezo" and len(cmd) == 2:
                success = lv.set_piezo_voltage(float(cmd[1]))
                print(f"Set piezo voltage: {'OK' if success else 'FAILED'}")
                
            elif cmd[0] == "oven" and len(cmd) == 2:
                success = lv.set_be_oven(cmd[1] == "1")
                print(f"Set Be+ oven: {'OK' if success else 'FAILED'}")
                
            elif cmd[0] == "bfield" and len(cmd) == 2:
                success = lv.set_b_field(cmd[1] == "1")
                print(f"Set B-field: {'OK' if success else 'FAILED'}")
                
            elif cmd[0] == "uv3" and len(cmd) == 2:
                success = lv.set_uv3(cmd[1] == "1")
                print(f"Set UV3: {'OK' if success else 'FAILED'}")
                
            elif cmd[0] == "egun" and len(cmd) == 2:
                success = lv.set_e_gun(cmd[1] == "1")
                print(f"Set E-gun: {'OK' if success else 'FAILED'}")
                
            elif cmd[0] == "estop":
                success = lv.emergency_stop()
                print(f"Emergency stop: {'OK' if success else 'FAILED'}")
                
            else:
                print("Unknown command")
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        lv.stop()
