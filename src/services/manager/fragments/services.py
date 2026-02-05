"""
Service Fragments

Fragments for managing services:
- OptimizerFragment: Bayesian optimization coordination
"""

import threading
import time
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from .base import BaseFragment, FragmentPriority


@dataclass
class OptimizerState:
    """State tracking for optimizer."""
    status: str = "IDLE"  # IDLE, RUNNING, STOPPED
    current_iteration: int = 0
    convergence_delta: float = 0.0
    target_parameter: Optional[str] = None
    start_time: Optional[float] = None
    last_update: Optional[float] = None
    error_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "iteration": self.current_iteration,
            "convergence_delta": self.convergence_delta,
            "target_parameter": self.target_parameter,
            "runtime_seconds": time.time() - self.start_time if self.start_time else 0
        }


class OptimizerFragment(BaseFragment):
    """
    Fragment for Bayesian optimization coordination.
    
    Handles:
    - Starting/stopping optimization
    - Getting parameter suggestions
    - Registering measurement results
    - Tracking optimization state
    """
    
    NAME = "optimizer"
    PRIORITY = FragmentPriority.MEDIUM
    
    def _do_initialize(self):
        """Initialize optimizer controller."""
        # Import here to avoid circular dependencies
        try:
            from ..optimizer_controller import OptimizerController
            self._controller = OptimizerController(control_manager=self.manager)
            self._available = True
            self.log_info("Optimizer controller initialized")
        except ImportError:
            self._controller = None
            self._available = False
            self.log_info("Optimizer controller not available")
            return
        
        self._state = OptimizerState()
        self._state_lock = threading.Lock()
    
    def _do_shutdown(self):
        """Shutdown optimizer."""
        if self._controller and self._controller.is_running():
            self._controller.stop()
    
    @property
    def is_available(self) -> bool:
        """True if optimizer is available."""
        return self._available
    
    @property
    def is_running(self) -> bool:
        """True if optimizer is running."""
        return self._controller and self._controller.is_running()
    
    # ----------------------------------------------------------------------
    # Control Methods
    # ----------------------------------------------------------------------
    
    def start(self, **config) -> bool:
        """
        Start optimization.
        
        Args:
            **config: Configuration parameters
                - target_be_count: Target number of Be+ ions
                - target_hd_present: Whether HD+ should be present
                - max_iterations: Maximum optimization iterations
        
        Returns:
            True if started successfully
        """
        if not self._available:
            self.log_error("Optimizer not available")
            return False
        
        if self._controller.is_running():
            self.log_warning("Optimizer already running")
            return False
        
        try:
            success = self._controller.start(**config)
            if success:
                with self._state_lock:
                    self._state.status = "RUNNING"
                    self._state.start_time = time.time()
                    self._state.current_iteration = 0
                self.log_info(f"Optimization started: {config}")
            return success
        except Exception as e:
            self.log_error(f"Failed to start optimization: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop optimization."""
        if not self._available:
            return False
        
        success = self._controller.stop()
        if success:
            with self._state_lock:
                self._state.status = "STOPPED"
            self.log_info("Optimization stopped")
        return success
    
    def reset(self) -> bool:
        """Reset optimizer state."""
        if not self._available:
            return False
        
        success = self._controller.reset()
        if success:
            with self._state_lock:
                self._state = OptimizerState()
            self.log_info("Optimizer reset")
        return success
    
    # ----------------------------------------------------------------------
    # Suggestion/Result Methods
    # ----------------------------------------------------------------------
    
    def get_next_suggestion(self) -> Optional[Dict[str, Any]]:
        """
        Get next parameter suggestion from optimizer.
        
        Returns:
            Dictionary with suggested parameters, or None if not available
        """
        if not self._available or not self._controller.is_running():
            return None
        
        suggestion = self._controller.get_next_suggestion()
        
        if suggestion:
            with self._state_lock:
                self._state.current_iteration = self._controller.iteration
        
        return suggestion
    
    def register_result(self, measurements: Dict[str, Any]) -> 'OptimizerState':
        """
        Register measurement results with optimizer.
        
        Args:
            measurements: Dictionary of measurement results
                - ion_count: Number of ions detected
                - secular_freq: Secular frequency
                etc.
        
        Returns:
            Current optimizer state
        """
        if not self._available:
            return self._state
        
        status = self._controller.register_result(measurements)
        
        with self._state_lock:
            self._state.current_iteration = status.iteration
            self._state.convergence_delta = getattr(status, 'convergence_delta', 0.0)
        
        return self._state
    
    def has_suggestion_pending(self) -> bool:
        """True if waiting for result from current suggestion."""
        if not self._available:
            return False
        return self._controller.has_suggestion_pending()
    
    # ----------------------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------------------
    
    def get_config(self) -> Dict[str, Any]:
        """Get optimizer configuration."""
        if not self._available:
            return {}
        
        config = self._controller.config
        return {
            "target_be_count": config.target_be_count,
            "target_hd_present": config.target_hd_present,
            "max_iterations": config.max_iterations,
            "convergence_threshold": config.convergence_threshold,
            "n_initial_points": config.n_initial_points,
        }
    
    def update_config(self, updates: Dict[str, Any]):
        """Update optimizer configuration."""
        if not self._available:
            return
        
        for key, value in updates.items():
            if hasattr(self._controller.config, key):
                setattr(self._controller.config, key, value)
        
        self.log_info(f"Configuration updated: {updates}")
    
    # ----------------------------------------------------------------------
    # Request Handling
    # ----------------------------------------------------------------------
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle optimizer-related requests."""
        handlers = {
            "OPTIMIZE_START": self._handle_optimize_start,
            "OPTIMIZE_STOP": self._handle_optimize_stop,
            "OPTIMIZE_RESET": self._handle_optimize_reset,
            "OPTIMIZE_STATUS": self._handle_optimize_status,
            "OPTIMIZE_SUGGESTION": self._handle_optimize_suggestion,
            "OPTIMIZE_RESULT": self._handle_optimize_result,
            "OPTIMIZE_CONFIG": self._handle_optimize_config,
        }
        
        handler = handlers.get(action)
        if handler:
            return handler(request)
        
        return None
    
    def _handle_optimize_start(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_START request."""
        if not self._available:
            return {"status": "error", "message": "Optimizer not available"}
        
        # Check mode
        from core import SystemMode
        if self.manager.mode != SystemMode.AUTO:
            return {
                "status": "rejected",
                "reason": f"System must be in AUTO mode (currently {self.manager.mode.value})"
            }
        
        # Extract config from request
        config = {k: v for k, v in req.items() if k not in ['action', 'source', 'exp_id']}
        
        success = self.start(**config)
        
        if success:
            return {
                "status": "success",
                "message": "Optimization started",
                "config": config
            }
        else:
            return {"status": "error", "message": "Failed to start optimization"}
    
    def _handle_optimize_stop(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_STOP request."""
        success = self.stop()
        return {
            "status": "success" if success else "error",
            "message": "Optimization stopped" if success else "Not running"
        }
    
    def _handle_optimize_reset(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_RESET request."""
        success = self.reset()
        return {
            "status": "success" if success else "error",
            "message": "Optimizer reset" if success else "Failed"
        }
    
    def _handle_optimize_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_STATUS request."""
        if not self._available:
            return {"status": "error", "message": "Optimizer not available"}
        
        with self._state_lock:
            state_dict = self._state.to_dict()
        
        return {
            "status": "success",
            "data": state_dict
        }
    
    def _handle_optimize_suggestion(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_SUGGESTION request."""
        if not self._available:
            return {"status": "error", "message": "Optimizer not available"}
        
        suggestion = self.get_next_suggestion()
        
        if suggestion is None:
            return {
                "status": "no_suggestion",
                "message": "No suggestion available"
            }
        
        return {
            "status": "success",
            "data": suggestion
        }
    
    def _handle_optimize_result(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_RESULT request."""
        if not self._available:
            return {"status": "error", "message": "Optimizer not available"}
        
        measurements = req.get("measurements", {})
        
        if not measurements:
            return {"status": "error", "message": "No measurements provided"}
        
        state = self.register_result(measurements)
        
        return {
            "status": "success",
            "data": state.to_dict()
        }
    
    def _handle_optimize_config(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Handle OPTIMIZE_CONFIG request."""
        if not self._available:
            return {"status": "error", "message": "Optimizer not available"}
        
        method = req.get("method", "GET")
        
        if method == "GET":
            return {
                "status": "success",
                "data": self.get_config()
            }
        else:  # POST
            config_updates = req.get("config", {})
            self.update_config(config_updates)
            return {
                "status": "success",
                "message": "Configuration updated"
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Get fragment status."""
        return {
            "available": self._available,
            "running": self.is_running,
            "state": self._state.to_dict()
        }
