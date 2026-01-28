"""
Centralized configuration management.
Loads settings from YAML file and provides easy access.
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


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
        if config_path is None:
            # Default location: project_root/config/settings.yaml
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "settings.yaml"
        
        self._config_path = Path(config_path)
        
        if not self._config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(self._config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
    
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
        path = self.get(f'paths.{key}')
        if path is None:
            raise KeyError(f"Path '{key}' not found in configuration")
        
        # Convert to Path object and resolve
        path_obj = Path(path)
        
        # If relative, make it relative to project root
        if not path_obj.is_absolute():
            project_root = Path(__file__).parent.parent
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
