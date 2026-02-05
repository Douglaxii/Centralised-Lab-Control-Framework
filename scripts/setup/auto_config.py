#!/usr/bin/env python3
"""
MLS Auto-Configuration Script

Automatically detects environment and sets up paths.
Run this script to:
1. Detect development vs production environment
2. Configure paths automatically
3. Create necessary directories
4. Validate the setup

Usage:
    python scripts/setup/auto_config.py         # Auto-detect and configure
    python scripts/setup/auto_config.py --dev   # Force development mode
    python scripts/setup/auto_config.py --prod  # Force production mode
    python scripts/setup/auto_config.py --check # Check current setup only
"""

import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.config.auto_setup import (
    setup_environment, 
    ensure_directories, 
    validate_setup,
    detect_environment,
    get_auto_paths,
    get_drive_options
)
from core import get_config

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger("auto_config")


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="MLS Auto-Configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python auto_config.py          # Auto-detect and setup
    python auto_config.py --dev    # Force development mode
    python auto_config.py --prod   # Force production mode
    python auto_config.py --check  # Validate current setup only
        """
    )
    
    parser.add_argument(
        '--dev', '--development',
        action='store_true',
        help='Force development mode (laptop)'
    )
    parser.add_argument(
        '--prod', '--production',
        action='store_true',
        help='Force production mode (manager PC)'
    )
    parser.add_argument(
        '--check', '--validate',
        action='store_true',
        help='Check current setup without making changes'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine environment
    force_env = None
    if args.dev:
        force_env = 'development'
    elif args.prod:
        force_env = 'production'
    
    print_section("MLS Auto-Configuration")
    
    # Environment detection
    print("\n📍 Environment Detection")
    detected = detect_environment()
    print(f"   Detected: {detected}")
    if force_env:
        print(f"   Forced: {force_env}")
    
    # Drive detection
    print("\n💾 Drive Detection")
    drives = get_drive_options()
    for dtype, paths in drives.items():
        if paths:
            print(f"   {dtype}: {', '.join(paths[:3])}")
            if len(paths) > 3:
                print(f"          ... and {len(paths) - 3} more")
    
    if args.check:
        # Validate only
        print_section("Setup Validation")
        is_valid, issues = validate_setup()
        if is_valid:
            print("\n✅ Setup is valid!")
        else:
            print("\n❌ Issues found:")
            for issue in issues:
                print(f"   - {issue}")
        return 0 if is_valid else 1
    
    # Setup environment
    print_section("Environment Setup")
    info = setup_environment(force_env=force_env)
    print(f"\n✅ Environment: {info['environment']}")
    print(f"   Hostname: {info['hostname']}")
    print(f"   IP Address: {info['ip_address']}")
    
    # Show auto-generated paths
    print("\n📁 Auto-Generated Paths:")
    for key, path in info['auto_paths'].items():
        print(f"   {key}: {path}")
    
    # Create directories
    print("\n📂 Creating Directories...")
    created = ensure_directories()
    if created:
        print(f"   Created {len(created)} directories:")
        for d in created:
            print(f"      {d}")
    else:
        print("   All directories already exist")
    
    # Load config and show current settings
    print_section("Current Configuration")
    try:
        config = get_config()
        print(f"\n   Environment: {config.environment}")
        print(f"   Master IP: {config.master_ip}")
        print(f"   Config File: {config.config_file}")
        
        print("\n   Key Paths:")
        path_keys = [
            'paths.output_base',
            'paths.jpg_frames',
            'paths.ion_data',
            'paths.labview_telemetry',
        ]
        for key in path_keys:
            try:
                value = config.get(key)
                print(f"      {key}: {value}")
            except:
                pass
    except Exception as e:
        print(f"\n   ⚠️ Could not load config: {e}")
    
    # Final validation
    print_section("Final Validation")
    is_valid, issues = validate_setup()
    if is_valid:
        print("\n✅ Setup is valid and ready!")
        print("\n   You can now start the system with:")
        print("      python -m src.launcher")
    else:
        print("\n⚠️ Setup completed with warnings:")
        for issue in issues:
            print(f"   - {issue}")
    
    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
