"""
Centralized configuration management for MLS.

Loads settings from the new modular YAML structure and provides easy access.
The configuration system supports:
- Base configuration (base.yaml)
- Service configuration (services.yaml)
- Hardware configuration (hardware.yaml)
- Environment-specific overrides (environments/*.yaml)
- Pydantic validation (schemas/config_schema.py)

Environment Selection:
    Set MLS_ENV environment variable to choose the environment:
    - MLS_ENV=development (default)
    - MLS_ENV=production
    - MLS_ENV=local (user-specific, gitignored)
    
Example usage:
    from MLS.core.config import get_config
    
    config = get_config()
    
    # Access via properties
    master_ip = config.master_ip
    cmd_port = config.cmd_port
    
    # Access via get() method with dot notation
    exposure = config.get('hardware.camera.exposure_default')
    
    # Get paths (auto-resolves relative paths)
    output_path = config.get_path('output_base')
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Try to import Pydantic schemas
try:
    from ..config.schemas import load_config as _load_schema_config
    from ..config.schemas import AppConfig, BaseConfig, ServicesConfig
    _HAS_PYDANTIC = True
except ImportError:
    _HAS_PYDANTIC = False
    AppConfig = None
    ServicesConfig = None


class Config:
    """
    Configuration manager for the lab framework.
    
    Supports both the new modular structure and legacy settings.yaml format.
    Automatically loads environment-specific overrides based on MLS_ENV.
    
    Attributes:
        _config: The merged configuration dictionary
        _config_path: Path to the primary config file
        _environment: The active environment name
    """
    
    _instance = None
    _config = None
    _environment = None
    _use_pydantic = False
    _pydantic_config = None
    
    def __new__(cls, config_path: Optional[Union[str, Path]] = None, 
                environment: Optional[str] = None,
                use_pydantic: bool = True):
        """
        Singleton pattern to ensure one config instance.
        
        Args:
            config_path: Optional path to a specific config file (legacy mode)
            environment: Environment name to load (e.g., 'development', 'production')
            use_pydantic: Whether to use Pydantic validation if available
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(config_path, environment, use_pydantic)
        return cls._instance
    
    def _get_config_dir(self) -> Path:
        """Get the configuration directory path."""
        # Try relative to this file first
        current_file = Path(__file__).resolve()
        config_dir = current_file.parent.parent / "config"
        
        if config_dir.exists() and (config_dir / "base.yaml").exists():
            return config_dir
        
        # Fallback: look in current working directory
        cwd = Path.cwd()
        for path in [cwd / "MLS/config", cwd / "config"]:
            if path.exists() and (path / "base.yaml").exists():
                return path
        
        raise FileNotFoundError(
            "Could not find configuration directory. "
            "Expected MLS/config/base.yaml to exist."
        )
    
    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load a YAML file."""
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge override into base."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _load_config(self, config_path: Optional[Union[str, Path]] = None,
                     environment: Optional[str] = None,
                     use_pydantic: bool = True):
        """
        Load configuration from YAML files.
        
        Args:
            config_path: Optional legacy config file path
            environment: Environment name (overrides MLS_ENV)
            use_pydantic: Whether to use Pydantic validation
        """
        # Determine environment
        if environment is None:
            environment = os.environ.get('MLS_ENV', 'development')
        self._environment = environment
        
        # Try Pydantic validation first if available
        if use_pydantic and _HAS_PYDANTIC and config_path is None:
            try:
                self._pydantic_config = _load_schema_config(environment)
                self._use_pydantic = True
                self._config = self._pydantic_config.model_dump()
                return
            except Exception as e:
                print(f"Warning: Pydantic validation failed ({e}), falling back to dict mode")
                self._use_pydantic = False
        
        # Legacy or fallback loading
        self._use_pydantic = False
        
        if config_path is not None:
            # Legacy mode: load single file
            self._config_path = Path(config_path)
            self._config = self._load_yaml(self._config_path)
            return
        
        # New modular structure loading
        config_dir = self._get_config_dir()
        
        # Load base configuration
        base_path = config_dir / "base.yaml"
        if not base_path.exists():
            # Fall back to legacy settings.yaml
            legacy_path = config_dir / "settings.yaml"
            if legacy_path.exists():
                self._config_path = legacy_path
                self._config = self._load_yaml(legacy_path)
                return
            raise FileNotFoundError(
                f"No configuration found. Expected {base_path} or {legacy_path}"
            )
        
        self._config = self._load_yaml(base_path)
        self._config_path = base_path
        
        # Load environment override
        env_path = config_dir / "environments" / f"{environment}.yaml"
        
        # Fallback to local.yaml for development
        if not env_path.exists() and environment == 'development':
            local_path = config_dir / "environments" / "local.yaml"
            if local_path.exists():
                env_path = local_path
        
        if env_path.exists():
            env_config = self._load_yaml(env_path)
            # Remove environment key before merging
            env_config.pop('environment', None)
            self._config = self._merge_configs(self._config, env_config)
        
        # Load services configuration
        services_path = config_dir / "services.yaml"
        if services_path.exists():
            services_config = self._load_yaml(services_path)
            self._config = self._merge_configs(self._config, services_config)
        
        # Ensure log directory exists
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation path.
        
        Args:
            key_path: Dot-separated path (e.g., 'network.master_ip')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        if self._use_pydantic and self._pydantic_config is not None:
            # Use Pydantic model navigation
            keys = key_path.split('.')
            value = self._pydantic_config
            
            for key in keys:
                if hasattr(value, key):
                    value = getattr(value, key)
                elif isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            
            return value
        
        # Dict-based navigation
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_network(self, key: str) -> Any:
        """Get network configuration value."""
        return self.get(f'network.{key}')
    
    def get_path(self, key: str) -> str:
        """
        Get path configuration.
        
        Automatically resolves relative paths to absolute paths
        relative to the project root.
        
        Args:
            key: Path key (e.g., 'output_base', 'camera_frames')
            
        Returns:
            Absolute path string
        """
        # Try paths section first
        path = self.get(f'paths.{key}')
        
        # Fall back to service paths
        if path is None:
            path = self.get(f'services.camera.{key}')
        
        # Fall back to camera paths
        if path is None:
            path = self.get(f'camera.{key}_path')
        
        if path is None:
            raise KeyError(f"Path '{key}' not found in configuration")
        
        # Convert to Path object and resolve
        path_obj = Path(path)
        
        # If relative, make it relative to project root
        if not path_obj.is_absolute():
            project_root = Path(__file__).parent.parent
            path_obj = project_root / path_obj
        
        return str(path_obj.resolve())
    
    def get_hardware_default(self, key: str) -> Any:
        """Get hardware default value."""
        return self.get(f'hardware.worker_defaults.{key}')
    
    def get_all_hardware_defaults(self) -> Dict[str, Any]:
        """Get all hardware default values."""
        return self.get('hardware.worker_defaults', {})
    
    def get_camera_setting(self, key: str) -> Any:
        """Get camera setting."""
        return self.get(f'hardware.camera.{key}')
    
    def get_service_config(self, service: str) -> Dict[str, Any]:
        """
        Get service configuration.
        
        Args:
            service: Service name ('camera', 'manager', 'flask')
            
        Returns:
            Service configuration dictionary
        """
        return self.get(f'services.{service}', {})
    
    def reload(self):
        """Reload configuration from files."""
        self._load_config(self._config_path, self._environment, self._use_pydantic)
    
    @property
    def environment(self) -> str:
        """Get the current environment name."""
        return self._environment
    
    @property
    def master_ip(self) -> str:
        """Get master IP address."""
        return self.get_network('master_ip')
    
    @property
    def cmd_port(self) -> int:
        """Get command port."""
        return self.get_network('cmd_port')
    
    @property
    def data_port(self) -> int:
        """Get data port."""
        return self.get_network('data_port')
    
    @property
    def client_port(self) -> int:
        """Get client port."""
        return self.get_network('client_port')
    
    @property
    def camera_port(self) -> int:
        """Get camera port."""
        return self.get_network('camera_port')
    
    @property
    def flask_port(self) -> int:
        """Get Flask HTTP port."""
        return self.get('services.flask.http_port', 5000)
    
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        if self._use_pydantic and self._pydantic_config is not None:
            return self._pydantic_config.model_dump()
        return self._config.copy()
    
    def get_pydantic_config(self) -> Optional[AppConfig]:
        """
        Get the Pydantic configuration model if available.
        
        Returns:
            AppConfig instance or None if not using Pydantic
        """
        return self._pydantic_config if self._use_pydantic else None


# Global config instance
_config_instance = None


def get_config(config_path: Optional[Union[str, Path]] = None,
               environment: Optional[str] = None,
               use_pydantic: bool = True) -> Config:
    """
    Get the global configuration instance.
    
    This function implements the singleton pattern to ensure only one
    configuration instance exists across the application.
    
    Args:
        config_path: Optional path to config file (only used on first call, legacy mode)
        environment: Optional environment name (overrides MLS_ENV)
        use_pydantic: Whether to use Pydantic validation if available
        
    Returns:
        Config instance
        
    Example:
        >>> config = get_config()
        >>> config.get('network.master_ip')
        '134.99.120.40'
        
        >>> config = get_config(environment='production')
        >>> config.environment
        'production'
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path, environment, use_pydantic)
    return _config_instance


def reset_config():
    """
    Reset the global configuration instance.
    
    This is useful for testing or when switching environments
    at runtime. The next call to get_config() will create a new instance.
    """
    global _config_instance
    _config_instance = None


def list_environments() -> list:
    """
    List available environment configurations.
    
    Returns:
        List of environment names available in MLS/config/environments/
    """
    try:
        config = Config.__new__(Config)  # Create without calling __init__
        config_dir = config._get_config_dir()
        env_dir = config_dir / "environments"
        
        if not env_dir.exists():
            return []
        
        environments = []
        for f in env_dir.glob("*.yaml"):
            name = f.stem
            if not name.endswith('.example'):
                environments.append(name)
        
        return sorted(environments)
    except Exception:
        return []


# Backward compatibility aliases
load_config = get_config
ConfigManager = Config
