#!/usr/bin/env python3
"""
MLS Environment Setup Script

Detects environment and creates necessary directories.
"""
import argparse
import sys
import os
import socket
from pathlib import Path

def detect_environment():
    """Detect if running on development or production machine."""
    hostname = socket.gethostname().lower()
    
    # Production hostnames (Manager PC, Lab machines)
    production_hosts = ['manager', 'lab', 'desktop-3r8n1la']
    
    for prod_host in production_hosts:
        if prod_host in hostname:
            return 'production'
    
    return 'development'

def setup_directories():
    """Create necessary directories."""
    project_root = Path(__file__).parent.parent
    
    dirs = [
        project_root / "logs",
        project_root / "data" / "camera" / "raw",
        project_root / "data" / "camera" / "processed",
        project_root / "data" / "experiments",
        project_root / "data" / "analysis",
    ]
    
    created = []
    for d in dirs:
        if not d.exists():
            d.mkdir(parents=True)
            created.append(d.relative_to(project_root))
    
    return created

def switch_environment(env):
    """Switch environment in config file."""
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        return False
    
    content = config_path.read_text()
    
    # Replace environment line
    import re
    new_content = re.sub(
        r'^environment:\s*\w+$',
        f'environment: {env}',
        content,
        flags=re.MULTILINE
    )
    
    config_path.write_text(new_content)
    return True

def main():
    parser = argparse.ArgumentParser(description="MLS Environment Setup")
    parser.add_argument('--dev', action='store_true', help='Force development mode')
    parser.add_argument('--prod', action='store_true', help='Force production mode')
    parser.add_argument('--check', action='store_true', help='Check setup only')
    args = parser.parse_args()
    
    print("=" * 50)
    print("MLS Environment Setup")
    print("=" * 50)
    print()
    
    # Detect environment
    detected = detect_environment()
    env = detected
    
    if args.dev:
        env = 'development'
    elif args.prod:
        env = 'production'
    
    print(f"Detected: {detected}")
    if env != detected:
        print(f"Forced: {env}")
    print()
    
    if args.check:
        # Just check
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        if config_path.exists():
            content = config_path.read_text()
            import re
            match = re.search(r'^environment:\s*(\w+)', content, re.MULTILINE)
            if match:
                print(f"Current environment: {match.group(1)}")
        return 0
    
    # Switch environment if needed
    if env != detected or args.dev or args.prod:
        if switch_environment(env):
            print(f"[OK] Environment set to: {env}")
        else:
            print("[ERROR] Failed to switch environment")
            return 1
    
    # Create directories
    print("\nCreating directories...")
    created = setup_directories()
    if created:
        for d in created:
            print(f"  Created: {d}")
    else:
        print("  All directories already exist")
    
    # Show config
    print("\n" + "=" * 50)
    print("Configuration Summary")
    print("=" * 50)
    print(f"Environment: {env}")
    print(f"Hostname: {socket.gethostname()}")
    print()
    
    if env == 'development':
        print("Settings:")
        print("  - Master IP: 127.0.0.1 (localhost)")
        print("  - LabVIEW: Disabled")
        print("  - Camera: Software trigger")
        print()
        print("Use this for: Local development on laptop")
    else:
        print("Settings:")
        print("  - Master IP: 134.99.120.40 (Manager PC)")
        print("  - LabVIEW: Enabled")
        print("  - Camera: External trigger")
        print()
        print("Use this for: Running on manager PC in lab")
    
    print()
    print("=" * 50)
    return 0

if __name__ == "__main__":
    sys.exit(main())
