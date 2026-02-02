#!/usr/bin/env python3
"""
MLS Setup Validation Script

Checks that the conda environment is properly configured and all
dependencies are available.

Usage:
    python validate_setup.py
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple


def check_conda_environment() -> Tuple[bool, str]:
    """Check if running in a conda environment."""
    if sys.prefix != sys.base_prefix or 'conda' in sys.prefix.lower():
        return True, f"Running in conda env: {sys.prefix}"
    return False, "Not running in a conda environment"


def check_python_version() -> Tuple[bool, str]:
    """Check Python version."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor}.{version.micro} (requires 3.10+)"


def check_imports() -> List[Tuple[str, bool, str]]:
    """Check all required imports."""
    packages = [
        ('flask', 'Flask'),
        ('zmq', 'ZMQ'),
        ('numpy', 'NumPy'),
        ('scipy', 'SciPy'),
        ('cv2', 'OpenCV'),
        ('yaml', 'PyYAML'),
        ('pandas', 'Pandas'),
        ('h5py', 'HDF5'),
    ]
    
    results = []
    for module, name in packages:
        try:
            mod = __import__(module)
            version = getattr(mod, '__version__', 'unknown')
            results.append((name, True, f"v{version}"))
        except ImportError as e:
            results.append((name, False, str(e)))
    
    return results


def check_project_structure() -> List[Tuple[str, bool]]:
    """Check that project structure is correct."""
    required = [
        ('core/', 'Core module'),
        ('server/', 'Server modules'),
        ('config/settings.yaml', 'Configuration'),
        ('launcher.py', 'Launcher script'),
        ('.vscode/settings.json', 'VS Code settings'),
    ]
    
    results = []
    for path, desc in required:
        exists = Path(path).exists()
        results.append((desc, exists))
    
    return results


def check_vscode_config() -> Tuple[bool, str]:
    """Check VS Code configuration."""
    vscode_settings = Path('.vscode/settings.json')
    if not vscode_settings.exists():
        return False, "VS Code settings not found"
    
    import json
    try:
        with open(vscode_settings) as f:
            settings = json.load(f)
        
        if 'python.defaultInterpreterPath' in settings:
            return True, "VS Code configured"
        return False, "VS Code settings incomplete"
    except json.JSONDecodeError:
        return False, "Invalid VS Code settings JSON"


def main():
    print("="*60)
    print("MLS Setup Validation")
    print("="*60)
    print()
    
    all_pass = True
    
    # Check conda environment
    print("1. Checking Conda Environment...")
    ok, msg = check_conda_environment()
    status = "✓" if ok else "✗"
    print(f"   {status} {msg}")
    all_pass = all_pass and ok
    print()
    
    # Check Python version
    print("2. Checking Python Version...")
    ok, msg = check_python_version()
    status = "✓" if ok else "✗"
    print(f"   {status} {msg}")
    all_pass = all_pass and ok
    print()
    
    # Check imports
    print("3. Checking Package Imports...")
    import_results = check_imports()
    for name, ok, msg in import_results:
        status = "✓" if ok else "✗"
        print(f"   {status} {name}: {msg}")
        all_pass = all_pass and ok
    print()
    
    # Check project structure
    print("4. Checking Project Structure...")
    structure_results = check_project_structure()
    for desc, exists in structure_results:
        status = "✓" if exists else "✗"
        print(f"   {status} {desc}")
        all_pass = all_pass and exists
    print()
    
    # Check VS Code config
    print("5. Checking VS Code Configuration...")
    ok, msg = check_vscode_config()
    status = "✓" if ok else "✗"
    print(f"   {status} {msg}")
    all_pass = all_pass and ok
    print()
    
    # Summary
    print("="*60)
    if all_pass:
        print("✓ All checks passed! Setup is complete.")
        print()
        print("Next steps:")
        print("  1. Start services: python launcher.py")
        print("  2. Open browser: http://localhost:5000")
        print("  3. Or use VS Code: Press F5 to debug")
    else:
        print("✗ Some checks failed. Please review the errors above.")
        print()
        print("Troubleshooting:")
        print("  - Run setup: python setup_conda.py")
        print("  - See CONDA_SETUP.md for detailed instructions")
        return 1
    print("="*60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
