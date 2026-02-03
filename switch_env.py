#!/usr/bin/env python3
"""
Environment Switcher for MLS

Quickly switch between development (laptop) and production (manager PC) environments.

Usage:
    python switch_env.py              # Show current environment
    python switch_env.py dev          # Switch to development
    python switch_env.py prod         # Switch to production
    python switch_env.py development  # Switch to development (explicit)
    python switch_env.py production   # Switch to production (explicit)

The configuration is stored in config/config.yaml
"""

import sys
import re
from pathlib import Path


def get_config_path() -> Path:
    """Get the path to the unified config file."""
    return Path(__file__).parent / "config" / "config.yaml"


def read_config() -> str:
    """Read the config file content."""
    config_path = get_config_path()
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        print("Make sure you're running this from the MLS directory.")
        sys.exit(1)
    return config_path.read_text(encoding='utf-8')


def write_config(content: str):
    """Write content to config file."""
    config_path = get_config_path()
    config_path.write_text(content, encoding='utf-8')


def get_current_env(config_content: str) -> str:
    """Extract current environment from config content."""
    match = re.search(r'^environment:\s*(\w+)', config_content, re.MULTILINE)
    if match:
        return match.group(1)
    return "unknown"


def set_environment(env: str) -> bool:
    """Set the active environment in config file."""
    if env not in ['development', 'production']:
        print(f"Error: Unknown environment '{env}'")
        print("Valid options: development, production")
        return False
    
    config_content = read_config()
    current = get_current_env(config_content)
    
    if current == env:
        print(f"Environment is already set to '{env}'")
        return True
    
    # Replace the environment line
    new_content = re.sub(
        r'^(environment:\s*)\w+$',
        f'\\1{env}',
        config_content,
        flags=re.MULTILINE
    )
    
    write_config(new_content)
    return True


def show_status():
    """Show current environment status."""
    config_content = read_config()
    current = get_current_env(config_content)
    
    print("=" * 60)
    print("MLS Environment Status")
    print("=" * 60)
    print()
    print(f"Current environment: {current}")
    print()
    
    if current == 'development':
        print("Settings:")
        print("  - Master IP: 127.0.0.1 (localhost)")
        print("  - Data path: ./data (local)")
        print("  - LabVIEW: Disabled")
        print("  - Camera: Software trigger (safe for testing)")
        print("  - GPU: Disabled")
        print()
        print("Use this for: Local development on your laptop")
        
    elif current == 'production':
        print("Settings:")
        print("  - Master IP: 134.99.120.40 (Manager PC)")
        print("  - Data path: E:/data (local) + Y:/Xi/Data (network)")
        print("  - LabVIEW: Enabled (SMILE PC at 172.17.1.217)")
        print("  - Camera: External trigger (hardware)")
        print("  - GPU: Enabled")
        print()
        print("Use this for: Running on the manager PC in the lab")
        
    else:
        print("WARNING: Unknown environment configuration!")
        print("Please check config/config.yaml")
    
    print()
    print("=" * 60)
    print("To switch environments:")
    print("  python switch_env.py dev   # Development (laptop)")
    print("  python switch_env.py prod  # Production (manager PC)")
    print("=" * 60)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        # Show current status
        show_status()
        return 0
    
    arg = sys.argv[1].lower()
    
    # Map short forms to full names
    env_map = {
        'dev': 'development',
        'development': 'development',
        'prod': 'production',
        'production': 'production',
    }
    
    if arg not in env_map:
        print(f"Unknown option: {arg}")
        print()
        print("Usage:")
        print("  python switch_env.py              Show current status")
        print("  python switch_env.py dev          Switch to development")
        print("  python switch_env.py prod         Switch to production")
        return 1
    
    env = env_map[arg]
    
    if set_environment(env):
        print(f"✓ Environment switched to: {env}")
        print()
        print("Next steps:")
        if env == 'development':
            print("  1. Ensure no services are running from production")
            print("  2. Run: python src/launcher.py")
            print("  3. Access: http://localhost:5000")
        else:
            print("  1. Copy the project to E:/mls on the manager PC")
            print("  2. Ensure E:/data directory exists")
            print("  3. Run: python src/launcher.py")
            print("  4. Access: http://134.99.120.40:5000")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
