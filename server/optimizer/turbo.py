"""
TuRBO (Trust Region Bayesian Optimization) for Phase I.

TuRBO creates local "Trust Regions" (hyperspheres) to focus the search,
allowing for rapid convergence even with >20 parameters.
"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass
from scipy.optimize import minimize
from scipy.spatial.distance import cdist

logger = logging.getLogger("optimizer.turbo")


@dataclass
class TrustRegionState:
    """State of a single trust region."""
    center: np.ndarray  # Center point in normalized space [0, 1]^d
    length: float  # Trust region length (0 to 1)
    success_counter: int = 0
    failure_counter: int = 0
    
    # Bounds for this trust region (in normalized space)
    @property
    def lower_bounds(self) -> np.ndarray:
        return np.maximum(self.center - self.length / 2, 0.0)
    
    @property
    def upper_bounds(self) -> np.ndarray:
        return np.minimum(self.center + self.length / 2, 1.0)


class TuRBOOptimizer:
    """
    TuRBO-1: Trust Region Bayesian Optimization.
    
    Unlike standard BO that searches globally, TuRBO maintains a local
    trust region that expands on success and shrinks on failure.
    
    Key features:
    - Local search within trust region
    - Automatic trust region adjustment
    - Better scaling for high dimensions (>20 params)
    - Faster convergence for local optima
    """
    
    def __init__(
        self,
        n_dims: int,
        bounds: List[Tuple[float, float]],
        n_initial_points: int = 10,
        max_iterations: int = 100,
        trust_region_length_init: float = 0.8,
        trust_region_length_min: float = 0.5**7,  # ~0.0078
        trust_region_length_max: float = 1.6,
        success_tolerance: int = 3,
        failure_tolerance: int = 3,
        acquisition_type: str = "ei",
        noise_variance: float = 1e-5
    ):
        """
        Initialize TuRBO optimizer.
        
        Args:
            n_dims: Number of dimensions
            bounds: List of (min, max) bounds for each dimension
            n_initial_points: Number of random initial samples
            max_iterations: Maximum iterations
            trust_region_length_init: Initial trust region length (0-1)
            trust_region_length_min: Minimum trust region length
            trust_region_length_max: Maximum trust region length
            success_tolerance: Consecutive successes before expanding
            failure_tolerance: Consecutive failures before shrinking
            acquisition_type: Acquisition function type
            noise_variance: GP noise variance
        """
        self.n_dims = n_dims
        self.bounds = np.array(bounds)
        self.n_initial_points = n_initial_points
        self.max_iterations = max_iterations
        
        # Trust region parameters
        self.trust_region_length_init = trust_region_length_init
        self.trust_region_length_min = trust_region_length_min
        self.trust_region_length_max = trust_region_length_max
        self.success_tolerance = success_tolerance
        self.failure_tolerance = failure_tolerance
        
        self.acquisition_type = acquisition_type
        self.noise_variance = noise_variance
        
        # Trust region state
        self.tr_state: Optional[TrustRegionState] = None
        
        # Observations
        self.X_observed: List[np.ndarray] = []
        self.y_observed: List[float] = []
        
        # Iteration tracking
        self.iteration = 0
        self.best_value = float('inf')
        self.best_point: Optional[np.ndarray] = None
        
        # GP hyperparameters
        self.length_scales = np.ones(n_dims) * 0.5
        self.signal_variance = 1.0
        
        logger.info(
            f"TuRBO initialized: {n_dims} dims, "
            f"TR length init={trust_region_length_init}"
        )
    
    def _normalize(self, x: np.ndarray) -> np.ndarray:
        """Normalize to [0, 1]."""
        return (x - self.bounds[:, 0]) / (self.bounds[:, 1] - self.bounds[:, 0])
    
    def _denormalize(self, x: np.ndarray) -> np.ndarray:
        """Denormalize from [0, 1]."""
        return x * (self.bounds[:, 1] - self.bounds[:, 0]) + self.bounds[:, 0]
    
    def _kernel(self, X1: np.ndarray, X2: np.ndarray = None) -> np.ndarray:
        """ARD Squared Exponential kernel."""
        if X2 is None:
            X2 = X1
        
        X1_scaled = X1 / self.length_scales
        X2_scaled = X2 / self.length_scales
        
        sq_dist = (
            np.sum(X1_scaled**2, axis=1).reshape(-1, 1) +
            np.sum(X2_scaled**2, axis=1).reshape(1, -1) -
            2 * np.dot(X1_scaled, X2_scaled.T)
        )
        
        return self.signal_variance * np.exp(-0.5 * sq_dist)
    
    def _fit_gp(self, X: np.ndarray, y: np.ndarray):
        """Fit Gaussian Process to data."""
        # Simple hyperparameter optimization
        # In practice, you'd optimize length scales via marginal likelihood
        
        # Update length scales based on data variance
        if len(X) > 2:
            for d in range(self.n_dims):
                x_range = np.std(X[:, d])
                if x_range > 0:
                    self.length_scales[d] = np.clip(x_range * 2, 0.01, 1.0)
    
    def _gp_predict(self, X_train: np.ndarray, y_train: np.ndarray, 
                    X_test: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """GP prediction with ARD kernel."""
        K = self._kernel(X_train) + self.noise_variance * np.eye(len(X_train))
        K_s = self._kernel(X_train, X_test)
        K_ss = self._kernel(X_test) + self.noise_variance * np.eye(len(X_test))
        
        try:
            L = np.linalg.cholesky(K)
            alpha = np.linalg.solve(L.T, np.linalg.solve(L, y_train))
            mu = K_s.T @ alpha
            
            v = np.linalg.solve(L, K_s)
            var = np.diag(K_ss) - np.sum(v**2, axis=0)
            std = np.sqrt(np.maximum(var, 1e-10))
            
            return mu, std
        except np.linalg.LinAlgError:
            # Fallback to pseudo-inverse
            K_inv = np.linalg.pinv(K)
            mu = K_s.T @ K_inv @ y_train
            var = np.diag(K_ss)
            return mu, np.sqrt(var)
    
    def _expected_improvement(self, X_test: np.ndarray, X_train: np.ndarray, 
                              y_train: np.ndarray) -> np.ndarray:
        """Expected Improvement acquisition function."""
        mu, std = self._gp_predict(X_train, y_train, X_test)
        
        y_best = np.min(y_train)
        
        with np.errstate(divide='ignore', invalid='ignore'):
            Z = (y_best - mu) / std
            
            from scipy.stats import norm
            ei = (y_best - mu) * norm.cdf(Z) + std * norm.pdf(Z)
            ei = np.where(std < 1e-10, 0, ei)
        
        return ei
    
    def _generate_candidate(self) -> np.ndarray:
        """Generate candidate point within trust region."""
        if self.tr_state is None:
            # Initialize trust region at random point
            center = np.random.uniform(0, 1, self.n_dims)
            self.tr_state = TrustRegionState(
                center=center,
                length=self.trust_region_length_init
            )
        
        # Sample uniformly within trust region bounds
        lower = self.tr_state.lower_bounds
        upper = self.tr_state.upper_bounds
        
        return np.random.uniform(lower, upper)
    
    def _optimize_acquisition(self) -> np.ndarray:
        """Optimize acquisition function within trust region."""
        if len(self.X_observed) < self.n_initial_points:
            # Random sampling for initialization
            return self._generate_candidate()
        
        # Fit GP
        X_norm = np.array([self._normalize(x) for x in self.X_observed])
        y_norm = np.array(self.y_observed)
        self._fit_gp(X_norm, y_norm)
        
        # Multi-start optimization
        best_x = None
        best_ei = -float('inf')
        
        lower = self.tr_state.lower_bounds
        upper = self.tr_state.upper_bounds
        
        for _ in range(10):
            x0 = self._generate_candidate()
            
            try:
                result = minimize(
                    lambda x: -float(self._expected_improvement(
                        x.reshape(1, -1), X_norm, y_norm
                    )[0]),
                    x0,
                    method='L-BFGS-B',
                    bounds=list(zip(lower, upper))
                )
                
                if -result.fun > best_ei:
                    best_ei = -result.fun
                    best_x = result.x
            except Exception:
                continue
        
        if best_x is None:
            best_x = self._generate_candidate()
        
        return best_x
    
    def suggest(self) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Suggest next point to evaluate.
        
        Returns:
            Tuple of (suggested point, metadata)
        """
        # Initialize trust region if needed
        if self.tr_state is None:
            center = np.random.uniform(0, 1, self.n_dims)
            self.tr_state = TrustRegionState(
                center=center,
                length=self.trust_region_length_init
            )
        
        # Check if we need random initialization
        if len(self.X_observed) < self.n_initial_points:
            x_norm = np.random.uniform(
                self.tr_state.lower_bounds,
                self.tr_state.upper_bounds
            )
            x_denorm = self._denormalize(x_norm)
            
            return x_denorm, {
                "iteration": self.iteration,
                "trust_region_length": self.tr_state.length,
                "acquisition_value": 0.0,
                "phase": "initialization"
            }
        
        # Optimize acquisition within trust region
        x_norm = self._optimize_acquisition()
        x_denorm = self._denormalize(x_norm)
        
        metadata = {
            "iteration": self.iteration,
            "trust_region_length": self.tr_state.length if self.tr_state else self.trust_region_length_init,
            "trust_region_center": self._denormalize(self.tr_state.center) if self.tr_state else None,
            "phase": "turbo"
        }
        
        return x_denorm, metadata
    
    def register(self, x: np.ndarray, y: float):
        """
        Register observation and update trust region.
        
        Args:
            x: Point evaluated
            y: Observed value (lower is better)
        """
        self.X_observed.append(x)
        self.y_observed.append(y)
        
        # Update best
        if y < self.best_value:
            self.best_value = y
            self.best_point = x.copy()
            
            # Success: move trust region center to new best
            if self.tr_state is not None:
                self.tr_state.center = self._normalize(x)
                self.tr_state.success_counter += 1
                self.tr_state.failure_counter = 0
                
                # Expand trust region
                if self.tr_state.success_counter >= self.success_tolerance:
                    self.tr_state.length = min(
                        self.tr_state.length * 2.0,
                        self.trust_region_length_max
                    )
                    self.tr_state.success_counter = 0
                    logger.debug(f"TR expanded to {self.tr_state.length:.4f}")
        else:
            # Failure
            if self.tr_state is not None:
                self.tr_state.failure_counter += 1
                self.tr_state.success_counter = 0
                
                # Shrink trust region
                if self.tr_state.failure_counter >= self.failure_tolerance:
                    self.tr_state.length = max(
                        self.tr_state.length / 2.0,
                        self.trust_region_length_min
                    )
                    self.tr_state.failure_counter = 0
                    logger.debug(f"TR shrunk to {self.tr_state.length:.4f}")
        
        self.iteration += 1
    
    def get_top_candidates(self, n: int = 5) -> List[Tuple[np.ndarray, float]]:
        """
        Get top n best observed points.
        
        Returns:
            List of (point, value) tuples sorted by value
        """
        if not self.y_observed:
            return []
        
        sorted_indices = np.argsort(self.y_observed)
        return [
            (self.X_observed[i], self.y_observed[i])
            for i in sorted_indices[:n]
        ]
    
    def get_trust_region_bounds(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Get current trust region bounds (denormalized)."""
        if self.tr_state is None:
            return None
        
        lower = self._denormalize(self.tr_state.lower_bounds)
        upper = self._denormalize(self.tr_state.upper_bounds)
        
        return lower, upper
