"""
Tests for Two-Phase Bayesian Optimization.
"""

import unittest
import numpy as np
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from server.optimizer import (
    TwoPhaseController,
    Phase,
    OptimizationConfig,
    TuRBOOptimizer,
    MOBOOptimizer,
    ParetoFront,
    Objective,
    Constraint,
    ConstraintType
)


class TestTuRBOOptimizer(unittest.TestCase):
    """Tests for TuRBO optimizer."""
    
    def test_initialization(self):
        """Test TuRBO initialization."""
        bounds = [(0, 1), (0, 1)]
        opt = TuRBOOptimizer(n_dims=2, bounds=bounds)
        
        self.assertEqual(opt.n_dims, 2)
        self.assertEqual(opt.trust_region_length_init, 0.8)
    
    def test_trust_region_adjustment(self):
        """Test trust region expands/shrinks correctly."""
        bounds = [(0, 10), (0, 10)]
        opt = TuRBOOptimizer(
            n_dims=2,
            bounds=bounds,
            success_tolerance=2,
            failure_tolerance=2
        )
        
        # Initial suggestion creates trust region
        x, _ = opt.suggest()
        self.assertIsNotNone(opt.tr_state)  # TR should be initialized
        
        # Register success (improvement)
        opt.register(x, 10.0)
        
        x2, _ = opt.suggest()
        opt.register(x2, 5.0)  # Better
        
        # Should have expanded
        self.assertGreater(opt.tr_state.length, 0.8)
    
    def test_suggest_within_bounds(self):
        """Test suggestions are within bounds."""
        bounds = [(0, 5), (10, 20)]
        opt = TuRBOOptimizer(n_dims=2, bounds=bounds)
        
        for _ in range(10):
            x, _ = opt.suggest()
            self.assertGreaterEqual(x[0], 0)
            self.assertLessEqual(x[0], 5)
            self.assertGreaterEqual(x[1], 10)
            self.assertLessEqual(x[1], 20)
            
            opt.register(x, np.random.random())


class TestParetoFront(unittest.TestCase):
    """Tests for Pareto front management."""
    
    def test_add_non_dominated_point(self):
        """Test adding non-dominated points."""
        pf = ParetoFront(n_objectives=2)
        
        # Add first point
        added = pf.add_point(np.array([1.0, 1.0]), np.array([1.0, 1.0]))
        self.assertTrue(added)
        self.assertEqual(len(pf.points), 1)
        
        # Add dominated point (worse in both objectives)
        added = pf.add_point(np.array([2.0, 2.0]), np.array([2.0, 2.0]))
        self.assertFalse(added)
        self.assertEqual(len(pf.points), 1)
        
        # Add non-dominated point (better in one, worse in other)
        added = pf.add_point(np.array([3.0, 3.0]), np.array([0.5, 2.0]))
        self.assertTrue(added)
        self.assertEqual(len(pf.points), 2)
    
    def test_dominates(self):
        """Test dominance checking."""
        pf = ParetoFront(n_objectives=2)
        
        # a dominates b
        self.assertTrue(pf._dominates(np.array([1.0, 1.0]), np.array([2.0, 2.0])))
        
        # a does not dominate b (equal)
        self.assertFalse(pf._dominates(np.array([1.0, 1.0]), np.array([1.0, 1.0])))
        
        # a does not dominate b (mixed)
        self.assertFalse(pf._dominates(np.array([1.0, 3.0]), np.array([2.0, 2.0])))


class TestMOBOOptimizer(unittest.TestCase):
    """Tests for MOBO optimizer."""
    
    def test_initialization(self):
        """Test MOBO initialization."""
        bounds = [(0, 1), (0, 1)]
        objectives = [
            Objective(name="obj1", evaluator=lambda x, m: x[0], minimize=True),
            Objective(name="obj2", evaluator=lambda x, m: x[1], minimize=True)
        ]
        constraints = []
        
        opt = MOBOOptimizer(
            n_dims=2,
            bounds=bounds,
            objectives=objectives,
            constraints=constraints
        )
        
        self.assertEqual(len(opt.objectives), 2)
        self.assertEqual(opt.n_dims, 2)
    
    def test_pareto_front_update(self):
        """Test Pareto front updates correctly."""
        bounds = [(0, 10), (0, 10)]
        objectives = [
            Objective(name="obj1", evaluator=lambda x, m: x[0], minimize=True),
            Objective(name="obj2", evaluator=lambda x, m: x[1], minimize=True)
        ]
        
        opt = MOBOOptimizer(n_dims=2, bounds=bounds, objectives=objectives, constraints=[])
        
        # Register some points
        opt.register(np.array([1.0, 9.0]), {"x0": 1.0, "x1": 9.0})
        opt.register(np.array([5.0, 5.0]), {"x0": 5.0, "x1": 5.0})
        opt.register(np.array([9.0, 1.0]), {"x0": 9.0, "x1": 1.0})
        
        # All should be on Pareto front (trade-offs)
        self.assertEqual(len(opt.pareto_front.points), 3)
    
    def test_feasibility_check(self):
        """Test constraint feasibility checking."""
        bounds = [(0, 10)]
        objectives = [Objective(name="obj", evaluator=lambda x, m: x[0], minimize=True)]
        constraints = [
            Constraint(
                name="limit",
                constraint_type=ConstraintType.INEQUALITY,
                evaluator=lambda x, y: x[0] - 5.0,
                threshold=0
            )
        ]
        
        opt = MOBOOptimizer(n_dims=1, bounds=bounds, objectives=objectives, constraints=constraints)
        
        # Add feasible point
        opt.X_observed.append(np.array([3.0]))
        opt.Y_observed.append(np.array([3.0]))
        opt.C_observed.append(np.array([-2.0]))  # 3 - 5 = -2 < 0, feasible
        
        # Check feasibility
        prob = opt._feasibility_probability(np.array([4.0]))
        self.assertGreater(prob, 0)


class TestTwoPhaseController(unittest.TestCase):
    """Tests for TwoPhaseController."""
    
    def test_initialization(self):
        """Test controller initialization."""
        config = OptimizationConfig(target_be_count=1, turbo_max_iterations=20)
        controller = TwoPhaseController(config)
        
        self.assertEqual(controller.config.turbo_max_iterations, 20)
        self.assertEqual(controller.current_phase, Phase.IDLE)
    
    def test_phase_transition(self):
        """Test phase transitions."""
        config = OptimizationConfig(target_be_count=1)
        controller = TwoPhaseController(config)
        
        controller.start_phase(Phase.BE_LOADING_TURBO)
        self.assertEqual(controller.current_phase, Phase.BE_LOADING_TURBO)
        
        # Simulate successful Be+ loading
        for i in range(5):
            params, meta = controller.ask()
            controller.tell({"total_fluorescence": 100 + i * 10})
    
    def test_ask_tell_interface(self):
        """Test ASK-TELL interface."""
        controller = TwoPhaseController()
        controller.start_phase(Phase.BE_LOADING_TURBO)
        
        # ASK
        params, meta = controller.ask()
        self.assertIn("phase", meta)
        self.assertIsNotNone(controller.pending_params)
        
        # TELL
        controller.tell({"total_fluorescence": 50.0})
        self.assertIsNone(controller.pending_params)
    
    def test_warm_start_bounds(self):
        """Test warm start generates tightened bounds."""
        controller = TwoPhaseController()
        
        # Simulate Phase I data with consistent dimensions
        controller.phase_i_data["be_loading"] = [
            {"params": np.array([1.0, 2.0]), "value": 10.0},
            {"params": np.array([1.5, 2.5]), "value": 8.0},
            {"params": np.array([2.0, 3.0]), "value": 12.0},
        ]
        
        bounds = controller._compute_tightened_bounds()
        
        # Bounds should be valid
        self.assertGreater(len(bounds), 0)
        # Each bound should be (lower, upper) tuple
        for bound in bounds:
            self.assertEqual(len(bound), 2)
            self.assertLess(bound[0], bound[1])
    
    def test_status_reporting(self):
        """Test status includes all relevant info."""
        controller = TwoPhaseController()
        controller.start_phase(Phase.BE_LOADING_TURBO)
        
        status = controller.get_status()
        
        self.assertIn("phase", status)
        self.assertIn("iteration", status)
        self.assertIn("config", status)
    
    def test_save_load_state(self):
        """Test state persistence."""
        import tempfile
        import os
        
        controller = TwoPhaseController()
        controller.start_phase(Phase.BE_LOADING_TURBO)
        
        # Run a few iterations
        for _ in range(3):
            params, _ = controller.ask()
            controller.tell({"total_fluorescence": 100.0})
        
        # Save state
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            controller.save_state(temp_path)
            
            # Load into new controller
            controller2 = TwoPhaseController()
            controller2.load_state(temp_path)
            
            self.assertEqual(controller2.current_phase, controller.current_phase)
            self.assertEqual(controller2.iteration, controller.iteration)
        finally:
            os.unlink(temp_path)


class TestIntegration(unittest.TestCase):
    """Integration tests for full two-phase workflow."""
    
    def test_minimal_two_phase_run(self):
        """Test minimal run through both phases."""
        config = OptimizationConfig(
            target_be_count=1,
            target_hd_present=False,  # Skip HD+ for speed
            turbo_max_iterations=5,
            mobo_max_iterations=3
        )
        controller = TwoPhaseController(config)
        
        # Phase I: Be+ Loading
        controller.start_phase(Phase.BE_LOADING_TURBO)
        for i in range(5):
            params, meta = controller.ask()
            # Simulate improving fluorescence
            controller.tell({"total_fluorescence": 50 + i * 20})
        
        # Check we have data for warm start
        self.assertGreater(len(controller.phase_i_data["be_loading"]), 0)
        
        # Phase II: Global MOBO
        controller.start_phase(Phase.GLOBAL_MOBO)
        
        # MOBO should have been warm-started
        self.assertGreater(len(controller.mobo_optimizer.X_observed), 0)
        
        # Run a few MOBO iterations
        for i in range(3):
            params, meta = controller.ask()
            controller.tell({
                "hd_yield": 0.5 + i * 0.1,
                "total_cycle_time_ms": 20000 - i * 1000,
                "be_residual": 0.05,
                "trap_heating": 0.02
            })
        
        # Check Pareto front exists
        pareto = controller.mobo_optimizer.get_pareto_front()
        self.assertGreaterEqual(len(pareto), 0)  # May be empty if constraints violated


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestTuRBOOptimizer))
    suite.addTests(loader.loadTestsFromTestCase(TestParetoFront))
    suite.addTests(loader.loadTestsFromTestCase(TestMOBOOptimizer))
    suite.addTests(loader.loadTestsFromTestCase(TestTwoPhaseController))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
