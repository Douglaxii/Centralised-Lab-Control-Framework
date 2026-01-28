"""
Custom exceptions for the Lab Control Framework.
"""


class LabFrameworkError(Exception):
    """Base exception for all lab framework errors."""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "FRAMEWORK_ERROR"
        self.details = details or {}
    
    def __str__(self):
        if self.details:
            return f"[{self.error_code}] {self.message} - Details: {self.details}"
        return f"[{self.error_code}] {self.message}"


class ConnectionError(LabFrameworkError):
    """Raised when network connection fails."""
    
    def __init__(self, message: str, endpoint: str = None, retries: int = None):
        details = {}
        if endpoint:
            details['endpoint'] = endpoint
        if retries is not None:
            details['retries_attempted'] = retries
        super().__init__(message, "CONN_ERROR", details)
        self.endpoint = endpoint


class TimeoutError(LabFrameworkError):
    """Raised when an operation times out."""
    
    def __init__(self, message: str, timeout_seconds: float = None, operation: str = None):
        details = {}
        if timeout_seconds:
            details['timeout_seconds'] = timeout_seconds
        if operation:
            details['operation'] = operation
        super().__init__(message, "TIMEOUT_ERROR", details)
        self.timeout_seconds = timeout_seconds


class HardwareError(LabFrameworkError):
    """Raised when hardware operation fails."""
    
    def __init__(self, message: str, device: str = None, operation: str = None):
        details = {}
        if device:
            details['device'] = device
        if operation:
            details['operation'] = operation
        super().__init__(message, "HARDWARE_ERROR", details)
        self.device = device


class SafetyError(LabFrameworkError):
    """Raised when safety check fails."""
    
    def __init__(self, message: str, safety_system: str = None, trigger_value=None):
        details = {}
        if safety_system:
            details['safety_system'] = safety_system
        if trigger_value is not None:
            details['trigger_value'] = trigger_value
        super().__init__(message, "SAFETY_ERROR", details)
        self.safety_system = safety_system


class ConfigurationError(LabFrameworkError):
    """Raised when configuration is invalid."""
    
    def __init__(self, message: str, config_key: str = None):
        details = {}
        if config_key:
            details['config_key'] = config_key
        super().__init__(message, "CONFIG_ERROR", details)
        self.config_key = config_key


class ExperimentError(LabFrameworkError):
    """Raised when experiment operation fails."""
    
    def __init__(self, message: str, exp_id: str = None, phase: str = None):
        details = {}
        if exp_id:
            details['experiment_id'] = exp_id
        if phase:
            details['phase'] = phase
        super().__init__(message, "EXPERIMENT_ERROR", details)
        self.exp_id = exp_id
