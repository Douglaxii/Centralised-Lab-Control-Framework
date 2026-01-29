#!/usr/bin/env python3
"""
Server diagnostic script - Check configuration and environment
"""

import sys
import os

print("=" * 70)
print("LAB CONTROL FRAMEWORK - SERVER DIAGNOSTIC")
print("=" * 70)

# Check Python version
print(f"\n[1] Python Version: {sys.version}")

# Check YAML configuration
print("\n[2] Checking YAML Configuration...")
try:
    import yaml
    config_path = "config/settings.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    print(f"   [OK] YAML parse successful: {config_path}")
    print(f"   [OK] Master IP: {config['network']['master_ip']}")
    print(f"   [OK] Output base: {config['paths']['output_base']}")
except Exception as e:
    print(f"   [ERROR] YAML ERROR: {e}")
    sys.exit(1)

# Check critical imports
print("\n[3] Checking Python Dependencies...")
deps = {
    'cv2': 'opencv-python',
    'numpy': 'numpy',
    'scipy': 'scipy',
    'yaml': 'pyyaml',
    'zmq': 'pyzmq',
    'flask': 'flask',
    'h5py': 'h5py',
    'pandas': 'pandas',
}

missing = []
for module, package in deps.items():
    try:
        __import__(module)
        print(f"   [OK] {package}")
    except ImportError:
        print(f"   [MISSING] {package}")
        missing.append(package)

if missing:
    print(f"\n[!] Missing packages. Install with:")
    print(f"    pip install {' '.join(missing)}")

# Check paths exist
print("\n[4] Checking Paths...")
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from core import get_config
    config = get_config()
    paths_to_check = [
        ('output_base', config.get_path('output_base')),
        ('jpg_frames', config.get_path('jpg_frames')),
        ('jpg_frames_labelled', config.get_path('jpg_frames_labelled')),
    ]

    for name, path in paths_to_check:
        if path:
            exists = os.path.exists(path)
            status = "[OK]" if exists else "[WARN - will be created]"
            print(f"   {status} {name}: {path}")
        else:
            print(f"   [ERROR] {name}: NOT CONFIGURED")
except Exception as e:
    print(f"   [ERROR] Could not check paths: {e}")

# Summary
print("\n" + "=" * 70)
if missing:
    print("RESULT: FAILED - Install missing packages")
    print(f"        pip install {' '.join(missing)}")
else:
    print("RESULT: OK - All checks passed")
    print("        You can now run: python launcher.py")
print("=" * 70)
