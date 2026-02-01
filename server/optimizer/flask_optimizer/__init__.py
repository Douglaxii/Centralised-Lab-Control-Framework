"""
Flask Optimizer Monitor - Web interface for Bayesian optimization.

A dedicated Flask server for monitoring and controlling the ion loading
optimization process. Runs independently from the main Flask server.

Features:
- Real-time optimization status
- Parameter viewing and editing
- Optimization history visualization
- Start/stop/control optimization phases
- Profile management
"""

from .app import create_app, OptimizerWebServer

__all__ = ['create_app', 'OptimizerWebServer']
