"""
MLS System Diagnostic Tool
Checks all services, configurations, and connections.
"""

import socket
import sys
import subprocess
import time
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import get_config

def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a port is accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((host, port))
            return result == 0
    except:
        return False

def test_service(name: str, host: str, port: int) -> dict:
    """Test a single service."""
    print(f"  Testing {name} ({host}:{port})...", end=" ")
    
    is_open = check_port(host, port)
    
    if is_open:
        print("[OK] RUNNING")
        return {"name": name, "status": "running", "host": host, "port": port}
    else:
        print("[XX] NOT RESPONDING")
        return {"name": name, "status": "stopped", "host": host, "port": port}

def check_wavemeter(config) -> dict:
    """Check wavemeter connection."""
    print("\n[4] Wavemeter Check")
    print("-" * 50)
    
    host = config.get('wavemeter.host', '134.99.120.141')
    port = config.get('wavemeter.port', 1790)
    enabled = config.get('wavemeter.enabled', False)
    
    print(f"  Config: enabled={enabled}, host={host}, port={port}")
    
    if not enabled:
        print("  ⚠ Wavemeter is DISABLED in config")
        return {"enabled": False, "connected": False}
    
    # Try to connect
    print(f"  Testing connection to {host}:{port}...", end=" ")
    connected = check_port(host, port, timeout=3.0)
    
    if connected:
        print("[OK] CONNECTED")
    else:
        print("[XX] CONNECTION FAILED")
        print(f"  \n  Troubleshooting:")
        print(f"    - Is wavemeter PC ({host}) reachable?")
        print(f"    - Is wavemeter software broadcasting on port {port}?")
        print(f"    - Check firewall settings on wavemeter PC")
    
    return {"enabled": True, "host": host, "port": port, "connected": connected}

def check_labview(config) -> dict:
    """Check LabVIEW connection."""
    print("\n[5] LabVIEW Check")
    print("-" * 50)
    
    host = config.get('labview.host', '127.0.0.1')
    port = config.get('labview.port', 5559)
    enabled = config.get('labview.enabled', False)
    wait_response = config.get('labview.wait_for_response', False)
    
    print(f"  Config: enabled={enabled}, host={host}, port={port}")
    print(f"  Mode: {'Two-way' if wait_response else 'One-way (fire-and-forget)'}")
    
    if not enabled:
        print("  ⚠ LabVIEW is DISABLED in config")
        return {"enabled": False, "connected": False}
    
    # Try to connect
    print(f"  Testing connection to {host}:{port}...", end=" ")
    connected = check_port(host, port, timeout=3.0)
    
    if connected:
        print("[OK] CONNECTED")
    else:
        print("[XX] CONNECTION FAILED")
        print(f"  \n  Troubleshooting:")
        print(f"    - Is SMILE PC ({host}) reachable?")
        print(f"    - Is LabVIEW TCP listener running on port {port}?")
        print(f"    - Check firewall settings on SMILE PC")
    
    return {"enabled": True, "host": host, "port": port, "connected": connected}

def check_camera_paths(config) -> dict:
    """Check camera data paths."""
    print("\n[6] Camera Paths Check")
    print("-" * 50)
    
    import os
    
    jpg_frames = config.get('paths.jpg_frames', './data/jpg_frames')
    jpg_frames_labelled = config.get('paths.jpg_frames_labelled', './data/jpg_frames_labelled')
    
    print(f"  jpg_frames: {jpg_frames}")
    print(f"  jpg_frames_labelled: {jpg_frames_labelled}")
    
    # Check if paths exist
    jpg_exists = os.path.exists(jpg_frames)
    labelled_exists = os.path.exists(jpg_frames_labelled)
    
    if jpg_exists:
        print(f"    [OK] jpg_frames exists")
    else:
        print(f"    [XX] jpg_frames does NOT exist (will be created on startup)")
    
    if labelled_exists:
        print(f"    [OK] jpg_frames_labelled exists")
    else:
        print(f"    [XX] jpg_frames_labelled does NOT exist (will be created on startup)")
    
    return {
        "jpg_frames": {"path": jpg_frames, "exists": jpg_exists},
        "jpg_frames_labelled": {"path": jpg_frames_labelled, "exists": labelled_exists}
    }

def check_zmq_ports():
    """Check ZMQ ports used by manager."""
    print("\n[7] ZMQ Ports Check")
    print("-" * 50)
    
    ports = [
        ("Command (PUSH)", "127.0.0.1", 5555),
        ("Data (PULL)", "127.0.0.1", 5556),
        ("Client (REP)", "127.0.0.1", 5557),
        ("Camera", "127.0.0.1", 5558),
    ]
    
    results = []
    for name, host, port in ports:
        in_use = check_port(host, port)
        status = "IN USE" if in_use else "AVAILABLE"
        symbol = "!" if in_use else "+"
        print(f"  {symbol} {name}: port {port} is {status}")
        results.append({"name": name, "port": port, "in_use": in_use})
    
    return results

def main():
    print("=" * 70)
    print("              MLS SYSTEM DIAGNOSTIC TOOL")
    print("=" * 70)
    
    # Load config
    print("\n[1] Configuration")
    print("-" * 50)
    try:
        config = get_config()
        env = config.get('environment', 'unknown')
        print("  [OK] Config loaded successfully")
        print(f"  Environment: {env}")
    except Exception as e:
        print(f"  [XX] Failed to load config: {e}")
        return
    
    # Check Python path
    print("\n[2] Python Environment")
    print("-" * 50)
    print(f"  Python: {sys.executable}")
    print(f"  Version: {sys.version.split()[0]}")
    print(f"  Platform: {sys.platform}")
    
    # Check services
    print("\n[3] Service Status")
    print("-" * 50)
    
    services = [
        ("Manager (Client)", config.get('network.bind_host', '0.0.0.0'), config.get('network.client_port', 5557)),
        ("Flask API", config.get('services.flask.host', '0.0.0.0'), config.get('services.flask.port', 5000)),
        ("Camera", config.get('services.camera.host', '127.0.0.1'), config.get('services.camera.port', 5558)),
        ("Optimizer", config.get('services.optimizer.host', '127.0.0.1'), config.get('services.optimizer.port', 5050)),
    ]
    
    service_status = []
    for name, host, port in services:
        status = test_service(name, host, port)
        service_status.append(status)
    
    # Check external connections
    wavemeter_status = check_wavemeter(config)
    labview_status = check_labview(config)
    
    # Check paths
    camera_paths = check_camera_paths(config)
    
    # Check ZMQ
    zmq_status = check_zmq_ports()
    
    # Summary
    print("\n" + "=" * 70)
    print("                         SUMMARY")
    print("=" * 70)
    
    running_services = [s for s in service_status if s["status"] == "running"]
    stopped_services = [s for s in service_status if s["status"] == "stopped"]
    
    print(f"\nServices Running: {len(running_services)}/{len(service_status)}")
    for s in running_services:
        print(f"  [OK] {s['name']}")
    for s in stopped_services:
        print(f"  [XX] {s['name']} (not running)")
    
    print(f"\nExternal Connections:")
    if wavemeter_status["enabled"]:
        status = "[OK] Connected" if wavemeter_status["connected"] else "[XX] Disconnected"
        print(f"  {status} to Wavemeter ({wavemeter_status['host']}:{wavemeter_status['port']})")
    else:
        print(f"  [!] Wavemeter disabled")
    
    if labview_status["enabled"]:
        status = "[OK] Connected" if labview_status["connected"] else "[XX] Disconnected"
        print(f"  {status} to LabVIEW ({labview_status['host']}:{labview_status['port']})")
    else:
        print(f"  [!] LabVIEW disabled")
    
    print(f"\nRecommendations:")
    if not running_services:
        print("  1. No services are running. Start them with:")
        print("     python -m src.launcher")
    elif stopped_services:
        print("  1. Some services are not running. Check logs for errors.")
    
    if wavemeter_status["enabled"] and not wavemeter_status["connected"]:
        print("  2. Wavemeter not connected. Check:")
        print("     - Is wavemeter PC powered on and on network?")
        print("     - Is wavemeter software broadcasting?")
        print("     - Run: python scripts/debug_wavemeter.py")
    
    if labview_status["enabled"] and not labview_status["connected"]:
        print("  3. LabVIEW not connected. Check:")
        print("     - Is SMILE PC powered on and on network?")
        print("     - Is LabVIEW TCP listener running?")
        print("     - Run: python scripts/debug_labview_tcp.py")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
