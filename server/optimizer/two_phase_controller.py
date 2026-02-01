"""
Two-Phase Bayesian Optimization Controller.

Architecture from BO.md:
- Phase I (TuRBO): Component-level optimization of individual stages
- Phase II (MOBO): System-level optimization with multi-objective trade-offs
- Warm Start: Data handover from Phase I to Phase II

Ask-Tell Interface:
    Controller provides parameters (ASK) → Hardware executes → 
    Controller registers results (TELL) → Controller updates model
"""

import numpy as np
import logging
import json
from typing import Dict, Any, Optional, List, Tuple, Callable
from enum import Enum, auto
from dataclasses import dataclass, asdict
from pathlib import Path

from .turbo import TuRBOOptimizer
from .mobo import MOBOOptimizer, Objective, Constraint, ConstraintType
from .parameters import create_be_loading_space, create_be_ejection_space, create_hd_loading_space
from .storage import ProfileStorage

logger = logging.getLogger("optimizer.two_phase")


class Phase(Enum):
    """Optimization phases."""
    IDLE = "idle"
    BE_LOADING_TURBO = "be_loading_turbo"      # Phase I-A
    BE_EJECTION_TURBO = "be_ejection_turbo"    # Phase I-B
    HD_LOADING_TURBO = "hd_loading_turbo"      # Phase I-C
    GLOBAL_MOBO = "global_mobo"                 # Phase II
    COMPLETE = "complete"


@dataclass
class OptimizationConfig:
    """Configuration for two-phase optimization."""
    # Targets
    target_be_count: int = 1
    target_hd_present: bool = False
    
    # Phase I: TuRBO settings
    turbo_max_iterations: int = 50
    turbo_n_init: int = 10
    
    # Phase II: MOBO settings  
    mobo_max_iterations: int = 30
    mobo_n_init: int = 5
    
    # Warm start
    warm_start_top_k: int = 5  # Number of top Phase I points to seed Phase II
    
    # Constraints
    be_residual_threshold: float = 0.1  # Max residual Be+ fluorescence
    max_cycle_time_ms: float = 30000.0   # Max total cycle time
    
    # Stopping criteria
    turbo_success_threshold: float = 0.9
    mobo_hypervolume_improvement_threshold: float = 0.01


class TwoPhaseController:
    """
    Two-Phase Bayesian Optimization Controller.
    
    Manages the transition from TuRBO (Phase I) to MOBO (Phase II)
    with automatic data handover and warm starting.
    
    Usage:
        controller = TwoPhaseController()
        controller.start_phase(Phase.BE_LOADING_TURBO)
        
        # ASK: Get parameters
        params = controller.ask()
        
        # ... run experiment with params ...
        
        # TELL: Register results
        controller.tell(measurements)
    """
    
    def __init__(self, config: Optional[OptimizationConfig] = None):
        """
        Initialize two-phase controller.
        
        Args:
            config: Optimization configuration
        """
        self.config = config or OptimizationConfig()
        self.current_phase = Phase.IDLE
        
        # Phase I optimizers (TuRBO)
        self.turbo_optimizers: Dict[Phase, Optional[TuRBOOptimizer]] = {
            Phase.BE_LOADING_TURBO: None,
            Phase.BE_EJECTION_TURBO: None,
            Phase.HD_LOADING_TURBO: None
        }
        
        # Phase II optimizer (MOBO)
        self.mobo_optimizer: Optional[MOBOOptimizer] = None
        
        # Data storage for warm start
        self.phase_i_data: Dict[str, List[Dict]] = {
            "be_loading": [],
            "be_ejection": [],
            "hd_loading": []
        }
        
        # Current state
        self.iteration = 0
        self.pending_params: Optional[np.ndarray] = None
        
        # Storage
        self.storage = ProfileStorage()
        
        logger.info("TwoPhaseController initialized")
    
    def start_phase(self, phase: Phase):
        """Start a specific optimization phase."""
        self.current_phase = phase
        self.iteration = 0
        
        if phase == Phase.BE_LOADING_TURBO:
            self._init_be_loading_turbo()
        elif phase == Phase.BE_EJECTION_TURBO:
            self._init_be_ejection_turbo()
        elif phase == Phase.HD_LOADING_TURBO:
            self._init_hd_loading_turbo()
        elif phase == Phase.GLOBAL_MOBO:
            self._init_global_mobo()
        
        logger.info(f"Started phase: {phase.value}")
    
    def _init_be_loading_turbo(self):
        """Initialize TuRBO for Be+ loading."""
        space = create_be_loading_space()
        
        def objective(x: np.ndarray, measurements: Dict) -> float:
            """Maximize Be+ fluorescence."""
            fluorescence = measurements.get("total_fluorescence", 0)
            return -fluorescence  # Negative because TuRBO minimizes
        
        self.turbo_optimizers[Phase.BE_LOADING_TURBO] = TuRBOOptimizer(
            n_dims=space.get_n_dims(),
            bounds=space.get_bounds_list(),
            n_initial_points=self.config.turbo_n_init,
            max_iterations=self.config.turbo_max_iterations
        )
    
    def _init_be_ejection_turbo(self):
        """Initialize TuRBO for Be+ ejection."""
        space = create_be_ejection_space()
        
        def objective(x: np.ndarray, measurements: Dict) -> float:
            """Minimize residual Be+ fluorescence (inverse of ejection efficiency)."""
            residual = measurements.get("residual_fluorescence", 0)
            return residual
        
        self.turbo_optimizers[Phase.BE_EJECTION_TURBO] = TuRBOOptimizer(
            n_dims=space.get_n_dims(),
            bounds=space.get_bounds_list(),
            n_initial_points=self.config.turbo_n_init,
            max_iterations=self.config.turbo_max_iterations
        )
    
    def _init_hd_loading_turbo(self):
        """Initialize TuRBO for HD+ loading."""
        space = create_hd_loading_space()
        
        def objective(x: np.ndarray, measurements: Dict) -> float:
            """Maximize HD+ yield (dark ion dip depth)."""
            dip_depth = measurements.get("dark_ion_dip_depth", 0)
            return -dip_depth
        
        self.turbo_optimizers[Phase.HD_LOADING_TURBO] = TuRBOOptimizer(
            n_dims=space.get_n_dims(),
            bounds=space.get_bounds_list(),
            n_initial_points=self.config.turbo_n_init,
            max_iterations=self.config.turbo_max_iterations
        )
    
    def _init_global_mobo(self):
        """Initialize MOBO for global optimization."""
        # Combined parameter space from all phases
        be_space = create_be_loading_space()
        hd_space = create_hd_loading_space()
        
        # MOBO uses tightened bounds from Phase I
        bounds = self._compute_tightened_bounds()
        n_dims = len(bounds)
        
        # Define objectives
        objectives = [
            Objective(
                name="yield",
                evaluator=lambda x, m: -m.get("hd_yield", 0),  # Maximize
                minimize=False
            ),
            Objective(
                name="speed",
                evaluator=lambda x, m: m.get("total_cycle_time_ms", 30000),  # Minimize
                minimize=True
            )
        ]
        
        # Define constraints
        # Note: MOBO passes measurements dict as second argument, not ndarray
        constraints = [
            Constraint(
                name="purity",
                constraint_type=ConstraintType.INEQUALITY,
                evaluator=lambda x, measurements: measurements.get("be_residual", 0) - self.config.be_residual_threshold,
                threshold=0
            ),
            Constraint(
                name="stability",
                constraint_type=ConstraintType.INEQUALITY,
                evaluator=lambda x, measurements: measurements.get("trap_heating", 0) - 0.1,
                threshold=0
            )
        ]
        
        self.mobo_optimizer = MOBOOptimizer(
            n_dims=n_dims,
            bounds=bounds,
            objectives=objectives,
            constraints=constraints,
            n_initial_points=self.config.mobo_n_init,
            max_iterations=self.config.mobo_max_iterations
        )
        
        # Warm start: Seed MOBO with top Phase I results
        self._warm_start_mobo()
    
    def _compute_tightened_bounds(self) -> List[Tuple[float, float]]:
        """
        Compute tightened bounds from Phase I results.
        
        Uses top-k points from each Phase I run to constrain search space.
        """
        all_points = []
        
        for phase_data in self.phase_i_data.values():
            if phase_data:
                # Sort by value (ascending since we minimize)
                sorted_data = sorted(phase_data, key=lambda d: d.get("value", float('inf')))
                top_k = sorted_data[:self.config.warm_start_top_k]
                all_points.extend([np.array(d["params"]).flatten() for d in top_k])
        
        if not all_points:
            # No Phase I data, use default bounds
            space = create_be_loading_space()
            return space.get_bounds_list()
        
        # Ensure all points have same dimensionality
        dims = [p.shape[0] if len(p.shape) > 0 else 1 for p in all_points]
        if len(set(dims)) > 1:
            # Different dimensions, use default bounds
            logger.warning(f"Inconsistent dimensions in Phase I data: {dims}")
            space = create_be_loading_space()
            return space.get_bounds_list()
        
        # Compute bounds that encompass top points
        points_array = np.vstack(all_points)
        lower = np.min(points_array, axis=0)
        upper = np.max(points_array, axis=0)
        
        # Add some margin (20%)
        margin = (upper - lower) * 0.2
        lower = lower - margin
        upper = upper + margin
        
        return list(zip(lower, upper))
    
    def _warm_start_mobo(self):
        """Seed MOBO with Phase I data points."""
        if self.mobo_optimizer is None:
            return
        
        for phase_name, phase_data in self.phase_i_data.items():
            for data_point in phase_data:
                # Register as observation
                self.mobo_optimizer.X_observed.append(data_point["params"])
                self.mobo_optimizer.Y_observed.append(data_point["objectives"])
                self.mobo_optimizer.C_observed.append(data_point["constraints"])
        
        logger.info(f"Warm started MOBO with {len(self.mobo_optimizer.X_observed)} points")
    
    def ask(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        ASK: Get next parameters to evaluate.
        
        Returns:
            Tuple of (parameters dict, metadata)
        """
        if self.current_phase in self.turbo_optimizers:
            optimizer = self.turbo_optimizers[self.current_phase]
            if optimizer:
                x, meta = optimizer.suggest()
                self.pending_params = x
                
                # Convert to parameter dict
                space = self._get_current_space()
                params = space.array_to_dict(x)
                
                return params, {"phase": self.current_phase.value, **meta}
        
        elif self.current_phase == Phase.GLOBAL_MOBO and self.mobo_optimizer:
            x, meta = self.mobo_optimizer.suggest()
            self.pending_params = x
            
            # For MOBO, parameters span all stages
            params = {"global_params": x.tolist()}
            
            return params, {"phase": self.current_phase.value, **meta}
        
        return {}, {"phase": self.current_phase.value, "error": "No optimizer"}
    
    def tell(self, measurements: Dict[str, Any]):
        """
        TELL: Register experimental results.
        
        Args:
            measurements: Experimental measurements including:
                - total_fluorescence (for Be+ loading)
                - residual_fluorescence (for Be+ ejection)
                - dark_ion_dip_depth (for HD+ loading)
                - total_cycle_time_ms (for MOBO)
                - hd_yield (for MOBO)
                - be_residual (for MOBO constraints)
        """
        if self.pending_params is None:
            logger.warning("Tell called without pending parameters")
            return
        
        x = self.pending_params
        
        if self.current_phase in self.turbo_optimizers:
            optimizer = self.turbo_optimizers[self.current_phase]
            if optimizer:
                # Compute objective value
                y = self._compute_objective_value(measurements)
                optimizer.register(x, y)
                
                # Store for warm start
                self._store_phase_i_data(x, y, measurements)
        
        elif self.current_phase == Phase.GLOBAL_MOBO and self.mobo_optimizer:
            self.mobo_optimizer.register(x, measurements)
        
        self.iteration += 1
        self.pending_params = None
        
        # Check for phase transition
        self._check_phase_transition(measurements)
    
    def _compute_objective_value(self, measurements: Dict[str, Any]) -> float:
        """Compute scalar objective value for current phase."""
        if self.current_phase == Phase.BE_LOADING_TURBO:
            return -measurements.get("total_fluorescence", 0)
        elif self.current_phase == Phase.BE_EJECTION_TURBO:
            return measurements.get("residual_fluorescence", 0)
        elif self.current_phase == Phase.HD_LOADING_TURBO:
            return -measurements.get("dark_ion_dip_depth", 0)
        return 0.0
    
    def _store_phase_i_data(self, x: np.ndarray, y: float, measurements: Dict):
        """Store Phase I data for warm start."""
        phase_name = self.current_phase.value.replace("_turbo", "")
        
        # For MOBO, we need multi-objective values
        objectives = np.array([
            measurements.get("hd_yield", 0),
            measurements.get("total_cycle_time_ms", 30000)
        ])
        
        # Constraints
        constraints = np.array([
            measurements.get("be_residual", 0),
            measurements.get("trap_heating", 0)
        ])
        
        self.phase_i_data[phase_name].append({
            "params": x,
            "value": y,
            "objectives": objectives,
            "constraints": constraints,
            "measurements": measurements
        })
    
    def is_complete(self) -> bool:
        """Check if optimization is complete."""
        return self.current_phase == Phase.COMPLETE
    
    def _check_phase_transition(self, measurements: Dict[str, Any]):
        """Check if we should transition to next phase."""
        if self.current_phase == Phase.BE_LOADING_TURBO:
            # Check if we have enough Be+ loaded
            fluorescence = measurements.get("total_fluorescence", 0)
            if fluorescence > self.config.turbo_success_threshold:
                logger.info("Be+ loading successful, proceeding")
                self.start_phase(Phase.BE_EJECTION_TURBO)
        
        elif self.current_phase == Phase.BE_EJECTION_TURBO:
            # Check if residual Be+ is low enough
            residual = measurements.get("residual_fluorescence", float('inf'))
            if residual < self.config.be_residual_threshold:
                logger.info("Be+ ejection successful")
                if self.config.target_hd_present:
                    self.start_phase(Phase.HD_LOADING_TURBO)
                else:
                    self.start_phase(Phase.GLOBAL_MOBO)
        
        elif self.current_phase == Phase.HD_LOADING_TURBO:
            # Check HD+ loading
            dip_depth = measurements.get("dark_ion_dip_depth", 0)
            if dip_depth > 0.5:  # Threshold for successful loading
                logger.info("HD+ loading successful")
                self.start_phase(Phase.GLOBAL_MOBO)
        
        elif self.current_phase == Phase.GLOBAL_MOBO:
            # Check if MOBO converged
            if self.mobo_optimizer and len(self.mobo_optimizer.pareto_front.points) > 5:
                logger.info("MOBO converged")
                self.current_phase = Phase.COMPLETE
    
    def _get_current_space(self):
        """Get parameter space for current phase."""
        if self.current_phase == Phase.BE_LOADING_TURBO:
            return create_be_loading_space()
        elif self.current_phase == Phase.BE_EJECTION_TURBO:
            return create_be_ejection_space()
        elif self.current_phase == Phase.HD_LOADING_TURBO:
            return create_hd_loading_space()
        else:
            return create_be_loading_space()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current optimization status."""
        status = {
            "phase": self.current_phase.value,
            "iteration": self.iteration,
            "config": asdict(self.config)
        }
        
        if self.current_phase in self.turbo_optimizers:
            opt = self.turbo_optimizers[self.current_phase]
            if opt:
                status.update({
                    "best_value": opt.best_value,
                    "trust_region_length": opt.tr_state.length if opt.tr_state else None,
                    "n_observed": len(opt.X_observed)
                })
        
        elif self.current_phase == Phase.GLOBAL_MOBO and self.mobo_optimizer:
            status.update({
                "pareto_front_size": len(self.mobo_optimizer.pareto_front.points),
                "n_observed": len(self.mobo_optimizer.X_observed)
            })
        
        return status
    
    def get_best_config(self) -> Optional[Dict[str, Any]]:
        """Get best configuration found."""
        if self.current_phase == Phase.COMPLETE and self.mobo_optimizer:
            pareto = self.mobo_optimizer.get_pareto_front()
            if pareto:
                # Return first Pareto-optimal point
                params, objs = pareto[0]
                return {
                    "params": params.tolist(),
                    "objectives": objs.tolist()
                }
        
        # Otherwise return best from current phase
        opt = self.turbo_optimizers.get(self.current_phase)
        if opt and opt.best_point is not None:
            space = self._get_current_space()
            return {
                "params": space.array_to_dict(opt.best_point),
                "value": opt.best_value
            }
        
        return None
    
    def save_state(self, filepath: str):
        """Save optimization state."""
        state = {
            "config": asdict(self.config),
            "current_phase": self.current_phase.value,
            "iteration": self.iteration,
            "phase_i_data": {
                k: [{"params": d["params"].tolist(), 
                     "value": float(d["value"])} for d in v]
                for k, v in self.phase_i_data.items()
            }
        }
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"State saved to {filepath}")
    
    def load_state(self, filepath: str):
        """Load optimization state."""
        with open(filepath, 'r') as f:
            state = json.load(f)
        
        self.config = OptimizationConfig(**state["config"])
        self.current_phase = Phase(state["current_phase"])
        self.iteration = state["iteration"]
        
        # Restore Phase I data
        for k, v in state["phase_i_data"].items():
            self.phase_i_data[k] = [
                {"params": np.array(d["params"]), "value": d["value"]}
                for d in v
            ]
        
        logger.info(f"State loaded from {filepath}")
