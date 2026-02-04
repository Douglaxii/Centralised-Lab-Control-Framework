"""
config_loader.py - Configuration Loader for ARTIQ

Phase 3C: External configuration management.

Loads YAML configuration with environment-specific overrides.

Usage:
    from utils.config_loader import get_artiq_config, get_config_value
    
    # Get full config
    config = get_artiq_config()
    ip = config['network']['master_ip']
    
    # Get specific value with default
    port = get_config_value('network.cmd_port', default=5555)
    
    # Get fragment config
    dds_config = get_config_value('fragments.dds')
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Try to import YAML - fallback to JSON if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    import json

# Configuration file paths (in order of loading)
CONFIG_PATHS = [
    # 1. Base configuration
    "config/artiq/artiq_config.yaml",
    
    # 2. Environment-specific (development/production)
    "config/artiq/artiq_config_{environment}.yaml",
    
    # 3. Local machine overrides (not in git)
    "config/artiq/artiq_config_local.yaml",
]

# Cache for loaded config
_config_cache: Optional[Dict[str, Any]] = None


def _load_yaml_or_json(path: str) -> Dict[str, Any]:
    """Load configuration from YAML or JSON file."""
    if not os.path.exists(path):
        return {}
    
    try:
        with open(path, 'r') as f:
            if HAS_YAML and path.endswith('.yaml'):
                return yaml.safe_load(f) or {}
            elif path.endswith('.json'):
                return json.load(f)
            else:
                # Try YAML first, then JSON
                if HAS_YAML:
                    return yaml.safe_load(f) or {}
                else:
                    return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load config from {path}: {e}")
        return {}


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_artiq_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Load ARTIQ configuration with environment-specific overrides.
    
    Loads configuration files in order:
        1. artiq_config.yaml (base)
        2. artiq_config_{environment}.yaml (environment)
        3. artiq_config_local.yaml (local machine)
    
    Args:
        force_reload: Force reloading from disk (ignore cache)
        
    Returns:
        Merged configuration dictionary
        
    Example:
        config = get_artiq_config()
        ip = config['network']['master_ip']
        port = config['network']['cmd_port']
    """
    global _config_cache
    
    # Return cached config if available
    if _config_cache is not None and not force_reload:
        return _config_cache
    
    # Find repository root
    repo_root = Path("/home/artiq/Developer/artiq/artiq-master/repository")
    if not repo_root.exists():
        # Fallback to current directory
        repo_root = Path.cwd()
    
    # Get environment
    environment = os.environ.get('ARTIQ_ENV', 'development')
    
    # Load configurations in order
    config = {}
    
    for path_template in CONFIG_PATHS:
        path = path_template.format(environment=environment)
        full_path = repo_root / path
        
        if full_path.exists():
            loaded = _load_yaml_or_json(str(full_path))
            config = _deep_merge(config, loaded)
    
    # Also check MLS directory (for development on Windows)
    mls_config = Path("D:/MLS/config/artiq/artiq_config.yaml")
    if mls_config.exists():
        loaded = _load_yaml_or_json(str(mls_config))
        config = _deep_merge(config, loaded)
    
    # Cache and return
    _config_cache = config
    return config


def get_config_value(key_path: str, default: Any = None, config: Optional[Dict] = None) -> Any:
    """
    Get a specific configuration value by dot-separated path.
    
    Args:
        key_path: Dot-separated path (e.g., "network.master_ip")
        default: Default value if key not found
        config: Configuration dict (loads if not provided)
        
    Returns:
        Configuration value or default
        
    Example:
        ip = get_config_value('network.master_ip', default='127.0.0.1')
        port = get_config_value('network.cmd_port', default=5555)
    """
    if config is None:
        config = get_artiq_config()
    
    keys = key_path.split('.')
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


def reload_config() -> Dict[str, Any]:
    """Force reload configuration from disk."""
    return get_artiq_config(force_reload=True)


def get_network_config() -> Dict[str, Any]:
    """Get network configuration section."""
    return get_config_value('network', default={})


def get_fragment_config(fragment_name: str) -> Dict[str, Any]:
    """Get configuration for a specific fragment."""
    return get_config_value(f'fragments.{fragment_name}', default={})


def get_experiment_config(exp_name: str) -> Dict[str, Any]:
    """Get configuration for a specific experiment."""
    return get_config_value(f'experiments.{exp_name}', default={})


# Convenience properties for common values
class ConfigShortcuts:
    """Shortcuts for commonly accessed config values."""
    
    @property
    def master_ip(self) -> str:
        return get_config_value('network.master_ip', default='192.168.56.101')
    
    @property
    def cmd_port(self) -> int:
        return get_config_value('network.cmd_port', default=5555)
    
    @property
    def data_port(self) -> int:
        return get_config_value('network.data_port', default=5556)
    
    @property
    def client_port(self) -> int:
        return get_config_value('network.client_port', default=5557)
    
    @property
    def dds_devices(self) -> Dict[str, str]:
        return get_config_value('fragments.dds.devices', default={})
    
    @property
    def pmt_device(self) -> str:
        return get_config_value('fragments.pmt.device', default='ttl0_counter')
    
    @property
    def camera_device(self) -> str:
        return get_config_value('fragments.camera.device', default='ttl4')


# Global shortcuts instance
config = ConfigShortcuts()


# Self-test
if __name__ == "__main__":
    print("Testing config loader...")
    cfg = get_artiq_config()
    print(f"Config loaded: {len(cfg)} top-level keys")
    print(f"  master_ip: {config.master_ip}")
    print(f"  cmd_port: {config.cmd_port}")
    print(f"  data_port: {config.data_port}")
    print(f"  DDS devices: {config.dds_devices}")
    print("Config loader test passed!")
