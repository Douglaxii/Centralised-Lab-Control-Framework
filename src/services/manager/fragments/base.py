"""
Base Fragment - Abstract base class for all manager fragments.

Provides the common interface and lifecycle management for fragments.
"""

import logging
import threading
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ..manager import ControlManager


class FragmentPriority(IntEnum):
    """Priority levels for fragment initialization and shutdown."""
    CRITICAL = 0    # Safety, must be first
    HIGH = 1        # Core hardware interfaces
    MEDIUM = 2      # Services
    LOW = 3         # Optional features
    BACKGROUND = 4  # Telemetry, monitoring


class BaseFragment(ABC):
    """
    Abstract base class for all ControlManager fragments.
    
    Fragments are modular components that handle specific functionality:
    - Hardware interfaces (ARTIQ, LabVIEW, Camera)
    - Services (Optimizer)
    - Applets (AutoComp, CamSweep, etc.)
    - Safety (Kill switches)
    - Data (Telemetry)
    
    Lifecycle:
        1. __init__() - Store manager reference, create logger
        2. initialize() - Setup resources, start threads
        3. run() - Main loop (if needed)
        4. shutdown() - Cleanup resources
    
    Example:
        class MyFragment(BaseFragment):
            PRIORITY = FragmentPriority.MEDIUM
            
            def initialize(self):
                self.data = {}
                
            def handle_request(self, action: str, params: dict) -> dict:
                if action == "MY_ACTION":
                    return {"status": "success"}
                return None  # Not handled
                
            def shutdown(self):
                self.data.clear()
    """
    
    # Fragment metadata (override in subclasses)
    NAME: str = "base"
    PRIORITY: FragmentPriority = FragmentPriority.MEDIUM
    DEPENDENCIES: list = []  # List of fragment names this fragment depends on
    
    def __init__(self, manager: 'ControlManager'):
        """
        Initialize fragment.
        
        Args:
            manager: Reference to the ControlManager instance
        """
        self.manager = manager
        self.logger = logging.getLogger(f"fragment.{self.NAME}")
        self._initialized = False
        self._running = False
        self._lock = threading.RLock()
        
        # Fragment state
        self._state: Dict[str, Any] = {}
    
    # ======================================================================
    # Lifecycle Methods
    # ======================================================================
    
    def initialize(self):
        """
        Initialize fragment resources.
        
        Called by ControlManager after all fragments are created.
        Override to setup resources, connect to hardware, etc.
        """
        with self._lock:
            if self._initialized:
                return
            
            self.logger.info(f"Initializing {self.NAME} fragment")
            self._do_initialize()
            self._initialized = True
            self._running = True
    
    @abstractmethod
    def _do_initialize(self):
        """
        Actual initialization logic. Override in subclasses.
        """
        pass
    
    def shutdown(self):
        """
        Shutdown fragment and cleanup resources.
        
        Called by ControlManager during shutdown.
        Override to cleanup resources, close connections, etc.
        """
        with self._lock:
            if not self._initialized:
                return
            
            self.logger.info(f"Shutting down {self.NAME} fragment")
            self._do_shutdown()
            self._running = False
            self._initialized = False
    
    def _do_shutdown(self):
        """
        Actual shutdown logic. Override in subclasses.
        """
        pass
    
    # ======================================================================
    # Request Handling
    # ======================================================================
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle a request from the main manager.
        
        Args:
            action: The action to handle (e.g., "SET", "GET", "SWEEP")
            request: Full request dictionary
            
        Returns:
            Response dictionary if handled, None if not handled
            
        Override to handle specific actions.
        """
        return None
    
    def handle_data(self, packet: Dict[str, Any]) -> bool:
        """
        Handle data packet from worker.
        
        Args:
            packet: Data packet from worker
            
        Returns:
            True if packet was handled, False otherwise
            
        Override to process worker data.
        """
        return False
    
    # ======================================================================
    # State Management
    # ======================================================================
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get current fragment state.
        
        Returns:
            Dictionary with fragment state information
        """
        with self._lock:
            return {
                "name": self.NAME,
                "initialized": self._initialized,
                "running": self._running,
                "state": self._state.copy()
            }
    
    def set_state(self, key: str, value: Any):
        """Set a state value."""
        with self._lock:
            self._state[key] = value
    
    def get_state_value(self, key: str, default: Any = None) -> Any:
        """Get a state value."""
        with self._lock:
            return self._state.get(key, default)
    
    # ======================================================================
    # Properties
    # ======================================================================
    
    @property
    def is_initialized(self) -> bool:
        """True if fragment is initialized."""
        return self._initialized
    
    @property
    def is_running(self) -> bool:
        """True if fragment is running."""
        return self._running
    
    @property
    def config(self):
        """Access to manager configuration."""
        return self.manager.config
    
    @property
    def params(self) -> Dict[str, Any]:
        """Access to manager parameter state."""
        return self.manager.params
    
    @property
    def zmq_context(self):
        """Access to ZMQ context."""
        return self.manager.ctx
    
    @property
    def pub_socket(self):
        """Access to publish socket for sending commands."""
        return self.manager.pub_socket
    
    @property
    def pull_socket(self):
        """Access to pull socket for receiving data."""
        return self.manager.pull_socket
    
    @property
    def current_exp(self):
        """Access to current experiment."""
        return self.manager.current_exp
    
    # ======================================================================
    # Helper Methods
    # ======================================================================
    
    def publish_command(self, target: str, msg: Dict[str, Any]):
        """
        Publish a command to workers.
        
        Args:
            target: Target worker ("ALL", "ARTIQ", etc.)
            msg: Message dictionary
        """
        if self.pub_socket:
            self.pub_socket.send_string(target, flags=0x20000)  # zmq.SNDMORE
            self.pub_socket.send_json(msg)
    
    def log_debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)
    
    def log_info(self, message: str):
        """Log info message."""
        self.logger.info(message)
    
    def log_warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
    
    def log_error(self, message: str):
        """Log error message."""
        self.logger.error(message)
