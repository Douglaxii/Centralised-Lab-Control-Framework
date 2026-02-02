"""
Pydantic validation schemas for MLS configuration.

This module provides comprehensive type validation for all configuration
files in the MLS/config directory.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Network Configuration
# =============================================================================

class NetworkConfig(BaseModel):
    """Network and ZMQ configuration."""
    
    master_ip: str = Field(default="127.0.0.1", description="Master PC IP address")
    bind_host: str = Field(default="127.0.0.1", description="Default bind address")
    
    # ZMQ Ports
    cmd_port: int = Field(default=5555, ge=1024, le=65535, description="Command port")
    data_port: int = Field(default=5556, ge=1024, le=65535, description="Data port")
    client_port: int = Field(default=5557, ge=1024, le=65535, description="Client port")
    camera_port: int = Field(default=5558, ge=1024, le=65535, description="Camera port")
    
    # Timeouts
    connection_timeout: float = Field(default=5.0, gt=0, description="Connection timeout in seconds")
    receive_timeout: float = Field(default=1.0, gt=0, description="Receive timeout in seconds")
    watchdog_timeout: float = Field(default=60.0, gt=0, description="Watchdog timeout in seconds")
    heartbeat_interval: float = Field(default=10.0, gt=0, description="Heartbeat interval in seconds")
    
    # Retry settings
    max_retries: int = Field(default=5, ge=0, description="Maximum retry attempts")
    retry_base_delay: float = Field(default=1.0, gt=0, description="Base delay between retries")


# =============================================================================
# Paths Configuration
# =============================================================================

class PathsConfig(BaseModel):
    """Data and file path configuration."""
    
    artiq_data: str = Field(default="C:/artiq-master/results")
    output_base: str = Field(default="./data")
    
    # LabVIEW paths
    labview_tdms: str = Field(default="Y:/Xi/Data/PMT")
    labview_telemetry: str = Field(default="Y:/Xi/Data/telemetry")
    
    # Camera paths
    camera_frames: str = Field(default="Y:/Xi/Data/camera/raw_frames")
    camera_settings: str = Field(default="Y:/Xi/Data/camera/settings")
    camera_dcimg: str = Field(default="Y:/Xi/Data/camera/dcimg")
    live_frames: str = Field(default="Y:/Xi/Data/camera/live_frames")
    
    # Processed data paths
    jpg_frames: str = Field(default="E:/Data/jpg_frames")
    jpg_frames_labelled: str = Field(default="E:/Data/jpg_frames_labelled")
    ion_data: str = Field(default="E:/Data/ion_data")
    
    # Experiment paths
    experiments: str = Field(default="Y:/Xi/Data/experiments")
    analysis_results: str = Field(default="Y:/Xi/Data/analysis/results")
    analysis_settings: str = Field(default="Y:/Xi/Data/analysis/settings")
    
    # Other paths
    dac_settings: str = Field(default="artiq/Settings/DAC/2944_dac_diff_fits.json")
    debug_path: str = Field(default="Y:/Xi/Data/debug")


# =============================================================================
# Hardware Configuration
# =============================================================================

class HardwareWorkerDefaults(BaseModel):
    """ARTIQ worker default values."""
    
    # DC electrodes
    ec1: float = Field(default=0.0, ge=-1.0, le=50.0)
    ec2: float = Field(default=0.0, ge=-1.0, le=50.0)
    comp_h: float = Field(default=0.0, ge=-10.0, le=10.0)
    comp_v: float = Field(default=0.0, ge=-10.0, le=10.0)
    
    # RF and piezo
    u_rf_volts: float = Field(default=200.0, ge=0.0, le=250.0)
    piezo: float = Field(default=0.0, ge=0.0, le=4.0)
    
    # Raman laser frequencies
    freq0: float = Field(default=215.5)
    freq1: float = Field(default=215.5)
    
    # Raman amplitudes
    amp0: float = Field(default=0.05, ge=0.0, le=1.0)
    amp1: float = Field(default=0.05, ge=0.0, le=1.0)
    
    # Shutters and toggles
    sw0: Union[int, bool] = Field(default=0)
    sw1: Union[int, bool] = Field(default=0)
    bephi: Union[int, bool] = Field(default=0)
    b_field: Union[int, bool] = Field(default=1)
    be_oven: Union[int, bool] = Field(default=0)
    uv3: Union[int, bool] = Field(default=0)
    e_gun: Union[int, bool] = Field(default=0)
    
    # Sweep parameters
    sweep_target: float = Field(default=307.0)
    sweep_span: float = Field(default=40.0)
    sweep_att: float = Field(default=25.0)
    sweep_on: float = Field(default=300.0)
    sweep_off: float = Field(default=300.0)
    sweep_points: int = Field(default=41, ge=1)


class CameraSubarray(BaseModel):
    """Camera subarray configuration."""
    
    hsize: int = Field(default=300, gt=0)
    hpos: int = Field(default=1624, ge=0)
    vsize: int = Field(default=600, gt=0)
    vpos: int = Field(default=1396, ge=0)


class HardwareCameraConfig(BaseModel):
    """Camera hardware settings."""
    
    target_temperature: float = Field(default=-20.0)
    cooler_timeout: int = Field(default=300, gt=0)
    max_frames_default: int = Field(default=100, gt=0)
    exposure_default: float = Field(default=0.3, gt=0)
    trigger_mode: Literal["extern", "software", "internal"] = Field(default="extern")
    trigger_delay: float = Field(default=0.033138, ge=0)
    subarray: CameraSubarray = Field(default_factory=CameraSubarray)


class HardwareConfig(BaseModel):
    """Hardware-specific configuration."""
    
    worker_defaults: HardwareWorkerDefaults = Field(default_factory=HardwareWorkerDefaults)
    camera: HardwareCameraConfig = Field(default_factory=HardwareCameraConfig)


# =============================================================================
# LabVIEW Configuration
# =============================================================================

class LabVIEWConfig(BaseModel):
    """LabVIEW SMILE interface configuration."""
    
    enabled: bool = Field(default=True)
    host: str = Field(default="172.17.1.217")
    port: int = Field(default=5559, ge=1024, le=65535)
    timeout: float = Field(default=5.0, gt=0)
    retry_delay: float = Field(default=1.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    auto_reconnect: bool = Field(default=True)
    
    # Pressure safety
    pressure_threshold_mbar: float = Field(default=5.0e-9, gt=0)
    pressure_check_interval: float = Field(default=0.05, gt=0)
    
    # Supported devices
    devices: List[str] = Field(default_factory=lambda: [
        "u_rf", "piezo", "be_oven", "b_field", "bephi",
        "uv3", "e_gun", "hd_valve", "dds"
    ])


# =============================================================================
# Telemetry Configuration
# =============================================================================

class TelemetryConfig(BaseModel):
    """Telemetry data configuration."""
    
    enabled: bool = Field(default=True)
    path: str = Field(default="Y:/Xi/Data/telemetry")
    poll_interval: float = Field(default=1.0, gt=0)
    max_points: int = Field(default=1000, gt=0)
    window_seconds: int = Field(default=300, gt=0)
    tdms_path: str = Field(default="Y:/Xi/Data/PMT")
    tdms_extension: str = Field(default=".tdms")


# =============================================================================
# Camera Control Configuration
# =============================================================================

class CameraInfiniteMode(BaseModel):
    """Camera infinite mode settings."""
    
    max_frames: int = Field(default=100, gt=0)
    exposure_ms: int = Field(default=300, gt=0)
    trigger_mode: Literal["software", "extern"] = Field(default="software")


class CameraProcessing(BaseModel):
    """Camera image processing settings."""
    
    enabled: bool = Field(default=True)
    roi: List[int] = Field(default_factory=lambda: [180, 220, 425, 495])
    filter_radius: int = Field(default=6, gt=0)
    threshold_sigma: float = Field(default=3.0, gt=0)
    max_ions: int = Field(default=5, gt=0)


class CameraConfig(BaseModel):
    """Camera control configuration."""
    
    auto_start: bool = Field(default=True)
    mode: Literal["inf", "single", "dcimg"] = Field(default="inf")
    send_initial_trigger: bool = Field(default=True)
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=5558, ge=1024, le=65535)
    
    # Frame storage paths
    raw_frames_path: str = Field(default="E:/Data/jpg_frames")
    labelled_frames_path: str = Field(default="E:/Data/jpg_frames_labelled")
    ion_data_path: str = Field(default="E:/Data/ion_data")
    
    # Mode settings
    infinite_mode: CameraInfiniteMode = Field(default_factory=CameraInfiniteMode)
    processing: CameraProcessing = Field(default_factory=CameraProcessing)
    
    # HTTP API
    flask_base_url: str = Field(default="http://127.0.0.1:5000")


# =============================================================================
# Logging Configuration
# =============================================================================

class LoggingFiles(BaseModel):
    """Log file paths."""
    
    manager: str = Field(default="Y:/Xi/Data/logs/manager.log")
    worker: str = Field(default="Y:/Xi/Data/logs/artiq_worker.log")
    camera: str = Field(default="Y:/Xi/Data/logs/camera.log")
    analysis: str = Field(default="Y:/Xi/Data/logs/analysis.log")


class LoggingFileRotation(BaseModel):
    """Log file rotation settings."""
    
    max_bytes: int = Field(default=1048576, gt=0)
    backup_count: int = Field(default=5, ge=0)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")
    format: str = Field(default="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s")
    file_rotation: LoggingFileRotation = Field(default_factory=LoggingFileRotation)
    files: LoggingFiles = Field(default_factory=LoggingFiles)


# =============================================================================
# Analysis Configuration
# =============================================================================

class AnalysisSweep(BaseModel):
    """Sweep analysis configuration."""
    
    model: Literal["lorentzian", "gaussian"] = Field(default="lorentzian")
    initial_guess: Dict[str, float] = Field(default_factory=lambda: {"gamma": 5000.0})


class ImageHandlerROI(BaseModel):
    """Image handler ROI configuration."""
    
    x_start: int = Field(default=0, ge=0)
    x_finish: int = Field(default=500, gt=0)
    y_start: int = Field(default=10, ge=0)
    y_finish: int = Field(default=300, gt=0)


class ImageHandlerDetection(BaseModel):
    """Image handler detection parameters."""
    
    threshold_percentile: float = Field(default=99.5, ge=0, le=100)
    min_snr: float = Field(default=6.0, gt=0)
    min_intensity: int = Field(default=35, ge=0)
    max_intensity: int = Field(default=65000, gt=0)
    min_sigma: float = Field(default=2.0, gt=0)
    max_sigma: float = Field(default=30.0, gt=0)
    max_ions: int = Field(default=10, gt=0)
    min_distance: int = Field(default=15, gt=0)
    edge_margin: int = Field(default=20, ge=0)
    bg_kernel_size: int = Field(default=15, gt=0)
    scales: List[int] = Field(default_factory=lambda: [3, 5, 7])


class ImageHandlerVisualization(BaseModel):
    """Image handler visualization parameters."""
    
    panel_height_ratio: float = Field(default=0.25, gt=0, le=1.0)
    font_scale_title: float = Field(default=0.4, gt=0)
    font_scale_data: float = Field(default=0.32, gt=0)
    font_scale_ion_num: float = Field(default=0.45, gt=0)
    crosshair_size: int = Field(default=12, gt=0)
    circle_radius_factor: float = Field(default=1.5, gt=0)


class ImageHandlerPerformance(BaseModel):
    """Image handler performance parameters."""
    
    num_threads: int = Field(default=8, gt=0)
    use_vectorized: bool = Field(default=True)
    use_gpu: bool = Field(default=True)
    jpeg_quality: int = Field(default=85, ge=1, le=100)


class ImageHandlerConfig(BaseModel):
    """Image handler configuration."""
    
    roi: ImageHandlerROI = Field(default_factory=ImageHandlerROI)
    detection: ImageHandlerDetection = Field(default_factory=ImageHandlerDetection)
    visualization: ImageHandlerVisualization = Field(default_factory=ImageHandlerVisualization)
    performance: ImageHandlerPerformance = Field(default_factory=ImageHandlerPerformance)


class AnalysisConfig(BaseModel):
    """Analysis configuration."""
    
    sweep: AnalysisSweep = Field(default_factory=AnalysisSweep)
    image_handler: ImageHandlerConfig = Field(default_factory=ImageHandlerConfig)


# =============================================================================
# Experiment Configuration
# =============================================================================

class ExperimentConfig(BaseModel):
    """Experiment tracking configuration."""
    
    auto_generate_id: bool = Field(default=True)
    id_prefix: str = Field(default="EXP")
    save_metadata: bool = Field(default=True)
    max_frames_keep: int = Field(default=100, gt=0)
    cleanup_interval: int = Field(default=5, gt=0)


# =============================================================================
# Services Configuration
# =============================================================================

class ServiceCameraConfig(BaseModel):
    """Camera service configuration."""
    
    enabled: bool = Field(default=True)
    tcp_port: int = Field(default=5558, ge=1024, le=65535)
    cmd_port: int = Field(default=5559, ge=1024, le=65535)
    host: str = Field(default="127.0.0.1")
    queue_size: int = Field(default=50, gt=0)
    skip_frames: int = Field(default=0, ge=0)
    jpeg_quality: int = Field(default=85, ge=1, le=100)
    raw_frames: str = Field(default="E:/Data/camera/raw_frames")
    labelled_frames: str = Field(default="E:/Data/camera/processed_frames")
    max_concurrent_processing: int = Field(default=2, gt=0)
    use_shared_memory: bool = Field(default=True)


class ServiceManagerConfig(BaseModel):
    """Manager service configuration."""
    
    enabled: bool = Field(default=True)
    cmd_port: int = Field(default=5555, ge=1024, le=65535)
    data_port: int = Field(default=5556, ge=1024, le=65535)
    client_port: int = Field(default=5557, ge=1024, le=65535)
    bind_host: str = Field(default="127.0.0.1")
    labview_host: str = Field(default="192.168.1.100")
    labview_port: int = Field(default=5559, ge=1024, le=65535)
    telemetry_poll_interval: float = Field(default=1.0, gt=0)
    max_worker_threads: int = Field(default=4, gt=0)


class ServiceFlaskConfig(BaseModel):
    """Flask service configuration."""
    
    enabled: bool = Field(default=True)
    http_port: int = Field(default=5000, ge=1024, le=65535)
    host: str = Field(default="0.0.0.0")
    threaded: bool = Field(default=True)
    processes: int = Field(default=1, ge=1)
    max_camera_fps: int = Field(default=30, gt=0)
    telemetry_update_hz: int = Field(default=2, gt=0)


class ServiceHealthConfig(BaseModel):
    """Health monitoring configuration."""
    
    check_interval_seconds: int = Field(default=5, gt=0)
    
    class AutoRestart(BaseModel):
        enabled: bool = Field(default=True)
        max_restarts: int = Field(default=3, ge=0)
        restart_window_seconds: int = Field(default=60, gt=0)
    
    class ResourceLimits(BaseModel):
        max_memory_mb: int = Field(default=2048, gt=0)
        max_cpu_percent: float = Field(default=80.0, ge=0, le=100)
    
    auto_restart: AutoRestart = Field(default_factory=AutoRestart)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)


class ServicesConfig(BaseModel):
    """Services orchestration configuration."""
    
    camera: ServiceCameraConfig = Field(default_factory=ServiceCameraConfig)
    manager: ServiceManagerConfig = Field(default_factory=ServiceManagerConfig)
    flask: ServiceFlaskConfig = Field(default_factory=ServiceFlaskConfig)
    
    dependencies: Dict[str, List[str]] = Field(default_factory=lambda: {
        "camera": [],
        "manager": ["camera"],
        "flask": ["manager"]
    })
    
    health: ServiceHealthConfig = Field(default_factory=ServiceHealthConfig)


# =============================================================================
# Main Configuration Models
# =============================================================================

class BaseConfig(BaseModel):
    """Base configuration model (from base.yaml)."""
    
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    labview: LabVIEWConfig = Field(default_factory=LabVIEWConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    experiment: ExperimentConfig = Field(default_factory=ExperimentConfig)


class AppConfig(BaseModel):
    """Complete application configuration with all sections."""
    
    # Core sections from base.yaml
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    labview: LabVIEWConfig = Field(default_factory=LabVIEWConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    experiment: ExperimentConfig = Field(default_factory=ExperimentConfig)
    
    # Additional sections from other config files
    services: Optional[ServicesConfig] = None
    environment: Optional[str] = Field(default=None, description="Environment name")


# =============================================================================
# Configuration Loading Functions
# =============================================================================

def get_config_dir() -> Path:
    """Get the configuration directory path."""
    # Look for MLS/config relative to this file
    current_file = Path(__file__).resolve()
    config_dir = current_file.parent.parent
    
    if config_dir.exists() and (config_dir / "base.yaml").exists():
        return config_dir
    
    # Fallback: try to find from current working directory
    cwd = Path.cwd()
    for path in [cwd / "MLS/config", cwd / "config"]:
        if path.exists() and (path / "base.yaml").exists():
            return path
    
    raise FileNotFoundError("Could not find configuration directory")


def load_yaml_file(path: Path) -> Dict[str, Any]:
    """Load and parse a YAML configuration file."""
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge override config into base config.
    
    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary
        
    Returns:
        Merged configuration dictionary
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


def load_base_config() -> BaseConfig:
    """Load the base configuration from base.yaml."""
    config_dir = get_config_dir()
    base_path = config_dir / "base.yaml"
    
    data = load_yaml_file(base_path)
    return BaseConfig(**data)


def load_services_config() -> ServicesConfig:
    """Load the services configuration from services.yaml."""
    config_dir = get_config_dir()
    services_path = config_dir / "services.yaml"
    
    data = load_yaml_file(services_path)
    return ServicesConfig(**data.get('services', {}))


def load_hardware_config() -> Dict[str, Any]:
    """Load the hardware configuration from hardware.yaml."""
    config_dir = get_config_dir()
    hardware_path = config_dir / "hardware.yaml"
    
    return load_yaml_file(hardware_path)


def load_config(environment: Optional[str] = None) -> AppConfig:
    """
    Load and merge configuration files.
    
    Loads base.yaml first, then applies environment-specific overrides
    if an environment is specified.
    
    Args:
        environment: Optional environment name (e.g., 'development', 'production')
                    If not specified, tries to get from MLS_ENV environment variable
                    
    Returns:
        Validated AppConfig instance
    """
    # Determine environment
    if environment is None:
        environment = os.environ.get('MLS_ENV', 'development')
    
    config_dir = get_config_dir()
    
    # Load base configuration
    base_data = load_yaml_file(config_dir / "base.yaml")
    
    # Load environment override if specified
    if environment:
        env_path = config_dir / "environments" / f"{environment}.yaml"
        
        # Also check for local.yaml as fallback for development
        if not env_path.exists() and environment == 'development':
            local_path = config_dir / "environments" / "local.yaml"
            if local_path.exists():
                env_path = local_path
        
        if env_path.exists():
            env_data = load_yaml_file(env_path)
            # Remove environment identifier before merging
            env_data.pop('environment', None)
            base_data = merge_configs(base_data, env_data)
    
    # Load services configuration
    services_path = config_dir / "services.yaml"
    if services_path.exists():
        services_data = load_yaml_file(services_path)
        base_data['services'] = services_data.get('services', {})
    
    # Add environment identifier
    base_data['environment'] = environment
    
    return AppConfig(**base_data)


# =============================================================================
# Backward Compatibility
# =============================================================================

def load_legacy_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration in legacy format for backward compatibility.
    
    This function provides a bridge to the old configuration format
    used by the original config.py.
    
    Args:
        config_path: Optional path to legacy settings.yaml
        
    Returns:
        Configuration dictionary in legacy format
    """
    config_dir = get_config_dir()
    
    if config_path is None:
        # Try to find legacy settings.yaml
        legacy_path = config_dir / "settings.yaml"
        if legacy_path.exists():
            return load_yaml_file(legacy_path)
        
        # Fall back to new structure
        config = load_config()
        return config.model_dump()
    
    return load_yaml_file(config_path)
