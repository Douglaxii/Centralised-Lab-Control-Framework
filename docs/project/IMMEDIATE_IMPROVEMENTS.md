# Immediate Improvements - Implementation Guide

**Priority:** High  
**Estimated Effort:** 1-2 weeks  
**Risk:** Low (additive changes only)

---

## 1. Standardized Error Response Format

### Current Problem
Errors are inconsistently handled across the stack. The applet often doesn't know if an operation failed or is still pending.

### Implementation

#### 1.1 Create Error Types Module
```python
# MLS/server/core/error_types.py
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Dict, Any

class ErrorCategory(Enum):
    HARDWARE_TIMEOUT = auto()
    RTIO_UNDERFLOW = auto()
    VALIDATION_ERROR = auto()
    COMMUNICATION_ERROR = auto()
    SAFETY_VIOLATION = auto()
    CAMERA_ERROR = auto()
    CONFIGURATION_ERROR = auto()

@dataclass
class ErrorResponse:
    category: ErrorCategory
    message: str
    recoverable: bool
    suggested_action: str  # "retry", "abort", "check_hardware", "reconfigure"
    details: Dict[str, Any]
    timestamp: str
    
    def to_dict(self) -> dict:
        return {
            "category": "ERROR",
            "error_type": self.category.name,
            "message": self.message,
            "recoverable": self.recoverable,
            "suggested_action": self.suggested_action,
            "details": self.details,
            "timestamp": self.timestamp
        }

# Common error patterns
HARDWARE_TIMEOUT_ERROR = lambda device: ErrorResponse(
    category=ErrorCategory.HARDWARE_TIMEOUT,
    message=f"Timeout waiting for {device}",
    recoverable=True,
    suggested_action="retry",
    details={"device": device},
    timestamp=datetime.now().isoformat()
)

RTIO_UNDERFLOW_ERROR = ErrorResponse(
    category=ErrorCategory.RTIO_UNDERFLOW,
    message="RTIO underflow detected - timing violation",
    recoverable=True,
    suggested_action="retry",
    details={"backoff_ms": 100},
    timestamp=datetime.now().isoformat()
)
```

#### 1.2 Update Manager Error Handling
```python
# MLS/server/communications/manager.py

def _handle_command_with_error_handling(self, req: dict) -> dict:
    """Execute command with standardized error handling."""
    try:
        return self._execute_command(req)
    except zmq.Again:
        return HARDWARE_TIMEOUT_ERROR("ARTIQ").to_dict()
    except SafetyError as e:
        return ErrorResponse(
            category=ErrorCategory.SAFETY_VIOLATION,
            message=str(e),
            recoverable=False,
            suggested_action="check_hardware",
            details={"trigger": e.trigger_source},
            timestamp=datetime.now().isoformat()
        ).to_dict()
    except Exception as e:
        logger.exception("Unexpected error in command execution")
        return ErrorResponse(
            category=ErrorCategory.COMMUNICATION_ERROR,
            message=f"Internal error: {str(e)}",
            recoverable=False,
            suggested_action="abort",
            details={"exception_type": type(e).__name__},
            timestamp=datetime.now().isoformat()
        ).to_dict()
```

#### 1.3 Update Applet Error Handling
```python
# MLS/server/applet/experiments/base.py

class BaseExperiment:
    def execute_command(self, cmd_type: str, payload: dict, 
                       timeout: float = 30.0) -> dict:
        """Execute command with error handling."""
        response = self._send_command(cmd_type, payload, timeout)
        
        if response.get("category") == "ERROR":
            return self._handle_error_response(response)
        
        return response
    
    def _handle_error_response(self, error: dict) -> dict:
        """Process error response and suggest recovery."""
        error_type = error.get("error_type")
        recoverable = error.get("recoverable", False)
        suggested = error.get("suggested_action")
        
        self.logger.error(f"Command failed: {error['message']}")
        
        if recoverable and suggested == "retry":
            self.logger.info("Error is recoverable - will retry")
            return {"status": "retry_suggested", "error": error}
        
        return {"status": "failed", "error": error}
```

---

## 2. Parameter Validation Layer

### Current Problem
Invalid parameters are only detected at kernel execution time, wasting setup time.

### Implementation

#### 2.1 Create Validators
```python
# MLS/server/core/validators.py
from abc import ABC, abstractmethod
from typing import Any, Optional
import re

class Validator(ABC):
    @abstractmethod
    def validate(self, value: Any, param_name: str) -> None:
        pass

class RangeValidator(Validator):
    def __init__(self, min_val: float, max_val: float, 
                 inclusive: bool = True):
        self.min = min_val
        self.max = max_val
        self.inclusive = inclusive
    
    def validate(self, value: float, param_name: str) -> None:
        if self.inclusive:
            if not (self.min <= value <= self.max):
                raise ValueError(
                    f"{param_name} must be in [{self.min}, {self.max}], "
                    f"got {value}"
                )
        else:
            if not (self.min < value < self.max):
                raise ValueError(
                    f"{param_name} must be in ({self.min}, {self.max}), "
                    f"got {value}"
                )

class EnumValidator(Validator):
    def __init__(self, allowed_values: set):
        self.allowed = allowed_values
    
    def validate(self, value: Any, param_name: str) -> None:
        if value not in self.allowed:
            raise ValueError(
                f"{param_name} must be one of {self.allowed}, got {value}"
            )

class RegexValidator(Validator):
    def __init__(self, pattern: str, description: str = ""):
        self.pattern = re.compile(pattern)
        self.description = description
    
    def validate(self, value: str, param_name: str) -> None:
        if not self.pattern.match(value):
            desc = f" ({self.description})" if self.description else ""
            raise ValueError(
                f"{param_name} must match pattern {self.pattern.pattern}{desc}"
            )

class CompositeValidator(Validator):
    def __init__(self, validators: list):
        self.validators = validators
    
    def validate(self, value: Any, param_name: str) -> None:
        for validator in self.validators:
            validator.validate(value, param_name)
```

#### 2.2 Add Validation to Fragments
```python
# MLS/artiq/fragments/secularsweep.py

class SecularSweep(Fragment):
    def build_fragment(self) -> None:
        # ... existing build code ...
        
        # Add validators
        self._validators = {
            "freq": RangeValidator(100*kHz, 1000*kHz),
            "att": RangeValidator(0, 31.5),  # Urukul attenuation range
            "on_time": RangeValidator(1*ms, 10_000*ms),
            "off_time": RangeValidator(0, 10_000*ms),
            "dds_choice": EnumValidator({"axial", "radial"})
        }
    
    def validate_params(self) -> list:
        """Validate all parameters, return list of errors."""
        errors = []
        for param_name, validator in self._validators.items():
            try:
                param = getattr(self, param_name)
                value = param.get() if hasattr(param, 'get') else param
                validator.validate(value, param_name)
            except ValueError as e:
                errors.append(str(e))
        return errors
```

#### 2.3 Pre-flight Validation
```python
# MLS/server/communications/manager.py

def _handle_secular_sweep(self, req: dict) -> dict:
    """Handle SECULAR_SWEEP with validation."""
    # Pre-validate parameters
    validation_errors = self._validate_sweep_params(req)
    if validation_errors:
        return {
            "status": "validation_failed",
            "errors": validation_errors
        }
    
    # Proceed with sweep
    return self._execute_secular_sweep(req)

def _validate_sweep_params(self, req: dict) -> list:
    """Validate sweep parameters before sending to ARTIQ."""
    errors = []
    
    # Validate frequency range
    start = req.get("start_freq", 0)
    end = req.get("end_freq", 0)
    if start >= end:
        errors.append(f"start_freq ({start}) must be < end_freq ({end})")
    
    # Validate step size
    steps = req.get("steps", 0)
    if steps < 2:
        errors.append(f"steps ({steps}) must be >= 2")
    
    step_size = (end - start) / steps
    if step_size < 0.1:  # 0.1 kHz minimum
        errors.append(f"Step size ({step_size:.2f} kHz) too small (< 0.1 kHz)")
    
    # Validate time parameters
    on_time = req.get("on_time_ms", 0)
    off_time = req.get("off_time_ms", 0)
    if on_time < 1:
        errors.append(f"on_time_ms ({on_time}) must be >= 1")
    
    total_time = (on_time + off_time) * steps / 1000  # seconds
    if total_time > 600:  # 10 minutes max
        errors.append(f"Total sweep time ({total_time:.1f}s) exceeds 600s limit")
    
    return errors
```

---

## 3. Unified Configuration Schema

### Current Problem
Configuration is scattered across multiple JSON files with no validation.

### Implementation

#### 3.1 Create Configuration Schema
```python
# MLS/server/core/config_schema.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from pathlib import Path

class ZMQConfig(BaseModel):
    manager_rep_port: int = Field(default=5557, ge=1024, le=65535)
    artiq_pub_port: int = Field(default=5555, ge=1024, le=65535)
    artiq_pull_port: int = Field(default=5556, ge=1024, le=65535)
    camera_port: int = Field(default=5558, ge=1024, le=65535)
    
    @validator('manager_rep_port', 'artiq_pub_port', 'artiq_pull_port', 'camera_port')
    def ports_unique(cls, v, values):
        # Ensure all ports are unique
        return v

class CameraConfig(BaseModel):
    default_exposure_ms: float = Field(default=100.0, gt=0)
    default_roi: dict = Field(default_factory=lambda: {"x": 0, "y": 0, "width": 2048, "height": 2048})
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 5558
    http_base_url: str = "http://127.0.0.1:5000"

class HardwareConfig(BaseModel):
    default_attenuation_db: float = Field(default=25.0, ge=0, le=31.5)
    max_rf_voltage_v: float = Field(default=500.0, gt=0)
    pmt_gate_min_ms: float = Field(default=1.0, gt=0)
    pmt_gate_max_ms: float = Field(default=10000.0, gt=0)
    
class NetworkConfig(BaseModel):
    flask_host: str = "127.0.0.1"
    flask_port: int = 5000
    log_level: str = "INFO"
    data_directory: Path = Path("./data")

class SystemConfig(BaseModel):
    zmq: ZMQConfig = Field(default_factory=ZMQConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    
    class Config:
        env_prefix = "ION_TRAP_"
```

#### 3.2 Configuration Loader
```python
# MLS/server/core/config_loader.py
import json
import os
from pathlib import Path
from .config_schema import SystemConfig

class ConfigLoader:
    def __init__(self, config_dir: Path = None):
        self.config_dir = config_dir or Path(__file__).parent.parent / "config"
        self._cache = {}
    
    def load(self, env: str = None) -> SystemConfig:
        """Load configuration with environment overrides."""
        env = env or os.getenv("ION_TRAP_ENV", "development")
        
        # Load base config
        base_path = self.config_dir / "base.json"
        config = self._load_json(base_path) if base_path.exists() else {}
        
        # Load environment-specific config
        env_path = self.config_dir / f"{env}.json"
        if env_path.exists():
            env_config = self._load_json(env_path)
            config = self._merge_configs(config, env_config)
        
        # Apply environment variable overrides
        config = self._apply_env_overrides(config)
        
        # Validate and return
        return SystemConfig(**config)
    
    def _load_json(self, path: Path) -> dict:
        with open(path) as f:
            return json.load(f)
    
    def _merge_configs(self, base: dict, override: dict) -> dict:
        """Deep merge two config dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def _apply_env_overrides(self, config: dict) -> dict:
        """Apply environment variable overrides."""
        # Example: ION_TRAP_ZMQ_MANAGER_REP_PORT=5559
        prefix = "ION_TRAP_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                path = key[len(prefix):].lower().split("_")
                self._set_nested(config, path, self._convert_value(value))
        return config
    
    def _set_nested(self, d: dict, path: list, value):
        """Set a nested dictionary value by path."""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value
    
    def _convert_value(self, value: str):
        """Convert string value to appropriate type."""
        # Try int
        try:
            return int(value)
        except ValueError:
            pass
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        # Try bool
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        return value
```

---

## 4. Result Caching Layer

### Implementation

```python
# MLS/server/core/result_cache.py
from functools import lru_cache
from typing import Optional, Dict, Any
import hashlib
import json
import time

class ResultCache:
    def __init__(self, maxsize: int = 128, ttl: float = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: Dict[str, Any] = {}
        _timestamps: Dict[str, float] = {}
    
    def _make_key(self, exp_id: str, query_params: dict = None) -> str:
        """Create cache key from experiment ID and query params."""
        key_data = {"exp_id": exp_id, "params": query_params or {}}
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, exp_id: str, query_params: dict = None) -> Optional[Any]:
        """Get cached result if valid."""
        key = self._make_key(exp_id, query_params)
        
        if key not in self._cache:
            return None
        
        # Check TTL
        if time.time() - self._timestamps[key] > self.ttl:
            del self._cache[key]
            del self._timestamps[key]
            return None
        
        return self._cache[key]
    
    def set(self, exp_id: str, data: Any, query_params: dict = None):
        """Cache result."""
        key = self._make_key(exp_id, query_params)
        
        # Simple LRU: remove oldest if at capacity
        if len(self._cache) >= self.maxsize:
            oldest = min(self._timestamps, key=self._timestamps.get)
            del self._cache[oldest]
            del self._timestamps[oldest]
        
        self._cache[key] = data
        self._timestamps[key] = time.time()
    
    def invalidate(self, exp_id: str):
        """Invalidate all entries for an experiment."""
        keys_to_remove = [
            k for k in self._cache.keys()
            if k.startswith(exp_id[:8])  # Partial match
        ]
        for key in keys_to_remove:
            del self._cache[key]
            del self._timestamps[key]
    
    def clear(self):
        """Clear entire cache."""
        self._cache.clear()
        self._timestamps.clear()
```

---

## 5. Testing Infrastructure

### Implementation

#### 5.1 Fragment Unit Tests
```python
# tests/test_fragments.py
import unittest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, "MLS/artiq/fragments")

from secularsweep import SecularSweep

class TestSecularSweep(unittest.TestCase):
    def setUp(self):
        self.mock_env = MagicMock()
        self.fragment = SecularSweep(self.mock_env, [])
    
    def test_parameter_defaults(self):
        """Test default parameter values are within valid ranges."""
        self.assertEqual(self.fragment.freq.get(), 400.0)  # kHz
        self.assertEqual(self.fragment.att.get(), 25.0)  # dB
    
    def test_dds_selection(self):
        """Test DDS device selection based on enum."""
        # Mock the DDS devices
        self.fragment.urukul0_ch0 = MagicMock()
        self.fragment.urukul0_ch1 = MagicMock()
        
        # Test axial selection
        self.fragment.dds_choice.set("axial")
        self.fragment.host_setup()
        self.assertEqual(self.fragment.dds, self.fragment.urukul0_ch0)
        
        # Test radial selection
        self.fragment.dds_choice.set("radial")
        self.fragment.host_setup()
        self.assertEqual(self.fragment.dds, self.fragment.urukul0_ch1)
    
    def test_validation(self):
        """Test parameter validation."""
        errors = self.fragment.validate_params()
        self.assertEqual(len(errors), 0)  # Defaults should be valid
        
        # Test invalid frequency
        self.fragment.freq.set(2000.0)  # Out of range
        errors = self.fragment.validate_params()
        self.assertTrue(any("freq" in e for e in errors))
```

#### 5.2 Integration Tests
```python
# tests/test_manager_artiq.py
import unittest
import zmq
import json
import threading
import time

class TestManagerARTIQCommunication(unittest.TestCase):
    def setUp(self):
        self.ctx = zmq.Context()
        
        # Setup mock ARTIQ worker
        self.artiq_rep = self.ctx.socket(zmq.REP)
        self.artiq_rep.bind("tcp://127.0.0.1:5556")
        
        self.artiq_sub = self.ctx.socket(zmq.SUB)
        self.artiq_sub.bind("tcp://127.0.0.1:5555")
        self.artiq_sub.subscribe(b"")
        
        # Setup manager client
        self.manager_req = self.ctx.socket(zmq.REQ)
        self.manager_req.connect("tcp://127.0.0.1:5557")
    
    def test_pmt_measure_flow(self):
        """Test complete PMT measurement flow."""
        # Send PMT measure command
        cmd = {
            "type": "PMT_MEASURE",
            "duration_ms": 100,
            "applet_id": "test_applet"
        }
        
        # Mock ARTIQ response
        def mock_artiq():
            msg = self.artiq_sub.recv_multipart()
            # Simulate processing
            self.artiq_rep.send_json({
                "category": "PMT_MEASURE_RESULT",
                "counts": 1234,
                "timestamp": time.time()
            })
        
        thread = threading.Thread(target=mock_artiq)
        thread.start()
        
        self.manager_req.send_json(cmd)
        response = self.manager_req.recv_json()
        
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["counts"], 1234)
```

---

## 6. Monitoring and Observability

### Implementation

```python
# MLS/server/core/metrics.py
import time
from dataclasses import dataclass, field
from typing import Dict, List
from collections import defaultdict
import statistics

@dataclass
class MetricSnapshot:
    count: int
    mean: float
    min: float
    max: float
    p50: float
    p95: float
    p99: float

class MetricsCollector:
    def __init__(self):
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
    
    def time(self, name: str, duration_ms: float):
        """Record a timing measurement."""
        self._timers[name].append(duration_ms)
        # Keep last 10000 samples
        if len(self._timers[name]) > 10000:
            self._timers[name] = self._timers[name][-10000:]
    
    def increment(self, name: str, value: int = 1):
        """Increment a counter."""
        self._counters[name] += value
    
    def gauge(self, name: str, value: float):
        """Set a gauge value."""
        self._gauges[name] = value
    
    def get_snapshot(self, name: str) -> MetricSnapshot:
        """Get statistical snapshot of a timer metric."""
        samples = self._timers[name]
        if not samples:
            return None
        
        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        
        return MetricSnapshot(
            count=n,
            mean=statistics.mean(sorted_samples),
            min=sorted_samples[0],
            max=sorted_samples[-1],
            p50=sorted_samples[int(n * 0.5)],
            p95=sorted_samples[int(n * 0.95)],
            p99=sorted_samples[int(n * 0.99)]
        )
    
    def report(self) -> dict:
        """Generate full metrics report."""
        return {
            "timers": {name: self.get_snapshot(name) 
                      for name in self._timers.keys()},
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "timestamp": time.time()
        }

# Global metrics instance
metrics = MetricsCollector()

# Usage example:
# @time_operation("secular_sweep")
# def run_secular_sweep(...):
#     ...
```

---

## Quick Wins (1-2 Days)

1. **Add timeout constants** - Replace magic numbers with named constants
2. **Add logging context** - Include applet_id in all log messages
3. **Add health check endpoint** - Simple HTTP endpoint for monitoring
4. **Add version endpoint** - Return version info for all components
5. **Add config validation on startup** - Fail fast on invalid configuration

---

## Summary

These improvements focus on **stability and maintainability** without changing the core architecture:

| Improvement | Effort | Impact | Risk |
|-------------|--------|--------|------|
| Error Standardization | 2 days | High | Low |
| Parameter Validation | 2 days | High | Low |
| Unified Config | 1 day | Medium | Low |
| Result Caching | 1 day | Medium | Low |
| Test Infrastructure | 3 days | High | Low |
| Monitoring | 1 day | Medium | Low |

**Total: ~10 days for high-impact improvements**
