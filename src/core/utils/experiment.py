"""
Experiment tracking and context management.
Provides unique experiment IDs and propagates metadata through the system.
"""

import uuid
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict

from .config import get_config


@dataclass
class ExperimentContext:
    """
    Context object that tracks an experiment through all components.
    Passed from Manager -> ARTIQ -> Camera -> Analysis.
    """
    
    # Identification
    exp_id: str = field(default_factory=lambda: generate_exp_id())
    parent_id: Optional[str] = None  # For sub-experiments
    
    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Parameters and metadata
    parameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Status tracking
    status: str = "created"  # created, running, completed, failed, aborted
    phase: str = "init"      # init, dc_setup, cooling, sweep, camera, analysis, complete
    
    # Component tracking
    components_completed: list = field(default_factory=list)
    components_pending: list = field(default_factory=list)
    
    # Results
    results: Dict[str, Any] = field(default_factory=dict)
    errors: list = field(default_factory=list)
    
    def start(self):
        """Mark experiment as started."""
        self.started_at = time.time()
        self.status = "running"
        self.phase = "dc_setup"
    
    def complete(self, success: bool = True):
        """Mark experiment as completed."""
        self.completed_at = time.time()
        self.status = "completed" if success else "failed"
        self.phase = "complete"
    
    def abort(self, reason: str):
        """Mark experiment as aborted."""
        self.completed_at = time.time()
        self.status = "aborted"
        self.errors.append({
            "timestamp": time.time(),
            "phase": self.phase,
            "reason": reason
        })
    
    def transition_to(self, phase: str):
        """Transition to a new phase."""
        if self.phase != phase:
            self.components_completed.append(self.phase)
            self.phase = phase
    
    def add_result(self, component: str, data: Dict[str, Any]):
        """Add results from a component."""
        self.results[component] = data
        self.components_completed.append(component)
    
    def add_error(self, error: str, component: Optional[str] = None):
        """Add an error record."""
        self.errors.append({
            "timestamp": time.time(),
            "phase": self.phase,
            "component": component,
            "error": error
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def save(self, directory: Optional[str] = None):
        """
        Save experiment context to disk.
        
        Args:
            directory: Directory to save in (default: E:/Data/[date]/metadata)
        """
        if directory is None:
            config = get_config()
            date_str = datetime.now().strftime("%y%m%d")
            base_path = config.get_path('output_base')
            directory = Path(base_path) / date_str / "metadata"
        
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        
        filepath = directory / f"{self.exp_id}_context.json"
        with open(filepath, 'w') as f:
            f.write(self.to_json())
        
        return filepath
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Get experiment duration in seconds."""
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return end - self.started_at
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExperimentContext':
        """Create from dictionary."""
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ExperimentContext':
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    @classmethod
    def load(cls, filepath: str) -> 'ExperimentContext':
        """Load from file."""
        with open(filepath, 'r') as f:
            return cls.from_json(f.read())


def generate_exp_id(prefix: Optional[str] = None) -> str:
    """
    Generate a unique experiment ID.
    
    Args:
        prefix: Optional prefix (default from config)
        
    Returns:
        Unique experiment ID string
    """
    config = get_config()
    
    if prefix is None:
        prefix = config.get('experiment.id_prefix', 'EXP')
    
    # Generate short UUID (first 8 chars)
    short_uuid = uuid.uuid4().hex[:8].upper()
    
    # Add timestamp component
    timestamp = datetime.now().strftime("%H%M%S")
    
    return f"{prefix}_{timestamp}_{short_uuid}"


class ExperimentTracker:
    """
    Tracks multiple experiments and provides lookup capabilities.
    Singleton pattern for global tracking.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._experiments = {}
            cls._instance._current_exp_id = None
        return cls._instance
    
    def create_experiment(self, parameters: Optional[Dict] = None) -> ExperimentContext:
        """Create and register a new experiment."""
        exp = ExperimentContext(parameters=parameters or {})
        self._experiments[exp.exp_id] = exp
        self._current_exp_id = exp.exp_id
        return exp
    
    def get_experiment(self, exp_id: str) -> Optional[ExperimentContext]:
        """Get experiment by ID."""
        return self._experiments.get(exp_id)
    
    def get_current(self) -> Optional[ExperimentContext]:
        """Get current active experiment."""
        if self._current_exp_id:
            return self._experiments.get(self._current_exp_id)
        return None
    
    def set_current(self, exp_id: str):
        """Set current experiment ID."""
        if exp_id in self._experiments:
            self._current_exp_id = exp_id
    
    def list_experiments(self, status: Optional[str] = None) -> list:
        """List all experiments, optionally filtered by status."""
        exps = list(self._experiments.values())
        if status:
            exps = [e for e in exps if e.status == status]
        return exps
    
    def cleanup_old(self, max_age_seconds: float = 86400):
        """Remove old completed experiments from memory."""
        now = time.time()
        to_remove = []
        
        for exp_id, exp in self._experiments.items():
            if exp.status in ("completed", "failed", "aborted"):
                if exp.completed_at and (now - exp.completed_at) > max_age_seconds:
                    to_remove.append(exp_id)
        
        for exp_id in to_remove:
            del self._experiments[exp_id]


# Global tracker instance
_tracker = None


def get_tracker() -> ExperimentTracker:
    """Get the global experiment tracker."""
    global _tracker
    if _tracker is None:
        _tracker = ExperimentTracker()
    return _tracker
