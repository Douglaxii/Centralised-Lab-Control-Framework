#!/usr/bin/env python3
"""
MLS Conda Environment Setup Script

This script automatically sets up the conda environment for the MLS project.
It handles:
- Creating the conda environment from environment.yml
- Installing pip dependencies
- Setting up VS Code configuration
- Verifying the installation

Usage:
    python setup_conda.py
    python setup_conda.py --env-name mls-custom
    python setup_conda.py --skip-vscode
"""

import subprocess
import sys
import os
import argparse
import json
from pathlib import Path
from typing import Optional, List


def run_command(cmd: List[str], description: str, check: bool = True) -> bool:
    """Run a shell command and report status."""
    print(f"\n{'='*60}")
    print(f"📦 {description}")
    print(f"   Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=False,
            text=True
        )
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            return True
        else:
            print(f"❌ {description} - FAILED (exit code {result.returncode})")
            return False
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - ERROR: {e}")
        return False
    except FileNotFoundError as e:
        print(f"❌ {description} - COMMAND NOT FOUND: {e}")
        return False


def check_conda_installed() -> bool:
    """Check if conda is installed and available."""
    try:
        result = subprocess.run(
            ["conda", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Conda found: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Conda not found!")
        print("   Please install Miniconda or Anaconda:")
        print("   https://docs.conda.io/en/latest/miniconda.html")
        return False


def create_conda_environment(env_name: str) -> bool:
    """Create the conda environment from environment.yml."""
    env_file = Path("environment.yml")
    
    if not env_file.exists():
        print(f"❌ environment.yml not found in {Path.cwd()}")
        return False
    
    # Check if environment already exists
    result = subprocess.run(
        ["conda", "env", "list"],
        capture_output=True,
        text=True
    )
    
    if env_name in result.stdout:
        print(f"⚠️  Environment '{env_name}' already exists")
        response = input("   Do you want to update it? (y/n): ").lower()
        if response == 'y':
            return run_command(
                ["conda", "env", "update", "-f", "environment.yml", "-n", env_name, "--prune"],
                f"Updating conda environment '{env_name}'"
            )
        else:
            print("   Skipping environment creation")
            return True
    
    # Create new environment
    return run_command(
        ["conda", "env", "create", "-f", "environment.yml", "-n", env_name],
        f"Creating conda environment '{env_name}'",
        check=False  # Don't fail immediately, conda might partially succeed
    )


def get_conda_prefix(env_name: str) -> Optional[Path]:
    """Get the conda prefix path for an environment."""
    try:
        result = subprocess.run(
            ["conda", "run", "-n", env_name, "python", "-c", 
             "import sys; print(sys.prefix)"],
            capture_output=True,
            text=True,
            check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def setup_vscode_settings(env_name: str) -> bool:
    """Update VS Code settings with the correct Python interpreter."""
    vscode_dir = Path(".vscode")
    settings_file = vscode_dir / "settings.json"
    
    if not vscode_dir.exists():
        print("⚠️  .vscode directory not found, creating...")
        vscode_dir.mkdir(exist_ok=True)
    
    # Get conda environment path
    conda_prefix = get_conda_prefix(env_name)
    if not conda_prefix:
        print(f"❌ Could not find conda environment '{env_name}'")
        return False
    
    python_path = conda_prefix / "python.exe"
    
    # Read existing settings or create new
    if settings_file.exists():
        with open(settings_file, 'r') as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}
    else:
        settings = {}
    
    # Update settings
    settings["python.defaultInterpreterPath"] = str(python_path)
    settings["python.terminal.activateEnvironment"] = True
    settings["python.condaPath"] = str(Path(sys.executable).parent / "conda.exe")
    
    # Write back
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=4)
    
    print(f"✅ Updated VS Code settings with Python: {python_path}")
    return True


def verify_installation(env_name: str) -> bool:
    """Verify that the environment is properly set up."""
    print(f"\n{'='*60}")
    print("🔍 Verifying Installation")
    print(f"{'='*60}")
    
    test_script = """
import sys
print(f"Python: {sys.executable}")
print(f"Version: {sys.version}")

# Test core imports
try:
    import flask
    print(f"✅ Flask: {flask.__version__}")
except ImportError as e:
    print(f"❌ Flask: {e}")
    sys.exit(1)

try:
    import zmq
    print(f"✅ ZMQ: {zmq.zmq_version()}")
except ImportError as e:
    print(f"❌ ZMQ: {e}")
    sys.exit(1)

try:
    import numpy as np
    print(f"✅ NumPy: {np.__version__}")
except ImportError as e:
    print(f"❌ NumPy: {e}")
    sys.exit(1)

try:
    import cv2
    print(f"✅ OpenCV: {cv2.__version__}")
except ImportError as e:
    print(f"❌ OpenCV: {e}")
    sys.exit(1)

try:
    import yaml
    print(f"✅ PyYAML: OK")
except ImportError as e:
    print(f"❌ PyYAML: {e}")
    sys.exit(1)

print()
print("🎉 All core dependencies verified!")
"""
    
    result = subprocess.run(
        ["conda", "run", "-n", env_name, "python", "-c", test_script],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    return result.returncode == 0


def print_next_steps(env_name: str) -> None:
    """Print instructions for next steps."""
    print(f"\n{'='*60}")
    print("📋 Next Steps")
    print(f"{'='*60}")
    print()
    print("1. Activate the environment:")
    print(f"   conda activate {env_name}")
    print()
    print("2. Start the MLS services:")
    print("   python launcher.py")
    print()
    print("3. Or start services individually:")
    print("   python -m server.communications.manager")
    print("   python -m server.Flask.flask_server")
    print("   python -m server.cam.camera_server")
    print()
    print("4. Access the dashboard:")
    print("   http://localhost:5000")
    print()
    print("5. In VS Code:")
    print("   - Press Ctrl+Shift+P")
    print("   - Type 'Python: Select Interpreter'")
    print(f"   - Choose '{env_name}' environment")
    print("   - Use F5 to run with debugging")
    print()
    print("6. VS Code Tasks (Ctrl+Shift+P -> 'Run Task'):")
    print("   - Start All Services (Launcher)")
    print("   - Start Manager")
    print("   - Start Flask Server")
    print("   - Run Tests")
    print("   - Format Code (Black)")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Setup MLS Conda Environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python setup_conda.py                    # Setup with default name 'mls'
    python setup_conda.py --env-name dev     # Use custom environment name
    python setup_conda.py --skip-vscode      # Don't update VS Code settings
        """
    )
    parser.add_argument(
        "--env-name",
        default="mls",
        help="Name of the conda environment (default: mls)"
    )
    parser.add_argument(
        "--skip-vscode",
        action="store_true",
        help="Skip VS Code configuration"
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip verification step"
    )
    
    args = parser.parse_args()
    
    print(f"""
{'='*60}
  MLS - Multi-Ion Lab System - Conda Setup
{'='*60}
  Environment Name: {args.env_name}
  Working Directory: {Path.cwd()}
{'='*60}
    """)
    
    # Check prerequisites
    if not check_conda_installed():
        sys.exit(1)
    
    # Create conda environment
    if not create_conda_environment(args.env_name):
        print("\n⚠️  Environment creation may have had issues, continuing...")
    
    # Setup VS Code
    if not args.skip_vscode:
        setup_vscode_settings(args.env_name)
    
    # Verify installation
    if not args.skip_verify:
        if verify_installation(args.env_name):
            print("\n✅ Installation verified successfully!")
        else:
            print("\n⚠️  Installation verification had issues")
    
    # Print next steps
    print_next_steps(args.env_name)
    
    print(f"{'='*60}")
    print("Setup complete! 🚀")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
