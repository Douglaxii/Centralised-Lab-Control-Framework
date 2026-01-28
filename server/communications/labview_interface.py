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
        "e_gun": 10.0,   # 10 seconds (testing mode)
    }
    
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
        self.logger.info("LabVIEW Interface started")
    
    def stop(self):
        """Stop the interface and close connection."""
        self.running = False
        # Shutdown kill switch (will zero all outputs)
        self.kill_switch.shutdown()
        self.disconnect()
        self.logger.info("LabVIEW Interface stopped")
    
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
        return {
            "host": self.host,
            "port": self.port,
            "connected": self.connected,
            "timeout": self.timeout
        }


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
