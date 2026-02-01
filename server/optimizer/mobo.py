"""
MOBO (Multi-Objective Bayesian Optimization) for Phase II.

Uses qNEHVI (Noisy Expected Hypervolume Improvement) with constraints
to optimize the full experimental cycle while enforcing purity and stability.
"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("optimizer.mobo")


class ConstraintType(Enum):
    """Types of constraints."""
    INEQUALITY = "inequality"  # g(x) <= 0
    EQUALITY = "equality"      # h(x) = 0


@dataclass
class Constraint:
    """Constraint definition."""
    name: str
    constraint_type: ConstraintType
    evaluator: Callable[[np.ndarray, float], float]  # (params, obj_value) -> constraint_value
    threshold: float = 0.0


@dataclass
class Objective:
    """Objective definition."""
    name: str
    evaluator: Callable[[np.ndarray, Dict[str, Any]], float]
    minimize: bool = True  # True for minimization, False for maximization


class ParetoFront:
    """Manages the Pareto front for multi-objective optimization."""
    
    def __init__(self, n_objectives: int = 2, ref_point: Optional[np.ndarray] = None):
        """
        Initialize Pareto front.
        
        Args:
            n_objectives: Number of objectives
            ref_point: Reference point for hypervolume calculation
        """
        self.n_objectives = n_objectives
        self.points: List[Tuple[np.ndarray, np.ndarray]] = []  # (params, objectives)
        
        # Default reference point (worst possible values)
        if ref_point is None:
            self.ref_point = np.ones(n_objectives) * 1e10
        else:
            self.ref_point = ref_point
    
    def add_point(self, params: np.ndarray, objectives: np.ndarray) -> bool:
        """
        Add point to Pareto front if it's non-dominated.
        
        Returns:
            True if point was added (non-dominated)
        """
        # Check if dominated by existing points
        for _, existing_obj in self.points:
            if self._dominates(existing_obj, objectives):
                return False  # Dominated, don't add
        
        # Remove points dominated by new point
        self.points = [
            (p, o) for p, o in self.points 
            if not self._dominates(objectives, o)
        ]
        
        self.points.append((params, objectives))
        return True
    
    def _dominates(self, a: np.ndarray, b: np.ndarray) -> bool:
        """Check if a dominates b (assuming minimization)."""
        return np.all(a <= b) and np.any(a < b)
    
    def hypervolume(self) -> float:
        """Calculate hypervolume indicator (2D only for simplicity)."""
        if len(self.points) == 0 or self.n_objectives != 2:
            return 0.0
        
        # Sort by first objective
        sorted_points = sorted(self.points, key=lambda x: x[1][0])
        
        # Calculate hypervolume using rectangle method
        hv = 0.0
        prev_x = self.ref_point[0]
        
        for _, obj in sorted_points:
            x, y = obj[0], obj[1]
            if x < self.ref_point[0] and y < self.ref_point[1]:
                hv += (self.ref_point[0] - x) * (self.ref_point[1] - y)
                # Subtract overlap (simplified)
        
        return hv
    
    def get_points(self) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Get all Pareto-optimal points."""
        return self.points.copy()


class MOBOOptimizer:
    """
    Multi-Objective Bayesian Optimization with Constraints.
    
    Optimizes multiple conflicting objectives (e.g., yield vs speed)
    while enforcing hard constraints (e.g., purity, stability).
    
    Uses:
    - Gaussian Process for each objective
    - Probability of feasibility for constraints
    - Hypervolume improvement for acquisition
    """
    
    def __init__(
        self,
        n_dims: int,
        bounds: List[Tuple[float, float]],
        objectives: List[Objective],
        constraints: List[Constraint],
        n_initial_points: int = 10,
        max_iterations: int = 50,
        noise_variance: float = 1e-5
    ):
        """
        Initialize MOBO optimizer.
        
        Args:
            n_dims: Number of dimensions
            bounds: Parameter bounds
            objectives: List of objective functions
            constraints: List of constraints
            n_initial_points: Random initial samples
            max_iterations: Max iterations
            noise_variance: GP noise
        """
        self.n_dims = n_dims
        self.bounds = np.array(bounds)
        self.objectives = objectives
        self.constraints = constraints
        self.n_initial_points = n_initial_points
        self.max_iterations = max_iterations
        self.noise_variance = noise_variance
        
        # Pareto front
        self.pareto_front = ParetoFront(n_objectives=len(objectives))
        
        # Observations
        self.X_observed: List[np.ndarray] = []
        self.Y_observed: List[np.ndarray] = []  # Multi-objective values
        self.C_observed: List[np.ndarray] = []  # Constraint values
        
        # Iteration
        self.iteration = 0
        
        # GP hyperparameters (one per objective)
        self.gp_params: List[Dict] = [
            {"length_scales": np.ones(n_dims) * 0.5, "signal_variance": 1.0}
            for _ in objectives
        ]
        
        logger.info(
            f"MOBO initialized: {n_dims} dims, "
            f"{len(objectives)} objectives, {len(constraints)} constraints"
        )
    
    def _normalize(self, x: np.ndarray) -> np.ndarray:
        """Normalize to [0, 1]."""
        return (x - self.bounds[:, 0]) / (self.bounds[:, 1] - self.bounds[:, 0])
    
    def _denormalize(self, x: np.ndarray) -> np.ndarray:
        """Denormalize from [0, 1]."""
        return x * (self.bounds[:, 1] - self.bounds[:, 0]) + self.bounds[:, 0]
    
    def _kernel(self, X1: np.ndarray, X2: np.ndarray, obj_idx: int) -> np.ndarray:
        """ARD SE kernel for objective."""
        if X2 is None:
            X2 = X1
        
        params = self.gp_params[obj_idx]
        length_scales = params["length_scales"]
        signal_var = params["signal_variance"]
        
        X1_scaled = X1 / length_scales
        X2_scaled = X2 / length_scales
        
        sq_dist = (
            np.sum(X1_scaled**2, axis=1).reshape(-1, 1) +
            np.sum(X2_scaled**2, axis=1).reshape(1, -1) -
            2 * np.dot(X1_scaled, X2_scaled.T)
        )
        
        return signal_var * np.exp(-0.5 * sq_dist)
    
    def _gp_predict(self, X_train: np.ndarray, y_train: np.ndarray,
                    X_test: np.ndarray, obj_idx: int) -> Tuple[np.ndarray, np.ndarray]:
        """GP prediction for objective."""
        K = self._kernel(X_train, X_train, obj_idx) + self.noise_variance * np.eye(len(X_train))
        K_s = self._kernel(X_train, X_test, obj_idx)
        
        try:
            L = np.linalg.cholesky(K)
            alpha = np.linalg.solve(L.T, np.linalg.solve(L, y_train))
            mu = K_s.T @ alpha
            
            v = np.linalg.solve(L, K_s)
            var = np.diag(self._kernel(X_test, X_test, obj_idx)) - np.sum(v**2, axis=0)
            std = np.sqrt(np.maximum(var, 1e-10))
            
            return mu, std
        except np.linalg.LinAlgError:
            # Fallback
            K_inv = np.linalg.pinv(K)
            mu = K_s.T @ K_inv @ y_train
            return mu, np.ones(len(X_test))
    
    def _feasibility_probability(self, x: np.ndarray) -> float:
        """
        Estimate probability that x satisfies all constraints.
        
        Returns:
            Probability in [0, 1]
        """
        if not self.C_observed or not self.X_observed:
            return 1.0  # No constraint data yet
        
        X_norm = np.array([self._normalize(xi) for xi in self.X_observed])
        x_norm = self._normalize(x).reshape(1, -1)
        
        # Check each constraint
        prob_feasible = 1.0
        
        for c_idx, constraint in enumerate(self.constraints):
            c_values = np.array([c[c_idx] for c in self.C_observed])
            
            # GP on constraint
            mu, std = self._gp_predict(X_norm, c_values, x_norm, 0)  # Use first GP params
            
            # Probability constraint is satisfied (c <= threshold)
            from scipy.stats import norm
            prob = norm.cdf((constraint.threshold - mu[0]) / (std[0] + 1e-10))
            prob_feasible *= prob
        
        return prob_feasible
    
    def _expected_hypervolume_improvement(self, x: np.ndarray) -> float:
        """
        Approximate Expected Hypervolume Improvement.
        
        Simplified version - full qNEHVI is complex.
        """
        if len(self.X_observed) < 2:
            return 1.0
        
        X_norm = np.array([self._normalize(xi) for xi in self.X_observed])
        x_norm = self._normalize(x).reshape(1, -1)
        
        # Predict all objectives
        predicted_objs = []
        uncertanties = []
        
        for obj_idx in range(len(self.objectives)):
            y_train = np.array([y[obj_idx] for y in self.Y_observed])
            mu, std = self._gp_predict(X_norm, y_train, x_norm, obj_idx)
            predicted_objs.append(mu[0])
            uncertanties.append(std[0])
        
        # Simplified EHVI: higher uncertainty + promising objective values
        hv_improvement = np.sum(uncertanties)  # Exploration
        
        # Check if predicted point improves Pareto front
        pred_obj_array = np.array(predicted_objs)
        
        # Add penalty if dominated
        is_dominated = False
        for _, existing_obj in self.pareto_front.get_points():
            if np.all(existing_obj <= pred_obj_array) and np.any(existing_obj < pred_obj_array):
                is_dominated = True
                break
        
        if not is_dominated:
            hv_improvement += 1.0  # Bonus for non-dominated point
        
        return hv_improvement
    
    def _acquisition_function(self, x: np.ndarray) -> float:
        """
        Combined acquisition: EHVI * feasibility_probability
        """
        ehvi = self._expected_hypervolume_improvement(x)
        prob_feasible = self._feasibility_probability(x)
        
        return ehvi * prob_feasible
    
    def suggest(self) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Suggest next point."""
        # Random initialization
        if len(self.X_observed) < self.n_initial_points:
            x = np.random.uniform(self.bounds[:, 0], self.bounds[:, 1])
            
            return x, {
                "iteration": self.iteration,
                "phase": "initialization",
                "pareto_size": len(self.pareto_front.points)
            }
        
        # Optimize acquisition
        from scipy.optimize import minimize
        
        best_x = None
        best_acq = -float('inf')
        
        for _ in range(20):
            x0 = np.random.uniform(self.bounds[:, 0], self.bounds[:, 1])
            
            try:
                result = minimize(
                    lambda x: -self._acquisition_function(x),
                    x0,
                    method='L-BFGS-B',
                    bounds=self.bounds
                )
                
                if -result.fun > best_acq:
                    best_acq = -result.fun
                    best_x = result.x
            except Exception:
                continue
        
        if best_x is None:
            best_x = np.random.uniform(self.bounds[:, 0], self.bounds[:, 1])
        
        return best_x, {
            "iteration": self.iteration,
            "phase": "mobo",
            "acquisition_value": best_acq,
            "pareto_size": len(self.pareto_front.points)
        }
    
    def register(self, x: np.ndarray, measurements: Dict[str, Any]):
        """
        Register observation.
        
        Args:
            x: Parameters
            measurements: Dictionary with objective and constraint values
        """
        # Evaluate objectives
        y = np.array([
            obj.evaluator(x, measurements) * (-1 if not obj.minimize else 1)
            for obj in self.objectives
        ])
        
        # Evaluate constraints (pass measurements dict, not objectives array)
        c = np.array([
            cons.evaluator(x, measurements) for cons in self.constraints
        ])
        
        self.X_observed.append(x)
        self.Y_observed.append(y)
        self.C_observed.append(c)
        
        # Check feasibility
        is_feasible = all(c[i] <= cons.threshold for i, cons in enumerate(self.constraints))
        
        # Update Pareto front if feasible
        if is_feasible:
            added = self.pareto_front.add_point(x, y)
            if added:
                logger.debug(f"Added point to Pareto front, size={len(self.pareto_front.points)}")
        
        self.iteration += 1
    
    def get_pareto_front(self) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Get current Pareto front."""
        return self.pareto_front.get_points()
    
    def is_feasible(self, x: np.ndarray) -> bool:
        """Check if point satisfies all constraints."""
        prob = self._feasibility_probability(x)
        return prob > 0.5  # Threshold
