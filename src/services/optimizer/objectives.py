"""
Objective functions for each optimization phase.

Scalable architecture supporting dynamic objectives and constraints.
New objectives can be registered via the ObjectiveRegistry.
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, List, Callable, Type
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
import logging

logger = logging.getLogger("optimizer.objectives")


class ObjectiveType(Enum):
    """Type of objective - minimize or maximize."""
    MINIMIZE = auto()
    MAXIMIZE = auto()


@dataclass
class ObjectiveConfig:
    """Configuration for an objective function."""
    name: str
    evaluator: Callable[[Dict[str, Any], Dict[str, Any]], float]
    objective_type: ObjectiveType = ObjectiveType.MINIMIZE
    weight: float = 1.0
    description: str = ""


@dataclass
class ConstraintConfig:
    """Configuration for a constraint."""
    name: str
    evaluator: Callable[[Dict[str, Any], Dict[str, Any]], float]
    threshold: float = 0.0
    constraint_type: str = "inequality"  # "inequality" or "equality"
    description: str = ""


class ObjectiveFunction(ABC):
    """Base class for objective functions."""
    
    @abstractmethod
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute scalarized cost from measurements.
        
        Args:
            params: Parameter values used
            measurements: Experimental measurements
            
        Returns:
            Tuple of (total_cost, cost_components)
        """
        pass
    
    @abstractmethod
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Check if optimization goal has been achieved."""
        pass
    
    def get_objectives(self) -> List[ObjectiveConfig]:
        """
        Get list of objective configurations for MOBO.
        Override for multi-objective phases.
        """
        return []
    
    def get_constraints(self) -> List[ConstraintConfig]:
        """
        Get list of constraint configurations for MOBO.
        Override for constrained phases.
        """
        return []


class ObjectiveRegistry:
    """
    Registry for objective functions.
    
    Allows registration of custom objectives at runtime.
    """
    
    _objectives: Dict[str, Type[ObjectiveFunction]] = {}
    
    @classmethod
    def register(cls, name: str, objective_class: Type[ObjectiveFunction]):
        """Register an objective class."""
        cls._objectives[name] = objective_class
        logger.info(f"Registered objective: {name}")
    
    @classmethod
    def create(cls, name: str, **kwargs) -> ObjectiveFunction:
        """Create an objective instance."""
        if name not in cls._objectives:
            raise ValueError(f"Unknown objective: {name}. "
                           f"Available: {list(cls._objectives.keys())}")
        return cls._objectives[name](**kwargs)
    
    @classmethod
    def list_objectives(cls) -> List[str]:
        """List all registered objectives."""
        return list(cls._objectives.keys())


# =============================================================================
# Phase I Objectives
# =============================================================================

class BeLoadingObjective(ObjectiveFunction):
    """
    Phase I-A: Be+ Loading Optimization
    
    Goal: Find optimal parameters for each ion_count [1,8]
    - Minimize PI laser duration (reduces patch potentials)
    - Achieve target ion count
    """
    
    def __init__(
        self,
        target_ion_count: int = 1,
        target_secular_freq: float = 307.0,
        w_count_match: float = -1000.0,  # Reward for correct count
        w_count_off: float = 500.0,      # Penalty per ion difference
        w_pi_duration: float = 2.0,      # Penalty per 100ms
        w_time: float = 0.1,
    ):
        self.target_ion_count = target_ion_count
        self.target_secular_freq = target_secular_freq
        self.w_count_match = w_count_match
        self.w_count_off = w_count_off
        self.w_pi_duration = w_pi_duration
        self.w_time = w_time
        
        logger.info(f"BeLoadingObjective: target={target_ion_count} ions")
    
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Measurements expected:
        - ion_count: Number of ions detected
        - total_time_ms: Total cycle time
        """
        components = {}
        
        ion_count = measurements.get("ion_count", 0)
        
        # Count-based cost (primary)
        if ion_count == self.target_ion_count:
            components["count"] = self.w_count_match  # Large reward
        else:
            components["count"] = self.w_count_off * abs(
                ion_count - self.target_ion_count
            )
        
        # PI duration penalty
        pi_duration = params.get("be_pi_laser_duration_ms", 500.0)
        components["pi_duration"] = self.w_pi_duration * (pi_duration / 100.0)
        
        # Time penalty
        total_time = measurements.get("total_time_ms", 5000.0)
        components["time"] = self.w_time * (total_time / 1000.0)
        
        total_cost = sum(components.values())
        
        logger.debug(
            f"Be+ Loading: ions={ion_count}, cost={total_cost:.2f}, "
            f"components={components}"
        )
        
        return total_cost, components
    
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Success: preferred ion number has been reached."""
        ion_count = measurements.get("ion_count", 0)
        return ion_count == self.target_ion_count


class BeEjectionObjective(ObjectiveFunction):
    """
    Phase I-B: Be+ Ejection Optimization
    
    Goal: Maximize ejection efficiency (minimize residual Be+)
    Stopping criterion: ion_count = 1 (can only measure after process)
    """
    
    def __init__(
        self,
        target_ion_count: int = 1,
        w_success: float = -1000.0,
        w_overshoot: float = 500.0,  # Penalty for emptying (N=0)
        w_time: float = 0.5,
    ):
        self.target_ion_count = target_ion_count
        self.w_success = w_success
        self.w_overshoot = w_overshoot
        self.w_time = w_time
    
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Measurements expected:
        - ion_count: Number of ions after ejection
        """
        components = {}
        
        ion_count = measurements.get("ion_count", 0)
        
        if ion_count == self.target_ion_count:
            components["ejection"] = self.w_success
        elif ion_count == 0:
            # Overshoot - emptied trap
            components["ejection"] = self.w_overshoot
        else:
            # Partial ejection
            components["ejection"] = 100.0 * abs(
                ion_count - self.target_ion_count
            )
        
        # Time penalty
        tickle_duration = params.get("tickle_duration_ms", 100.0)
        components["time"] = self.w_time * (tickle_duration / 100.0)
        
        total_cost = sum(components.values())
        return total_cost, components
    
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Success: ion_count = 1."""
        ion_count = measurements.get("ion_count", 0)
        return ion_count == self.target_ion_count


class HdLoadingObjective(ObjectiveFunction):
    """
    Phase I-C: HD+ Loading Optimization
    
    Goal: Maximize sympathetic cooling efficiency / HD+ yield / minimise crystallisation time
    Metrics: ion_counts, ion_pos, PMT
    """
    
    def __init__(
        self,
        target_be_count: int = 1,
        hd_secular_freq: float = 277.0,
        freq_tolerance: float = 5.0,
        w_hd_detected: float = -1000.0,
        w_be_preserved: float = -500.0,
        w_crystal_time: float = 1.0,
    ):
        self.target_be_count = target_be_count
        self.hd_secular_freq = hd_secular_freq
        self.freq_tolerance = freq_tolerance
        self.w_hd_detected = w_hd_detected
        self.w_be_preserved = w_be_preserved
        self.w_crystal_time = w_crystal_time
    
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Measurements expected:
        - ion_count: Be+ count after HD loading
        - sweep_peak_freq: Detected secular frequency
        - sweep_peak_found: Whether peak was detected
        - crystal_time_ms: Crystallisation time (optional)
        """
        components = {}
        
        # HD detection via secular sweep
        peak_found = measurements.get("sweep_peak_found", False)
        peak_freq = measurements.get("sweep_peak_freq", 0.0)
        
        if peak_found:
            hd_error = abs(peak_freq - self.hd_secular_freq)
            if hd_error < self.freq_tolerance:
                components["hd_detection"] = self.w_hd_detected
            else:
                components["hd_detection"] = 100.0  # Wrong frequency
        else:
            components["hd_detection"] = 200.0  # No peak
        
        # Be+ preservation
        ion_count = measurements.get("ion_count", 0)
        if ion_count == self.target_be_count:
            components["be_preservation"] = self.w_be_preserved
        else:
            components["be_preservation"] = 200.0 * abs(
                ion_count - self.target_be_count
            )
        
        # Crystallisation time
        crystal_time = measurements.get("crystal_time_ms", 1000.0)
        components["crystal_time"] = self.w_crystal_time * (crystal_time / 1000.0)
        
        total_cost = sum(components.values())
        return total_cost, components
    
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Check if HD+ loaded successfully."""
        ion_count = measurements.get("ion_count", 0)
        if ion_count != self.target_be_count:
            return False
        
        peak_freq = measurements.get("sweep_peak_freq", 0.0)
        peak_found = measurements.get("sweep_peak_found", False)
        
        if not peak_found:
            return False
        
        return abs(peak_freq - self.hd_secular_freq) < self.freq_tolerance


# =============================================================================
# Phase II Multi-Objective Architecture
# =============================================================================

class PhaseIIMultiObjective(ObjectiveFunction):
    """
    Phase II: System-Level Multi-Objective Optimization
    
    Objectives:
    1. Load preferred number of Be+
    2. Load exactly one MHI
    3. After ejection, only one visible ion remains
    4. Minimize Cycle Time
    5. Final secular frequency matches prediction
    
    Constraints:
    1. Be_Residual <= Threshold
    2. Pressure < threshold
    3. Laser high power output time < threshold
    """
    
    def __init__(
        self,
        target_be_count: int = 1,
        target_hd_count: int = 1,
        be_secular_freq: float = 307.0,
        hd_secular_freq: float = 277.0,
        freq_tolerance: float = 5.0,
        # Constraint thresholds
        be_residual_threshold: float = 0.1,
        pressure_threshold: float = 5e-10,  # mbar
        laser_time_threshold: float = 1000.0,  # ms
    ):
        self.target_be_count = target_be_count
        self.target_hd_count = target_hd_count
        self.be_secular_freq = be_secular_freq
        self.hd_secular_freq = hd_secular_freq
        self.freq_tolerance = freq_tolerance
        
        # Constraint thresholds
        self.be_residual_threshold = be_residual_threshold
        self.pressure_threshold = pressure_threshold
        self.laser_time_threshold = laser_time_threshold
    
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        For Phase II, cost is multi-dimensional.
        Returns vector of objective values for MOBO.
        """
        # This is used by TuRBO for scalarization
        # MOBO uses the individual objectives directly
        components = {}
        
        # Single scalar cost for TuRBO fallback
        be_count = measurements.get("final_be_count", 0)
        hd_count = measurements.get("final_hd_count", 0)
        cycle_time = measurements.get("cycle_time_ms", 30000.0)
        
        # Penalty for wrong counts
        be_penalty = abs(be_count - self.target_be_count)
        hd_penalty = abs(hd_count - self.target_hd_count)
        
        # Normalized cycle time
        time_cost = cycle_time / 10000.0  # 10s baseline
        
        components["be_count"] = 100.0 * be_penalty
        components["hd_count"] = 100.0 * hd_penalty
        components["time"] = time_cost
        
        total_cost = sum(components.values())
        return total_cost, components
    
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Check all success criteria."""
        be_count = measurements.get("final_be_count", 0)
        hd_count = measurements.get("final_hd_count", 0)
        
        return (
            be_count == self.target_be_count and
            hd_count == self.target_hd_count
        )
    
    def get_objectives(self) -> List[ObjectiveConfig]:
        """
        Define MOBO objectives.
        Each returns a value to be minimized or maximized.
        """
        return [
            ObjectiveConfig(
                name="be_yield",
                evaluator=lambda p, m: abs(
                    m.get("final_be_count", 0) - self.target_be_count
                ),
                objective_type=ObjectiveType.MINIMIZE,
                weight=1.0,
                description="Load preferred number of Be+"
            ),
            ObjectiveConfig(
                name="hd_yield",
                evaluator=lambda p, m: abs(
                    m.get("final_hd_count", 0) - self.target_hd_count
                ),
                objective_type=ObjectiveType.MINIMIZE,
                weight=1.0,
                description="Load exactly one MHI"
            ),
            ObjectiveConfig(
                name="ejection_purity",
                evaluator=lambda p, m: m.get("visible_ions_after_ejection", 0) - 1,
                objective_type=ObjectiveType.MINIMIZE,
                weight=1.0,
                description="After ejection, only one visible ion"
            ),
            ObjectiveConfig(
                name="speed",
                evaluator=lambda p, m: m.get("cycle_time_ms", 30000.0),
                objective_type=ObjectiveType.MINIMIZE,
                weight=0.1,  # Lower weight = less important
                description="Minimize cycle time"
            ),
            ObjectiveConfig(
                name="freq_match",
                evaluator=lambda p, m: abs(
                    m.get("final_secular_freq", 0) - self.hd_secular_freq
                ),
                objective_type=ObjectiveType.MINIMIZE,
                weight=1.0,
                description="Final secular frequency matches prediction"
            ),
        ]
    
    def get_constraints(self) -> List[ConstraintConfig]:
        """
        Define MOBO constraints.
        Constraints must be <= threshold to be feasible.
        """
        return [
            ConstraintConfig(
                name="purity",
                evaluator=lambda p, m: m.get("be_residual", 0.0),
                threshold=self.be_residual_threshold,
                constraint_type="inequality",
                description="Be residual below threshold"
            ),
            ConstraintConfig(
                name="pressure",
                evaluator=lambda p, m: m.get("pressure_mbar", 1e-10),
                threshold=self.pressure_threshold,
                constraint_type="inequality",
                description="Pressure below threshold"
            ),
            ConstraintConfig(
                name="laser_time",
                evaluator=lambda p, m: m.get("laser_high_power_time_ms", 0.0),
                threshold=self.laser_time_threshold,
                constraint_type="inequality",
                description="Laser high power time below threshold"
            ),
        ]


# =============================================================================
# Factory and Registration
# =============================================================================

def create_objective(phase: str, **kwargs) -> ObjectiveFunction:
    """
    Create an objective function for a given phase.
    
    Args:
        phase: One of "be_loading", "be_ejection", "hd_loading", "phase_ii"
        **kwargs: Phase-specific parameters
        
    Returns:
        ObjectiveFunction instance
    """
    # Map phase names to classes
    objective_map = {
        "be_loading": BeLoadingObjective,
        "be_ejection": BeEjectionObjective,
        "hd_loading": HdLoadingObjective,
        "phase_ii": PhaseIIMultiObjective,
        "global_mobo": PhaseIIMultiObjective,
    }
    
    if phase not in objective_map:
        # Try registry
        return ObjectiveRegistry.create(phase, **kwargs)
    
    return objective_map[phase](**kwargs)


# Register objectives
ObjectiveRegistry.register("be_loading", BeLoadingObjective)
ObjectiveRegistry.register("be_ejection", BeEjectionObjective)
ObjectiveRegistry.register("hd_loading", HdLoadingObjective)
ObjectiveRegistry.register("phase_ii", PhaseIIMultiObjective)


# Exports
__all__ = [
    # Base classes
    'ObjectiveFunction',
    'ObjectiveConfig',
    'ConstraintConfig',
    'ObjectiveType',
    'ObjectiveRegistry',
    
    # Phase I objectives
    'BeLoadingObjective',
    'BeEjectionObjective',
    'HdLoadingObjective',
    
    # Phase II multi-objective
    'PhaseIIMultiObjective',
    
    # Factory
    'create_objective',
]
