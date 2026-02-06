"""
Centralized configuration management for MLS.
Loads settings from unified YAML config file.

Usage:
    from src.core.config import get_config
    
    config = get_config()
    
    # Access via properties
    print(config.master_ip)
    print(config.flask_port)
    
    # Access nested settings
    print(config.get('hardware.defaults.ec1'))
    print(config.get_path('logs'))

Environment Selection:
    Set MLS_ENV environment variable:
    - MLS_ENV=development  (laptop)
    - MLS_ENV=production   (lab PC)
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Configuration manager for MLS.
    
    Loads unified config.yaml with multiple profiles.
    Active profile selected by 'environment' field or MLS_ENV var.
    """
    
    _instance = None
    _config = None
    _active_profile = None
    
    def __new__(cls, config_path: Optional[str] = None):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(config_path)
        return cls._instance
    
    def _load_config(self, config_path: Optional[str] = None):
        """Load configuration from YAML file."""
        project_root = Path(__file__).parent.parent.parent.parent
        
        if config_path is None:
            config_path = project_root / "config" / "config.yaml"
        
        self._config_path = Path(config_path)
        
        if not self._config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(self._config_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # Get environment from file or env var
        env_from_file = raw_config.get('environment', 'development')
        env_from_env = os.environ.get('MLS_ENV')
        self._active_profile = env_from_env or env_from_file
        
        profiles = raw_config.get('profiles', {})
        
        if self._active_profile not in profiles:
            available = list(profiles.keys())
            raise ValueError(
                f"Unknown environment '{self._active_profile}'. "
                f"Available: {available}. "
                f"Set MLS_ENV or edit config.yaml"
            )
        
        # Load active profile
        self._config = profiles[self._active_profile]
        
        # Store metadata
        self._config['_meta'] = {
            'config_file': str(self._config_path),
            'environment': self._active_profile,
            'description': self._config.get('description', '')
        }
        
        # Create directories
        self._setup_directories(project_root)
    
    def _setup_directories(self, project_root: Path):
        """Create necessary directories."""
        try:
            # Get paths config
            paths = self._config.get('paths', {})
            
            for key, path in paths.items():
                if path:
                    path_obj = Path(path)
                    if not path_obj.is_absolute():
                        path_obj = project_root / path_obj
                    path_obj.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass  # Directories will be created on demand
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation path.
        
        Args:
            key_path: Dot-separated path (e.g., 'network.master_ip')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_path(self, key: str) -> str:
        """
        Get path configuration, resolving relative paths.
        
        Args:
            key: Path key (e.g., 'logs', 'base', 'camera_raw')
            
        Returns:
            Absolute path as string
        """
        path = self.get(f'paths.{key}')
        
        if path is None:
            raise KeyError(f"Path '{key}' not found in configuration")
        
        path_obj = Path(path)
        
        if not path_obj.is_absolute():
            project_root = Path(__file__).parent.parent.parent.parent
            path_obj = project_root / path_obj
        
        return str(path_obj)
    
    # =======================================================================
    # Common Properties
    # =======================================================================
    
    @property
    def environment(self) -> str:
        """Current environment name."""
        return self._active_profile
    
    # Network
    @property
    def master_ip(self) -> str:
        return self.get('network.master_ip', '127.0.0.1')
    
    @property
    def bind_host(self) -> str:
        return self.get('network.bind_host', '127.0.0.1')
    
    @property
    def cmd_port(self) -> int:
        return self.get('network.cmd_port', 5555)
    
    @property
    def data_port(self) -> int:
        return self.get('network.data_port', 5556)
    
    @property
    def client_port(self) -> int:
        return self.get('network.client_port', 5557)
    
    @property
    def camera_port(self) -> int:
        return self.get('network.camera_port', 5558)
    
    # Services
    @property
    def flask_host(self) -> str:
        return self.get('services.flask.host', '127.0.0.1')
    
    @property
    def flask_port(self) -> int:
        return self.get('services.flask.port', 5000)
    
    @property
    def flask_debug(self) -> bool:
        return self.get('services.flask.debug', False)
    
    @property
    def optimizer_port(self) -> int:
        return self.get('services.optimizer.port', 5050)
    
    @property
    def applet_port(self) -> int:
        return self.get('services.applet.port', 5051)
    
    # Hardware
    def hardware_default(self, key: str, default: Any = None) -> Any:
        """Get hardware default value."""
        return self.get(f'hardware.defaults.{key}', default)
    
    @property
    def all_hardware_defaults(self) -> Dict[str, Any]:
        """Get all hardware default values."""
        return self.get('hardware.defaults', {})
    
    # Camera
    @property
    def camera_enabled(self) -> bool:
        return self.get('services.camera.enabled', True)
    
    @property
    def camera_auto_start(self) -> bool:
        return self.get('services.camera.auto_start', False)
    
    @property
    def camera_trigger_mode(self) -> str:
        return self.get('hardware.camera.trigger_mode', 'software')
    
    # LabVIEW
    @property
    def labview_enabled(self) -> bool:
        return self.get('labview.enabled', False)
    
    @property
    def labview_host(self) -> str:
        return self.get('labview.host', '127.0.0.1')
    
    @property
    def labview_port(self) -> int:
        return self.get('labview.port', 5559)
    
    # Logging
    @property
    def log_level(self) -> str:
        return self.get('logging.level', 'INFO')
    
    def log_file(self, name: str) -> str:
        """Get log file path for a component."""
        path = self.get(f'logging.files.{name}')
        if path:
            return self._resolve_path(path)
        return str(Path(__file__).parent.parent.parent.parent / 'logs' / f'{name}.log')
    
    # Optimizer
    @property
    def turbo_settings(self) -> Dict[str, Any]:
        return self.get('optimizer.turbo', {})
    
    @property
    def mobo_settings(self) -> Dict[str, Any]:
        return self.get('optimizer.mobo', {})
    
    # Network settings (backward compatibility)
    def get_network(self, key: str, default: Any = None) -> Any:
        """Get network configuration (backward compatibility)."""
        return self.get(f'network.{key}', default)
    
    # Camera settings (backward compatibility)
    def get_camera_setting(self, key: str, default: Any = None) -> Any:
        """Get camera setting (backward compatibility)."""
        return self.get(f'hardware.camera.{key}', default)
    
    # Hardware settings (backward compatibility)
    def get_hardware_default(self, key: str) -> Any:
        """Get hardware default value (backward compatibility)."""
        return self.hardware_default(key)
    
    def get_all_hardware_defaults(self) -> Dict[str, Any]:
        """Get all hardware default values (backward compatibility)."""
        return self.all_hardware_defaults
    
    # Helper methods
    def _resolve_path(self, path: str) -> str:
        """Resolve a path to absolute."""
        path_obj = Path(path)
        if not path_obj.is_absolute():
            project_root = Path(__file__).parent.parent.parent.parent
            path_obj = project_root / path_obj
        return str(path_obj)
    
    def get_path(self, key: str, default: Any = None) -> str:
        """
        Get a path from configuration and resolve to absolute.
        
        Args:
            key: Path key (e.g., 'jpg_frames', 'jpg_frames_labelled')
            default: Default value if key not found
            
        Returns:
            Absolute path string
        """
        # Try paths.jpg_frames or paths.jpg_frames_labelled first
        path = self.get(f'paths.{key}', default)
        if path is None:
            return None
        return self._resolve_path(path)
    
    def reload(self):
        """Reload configuration from file."""
        self._load_config(self._config_path)
    
    @property
    def config_file(self) -> str:
        """Path to loaded config file."""
        return str(self._config_path)


# Global config instance
_config_instance = None


def get_config(config_path: Optional[str] = None) -> Config:
    """
    Get the global configuration instance.
    
    Args:
        config_path: Optional path to config file (only used on first call)
        
    Returns:
        Config instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance


def reload_config():
    """Reload the global configuration from file."""
    global _config_instance
    if _config_instance is not None:
        _config_instance.reload()
    else:
        get_config()


def get_active_environment() -> str:
    """Get the name of the currently active environment."""
    return get_config().environment
