"""
Automatic path setup and environment detection for MLS.

This module provides:
1. Automatic environment detection (development vs production)
2. Path configuration with environment variable substitution
3. Directory auto-creation on startup
4. Drive detection for network shares (Y:, E:)

Usage:
    from core.config.auto_setup import setup_environment, ensure_directories
    
    # Auto-detect and setup
    env_info = setup_environment()
    
    # Ensure all directories exist
    created = ensure_directories()
"""

import os
import sys
import platform
import socket
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger("config.auto_setup")


def detect_environment() -> str:
    """
    Automatically detect whether running in development or production.
    
    Detection order:
    1. Check MLS_ENV environment variable
    2. Check hostname (manager PC has specific hostname)
    3. Check for network drives (Y:, E:)
    4. Check IP address (manager PC has specific IP)
    5. Default to development
    
    Returns:
        'development' or 'production'
    """
    # 1. Environment variable (explicit override)
    env_var = os.environ.get('MLS_ENV', '').lower()
    if env_var in ('development', 'dev'):
        logger.info("Environment detected from MLS_ENV: development")
        return 'development'
    elif env_var in ('production', 'prod'):
        logger.info("Environment detected from MLS_ENV: production")
        return 'production'
    
    # 2. Hostname check (common manager PC hostnames)
    hostname = socket.gethostname().lower()
    manager_hostnames = ['manager', 'lab-pc', 'server', 'mhi-manager', 'labcontrol']
    if any(h in hostname for h in manager_hostnames):
        logger.info(f"Environment detected from hostname '{hostname}': production")
        return 'production'
    
    # 3. Check for production network drives
    if _check_drive_exists('Y:') and _check_drive_exists('E:'):
        logger.info("Environment detected from network drives (Y:, E:): production")
        return 'production'
    
    # 4. Check IP address (manager PC IP)
    try:
        ip = _get_primary_ip()
        if ip.startswith('134.99.'):  # Production network
            logger.info(f"Environment detected from IP {ip}: production")
            return 'production'
    except Exception:
        pass
    
    # 5. Default to development
    logger.info("Environment auto-detected: development (no production indicators found)")
    return 'development'


def _check_drive_exists(drive: str) -> bool:
    """Check if a drive exists (Windows) or path exists (Linux)."""
    if sys.platform == 'win32':
        import ctypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
        # DRIVE_REMOTE = 4 (network drive), DRIVE_FIXED = 3
        return drive_type in (3, 4)
    else:
        # On Linux, check if the path is mounted
        return os.path.ismount(drive) or os.path.exists(drive)


def _get_primary_ip() -> str:
    """Get the primary IP address of this machine."""
    try:
        # Connect to a remote address to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_drive_options() -> Dict[str, List[str]]:
    """
    Get available drive options for path configuration.
    
    Returns:
        Dict mapping drive type to list of available paths
    """
    options = {
        'data': [],
        'network': [],
        'local_fast': []
    }
    
    # Windows drive detection
    if sys.platform == 'win32':
        import string
        import ctypes
        
        for letter in string.ascii_uppercase:
            drive = f"{letter}:"
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
            
            # DRIVE_FIXED = 3, DRIVE_REMOTE = 4, DRIVE_RAMDISK = 6
            if drive_type == 3:  # Fixed disk
                options['local_fast'].append(f"{drive}/")
                # Check if it looks like a data drive
                if os.path.exists(f"{drive}/data"):
                    options['data'].append(f"{drive}/data")
            elif drive_type == 4:  # Network drive
                options['network'].append(f"{drive}/")
                # Check for common network paths
                for subdir in ['Xi/Data', 'Xi', 'data']:
                    full_path = f"{drive}/{subdir}"
                    if os.path.exists(full_path):
                        options['data'].append(full_path)
    
    # Linux/Mac path detection
    else:
        common_paths = ['/mnt', '/media', '/data', os.path.expanduser('~')]
        for base in common_paths:
            if os.path.exists(base):
                options['data'].append(base)
    
    return options


def substitute_env_vars(config: Dict) -> Dict:
    """
    Recursively substitute environment variables in config strings.
    
    Supports:
    - ${VAR} syntax
    - $VAR syntax
    - %VAR% syntax (Windows style)
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Config with environment variables substituted
    """
    import re
    
    def substitute(value):
        if isinstance(value, str):
            # ${VAR} syntax
            value = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), value)
            # $VAR syntax
            value = re.sub(r'\$(\w+)', lambda m: os.environ.get(m.group(1), m.group(0)), value)
            # %VAR% syntax (Windows)
            value = re.sub(r'%(\w+)%', lambda m: os.environ.get(m.group(1), m.group(0)), value)
        elif isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [substitute(item) for item in value]
        return value
    
    return substitute(config)


def get_auto_paths(environment: str) -> Dict[str, str]:
    """
    Generate automatic path configuration based on environment.
    
    Args:
        environment: 'development' or 'production'
        
    Returns:
        Dictionary of path settings
    """
    project_root = Path(__file__).parent.parent.parent.parent
    
    if environment == 'production':
        # Production: use network drives
        drive_options = get_drive_options()
        
        # Find best data path
        data_base = None
        for path in drive_options.get('data', []):
            if 'Xi/Data' in path or 'Xi' in path:
                data_base = path
                break
        if not data_base:
            data_base = "E:/data" if _check_drive_exists('E:') else "./data"
        
        # Find network path for shared data
        network_base = None
        for path in drive_options.get('network', []):
            if os.path.exists(f"{path}/Xi/Data"):
                network_base = f"{path}/Xi/Data"
                break
        if not network_base:
            network_base = "Y:/Xi/Data" if _check_drive_exists('Y:') else data_base
        
        return {
            'output_base': network_base,
            'artiq_data': "C:/artiq-master/results",
            'labview_tdms': f"{network_base}/PMT",
            'labview_telemetry': f"{network_base}/telemetry",
            'camera_frames': f"{network_base}/camera/raw_frames",
            'jpg_frames': f"{data_base}/jpg_frames",
            'jpg_frames_labelled': f"{data_base}/jpg_frames_labelled",
            'ion_data': f"{data_base}/ion_data",
            'ion_uncertainty': f"{data_base}/ion_uncertainty",
            'camera_settings': f"{data_base}/camera/settings",
            'camera_dcimg': f"{data_base}/camera/dcimg",
            'live_frames': f"{data_base}/camera/live_frames",
            'experiments': f"{network_base}/experiments",
            'analysis_results': f"{network_base}/analysis/results",
            'analysis_settings': f"{network_base}/analysis/settings",
            'debug_path': f"{network_base}/debug",
        }
    else:
        # Development: use local paths
        return {
            'output_base': "./data",
            'artiq_data': "./data/artiq",
            'labview_tdms': "./data/PMT",
            'labview_telemetry': "./data/telemetry",
            'camera_frames': "./data/jpg_frames",
            'jpg_frames': "./data/jpg_frames",
            'jpg_frames_labelled': "./data/jpg_frames_labelled",
            'ion_data': "./data/ion_data",
            'ion_uncertainty': "./data/ion_uncertainty",
            'camera_settings': "./data/camera/settings",
            'camera_dcimg': "./data/camera/dcimg",
            'live_frames': "./data/camera/live_frames",
            'experiments': "./data/experiments",
            'analysis_results': "./data/analysis/results",
            'analysis_settings': "./data/analysis/settings",
            'debug_path': "./data/debug",
        }


def ensure_directories(config=None, paths: Optional[List[str]] = None) -> List[str]:
    """
    Ensure all configured directories exist.
    
    Args:
        config: Config object (optional, will use global if not provided)
        paths: Specific paths to create (optional, will use config paths if not provided)
        
    Returns:
        List of directories that were created
    """
    if paths is None:
        if config is None:
            from core import get_config
            config = get_config()
        
        # Get all path keys from config
        path_keys = [
            'paths.output_base',
            'paths.jpg_frames',
            'paths.jpg_frames_labelled',
            'paths.ion_data',
            'paths.ion_uncertainty',
            'paths.camera_settings',
            'paths.camera_dcimg',
            'paths.live_frames',
            'paths.labview_telemetry',
            'paths.labview_tdms',
            'paths.experiments',
            'paths.analysis_results',
            'paths.debug_path',
        ]
        
        paths = []
        for key in path_keys:
            try:
                path = config.get(key)
                if path:
                    paths.append(path)
            except (KeyError, AttributeError):
                pass
        
        # Also add log directories
        paths.extend(['logs', 'logs/server'])
    
    created = []
    for path in paths:
        try:
            path_obj = Path(path)
            if not path_obj.is_absolute():
                # Resolve relative to project root
                project_root = Path(__file__).parent.parent.parent.parent
                path_obj = project_root / path_obj
            
            if not path_obj.exists():
                path_obj.mkdir(parents=True, exist_ok=True)
                created.append(str(path_obj))
                logger.info(f"Created directory: {path_obj}")
        except Exception as e:
            logger.warning(f"Could not create directory {path}: {e}")
    
    return created


def setup_environment(force_env: Optional[str] = None) -> Dict:
    """
    Perform full environment setup.
    
    This function:
    1. Detects the environment (dev/prod)
    2. Sets MLS_ENV if not already set
    3. Generates appropriate paths
    4. Creates necessary directories
    
    Args:
        force_env: Force a specific environment (optional)
        
    Returns:
        Dictionary with setup information
    """
    # 1. Detect environment
    environment = force_env or detect_environment()
    
    # 2. Set MLS_ENV for this process
    os.environ['MLS_ENV'] = environment
    
    # 3. Generate paths
    auto_paths = get_auto_paths(environment)
    
    # 4. Get drive options (for info)
    drive_options = get_drive_options()
    
    info = {
        'environment': environment,
        'hostname': socket.gethostname(),
        'ip_address': _get_primary_ip(),
        'platform': platform.platform(),
        'auto_paths': auto_paths,
        'drive_options': drive_options,
        'env_var_set': True,
    }
    
    logger.info(f"Environment setup complete: {environment}")
    logger.info(f"Detected drives: {drive_options}")
    
    return info


def validate_setup() -> Tuple[bool, List[str]]:
    """
    Validate that the current setup is correct.
    
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    from core import get_config
    
    issues = []
    config = get_config()
    
    # Check environment
    env = config.environment
    if env not in ('development', 'production'):
        issues.append(f"Unknown environment: {env}")
    
    # Check critical paths
    critical_paths = ['paths.output_base', 'paths.jpg_frames']
    for path_key in critical_paths:
        path = config.get(path_key)
        if not path:
            issues.append(f"Missing config: {path_key}")
        else:
            path_obj = Path(path)
            if not path_obj.is_absolute():
                project_root = Path(__file__).parent.parent.parent.parent
                path_obj = project_root / path_obj
            
            if not path_obj.exists():
                issues.append(f"Path does not exist: {path_key} = {path_obj}")
    
    # Check network connectivity (production only)
    if env == 'production':
        master_ip = config.get('network.master_ip')
        if master_ip:
            # Try to ping the master
            try:
                import socket
                with socket.create_connection((master_ip, 5557), timeout=2):
                    pass
            except Exception:
                issues.append(f"Cannot connect to master at {master_ip}:5557")
    
    is_valid = len(issues) == 0
    return is_valid, issues


# Convenience function for launcher
def auto_configure():
    """
    One-call auto-configuration for use in launcher.
    
    Usage:
        from core.config.auto_setup import auto_configure
        auto_configure()  # Sets up environment and creates directories
    """
    info = setup_environment()
    created = ensure_directories()
    
    if created:
        logger.info(f"Created {len(created)} directories")
    
    return info, created


if __name__ == "__main__":
    # Test the auto-setup
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("MLS Auto-Setup Test")
    print("=" * 60)
    
    # Detect environment
    env = detect_environment()
    print(f"\nDetected environment: {env}")
    
    # Get drive options
    drives = get_drive_options()
    print(f"\nAvailable drives:")
    for dtype, paths in drives.items():
        print(f"  {dtype}: {paths}")
    
    # Generate auto paths
    paths = get_auto_paths(env)
    print(f"\nAuto-generated paths for {env}:")
    for key, path in paths.items():
        print(f"  {key}: {path}")
    
    # Validate setup
    print("\nValidating setup...")
    is_valid, issues = validate_setup()
    if is_valid:
        print("  ✓ Setup is valid")
    else:
        print("  ✗ Issues found:")
        for issue in issues:
            print(f"    - {issue}")
