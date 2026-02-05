"""
MLS Source - Server-side Python code.

This package contains all Python code that runs on the server PC.

Structure:
    core/       - Shared utilities (config, logging, exceptions)
    services/   - All services (manager, api, camera, optimizer, applet, comms)
    analysis/   - Analysis modules
    launcher.py - Main entry point

Usage:
    # Start all services
    python -m src.launcher
    
    # Start specific service
    python -m src.launcher --services manager
    
    # Import in code
    from src.core import get_config
    from src.services import ControlManager
"""

__version__ = "2.0.0"
