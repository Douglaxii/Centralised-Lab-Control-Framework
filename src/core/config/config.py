"""
Centralized configuration management.
Loads settings from YAML file and provides easy access.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


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
    """Configuration manager for the lab framework."""
    
    _instance = None
    _config = None
    
    def __new__(cls, config_path: Optional[str] = None):
        """Singleton pattern to ensure one config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(config_path)
        return cls._instance
    
    def _load_config(self, config_path: Optional[str] = None):
        """Load configuration from YAML file."""
        # project_root is MLS (where config/ lives)
        project_root = Path(__file__).parent.parent.parent.parent  # src/core/config -> src/core -> src -> MLS
        
        if config_path is None:
            # Check for legacy settings first
            legacy_config = project_root / "config" / "settings.yaml"
            local_config = project_root / "config" / "settings_local.yaml"
            
            if legacy_config.exists():
                # Use legacy single-file config
                config_path = legacy_config
            elif local_config.exists():
                config_path = local_config
            else:
                # Use new modular config: base.yaml + environment override
                config_path = project_root / "config" / "base.yaml"
        
        self._config_path = Path(config_path)
        
        if not self._config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        # Load base config
        with open(self._config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        
        # If using modular config (base.yaml), load environment overrides
        if self._config_path.name == "base.yaml":
            # Check for environment override
            env = os.environ.get('MLS_ENV', 'development')
            env_config_path = project_root / "config" / "environments" / f"{env}.yaml"
            
            if env_config_path.exists():
                with open(env_config_path, 'r', encoding='utf-8') as f:
                    env_config = yaml.safe_load(f)
                if env_config:
                    self._config = _deep_merge(self._config, env_config)
        
        # Ensure log directory exists
        log_dir = project_root / "logs"
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
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_network(self, key: str) -> Any:
        """Get network configuration."""
        return self.get(f'network.{key}')
    
    def get_path(self, key: str) -> str:
        """
        Get path configuration.
        Automatically resolves relative paths to absolute.
        """
        # Try paths.* first, then fall back to other common path locations
        path = self.get(f'paths.{key}')
        if path is None:
            path = self.get(f'telemetry.{key}')
        if path is None:
            path = self.get(f'camera.{key}')
        
        if path is None:
            raise KeyError(f"Path '{key}' not found in configuration")
        
        # Convert to Path object and resolve
        path_obj = Path(path)
        
        # If relative, make it relative to project root
        if not path_obj.is_absolute():
            project_root = Path(__file__).parent.parent.parent.parent
            path_obj = project_root / path_obj
        
        return str(path_obj)
    
    def get_hardware_default(self, key: str) -> Any:
        """Get hardware default value."""
        return self.get(f'hardware.worker_defaults.{key}')
    
    def get_all_hardware_defaults(self) -> Dict[str, Any]:
        """Get all hardware default values."""
        return self.get('hardware.worker_defaults', {})
    
    def get_camera_setting(self, key: str) -> Any:
        """Get camera setting."""
        return self.get(f'hardware.camera.{key}')
    
    def reload(self):
        """Reload configuration from file."""
        self._load_config(self._config_path)
    
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
