"""
Configuration validation schemas for the MLS system.

This module provides Pydantic models for validating configuration files
and ensuring type safety across the application.

Example usage:
    from MLS.config.schemas import load_config, AppConfig
    
    # Load and validate configuration
    config = load_config("development")
    
    # Access validated settings
    print(config.network.master_ip)
    print(config.paths.output_base)
"""

from .config_schema import (
    AppConfig,
    BaseConfig,
    ServicesConfig,
    HardwareConfig,
    NetworkConfig,
    PathsConfig,
    CameraConfig,
    LoggingConfig,
    AnalysisConfig,
    LabVIEWConfig,
    TelemetryConfig,
    load_config,
    load_base_config,
    load_services_config,
    load_hardware_config,
    merge_configs,
)

__all__ = [
    "AppConfig",
    "BaseConfig",
    "ServicesConfig",
    "HardwareConfig",
    "NetworkConfig",
    "PathsConfig",
    "CameraConfig",
    "LoggingConfig",
    "AnalysisConfig",
    "LabVIEWConfig",
    "TelemetryConfig",
    "load_config",
    "load_base_config",
    "load_services_config",
    "load_hardware_config",
    "merge_configs",
]
