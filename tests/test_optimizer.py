"""
Unit tests for the Bayesian optimization module (Two-Phase Architecture).
"""

import unittest
import numpy as np
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from server.optimizer import (
    ParameterSpace,
    BeLoadingObjective,
    BeEjectionObjective,
    HdLoadingObjective,
    TwoPhaseController,
    Phase,
    OptimizationConfig,
    ProfileStorage,
    create_be_loading_space,
    create_be_ejection_space,
    create_hd_loading_space
)


class TestParameterSpace(unittest.TestCase):
    """Tests for parameter space definitions."""
    
    def test_parameter_bounds(self):
        """Test that parameter bounds are correctly set."""
        space = create_be_loading_space()
        
        # Check that bounds are returned correctly
        bounds = space.get_bounds_list()
        self.assertGreater(len(bounds), 0)
        
        # Check each bound is a tuple of (min, max)
        for bound in bounds:
            self.assertEqual(len(bound), 2)
            self.assertLess(bound[0], bound[1])
    
    def test_array_conversion(self):
        """Test conversion between dict and array representations."""
        space = create_be_loading_space()
        
        # Create a test parameter dict
        params = {"piezo": 2.0, "be_pi_laser_duration_ms": 500}
        
        # Convert to array (only valid params)
        arr = space.dict_to_array(params)
        self.assertIsInstance(arr, np.ndarray)
        
        # Convert back to dict
        params_back = space.array_to_dict(arr)
        self.assertIsInstance(params_back, dict)
    
    def test_be_loading_space(self):
        """Test Be+ loading parameter space."""
        space = create_be_loading_space()
        
        # Check required parameters exist
        self.assertIn("piezo", space.parameters)
        self.assertIn("be_pi_laser_duration_ms", space.parameters)
        
        # Check bounds
        piezo_param = space.parameters["piezo"]
        self.assertEqual(piezo_param.bounds, (0.0, 4.0))
    
    def test_time_windows(self):
        """Test absolute time window parameters."""
        space = create_be_loading_space()
        
        # Check oven timing parameters
        self.assertIn("be_oven_start_ms", space.parameters)
        self.assertIn("be_oven_duration_ms", space.parameters)
        
        # Check PI laser timing parameters
        self.assertIn("be_pi_laser_start_ms", space.parameters)
        self.assertIn("be_pi_laser_duration_ms", space.parameters)


class TestObjectives(unittest.TestCase):
    """Tests for objective functions."""
    
    def test_be_loading_cost(self):
        """Test Be+ loading cost function."""
        obj = BeLoadingObjective(target_ion_count=1)
        
        # Test with correct ion count
        cost, components = obj.compute_cost(
            params={"cooling_power_mw": 0.5, "be_pi_laser_duration_ms": 300},
            measurements={
                "ion_count": 1,
                "secular_freq": 307.0,
                "total_time_ms": 5000
            }
        )
        self.assertIsInstance(cost, float)
        self.assertGreater(cost, 0)
        self.assertIsInstance(components, dict)
        
        # Test with wrong ion count - should have higher cost
        cost_wrong, _ = obj.compute_cost(
            params={"cooling_power_mw": 0.5, "be_pi_laser_duration_ms": 300},
            measurements={
                "ion_count": 2,
                "secular_freq": 307.0,
                "total_time_ms": 5000
            }
        )
        self.assertGreater(cost_wrong, cost)  # Should be worse
    
    def test_be_loading_success(self):
        """Test Be+ loading success detection."""
        obj = BeLoadingObjective(target_ion_count=1)
        
        # Success case
        self.assertTrue(obj.is_success({
            "ion_count": 1,
            "secular_freq": 307.0
        }))
        
        # Failure cases
        self.assertFalse(obj.is_success({"ion_count": 0}))
        self.assertFalse(obj.is_success({"ion_count": 2}))
    
    def test_be_ejection_cost(self):
        """Test Be+ ejection cost function."""
        obj = BeEjectionObjective(target_ion_count=1)
        
        cost, components = obj.compute_cost(
            params={"tickle_amplitude": 0.5, "tickle_duration_ms": 100},
            measurements={
                "ion_count": 1,
                "initial_count": 3,
                "total_time_ms": 3000
            }
        )
        
        self.assertIsInstance(cost, (float, int))
        self.assertIsInstance(components, dict)
        # Cost should be negative (reward) when target is achieved
        self.assertLess(cost, 0, "Cost should be negative (reward) when target achieved")
    
    def test_hd_loading_cost(self):
        """Test HD+ loading cost function."""
        obj = HdLoadingObjective()
        
        cost, components = obj.compute_cost(
            params={"hd_egun_duration_ms": 800},
            measurements={
                "sweep_peak_found": True,
                "sweep_peak_freq": 277.0,
                "dark_ion_dip_depth": 0.8
            }
        )
        
        self.assertIsInstance(cost, float)
        self.assertIsInstance(components, dict)


class TestTwoPhaseController(unittest.TestCase):
    """Tests for the two-phase controller."""
    
    def test_initialization(self):
        """Test controller initialization."""
        config = OptimizationConfig(target_be_count=1)
        controller = TwoPhaseController(config)
        
        self.assertEqual(controller.config.target_be_count, 1)
        self.assertEqual(controller.current_phase, Phase.IDLE)
    
    def test_start_stop(self):
        """Test start and stop."""
        config = OptimizationConfig(target_be_count=1)
        controller = TwoPhaseController(config)
        
        controller.start_phase(Phase.BE_LOADING_TURBO)
        self.assertEqual(controller.current_phase, Phase.BE_LOADING_TURBO)
        
        # Test ASK-TELL
        params, meta = controller.ask()
        self.assertIsNotNone(params)
        self.assertIsNotNone(controller.pending_params)  # Check if waiting for result
        
        # Use low fluorescence to avoid triggering phase transition
        controller.tell({"total_fluorescence": 0.5})
        self.assertIsNone(controller.pending_params)  # Result received
    
    def test_ask_tell_interface(self):
        """Test ASK-TELL interface."""
        config = OptimizationConfig(
            target_be_count=1,
            turbo_max_iterations=10,
            turbo_n_init=2
        )
        controller = TwoPhaseController(config)
        controller.start_phase(Phase.BE_LOADING_TURBO)
        
        # Get suggestion
        params, meta = controller.ask()
        self.assertIsNotNone(params)
        self.assertIn("phase", meta)
        self.assertTrue(len(params) > 0, "params should not be empty")
        self.assertIsNotNone(controller.pending_params, "pending_params should be set after ask()")
        
        # Register result (use low fluorescence to not trigger phase transition)
        controller.tell({
            "total_fluorescence": 0.5,  # Below turbo_success_threshold of 0.9
            "cycle_time_ms": 5000
        })
        
        self.assertEqual(controller.iteration, 1)
    
    def test_phase_transition(self):
        """Test phase transitions."""
        config = OptimizationConfig(
            target_be_count=1,
            target_hd_present=True
        )
        controller = TwoPhaseController(config)
        
        # Manually transition phases
        controller.start_phase(Phase.BE_LOADING_TURBO)
        self.assertEqual(controller.current_phase, Phase.BE_LOADING_TURBO)
        
        controller.start_phase(Phase.HD_LOADING_TURBO)
        self.assertEqual(controller.current_phase, Phase.HD_LOADING_TURBO)


class TestProfileStorage(unittest.TestCase):
    """Tests for profile storage."""
    
    def setUp(self):
        """Set up test storage."""
        self.test_file = Path("test_profiles.json")
        if self.test_file.exists():
            self.test_file.unlink()
    
    def tearDown(self):
        """Clean up test file."""
        if self.test_file.exists():
            self.test_file.unlink()
    
    def test_save_and_load(self):
        """Test saving and loading profiles."""
        storage = ProfileStorage(filepath=str(self.test_file))
        
        # Save a profile
        storage.save_profile(
            be_count=1,
            hd_present=False,
            phase="be_loading",
            params={"piezo": 2.0, "pi_duration": 300},
            cost=45.0
        )
        
        # Load it back
        params = storage.get_be_loading_params(be_count=1, hd_present=False)
        self.assertIsNotNone(params)
        self.assertEqual(params["piezo"], 2.0)
    
    def test_profile_listing(self):
        """Test listing profiles."""
        storage = ProfileStorage(filepath=str(self.test_file))
        
        # Add multiple profiles
        storage.save_profile(1, False, "be_loading", {"a": 1}, 10.0)
        storage.save_profile(2, False, "be_loading", {"a": 2}, 20.0)
        storage.save_profile(1, True, "hd_loading", {"b": 1}, 30.0)
        
        profiles = storage.list_profiles()
        self.assertEqual(len(profiles), 3)


class TestIntegration(unittest.TestCase):
    """Integration tests."""
    
    def test_full_optimization_loop(self):
        """Test a full optimization loop."""
        # Create controller
        config = OptimizationConfig(
            target_be_count=1,
            turbo_max_iterations=10,
            turbo_n_init=2
        )
        controller = TwoPhaseController(config)
        controller.start_phase(Phase.BE_LOADING_TURBO)
        
        # Run a few iterations
        for i in range(5):
            if controller.is_complete():
                break
            
            params, meta = controller.ask()
            if params is None:
                break
            
            # Simulate measurement - simulate fluorescence response
            # Use low values to avoid triggering phase transition
            # (threshold is turbo_success_threshold = 0.9)
            piezo = params.get("piezo", 0.5)
            pi_dur = params.get("be_pi_laser_duration_ms", 500)
            
            # Closer to optimal = higher fluorescence, but cap at 0.8 to avoid transition
            fluorescence = 0.5 - abs(pi_dur - 300) / 10000 - abs(piezo - 0.5) * 0.2
            fluorescence += np.random.normal(0, 0.05)  # Add small noise
            fluorescence = max(0.1, min(0.8, fluorescence))  # Clamp between 0.1 and 0.8
            
            controller.tell({
                "total_fluorescence": fluorescence,
                "cycle_time_ms": 5000 + np.random.normal(0, 100)
            })
        
        # Check results
        self.assertGreater(controller.iteration, 0)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestParameterSpace))
    suite.addTests(loader.loadTestsFromTestCase(TestObjectives))
    suite.addTests(loader.loadTestsFromTestCase(TestTwoPhaseController))
    suite.addTests(loader.loadTestsFromTestCase(TestProfileStorage))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
