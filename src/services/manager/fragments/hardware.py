"""
Hardware Interface Fragments

Fragments for interfacing with hardware systems:
- ARTIQFragment: Commands to ARTIQ worker (DC, RF, cooling, sweeps)
- LabVIEWFragment: Commands to LabVIEW/SMILE (RF, piezo, toggles)
- CameraFragment: Camera control
- WavemeterFragment: Wavemeter frequency data via TCP
"""

import socket
import struct
import threading
import time
import re
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .base import BaseFragment, FragmentPriority


class ARTIQFragment(BaseFragment):
    """
    Fragment for ARTIQ worker communication.
    
    Handles:
    - DC electrode updates
    - RF voltage updates
    - Cooling parameter updates
    - Sweep commands (secular, camera)
    - PMT measurements
    - TTL triggers
    """
    
    NAME = "artiq"
    PRIORITY = FragmentPriority.HIGH
    
    def _do_initialize(self):
        """Initialize ARTIQ fragment."""
        self._sweep_callbacks: Dict[str, callable] = {}
        self._pending_sweeps: set = set()
    
    def _do_shutdown(self):
        """Shutdown ARTIQ fragment."""
        self._sweep_callbacks.clear()
        self._pending_sweeps.clear()
    
    # ----------------------------------------------------------------------
    # Command Publishing
    # ----------------------------------------------------------------------
    
    def publish_dc_update(self, ec1: float, ec2: float, comp_h: float, comp_v: float):
        """Send DC electrode update to ARTIQ."""
        msg = {
            "type": "SET_DC",
            "values": {"ec1": ec1, "ec2": ec2, "comp_h": comp_h, "comp_v": comp_v},
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.publish_command("ALL", msg)
        self.log_debug(f"Published DC update: {msg['values']}")
    
    def publish_cooling_update(self, amp0: float, amp1: float, sw0: int, sw1: int):
        """Send cooling parameter update to ARTIQ."""
        msg = {
            "type": "SET_COOLING",
            "values": {"amp0": amp0, "amp1": amp1, "sw0": sw0, "sw1": sw1},
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.publish_command("ALL", msg)
        self.log_debug(f"Published cooling update: {msg['values']}")
    
    def publish_rf_update(self, u_rf_volts: float):
        """Send RF voltage update to ARTIQ."""
        msg = {
            "type": "SET_RF",
            "values": {"u_rf_volts": u_rf_volts},
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.publish_command("ALL", msg)
        self.log_debug(f"Published RF update: U_RF={u_rf_volts} V")
    
    def publish_piezo_update(self, piezo: float):
        """Send piezo voltage update to ARTIQ."""
        msg = {
            "type": "SET_PIEZO",
            "values": {"piezo": piezo},
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.publish_command("ALL", msg)
        self.log_debug(f"Published piezo update: {piezo}")
    
    def publish_toggle_update(self, name: str, value: int):
        """Send toggle state update to ARTIQ."""
        msg = {
            "type": f"SET_{name.upper()}",
            "value": int(value),
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.publish_command("ALL", msg)
        self.log_debug(f"Published toggle update: {name}={value}")
    
    def publish_dds_update(self, dds_freq_mhz: float):
        """Send DDS frequency update to ARTIQ."""
        msg = {
            "type": "SET_DDS",
            "values": {"dds_freq_mhz": dds_freq_mhz},
            "exp_id": self.current_exp.exp_id if self.current_exp else None
        }
        self.publish_command("ALL", msg)
        self.log_debug(f"Published DDS update: freq={dds_freq_mhz} MHz")
    
    def publish_camera_trigger(self, exp_id: Optional[str] = None):
        """Publish camera TTL trigger command to ARTIQ."""
        msg = {
            "type": "CAMERA_TRIGGER",
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        self.publish_command("ARTIQ", msg)
        self.log_debug(f"Published camera trigger for exp {exp_id}")
    
    def publish_camera_inf_start(self, exp_id: Optional[str] = None):
        """Publish START_CAMERA_INF command to ARTIQ."""
        msg = {
            "type": "START_CAMERA_INF",
            "values": {},
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        self.publish_command("ARTIQ", msg)
        self.log_debug(f"Published START_CAMERA_INF for exp {exp_id}")
    
    def publish_emergency_zero(self, device: str):
        """Publish emergency zero command to ARTIQ."""
        msg = {
            "type": "EMERGENCY_ZERO",
            "device": device,
            "reason": "kill_switch_triggered",
            "timestamp": time.time()
        }
        self.publish_command("ALL", msg)
        self.log_warning(f"Published emergency zero for {device}")
    
    def publish_sweep_command(self, params: Dict[str, Any], exp_id: str):
        """Send sweep command to ARTIQ worker."""
        msg = {
            "type": "RUN_SWEEP",
            "values": params,
            "exp_id": exp_id
        }
        self.publish_command("ARTIQ", msg)
        self.log_info(f"Published sweep command for exp {exp_id}")
    
    # ----------------------------------------------------------------------
    # Sweep Commands
    # ----------------------------------------------------------------------
    
    def start_secular_sweep(self, params: Dict[str, Any], exp_id: str) -> Dict[str, Any]:
        """
        Start a secular frequency sweep.
        
        Returns immediately with status. Results come via data packets.
        """
        msg = {
            "type": "SECULAR_SWEEP",
            "params": params,
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        self.publish_command("ARTIQ", msg)
        self._pending_sweeps.add(exp_id)
        
        # Calculate expected duration
        steps = params.get("steps", 41)
        on_time = params.get("on_time_ms", 100)
        off_time = params.get("off_time_ms", 100)
        duration_s = (on_time + off_time) * steps / 1000.0
        
        return {
            "status": "started",
            "exp_id": exp_id,
            "expected_duration_s": duration_s,
            "message": f"Secular sweep started ({steps} steps, ~{duration_s:.1f}s)"
        }
    
    def start_cam_sweep(self, params: Dict[str, Any], exp_id: str) -> Dict[str, Any]:
        """
        Start a camera-synchronized sweep.
        
        Returns immediately with status. Results come via data packets.
        """
        msg = {
            "type": "CAM_SWEEP",
            "params": params,
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        self.publish_command("ARTIQ", msg)
        self._pending_sweeps.add(exp_id)
        
        steps = params.get("steps", 41)
        on_time = params.get("on_time_ms", 100)
        off_time = params.get("off_time_ms", 100)
        duration_s = (on_time + off_time) * steps / 1000.0
        
        return {
            "status": "started",
            "exp_id": exp_id,
            "expected_duration_s": duration_s,
            "message": f"Camera sweep started ({steps} steps, ~{duration_s:.1f}s)"
        }
    
    def request_pmt_measure(self, duration_ms: float, exp_id: Optional[str] = None):
        """Request a PMT measurement from ARTIQ."""
        msg = {
            "type": "PMT_MEASURE",
            "duration_ms": duration_ms,
            "exp_id": exp_id,
            "timestamp": time.time()
        }
        self.publish_command("ARTIQ", msg)
        self.log_debug(f"Published PMT measure request: {duration_ms}ms")
    
    # ----------------------------------------------------------------------
    # Data Handling
    # ----------------------------------------------------------------------
    
    def handle_data(self, packet: Dict[str, Any]) -> bool:
        """Handle data packets from ARTIQ."""
        category = packet.get("category", "")
        exp_id = packet.get("exp_id")
        
        if category == "SWEEP_COMPLETE":
            self._handle_sweep_complete(packet)
            return True
        elif category == "PMT_MEASURE_RESULT":
            return True  # Handled by polling in PMTMeasureApplet
        elif category == "SECULAR_SWEEP_COMPLETE":
            self._handle_secular_sweep_complete(packet)
            return True
        elif category == "CAM_SWEEP_COMPLETE":
            self._handle_cam_sweep_complete(packet)
            return True
        elif category == "HEARTBEAT":
            return True
        
        return False
    
    def _handle_sweep_complete(self, packet: Dict[str, Any]):
        """Handle sweep completion."""
        exp_id = packet.get("exp_id")
        payload = packet.get("payload", {})
        
        self.log_info(f"ARTIQ finished sweep for exp {exp_id}")
        
        # Update experiment context
        if exp_id and self.current_exp and self.current_exp.exp_id == exp_id:
            self.current_exp.transition_to("analysis")
            self.current_exp.add_result("artiq_sweep", payload)
        
        # Remove from pending
        self._pending_sweeps.discard(exp_id)
        
        # Trigger callback if registered
        if exp_id in self._sweep_callbacks:
            try:
                self._sweep_callbacks[exp_id](packet)
            except Exception as e:
                self.log_error(f"Sweep callback error: {e}")
    
    def _handle_secular_sweep_complete(self, packet: Dict[str, Any]):
        """Handle secular sweep completion."""
        exp_id = packet.get("exp_id")
        self._pending_sweeps.discard(exp_id)
        self.log_info(f"Secular sweep complete for exp {exp_id}")
    
    def _handle_cam_sweep_complete(self, packet: Dict[str, Any]):
        """Handle camera sweep completion."""
        exp_id = packet.get("exp_id")
        self._pending_sweeps.discard(exp_id)
        self.log_info(f"Camera sweep complete for exp {exp_id}")
    
    def register_sweep_callback(self, exp_id: str, callback: callable):
        """Register a callback for sweep completion."""
        self._sweep_callbacks[exp_id] = callback
    
    def unregister_sweep_callback(self, exp_id: str):
        """Unregister a sweep callback."""
        self._sweep_callbacks.pop(exp_id, None)


class LabVIEWFragment(BaseFragment):
    """
    Fragment for LabVIEW/SMILE communication.
    
    Handles:
    - RF voltage control
    - Piezo voltage control
    - Toggle control (oven, B-field, etc.)
    - DDS frequency
    - Pressure monitoring
    """
    
    NAME = "labview"
    PRIORITY = FragmentPriority.HIGH
    
    def _do_initialize(self):
        """Initialize LabVIEW interface."""
        # Import here to avoid circular dependencies
        try:
            from ..labview_interface import LabVIEWInterface
            self._interface = LabVIEWInterface()
            self._available = True
        except ImportError:
            self._interface = None
            self._available = False
            self.log_info("LabVIEW interface not available")
            return
        
        # Check if enabled in config
        enabled = self.config.get('labview.enabled', True)
        if not enabled:
            self.log_info("LabVIEW interface disabled in config")
            self._available = False
            return
        
        # Start interface
        self._interface.start()
        
        # Try initial connection
        if self._interface.connect():
            self.log_info(f"Connected to LabVIEW at {self._interface.host}:{self._interface.port}")
        else:
            self.log_warning(f"LabVIEW not available at {self._interface.host}:{self._interface.port}")
    
    def _do_shutdown(self):
        """Shutdown LabVIEW interface."""
        if self._interface:
            self._interface.stop()
    
    @property
    def is_connected(self) -> bool:
        """True if LabVIEW is connected."""
        return self._available and self._interface and self._interface.is_connected()
    
    @property
    def interface(self):
        """Access to LabVIEW interface."""
        return self._interface
    
    # ----------------------------------------------------------------------
    # Device Control
    # ----------------------------------------------------------------------
    
    def set_rf_voltage(self, u_rf_volts: float) -> bool:
        """
        Set RF voltage via LabVIEW.
        
        Args:
            u_rf_volts: RF voltage in volts (0-200V)
            
        Returns:
            True if successful
        """
        if not self.is_connected:
            return False
        
        # Convert U_RF volts to u_rf millivolts
        from core import U_RF_V_to_u_rf_mv
        u_rf_mv = U_RF_V_to_u_rf_mv(u_rf_volts)
        
        success = self._interface.set_rf_voltage(u_rf_mv)
        if not success:
            self.log_warning("Failed to set RF voltage in LabVIEW")
        return success
    
    def set_piezo_voltage(self, voltage: float) -> bool:
        """Set piezo voltage via LabVIEW."""
        if not self.is_connected:
            return False
        
        success = self._interface.set_piezo_voltage(voltage)
        if not success:
            self.log_warning("Failed to set piezo voltage in LabVIEW")
        return success
    
    def set_be_oven(self, state: bool) -> bool:
        """Set Be oven state via LabVIEW."""
        if not self.is_connected:
            return False
        return self._interface.set_be_oven(1 if state else 0)
    
    def set_b_field(self, state: bool) -> bool:
        """Set B-field state via LabVIEW."""
        if not self.is_connected:
            return False
        return self._interface.set_b_field(1 if state else 0)
    
    def set_bephi(self, state: bool) -> bool:
        """Set BEPHI state via LabVIEW."""
        if not self.is_connected:
            return False
        return self._interface.set_bephi(1 if state else 0)
    
    def set_uv3(self, state: bool) -> bool:
        """Set UV3 state via LabVIEW."""
        if not self.is_connected:
            return False
        return self._interface.set_uv3(1 if state else 0)
    
    def set_e_gun(self, state: bool) -> bool:
        """Set e-gun state via LabVIEW."""
        if not self.is_connected:
            return False
        return self._interface.set_e_gun(1 if state else 0)
    
    def set_hd_valve(self, state: bool) -> bool:
        """Set HD valve state via LabVIEW."""
        if not self.is_connected:
            return False
        return self._interface.set_hd_valve(1 if state else 0)
    
    def set_dds_frequency(self, freq_mhz: float) -> bool:
        """Set DDS frequency via LabVIEW."""
        if not self.is_connected:
            return False
        return self._interface.set_dds_frequency(freq_mhz)
    
    def apply_safety_defaults(self) -> Dict[str, bool]:
        """Apply safety defaults to all LabVIEW devices."""
        if not self.is_connected:
            return {}
        
        return self._interface.apply_safety_defaults()
    
    def get_status(self) -> Dict[str, Any]:
        """Get LabVIEW interface status."""
        if not self._interface:
            return {"available": False}
        
        return {
            "available": self._available,
            "connected": self.is_connected,
            "host": self._interface.host if self._interface else None,
            "port": self._interface.port if self._interface else None,
        }


class CameraFragment(BaseFragment):
    """
    Fragment for camera control.
    
    Handles:
    - Starting/stopping recording
    - TTL trigger coordination
    - Status monitoring
    """
    
    NAME = "camera"
    PRIORITY = FragmentPriority.HIGH
    
    def _do_initialize(self):
        """Initialize camera interface."""
        self._host = self.config.get('services.camera.host', '127.0.0.1')
        self._port = self.config.get('services.camera.port', 5558)
        self._timeout = 5.0
        self._is_recording = False
        self._lock = threading.RLock()
        
        # Test connection
        status = self.get_status()
        if status["connected"]:
            self.log_info("Camera server connection verified")
            
            # Auto-start if configured
            if self.config.get('services.camera.auto_start', False):
                self.start_recording(mode='inf')
        else:
            self.log_warning("Camera server not available (will retry on demand)")
    
    def _do_shutdown(self):
        """Stop camera recording."""
        if self._is_recording:
            self.stop_recording()
    
    def _send_command(self, command: str) -> Tuple[bool, str]:
        """Send command to camera server."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self._timeout)
                s.connect((self._host, self._port))
                s.sendall(command.encode() + b'\n')
                response = s.recv(1024).decode().strip()
                
                if response.startswith("OK:"):
                    return True, response
                else:
                    return False, response
                    
        except socket.timeout:
            self.log_error("Camera server timeout")
            return False, "Timeout"
        except ConnectionRefusedError:
            self.log_error(f"Camera server not available at {self._host}:{self._port}")
            return False, "Connection refused"
        except Exception as e:
            self.log_error(f"Camera communication error: {e}")
            return False, str(e)
    
    def start_recording(self, mode: str = "inf", exp_id: Optional[str] = None) -> bool:
        """Start camera recording."""
        with self._lock:
            if mode == "inf":
                success, msg = self._send_command("START_INF")
            else:
                success, msg = self._send_command("START")
            
            if success:
                self._is_recording = True
                self.log_info(f"Camera recording started ({mode} mode)")
                
                if exp_id:
                    self._send_command(f"EXP_ID:{exp_id}")
            else:
                self.log_error(f"Failed to start camera: {msg}")
            
            return success
    
    def stop_recording(self) -> bool:
        """Stop camera recording."""
        with self._lock:
            success, msg = self._send_command("STOP")
            
            if success:
                self._is_recording = False
                self.log_info("Camera recording stopped")
            else:
                self.log_error(f"Failed to stop camera: {msg}")
            
            return success
    
    def get_status(self) -> Dict[str, Any]:
        """Get camera status."""
        success, msg = self._send_command("STATUS")
        
        with self._lock:
            return {
                "connected": success,
                "recording": self._is_recording,
                "status_message": msg if success else "Unknown",
                "server": f"{self._host}:{self._port}"
            }
    
    @property
    def is_recording(self) -> bool:
        """True if camera is recording."""
        return self._is_recording


class WavemeterFragment(BaseFragment):
    """
    Fragment for wavemeter frequency data collection via TCP broadcast.
    
    Connects to HighFinesse/Angstrom WS7 Wavemeter LabVIEW server.
    Receives labeled data stream on TCP port 1790.
    
    Protocol:
    - Data is sent as labeled text with headers like "ws7.frequency", "ws7.temperature"
    - Frequency values follow "ws7.frequency" header in THz (e.g., "239.34912548655052")
    - Channel ID follows "ws7.switch.channelId" as binary double
    - Temperature (~27°C) and Pressure (~985 mBar) are filtered out
    
    Display:
    - Frequency is converted from THz to GHz (x1000)
    - Displayed with 1 MHz precision (3 decimal places in GHz)
    - Example: 239.349125 THz -> 239349.125 GHz
    
    Usage:
        wavemeter = mgr.fragments["wavemeter"]
        reading = wavemeter.get_current_reading()
        print(f"Frequency: {reading['frequency_ghz']:.3f} GHz")
    """
    
    NAME = "wavemeter"
    PRIORITY = FragmentPriority.BACKGROUND
    
    # Frequency filtering ranges (in THz)
    FUNDAMENTAL_RANGE = (200, 260)  # Fundamental range ~239 THz
    TEMP_RANGE = (20, 35)           # Temperature ~27°C (filter out)
    PRESSURE_RANGE = (900, 1100)    # Pressure ~985 mBar (filter out)
    
    def _do_initialize(self):
        """Initialize wavemeter TCP client."""
        enabled = self.config.get('wavemeter.enabled', True)
        if not enabled:
            self.log_info("Wavemeter interface disabled in config")
            self._enabled = False
            return
        
        self._enabled = True
        self._host = self.config.get('wavemeter.host', '134.99.120.141')
        self._port = self.config.get('wavemeter.port', 1790)
        self._timeout = 5.0
        self._reconnect_delay = 3.0
        
        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # Current readings
        self._current_channel = 1
        self._frequency_thz = 0.0
        self._frequency_ghz = 0.0
        self._last_update_time: Optional[float] = None
        self._reading_count = 0
        
        # Statistics
        self._stats = {
            "connections": 0,
            "readings": 0,
            "errors": 0,
            "start_time": None
        }
        
        # Regex to match floating point numbers
        self._number_pattern = re.compile(r'(\d+\.\d+)')
        
        # Start data collection
        self._start()
        
        self.log_info(f"Wavemeter initialized ({self._host}:{self._port})")
    
    def _do_shutdown(self):
        """Shutdown wavemeter data collection."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.log_info("Wavemeter stopped")
    
    def _start(self):
        """Start the wavemeter data collection thread."""
        if not self._enabled or self._running:
            return
        
        self._running = True
        self._stats["start_time"] = time.time()
        self._thread = threading.Thread(
            target=self._data_collection_loop,
            daemon=True,
            name="WavemeterFragment"
        )
        self._thread.start()
        self.log_info("Wavemeter data collection started")
    
    def _data_collection_loop(self):
        """Main data collection loop - connects and reads wavemeter data."""
        while self._running:
            try:
                self._connect_and_read()
            except Exception as e:
                self.log_error(f"Wavemeter connection error: {e}")
                self._stats["errors"] += 1
            
            if self._running:
                self.log_warning(f"Reconnecting in {self._reconnect_delay}s...")
                time.sleep(self._reconnect_delay)
    
    def _connect_and_read(self):
        """Connect to wavemeter and read data stream."""
        self.log_info(f"Connecting to wavemeter at {self._host}:{self._port}")
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(self._timeout)
            s.connect((self._host, self._port))
            
            self._connected = True
            self._stats["connections"] += 1
            self.log_info("Connected to wavemeter!")
            
            stream_buffer = ""  # Text buffer for decoded data
            
            while self._running:
                try:
                    # Receive data chunk
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    
                    # Decode bytes to string (ignore errors for binary data)
                    text_chunk = chunk.decode('utf-8', errors='ignore')
                    stream_buffer += text_chunk
                    
                    # Process buffer for frequency data
                    stream_buffer = self._process_stream(stream_buffer)
                    
                    # Keep buffer small (keep last 200 chars for split numbers)
                    if len(stream_buffer) > 1000:
                        stream_buffer = stream_buffer[-200:]
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    self.log_error(f"Read error: {e}")
                    self._stats["errors"] += 1
                    break
        
        self._connected = False
        self.log_warning("Wavemeter connection closed")
    
    def _process_stream(self, buffer: str) -> str:
        """
        Process text stream for wavemeter data.
        
        Looks for "ws7.frequency" followed by a number in THz.
        Filters out temperature and pressure readings.
        
        Args:
            buffer: Current text buffer
            
        Returns:
            Updated buffer
        """
        # Check for frequency header
        freq_idx = buffer.find("ws7.frequency")
        if freq_idx == -1:
            return buffer
        
        # Look for numbers after the frequency header
        search_area = buffer[freq_idx:freq_idx + 100]
        matches = self._number_pattern.findall(search_area)
        
        for m in matches:
            try:
                val_thz = float(m)
                
                # Filter: Only accept fundamental range (~239 THz)
                # This automatically rejects Temperature (~27) and Pressure (~985)
                if self.FUNDAMENTAL_RANGE[0] < val_thz < self.FUNDAMENTAL_RANGE[1]:
                    # Valid frequency reading
                    freq_ghz = val_thz * 1000.0  # Convert THz to GHz
                    self._store_reading(freq_ghz, val_thz)
                    
                    # Clear processed data from buffer
                    end_idx = buffer.find(m, freq_idx) + len(m)
                    return buffer[end_idx:]
                
                # Filter out temperature and pressure
                elif self.TEMP_RANGE[0] < val_thz < self.TEMP_RANGE[1]:
                    continue  # Temperature, skip
                elif self.PRESSURE_RANGE[0] < val_thz < self.PRESSURE_RANGE[1]:
                    continue  # Pressure, skip
                    
            except ValueError:
                continue
        
        # Clear processed header from buffer
        return buffer[freq_idx + len("ws7.frequency"):]
    
    def _store_reading(self, freq_ghz: float, raw_thz: float):
        """
        Store a valid frequency reading.
        
        Args:
            freq_ghz: Frequency in GHz (display value)
            raw_thz: Raw frequency in THz
        """
        timestamp = time.time()
        
        with self._lock:
            self._frequency_ghz = freq_ghz
            self._frequency_thz = raw_thz
            self._last_update_time = timestamp
            self._reading_count += 1
            self._stats["readings"] += 1
        
        # Store in telemetry if available
        try:
            from ..data_server import store_data_point, update_data_source
            store_data_point("laser_freq", freq_ghz, timestamp)
            update_data_source("wavemeter", timestamp)
        except ImportError:
            pass
        
        # Log periodically (every 5 seconds)
        if int(timestamp) % 5 == 0:
            # Display with 1 MHz precision (3 decimal places in GHz)
            self.log_debug(f"Laser: {freq_ghz:.3f} GHz ({raw_thz:.6f} THz)")
    
    def get_current_reading(self) -> Dict[str, Any]:
        """
        Get the current frequency reading.
        
        Returns:
            Dictionary with:
            - channel: Current channel number
            - frequency_ghz: Frequency in GHz (for display, 1 MHz precision)
            - frequency_thz: Raw frequency in THz
            - last_update: Timestamp of last reading
            - connected: Connection status
            - reading_count: Total readings received
        """
        with self._lock:
            return {
                "channel": self._current_channel,
                "frequency_ghz": self._frequency_ghz,
                "frequency_thz": self._frequency_thz,
                "last_update": self._last_update_time,
                "connected": self._connected,
                "reading_count": self._reading_count
            }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get wavemeter status.
        
        Returns:
            Dictionary with status information
        """
        with self._lock:
            uptime = time.time() - self._stats["start_time"] if self._stats["start_time"] else 0
            return {
                "enabled": self._enabled,
                "connected": self._connected,
                "running": self._running,
                "server": f"{self._host}:{self._port}",
                "current_channel": self._current_channel,
                "frequency_ghz": self._frequency_ghz,
                "frequency_thz": self._frequency_thz,
                "last_update": self._last_update_time,
                "reading_count": self._reading_count,
                "stats": self._stats.copy(),
                "uptime_seconds": uptime
            }
    
    @property
    def is_connected(self) -> bool:
        """True if wavemeter is connected."""
        return self._connected
