"""
Bayesian Optimization Module for Mixed-Species Ion Loading.

Two-Phase Architecture (from BO.md):
- Phase I (TuRBO): Component-level optimization of individual stages
- Phase II (MOBO): System-level multi-objective optimization
- Warm Start: Data handover from Phase I to Phase II

Usage:
    from services.optimizer import TwoPhaseController, Phase
    
    controller = TwoPhaseController()
    controller.start_phase(Phase.BE_LOADING_TURBO)
    
    # ASK-TELL interface
    params, meta = controller.ask()
    # ... run experiment ...
    controller.tell(measurements)
"""

__version__ = "2.0.0"

# Core optimizers
from .turbo import TuRBOOptimizer, TrustRegionState
from .mobo import (
    MOBOOptimizer,
    ParetoFront,
    Objective,
    Constraint,
    ConstraintType
)

# Two-phase controller
from .two_phase_controller import (
    TwoPhaseController,
    Phase,
    OptimizationConfig
)

# Parameters and objectives
from .parameters import (
    ParameterSpace,
    ParameterConfig,
    ParameterType,
    TimeWindow,
    create_be_loading_space,
    create_be_ejection_space,
    create_hd_loading_space
)
from .objectives import (
    BeLoadingObjective,
    BeEjectionObjective,
    HdLoadingObjective,
    PhaseIIMultiObjective,
    ObjectiveFunction,
    ObjectiveConfig,
    ConstraintConfig,
    ObjectiveType,
    ObjectiveRegistry,
    create_objective
)

# Storage
from .storage import ProfileStorage

__all__ = [
    # Version
    '__version__',
    
    # Two-Phase Architecture
    'TwoPhaseController',
    'Phase',
    'OptimizationConfig',
    
    # TuRBO (Phase I)
    'TuRBOOptimizer',
    'TrustRegionState',
    
    # MOBO (Phase II)
    'MOBOOptimizer',
    'ParetoFront',
    'Objective',
    'Constraint',
    'ConstraintType',
    
    # Parameters
    'ParameterSpace',
    'ParameterConfig',
    'ParameterType',
    'TimeWindow',
    'create_be_loading_space',
    'create_be_ejection_space',
    'create_hd_loading_space',
    
    # Objectives
    'ObjectiveFunction',
    'BeLoadingObjective',
    'BeEjectionObjective',
    'HdLoadingObjective',
    'PhaseIIMultiObjective',
    'ObjectiveConfig',
    'ConstraintConfig',
    'ObjectiveType',
    'ObjectiveRegistry',
    'create_objective',
    
    # Storage
    'ProfileStorage',
]
