"""
Hardware Interface Base Class - Plugin architecture for scalability.

New hardware can be added by implementing this interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("hardware.interface")


class HardwareInterface(ABC):
    """
    Base class for all hardware interfaces.
    
    To add new hardware:
    1. Create a class inheriting from HardwareInterface
    2. Implement all abstract methods
    3. Register in ControlManager
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.connected = False
        self.logger = logging.getLogger(f"hardware.{name}")
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to hardware. Returns True on success."""
        pass
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from hardware."""
        pass
    
    @abstractmethod
    def set_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Set hardware parameters.
        
        Returns:
            Dict with 'success': bool and optional 'error' message
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get current hardware status."""
        pass
    
    def get_telemetry(self) -> Optional[Dict[str, Any]]:
        """
        Get telemetry data (optional).
        
        Returns:
            Dict with telemetry data or None
        """
        return None
    
    def emergency_stop(self):
        """Emergency stop (optional). Override if hardware supports it."""
        self.logger.warning(f"Emergency stop not implemented for {self.name}")


class SensorInterface(ABC):
    """
    Base class for sensor interfaces.
    
    Sensors provide read-only data from hardware.
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.connected = False
        self.logger = logging.getLogger(f"sensor.{name}")
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to sensor."""
        pass
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from sensor."""
        pass
    
    @abstractmethod
    def read(self) -> Dict[str, Any]:
        """
        Read sensor data.
        
        Returns:
            Dict with sensor readings
        """
        pass
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get sensor metadata (units, range, etc.)."""
        return {
            "name": self.name,
            "units": self.config.get("units", "unknown"),
            "range": self.config.get("range", [None, None])
        }
