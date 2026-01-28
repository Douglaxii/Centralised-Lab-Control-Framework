"""
Unit tests for core utilities.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest
import tempfile
import shutil
from datetime import datetime

from core import Config, ExperimentContext, get_tracker


class TestConfig(unittest.TestCase):
    """Test configuration management."""
    
    def setUp(self):
        """Create temp config file."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "test_config.yaml"
        
        config_content = """
network:
  master_ip: "192.168.1.50"
  cmd_port: 5555
  
paths:
  test_path: "/tmp/test"
  
hardware:
  worker_defaults:
    ec1: 1.0
"""
        with open(self.config_path, 'w') as f:
            f.write(config_content)
    
    def tearDown(self):
        """Cleanup temp files."""
        shutil.rmtree(self.temp_dir)
    
    def test_config_loading(self):
        """Test config loads from file."""
        config = Config(str(self.config_path))
        self.assertEqual(config.master_ip, "192.168.1.50")
        self.assertEqual(config.cmd_port, 5555)
    
    def test_config_get(self):
        """Test dot-notation access."""
        config = Config(str(self.config_path))
        self.assertEqual(config.get('network.master_ip'), "192.168.1.50")
        self.assertIsNone(config.get('nonexistent.key'))
    
    def test_hardware_defaults(self):
        """Test hardware default retrieval."""
        config = Config(str(self.config_path))
        self.assertEqual(config.get_hardware_default('ec1'), 1.0)


class TestExperimentContext(unittest.TestCase):
    """Test experiment tracking."""
    
    def setUp(self):
        """Setup test directory."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Cleanup."""
        shutil.rmtree(self.temp_dir)
    
    def test_exp_creation(self):
        """Test experiment context creation."""
        exp = ExperimentContext()
        self.assertIsNotNone(exp.exp_id)
        self.assertEqual(exp.status, "created")
        self.assertEqual(exp.phase, "init")
    
    def test_exp_lifecycle(self):
        """Test experiment state transitions."""
        exp = ExperimentContext()
        
        exp.start()
        self.assertEqual(exp.status, "running")
        self.assertIsNotNone(exp.started_at)
        
        exp.transition_to("sweep")
        self.assertEqual(exp.phase, "sweep")
        
        exp.complete()
        self.assertEqual(exp.status, "completed")
        self.assertIsNotNone(exp.completed_at)
    
    def test_exp_save_load(self):
        """Test saving and loading experiment context."""
        exp = ExperimentContext(parameters={"test": 123})
        exp.start()
        exp.add_result("test", {"value": 42})
        
        # Save
        filepath = exp.save(self.temp_dir)
        self.assertTrue(Path(filepath).exists())
        
        # Load
        loaded = ExperimentContext.load(filepath)
        self.assertEqual(loaded.exp_id, exp.exp_id)
        self.assertEqual(loaded.parameters, {"test": 123})


class TestTracker(unittest.TestCase):
    """Test experiment tracker."""
    
    def test_singleton(self):
        """Test tracker is singleton."""
        t1 = get_tracker()
        t2 = get_tracker()
        self.assertIs(t1, t2)
    
    def test_create_and_get(self):
        """Test creating and retrieving experiments."""
        tracker = get_tracker()
        
        exp = tracker.create_experiment(parameters={"type": "test"})
        self.assertIsNotNone(exp.exp_id)
        
        retrieved = tracker.get_experiment(exp.exp_id)
        self.assertIs(retrieved, exp)
        
        # Cleanup
        tracker._experiments.clear()


class TestZMQUtils(unittest.TestCase):
    """Test ZMQ utility functions."""
    
    def test_imports(self):
        """Test that ZMQ utilities can be imported."""
        from core import connect_with_retry, create_zmq_socket
        self.assertTrue(True)  # If we got here, imports work


if __name__ == '__main__':
    unittest.main()
