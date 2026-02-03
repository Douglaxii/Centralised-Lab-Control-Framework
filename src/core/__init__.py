"""
Core module for the Lab Control Framework.

This module provides shared functionality used by all components:
- Configuration management
- Logging setup
- Experiment tracking
- ZMQ utilities
- Enumerations and constants
"""

from .config import get_config, Config
from .logging import setup_logging, log_safety_trigger
from .utils import (
    ExperimentContext,
    ExperimentTracker,
    get_tracker,
    generate_exp_id,
    create_zmq_socket,
    connect_with_retry,
    send_with_timeout,
    recv_with_timeout,
    ZMQConnection,
    HeartbeatSender,
    SystemMode,
    AlgorithmState,
    ExperimentStatus,
    ExperimentPhase,
    DataSource,
    CommandType,
    MatchQuality,
    u_rf_mv_to_U_RF_V,
    U_RF_V_to_u_rf_mv
)
from .exceptions import (
    LabFrameworkError,
    ConnectionError,
    SafetyError,
    TimeoutError,
    HardwareError,
    ConfigurationError,
    ExperimentError
)

__version__ = "2.0.0"

__all__ = [
    # Configuration
    'get_config',
    'Config',
    
    # Logging
    'setup_logging',
    'log_safety_trigger',
    
    # Experiment tracking
    'ExperimentContext',
    'ExperimentTracker',
    'get_tracker',
    'generate_exp_id',
    
    # ZMQ utilities
    'create_zmq_socket',
    'connect_with_retry',
    'send_with_timeout',
    'recv_with_timeout',
    'ZMQConnection',
    'HeartbeatSender',
    
    # Enums
    'SystemMode',
    'AlgorithmState',
    'ExperimentStatus',
    'ExperimentPhase',
    'DataSource',
    'CommandType',
    'MatchQuality',
    'u_rf_mv_to_U_RF_V',
    'U_RF_V_to_u_rf_mv',
    
    # Exceptions
    'LabFrameworkError',
    'ConnectionError',
    'SafetyError',
    'TimeoutError',
    'HardwareError',
    'ConfigurationError',
    'ExperimentError',
]
