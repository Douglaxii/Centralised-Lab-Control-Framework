"""
MLS Services - All server-side services.

This package contains all services that run on the server PC:
    - manager: ControlManager (ZMQ coordinator)
    - api: Flask REST API (port 5000)
    - camera: Camera server (port 5558)
    - optimizer: Bayesian optimization (port 5050)
    - applet: Applet server (port 5051)
    - comms: Communications (ZMQ, TCP, LabVIEW)

Usage:
    from src.services import ControlManager
    from src.services import flask_server
"""

# Core services
from .manager.manager import ControlManager
from .api import flask_server

__all__ = [
    'ControlManager',
    'flask_server',
]
