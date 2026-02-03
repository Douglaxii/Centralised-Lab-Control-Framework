"""
Experiment Controller for the Applet Server.

Manages experiment execution and provides API endpoints.
Singleton pattern - use `controller` instance.
"""

import threading
import logging
from typing import Dict, Any, Optional, List
from dataclasses import asdict

from ..base import ExperimentStatus
from ..auto_compensation import AutoCompensationExperiment
from ..cam_sweep import CamSweepExperiment
from ..sim_calibration import SimCalibrationExperiment
from ..trap_eigenmode import TrapEigenmodeExperiment


class ExperimentController:
    """
    Singleton controller for managing experiments.
    
    Provides:
    - Experiment registry
    - Execution management
    - Status/progress tracking
    - WebSocket/SSE broadcasting
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.logger = logging.getLogger("applet.controller")
        
        # Registry of available experiments
        self._experiments: Dict[str, Any] = {
            "auto_compensation": AutoCompensationExperiment,
            "trap_eigenmode": TrapEigenmodeExperiment,
            "cam_sweep": CamSweepExperiment,
            "sim_calibration": SimCalibrationExperiment,
        }
        
        # Currently running experiment
        self._current: Optional[Any] = None
        self._current_lock = threading.RLock()
        
        # Progress callbacks (for SSE broadcasting)
        self._progress_callbacks: List[Any] = []
        self._status_callbacks: List[Any] = []
        
        self.logger.info("ExperimentController initialized")
    
    # ==================== Experiment Management ====================
    
    def list_experiments(self) -> List[Dict[str, str]]:
        """List available experiments."""
        return [
            {
                "id": key,
                "name": cls.__name__,
                "description": cls.__doc__.strip().split('\n')[0] if cls.__doc__ else ""
            }
            for key, cls in self._experiments.items()
        ]
    
    def get_experiment(self, exp_id: str) -> Optional[Any]:
        """Get experiment class by ID."""
        return self._experiments.get(exp_id)
    
    # ==================== Execution Control ====================
    
    def start(self, exp_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Start an experiment.
        
        Args:
            exp_id: Experiment identifier
            config: Optional configuration dict
        
        Returns:
            Response dict with status and message
        """
        with self._current_lock:
            # Check if experiment already running
            if self._current is not None and self._current.status == ExperimentStatus.RUNNING:
                return {
                    "status": "error",
                    "message": f"Experiment '{self._current.name}' already running"
                }
            
            # Get experiment class
            exp_class = self._experiments.get(exp_id)
            if exp_class is None:
                return {
                    "status": "error",
                    "message": f"Unknown experiment: {exp_id}"
                }
            
            # Create instance
            try:
                config = config or {}
                self._current = exp_class(**config)
                
                # Register callbacks for SSE
                self._current.add_progress_callback(self._on_progress)
                self._current.add_status_callback(self._on_status)
                
            except Exception as e:
                self.logger.error(f"Failed to create experiment: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to create experiment: {e}"
                }
            
            # Start experiment
            success = self._current.start(blocking=False)
            
            if success:
                return {
                    "status": "success",
                    "message": f"Experiment '{exp_id}' started",
                    "experiment_id": exp_id
                }
            else:
                self._current = None
                return {
                    "status": "error",
                    "message": "Failed to start experiment"
                }
    
    def stop(self) -> Dict[str, Any]:
        """Stop current experiment."""
        with self._current_lock:
            if self._current is None:
                return {"status": "error", "message": "No experiment running"}
            
            self._current.stop()
            return {
                "status": "success",
                "message": "Stop requested"
            }
    
    def pause(self) -> Dict[str, Any]:
        """Pause current experiment."""
        with self._current_lock:
            if self._current is None:
                return {"status": "error", "message": "No experiment running"}
            
            self._current.pause()
            return {
                "status": "success",
                "message": "Pause requested"
            }
    
    def resume(self) -> Dict[str, Any]:
        """Resume paused experiment."""
        with self._current_lock:
            if self._current is None:
                return {"status": "error", "message": "No experiment running"}
            
            self._current.resume()
            return {
                "status": "success",
                "message": "Resume requested"
            }
    
    # ==================== Status & Data ====================
    
    def get_status(self) -> Dict[str, Any]:
        """Get current experiment status."""
        with self._current_lock:
            if self._current is None:
                return {
                    "status": "idle",
                    "experiment": None,
                    "progress": 0,
                    "message": "No experiment running"
                }
            
            result = self._current.result
            
            return {
                "status": self._current.status.value,
                "experiment": self._current.name,
                "progress": self._current.progress,
                "data": self._current.data,
                "result": asdict(result) if result else None,
                "message": result.message if result else "Running"
            }
    
    def get_progress(self) -> float:
        """Get current progress (0-100)."""
        with self._current_lock:
            if self._current is None:
                return 0.0
            return self._current.progress
    
    # ==================== Callback Broadcasting ====================
    
    def _on_progress(self, progress: float):
        """Handle progress update."""
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                self.logger.error(f"Progress callback error: {e}")
    
    def _on_status(self, status: ExperimentStatus):
        """Handle status update."""
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception as e:
                self.logger.error(f"Status callback error: {e}")
    
    def register_progress_callback(self, callback):
        """Register callback for progress updates."""
        self._progress_callbacks.append(callback)
    
    def register_status_callback(self, callback):
        """Register callback for status updates."""
        self._status_callbacks.append(callback)


# Singleton instance
controller = ExperimentController()
