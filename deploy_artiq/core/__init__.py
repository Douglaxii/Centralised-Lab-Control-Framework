"""
Core utilities for the Lab Control Framework.

This module provides shared functionality for:
- Configuration management
- Logging setup
- ZMQ communication helpers
- Custom exceptions
- Experiment tracking
"""

from .config import Config, get_config
from .logger import get_logger, setup_logging, log_safety_trigger
from .exceptions import (
    LabFrameworkError,
    ConnectionError,
    TimeoutError,
    HardwareError,
    SafetyError,
)
from .zmq_utils import (
    connect_with_retry,
    create_zmq_socket,
    send_with_timeout,
    recv_with_timeout,
)
from .experiment import ExperimentContext, get_tracker
from .enums import (
    SystemMode,
    AlgorithmState,
    ExperimentStatus,
    ExperimentPhase,
    DataSource,
    CommandType,
    MatchQuality,
    RF_SCALE_V_PER_MV,
    RF_SCALE_MV_PER_V,
    smile_mv_to_real_volts,
    real_volts_to_smile_mv,
)

__all__ = [
    'Config',
    'get_config',
    'get_logger',
    'setup_logging',
    'log_safety_trigger',
    'LabFrameworkError',
    'ConnectionError',
    'TimeoutError',
    'HardwareError',
    'SafetyError',
    'connect_with_retry',
    'create_zmq_socket',
    'send_with_timeout',
    'recv_with_timeout',
    'ExperimentContext',
    'get_tracker',
    # Enums
    'SystemMode',
    'AlgorithmState',
    'ExperimentStatus',
    'ExperimentPhase',
    'DataSource',
    'CommandType',
    'MatchQuality',
    # RF Voltage utilities
    'RF_SCALE_V_PER_MV',
    'RF_SCALE_MV_PER_V',
    'smile_mv_to_real_volts',
    'real_volts_to_smile_mv',
]
