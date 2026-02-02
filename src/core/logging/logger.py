"""
Logging utilities for the Lab Control Framework.
Provides structured logging with rotation.
"""

import os
import logging
import logging.handlers
from pathlib import Path
from typing import Optional
from datetime import datetime

from .config import get_config


class StructuredLogFormatter(logging.Formatter):
    """Custom formatter that includes structured data."""
    
    def format(self, record):
        # Add timestamp in ISO format
        record.iso_timestamp = datetime.utcnow().isoformat()
        
        # Add experiment ID if available
        if not hasattr(record, 'exp_id'):
            record.exp_id = 'N/A'
        
        return super().format(record)


def get_logger(name: str, exp_id: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically __name__)
        exp_id: Optional experiment ID to include in all logs
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # If exp_id provided, add it to logger context
    if exp_id:
        old_factory = logging.getLogRecordFactory()
        
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.exp_id = exp_id
            return record
        
        logging.setLogRecordFactory(record_factory)
    
    return logger


def setup_logging(
    log_file: Optional[str] = None,
    level: str = "INFO",
    component: Optional[str] = None,
    enable_console: bool = True
) -> logging.Logger:
    """
    Setup logging for a component.
    
    Args:
        log_file: Path to log file (if None, uses config default)
        level: Logging level
        component: Component name for default log file
        enable_console: Whether to also log to console
        
    Returns:
        Logger instance
    """
    config = get_config()
    
    # Get log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Get format
    log_format = config.get('logging.format', 
                           '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
    
    # Setup root logger for this component
    if component:
        logger = logging.getLogger(component)
    else:
        logger = logging.getLogger()
    
    logger.setLevel(log_level)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers = []
    
    # Create formatter
    formatter = StructuredLogFormatter(log_format)
    
    # File handler
    if log_file or component:
        if not log_file and component:
            # Use default path from config
            log_file = config.get(f'logging.files.{component}', f'logs/{component}.log')
        
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Rotating file handler
        max_bytes = config.get('logging.file_rotation.max_bytes', 1048576)
        backup_count = config.get('logging.file_rotation.backup_count', 5)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        logger.addHandler(console_handler)
    
    return logger


class ExperimentLogAdapter(logging.LoggerAdapter):
    """Adapter that automatically includes experiment ID in all logs."""
    
    def __init__(self, logger: logging.Logger, exp_id: str):
        super().__init__(logger, {'exp_id': exp_id})
    
    def process(self, msg, kwargs):
        # Add exp_id to the message
        return f"[{self.extra['exp_id']}] {msg}", kwargs


def get_experiment_logger(component: str, exp_id: str) -> ExperimentLogAdapter:
    """
    Get a logger that automatically includes experiment ID.
    
    Args:
        component: Component name
        exp_id: Experiment ID
        
    Returns:
        Logger adapter with experiment context
    """
    base_logger = logging.getLogger(component)
    return ExperimentLogAdapter(base_logger, exp_id)


def log_safety_trigger(
    logger: logging.Logger,
    trigger_type: str,
    previous_state: dict,
    safety_state: dict,
    exp_id: Optional[str] = None
):
    """
    Log a safety trigger event with full context.
    
    Args:
        logger: Logger instance
        trigger_type: Type of safety trigger (watchdog, connection_loss, etc.)
        previous_state: State before safety activation
        safety_state: Safety state applied
        exp_id: Optional experiment ID
    """
    extra = {
        'event_type': 'safety_trigger',
        'trigger_type': trigger_type,
        'previous_state': previous_state,
        'safety_state': safety_state,
    }
    
    if exp_id:
        extra['exp_id'] = exp_id
    
    logger.warning(
        f"SAFETY TRIGGER: {trigger_type} - Previous: {previous_state}, "
        f"Applied: {safety_state}",
        extra=extra
    )
