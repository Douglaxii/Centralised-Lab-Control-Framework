"""
Hardware interfaces for ControlManager.

To add new hardware:
1. Create a class inheriting from HardwareInterface
2. Implement connect(), disconnect(), set_parameters(), get_status()
3. Import and register in control_manager.py
"""

from core.hardware_interface import HardwareInterface, SensorInterface

__all__ = ['HardwareInterface', 'SensorInterface']
