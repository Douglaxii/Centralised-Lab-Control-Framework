"""
Centralized configuration management.
Loads settings from YAML file and provides easy access.

This version supports a UNIFIED config file with multiple profiles.

Usage:
    from core import get_config
    
    config = get_config()
    ip = config.master_ip
    port = config.get('network.client_port')
    
Environment Switching:
    Set MLS_ENV environment variable or change 'environment' in config.yaml:
    - MLS_ENV=development  (for laptop)
    - MLS_ENV=production   (for manager PC)
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
    """Configuration manager for the lab framework.
    
    Supports unified config file with multiple profiles.
    The active profile is selected by the 'environment' field.
    """
    
    _instance = None
    _config = None
    _active_profile = None
    
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
        
        # Determine config file path
        if config_path is None:
            # Priority:
            # 1. Unified config.yaml (new style)
            # 2. Legacy settings.yaml (old style)
            # 3. Legacy settings_local.yaml (old style)
            # 4. Modular base.yaml (intermediate style)
            
            unified_config = project_root / "config" / "config.yaml"
            legacy_config = project_root / "config" / "settings.yaml"
            local_config = project_root / "config" / "settings_local.yaml"
            base_config = project_root / "config" / "base.yaml"
            
            if unified_config.exists():
                config_path = unified_config
            elif legacy_config.exists():
                config_path = legacy_config
            elif local_config.exists():
                config_path = local_config
            else:
                config_path = base_config
        
        self._config_path = Path(config_path)
        
        if not self._config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        # Load config file
        with open(self._config_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)
        
        # Check if this is a unified config with profiles
        if 'profiles' in raw_config and isinstance(raw_config['profiles'], dict):
            # Unified config format
            self._load_unified_config(raw_config, project_root)
        elif self._config_path.name == "base.yaml":
            # Modular config: base.yaml + environment override
            self._config = raw_config
            env = os.environ.get('MLS_ENV', 'development')
            env_config_path = project_root / "config" / "environments" / f"{env}.yaml"
            
            if env_config_path.exists():
                with open(env_config_path, 'r', encoding='utf-8') as f:
                    env_config = yaml.safe_load(f)
                if env_config:
                    self._config = _deep_merge(self._config, env_config)
            self._active_profile = env
        else:
            # Legacy single-file config
            self._config = raw_config
            self._active_profile = raw_config.get('environment', 'unknown')
        
        # Ensure log directory exists
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
    
    def _load_unified_config(self, raw_config: Dict, project_root: Path):
        """Load configuration from unified format with profiles.
        
        Args:
            raw_config: The raw parsed YAML config
            project_root: Path to project root for resolving relative paths
        """
        # Get active environment (from env var or config file)
        env_from_file = raw_config.get('environment', 'development')
        env_from_env = os.environ.get('MLS_ENV')
        self._active_profile = env_from_env or env_from_file
        
        profiles = raw_config.get('profiles', {})
        
        if self._active_profile not in profiles:
            available = list(profiles.keys())
            raise ValueError(
                f"Unknown environment '{self._active_profile}'. "
                f"Available: {available}. "
                f"Check 'environment' in config.yaml or set MLS_ENV environment variable."
            )
        
        # Load the active profile
        profile_config = profiles[self._active_profile]
        
        # Profile should be a dict with the actual configuration
        if not isinstance(profile_config, dict):
            raise ValueError(
                f"Profile '{self._active_profile}' must be a dictionary containing configuration settings"
            )
        
        # The profile IS the config (it contains network, paths, hardware, etc.)
        self._config = profile_config
        
        # Store metadata
        self._config['_meta'] = {
            'config_file': str(self._config_path),
            'environment': self._active_profile,
            'description': profile_config.get('description', 'No description')
        }
    
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
    def environment(self) -> str:
        """Get current environment name."""
        return self._active_profile or 'unknown'
    
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
    def config_file(self) -> str:
        """Get path to the loaded config file."""
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
