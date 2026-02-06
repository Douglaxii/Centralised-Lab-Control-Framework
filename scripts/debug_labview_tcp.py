"""
Debug script to test LabVIEW TCP connection.
Run this to diagnose connection issues with LabVIEW.
"""

import socket
import json
import time
import sys

# Add project root
sys.path.insert(0, str(__file__).replace('\\scripts\\debug_labview_tcp.py', ''))

from src.core import get_config

def test_raw_tcp_connection(host: str, port: int, timeout: float = 5.0):
    """Test basic TCP connectivity to LabVIEW."""
    print(f"\n{'='*60}")
    print(f"Testing TCP connection to {host}:{port}")
    print(f"{'='*60}")
    
    sock = None
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        # Try to connect
        print(f"[1] Connecting to {host}:{port}...")
        sock.connect((host, port))
        print(f"    ✓ TCP connection established!")
        
        # Send a simple test command
        test_cmd = {"device": "ping", "value": 1}
        message = json.dumps(test_cmd) + "\n"
        
        print(f"[2] Sending: {message.strip()}")
        sock.sendall(message.encode('utf-8'))
        print(f"    ✓ Data sent ({len(message)} bytes)")
        
        # Wait for response
        print(f"[3] Waiting for response (timeout: {timeout}s)...")
        try:
            response = sock.recv(4096).decode('utf-8').strip()
            if response:
                print(f"    ✓ Response received: {response}")
                return True
            else:
                print(f"    ✗ Empty response (connection closed by LabVIEW?)")
                return False
        except socket.timeout:
            print(f"    ✗ TIMEOUT: No response from LabVIEW within {timeout}s")
            print(f"      This usually means LabVIEW didn't send a response back!")
            return False
            
    except socket.error as e:
        print(f"    ✗ Connection failed: {e}")
        return False
    finally:
        if sock:
            sock.close()
            print(f"[4] Connection closed")

def test_with_config():
    """Test using configuration values."""
    config = get_config()
    host = config.get('labview.host', '127.0.0.1')
    port = config.get('labview.port', 5559)
    timeout = config.get('labview.timeout', 5.0)
    
    print(f"\nConfig values:")
    print(f"  host: {host}")
    print(f"  port: {port}")
    print(f"  timeout: {timeout}")
    
    return test_raw_tcp_connection(host, port, timeout)

def manual_test():
    """Manual test with user input."""
    print("\nManual TCP Test")
    print("Enter LabVIEW server details:")
    
    host = input("Host [172.17.1.217]: ").strip() or "172.17.1.217"
    port_str = input("Port [5559]: ").strip() or "5559"
    port = int(port_str)
    
    test_raw_tcp_connection(host, port)

if __name__ == "__main__":
    print("LabVIEW TCP Connection Debugger")
    print("=" * 60)
    
    if len(sys.argv) > 1 and sys.argv[1] == "manual":
        manual_test()
    else:
        success = test_with_config()
        
        if not success:
            print("\n" + "="*60)
            print("TROUBLESHOOTING:")
            print("="*60)
            print("""
1. Check LabVIEW is running and listening on the correct port:
   - In LabVIEW, check the port number in your TCP Create Listener
   - Make sure it's 5559 (or update config.yaml)

2. Check firewall settings:
   - Windows Firewall might be blocking port 5559
   - Try: netsh advfirewall firewall add rule name="LabVIEW TCP" dir=in action=allow protocol=TCP localport=5559

3. Check IP address:
   - Python is trying to connect to the IP in config.yaml
   - If LabVIEW is on the same machine, use 127.0.0.1
   - If LabVIEW is on SMILE PC, make sure the IP is correct

4. LabVIEW code issues:
   - Ensure your inner while loop sends a response back
   - Python waits for a response after each command!
   - Send at least: "OK\\n" or a JSON response

5. Test manually:
   Run: python scripts/debug_labview_tcp.py manual
            """)
