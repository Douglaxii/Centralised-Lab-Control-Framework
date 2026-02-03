#!/usr/bin/env python3
"""
Setup script for Manager PC (134.99.120.40)

Ensures:
1. Data directories exist at E:/data
2. Required paths are accessible
3. Camera service can start properly

Usage:
    python setup_manager_pc.py
"""

import os
import sys
from pathlib import Path


def ensure_directories():
    """Create all required data directories."""
    
    # Required data paths for manager PC
    paths = [
        # Base data directory
        'E:/data',
        
        # Camera paths
        'E:/data/jpg_frames',
        'E:/data/jpg_frames_labelled',
        'E:/data/ion_data',
        'E:/data/camera',
        'E:/data/camera/settings',
        'E:/data/camera/frames',
        'E:/data/camera/dcimg',
        'E:/data/camera/live_frames',
        
        # Logs
        'E:/data/logs',
        'E:/data/logs/server',
        'logs',
        'logs/server',
        
        # Analysis and experiments
        'E:/data/analysis',
        'E:/data/analysis/results',
        'E:/data/analysis/settings',
        'E:/data/experiments',
        
        # Telemetry
        'E:/data/telemetry',
        
        # Debug
        'E:/data/debug',
    ]
    
    print("Creating data directories...")
    for path in paths:
        try:
            os.makedirs(path, exist_ok=True)
            print(f"  ✓ {path}")
        except Exception as e:
            print(f"  ✗ {path} - {e}")
            return False
    
    return True


def check_camera_availability():
    """Check if camera hardware is available."""
    try:
        # Try to import camera modules
        sys.path.insert(0, str(Path(__file__).parent / 'src' / 'hardware' / 'camera'))
        from dcamcon import dcam
        print("\nCamera library (dcamcon) found")
        return True
    except ImportError as e:
        print(f"\n⚠ Camera library not available: {e}")
        print("  The camera service will not be able to control hardware.")
        print("  However, the server will still start for testing purposes.")
        return False


def create_env_file():
    """Create environment file for manager PC."""
    env_content = """# MLS Environment Configuration for Manager PC
# IP: 134.99.120.40

MLS_ENV=production
MLS_DATA_ROOT=E:/data
"""
    
    env_path = Path('.env')
    try:
        with open(env_path, 'w') as f:
            f.write(env_content)
        print(f"\n✓ Created environment file: {env_path.absolute()}")
        return True
    except Exception as e:
        print(f"\n✗ Could not create environment file: {e}")
        return False


def main():
    """Main setup routine."""
    print("=" * 60)
    print("MLS Manager PC Setup")
    print("Target: 134.99.120.40 (Manager PC)")
    print("Data Root: E:/data")
    print("=" * 60)
    print()
    
    # Check if running on correct PC
    import socket
    hostname = socket.gethostname()
    try:
        ip = socket.gethostbyname(hostname)
    except:
        ip = "unknown"
    
    print(f"Hostname: {hostname}")
    print(f"IP Address: {ip}")
    print()
    
    # Create directories
    if not ensure_directories():
        print("\n✗ Failed to create directories")
        return 1
    
    print("\n✓ All directories created successfully")
    
    # Check camera
    check_camera_availability()
    
    # Create env file
    create_env_file()
    
    print()
    print("=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Activate conda environment: conda activate mls")
    print("  2. Start services: python src/launcher.py")
    print("  3. Access dashboard: http://134.99.120.40:5000")
    print()
    print("For camera control (separate process):")
    print("  cd src/hardware/camera")
    print("  python camera_server.py")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
