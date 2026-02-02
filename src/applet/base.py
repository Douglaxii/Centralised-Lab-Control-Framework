"""
Base class for experimental scripts.

Provides common functionality for:
- Status tracking
- Progress reporting
- Data logging
- Hardware control via ZMQ
"""

import threading
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import json
from pathlib import Path

import zmq


class ExperimentStatus(Enum):
    """Experiment execution states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class ExperimentResult:
    """Container for experiment results."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class BaseExperiment(ABC):
    """
    Abstract base class for all experimental scripts.
    
    Features:
    - Asynchronous execution in separate thread
    - Real-time progress updates
    - Data logging to JSON
    - ZMQ communication with ControlManager
    - Safe stop/pause/resume
    
    Usage:
        class MyExperiment(BaseExperiment):
            def run(self):
                self.set_status(ExperimentStatus.RUNNING)
                # ... experiment logic ...
                self.record_data("key", value)
                self.set_progress(50)
                # ...
                return ExperimentResult(success=True, data=self.data)
    """
    
    def __init__(
        self,
        name: str,
        manager_host: str = "localhost",
        manager_port: int = 5557,
        data_dir: str = "data/experiments"
    ):
        self.name = name
        self.manager_host = manager_host
        self.manager_port = manager_port
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Status and progress
        self._status = ExperimentStatus.IDLE
        self._progress = 0.0  # 0-100
        self._status_lock = threading.RLock()
        
        # Data storage
        self.data: Dict[str, Any] = {}
        self._data_lock = threading.RLock()
        
        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        
        # ZMQ
        self._zmq_context: Optional[zmq.Context] = None
        self._zmq_socket: Optional[zmq.Socket] = None
        self._zmq_lock = threading.Lock()
        
        # Callbacks
        self._progress_callbacks: List[Callable[[float], None]] = []
        self._status_callbacks: List[Callable[[ExperimentStatus], None]] = []
        
        # Logger
        self.logger = logging.getLogger(f"experiment.{name}")
        
        # Result
        self._result: Optional[ExperimentResult] = None
    
    # ==================== Status & Progress ====================
    
    @property
    def status(self) -> ExperimentStatus:
        """Get current experiment status."""
        with self._status_lock:
            return self._status
    
    def set_status(self, status: ExperimentStatus):
        """Set experiment status and notify callbacks."""
        with self._status_lock:
            old_status = self._status
            self._status = status
            self.logger.info(f"Status: {old_status.value} -> {status.value}")
        
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception as e:
                self.logger.error(f"Status callback error: {e}")
    
    @property
    def progress(self) -> float:
        """Get current progress (0-100)."""
        with self._status_lock:
            return self._progress
    
    def set_progress(self, progress: float):
        """Set progress (0-100) and notify callbacks."""
        progress = max(0.0, min(100.0, progress))
        with self._status_lock:
            self._progress = progress
        
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                self.logger.error(f"Progress callback error: {e}")
    
    def add_progress_callback(self, callback: Callable[[float], None]):
        """Add callback for progress updates."""
        self._progress_callbacks.append(callback)
    
    def add_status_callback(self, callback: Callable[[ExperimentStatus], None]):
        """Add callback for status updates."""
        self._status_callbacks.append(callback)
    
    # ==================== Data Management ====================
    
    def record_data(self, key: str, value: Any):
        """Record experimental data."""
        with self._data_lock:
            self.data[key] = value
        self.logger.debug(f"Recorded data: {key} = {value}")
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """Get recorded data."""
        with self._data_lock:
            return self.data.get(key, default)
    
    def save_data(self, filename: Optional[str] = None):
        """Save data to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.name}_{timestamp}.json"
        
        filepath = self.data_dir / filename
        
        with self._data_lock:
            data_to_save = {
                "experiment_name": self.name,
                "timestamp": datetime.now().isoformat(),
                "status": self._status.value,
                "data": self.data
            }
        
        with open(filepath, 'w') as f:
            json.dump(data_to_save, f, indent=2, default=str)
        
        self.logger.info(f"Data saved to {filepath}")
        return filepath
    
    # ==================== ZMQ Communication ====================
    
    def _get_socket(self) -> zmq.Socket:
        """Get or create ZMQ socket."""
        with self._zmq_lock:
            if self._zmq_socket is None:
                self._zmq_context = zmq.Context()
                self._zmq_socket = self._zmq_context.socket(zmq.REQ)
                self._zmq_socket.connect(f"tcp://{self.manager_host}:{self.manager_port}")
                self._zmq_socket.setsockopt(zmq.RCVTIMEO, 10000)  # 10 second timeout
                self._zmq_socket.setsockopt(zmq.LINGER, 0)
                self.logger.info(f"ZMQ connected to {self.manager_host}:{self.manager_port}")
            return self._zmq_socket
    
    def send_to_manager(self, message: Dict[str, Any], timeout_ms: int = 10000) -> Dict[str, Any]:
        """
        Send request to ControlManager.
        
        Args:
            message: Request dictionary
            timeout_ms: Timeout in milliseconds
        
        Returns:
            Response dictionary
        """
        try:
            sock = self._get_socket()
            sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
            sock.send_json(message)
            return sock.recv_json()
        except zmq.Again:
            self.logger.error("Manager request timeout")
            return {"status": "error", "message": "Timeout"}
        except Exception as e:
            self.logger.error(f"Manager request failed: {e}")
            return {"status": "error", "message": str(e)}
    
    # ==================== Hardware Control Helpers ====================
    
    def set_voltage(self, device: str, value: float) -> bool:
        """Set a voltage device."""
        response = self.send_to_manager({
            "action": "SET",
            "source": f"EXPERIMENT_{self.name.upper()}",
            "params": {device: value}
        })
        success = response.get("status") == "success"
        if success:
            self.logger.debug(f"Set {device} = {value}")
        else:
            self.logger.error(f"Failed to set {device}: {response.get('message')}")
        return success
    
    def get_voltage(self, device: str) -> Optional[float]:
        """Get current voltage reading."""
        response = self.send_to_manager({
            "action": "GET",
            "source": f"EXPERIMENT_{self.name.upper()}"
        })
        if response.get("status") == "success":
            params = response.get("params", {})
            return params.get(device)
        return None
    
    def measure_pmt(self, duration_ms: float = 100.0, timeout_ms: int = 10000) -> Optional[int]:
        """
        Measure PMT counts using ARTIQ ttl0_counter gated measurement.
        
        This follows the approach used in PMT_beam_finder.py:
        - Sends PMT_MEASURE command to manager
        - Manager forwards to ARTIQ worker
        - ARTIQ opens ttl0_counter gate for specified duration
        - Returns the accumulated count
        
        Args:
            duration_ms: Gate duration in milliseconds (default: 100ms)
            timeout_ms: Maximum time to wait for response in milliseconds
        
        Returns:
            PMT count as integer, or None if measurement failed
        
        Example:
            # Measure PMT for 100ms
            counts = self.measure_pmt(duration_ms=100.0)
            if counts is not None:
                print(f"PMT counts: {counts}")
        """
        self.logger.debug(f"Requesting PMT measurement: duration={duration_ms}ms")
        
        response = self.send_to_manager({
            "action": "PMT_MEASURE",
            "source": f"EXPERIMENT_{self.name.upper()}",
            "duration_ms": duration_ms
        }, timeout_ms=timeout_ms)
        
        if response.get("status") == "success":
            counts = response.get("counts")
            if counts is not None:
                self.logger.debug(f"PMT measurement result: {counts} counts")
                return int(counts)
        
        self.logger.warning(f"PMT measurement failed: {response.get('message', 'Unknown error')}")
        return None
    
    def set_multiple_voltages(self, voltages: Dict[str, float]) -> bool:
        """Set multiple voltages at once."""
        response = self.send_to_manager({
            "action": "SET",
            "source": f"EXPERIMENT_{self.name.upper()}",
            "params": voltages
        })
        success = response.get("status") == "success"
        if success:
            self.logger.debug(f"Set voltages: {voltages}")
        return success
    
    # ==================== Control Flow ====================
    
    def check_stop(self) -> bool:
        """Check if experiment should stop."""
        return self._stop_event.is_set()
    
    def pause_point(self):
        """Check for pause request and wait if needed."""
        if self._pause_event.is_set():
            self.set_status(ExperimentStatus.PAUSED)
            while self._pause_event.is_set() and not self._stop_event.is_set():
                time.sleep(0.1)
            if not self._stop_event.is_set():
                self.set_status(ExperimentStatus.RUNNING)
    
    def sleep(self, seconds: float):
        """Sleep with stop/pause checking."""
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self.check_stop():
                return
            self.pause_point()
            time.sleep(min(0.1, end_time - time.time()))
    
    # ==================== Execution Control ====================
    
    def start(self, blocking: bool = False) -> bool:
        """
        Start the experiment.
        
        Args:
            blocking: If True, run synchronously. If False, run in thread.
        
        Returns:
            True if started successfully
        """
        if self.status == ExperimentStatus.RUNNING:
            self.logger.warning("Experiment already running")
            return False
        
        self._stop_event.clear()
        self._pause_event.clear()
        self._result = None
        
        # Clear old data
        with self._data_lock:
            self.data = {}
        
        if blocking:
            self._run()
        else:
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name=f"Experiment_{self.name}"
            )
            self._thread.start()
        
        return True
    
    def _run(self):
        """Internal run wrapper."""
        try:
            self.logger.info(f"Starting experiment: {self.name}")
            result = self.run()
            self._result = result
            
            if result.success:
                self.set_status(ExperimentStatus.COMPLETED)
                self.logger.info(f"Experiment completed: {result.message}")
            else:
                self.set_status(ExperimentStatus.ERROR)
                self.logger.error(f"Experiment failed: {result.error}")
            
            # Save data
            self.save_data()
            
        except Exception as e:
            self.logger.exception("Experiment crashed")
            self._result = ExperimentResult(
                success=False,
                error=str(e),
                message="Experiment crashed"
            )
            self.set_status(ExperimentStatus.ERROR)
    
    def stop(self):
        """Request experiment stop."""
        self.logger.info("Stop requested")
        self._stop_event.set()
        self._pause_event.clear()
    
    def pause(self):
        """Request experiment pause."""
        if self.status == ExperimentStatus.RUNNING:
            self.logger.info("Pause requested")
            self._pause_event.set()
    
    def resume(self):
        """Resume paused experiment."""
        if self.status == ExperimentStatus.PAUSED:
            self.logger.info("Resume requested")
            self._pause_event.clear()
    
    def wait(self, timeout: Optional[float] = None) -> Optional[ExperimentResult]:
        """Wait for experiment to complete."""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        return self._result
    
    @property
    def result(self) -> Optional[ExperimentResult]:
        """Get experiment result."""
        return self._result
    
    # ==================== Abstract Method ====================
    
    @abstractmethod
    def run(self) -> ExperimentResult:
        """
        Main experiment logic. Override in subclass.
        
        Must return an ExperimentResult.
        
        Use self.set_progress(), self.record_data(), self.check_stop(),
        self.pause_point(), and self.sleep() for cooperative control.
        
        Hardware control: use self.set_voltage(), self.get_voltage()
        """
        pass
    
    def cleanup(self):
        """Cleanup resources. Override if needed."""
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
