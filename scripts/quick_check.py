"""
Quick status check for MLS - run this to see what's running and what's not.
"""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core import get_config

def check_port(host, port, timeout=1.0):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except:
        return False

def main():
    config = get_config()
    
    print("\n" + "="*60)
    print("           MLS Quick Status Check")
    print("="*60)
    
    # Services
    services = [
        ("Manager", config.get('network.bind_host', '0.0.0.0'), config.get('network.client_port', 5557)),
        ("Flask API", config.get('services.flask.host', '0.0.0.0'), config.get('services.flask.port', 5000)),
        ("Camera", config.get('services.camera.host', '127.0.0.1'), config.get('services.camera.port', 5558)),
        ("Optimizer", config.get('services.optimizer.host', '127.0.0.1'), config.get('services.optimizer.port', 5050)),
    ]
    
    print("\nServices:")
    for name, host, port in services:
        status = "[OK] RUNNING" if check_port(host, port) else "[--] STOPPED"
        print(f"  {status} {name:15} (port {port})")
    
    # External connections
    print("\nExternal Connections:")
    
    # Wavemeter
    wm_host = config.get('wavemeter.host', '134.99.120.141')
    wm_port = config.get('wavemeter.port', 1790)
    wm_enabled = config.get('wavemeter.enabled', False)
    if wm_enabled:
        wm_ok = check_port(wm_host, wm_port, 2.0)
        status = "[OK] CONNECTED" if wm_ok else "[XX] FAILED"
        print(f"  {status} Wavemeter ({wm_host}:{wm_port})")
    else:
        print(f"  [..] DISABLED  Wavemeter")
    
    # LabVIEW
    lv_host = config.get('labview.host', '172.17.1.217')
    lv_port = config.get('labview.port', 5559)
    lv_enabled = config.get('labview.enabled', False)
    if lv_enabled:
        lv_ok = check_port(lv_host, lv_port, 2.0)
        status = "[OK] CONNECTED" if lv_ok else "[XX] FAILED"
        print(f"  {status} LabVIEW ({lv_host}:{lv_port})")
    else:
        print(f"  [..] DISABLED  LabVIEW")
    
    print("\n" + "="*60)
    print("To start services: python -m src.launcher")
    print("For detailed check: python scripts/debug_mls.py")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
