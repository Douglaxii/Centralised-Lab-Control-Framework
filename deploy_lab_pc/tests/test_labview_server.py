"""
Test LabVIEW TCP Server - Simulates LabVIEW for testing

Run this to test the Python manager's LabVIEW interface without actual LabVIEW.
This simulates the SMILE LabVIEW program's TCP server behavior.
"""

import socket
import json
import threading
import time
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockLabVIEWServer:
    """
    Mock LabVIEW server that simulates the SMILE LabVIEW TCP interface.
    
    Use this to test the Python Control Manager's LabVIEW integration
    without needing the actual LabVIEW program running.
    """
    
    def __init__(self, host="0.0.0.0", port=5559):
        self.host = host
        self.port = port
        self.running = False
        self.server_socket = None
        
        # Simulated device states
        self.devices = {
            "U_RF": 0.0,
            "piezo": 0.0,
            "be_oven": False,
            "b_field": False,
            "bephi": False,
            "uv3": False,
            "e_gun": False,
            "hd_shutter_1": False,
            "hd_shutter_2": False,
            "dds": 212.5,
        }
        
        # Command handlers
        self.handlers = {
            "set_voltage": self._handle_set_voltage,
            "set_toggle": self._handle_set_toggle,
            "set_shutter": self._handle_set_shutter,
            "set_frequency": self._handle_set_frequency,
            "get_status": self._handle_get_status,
            "emergency_stop": self._handle_emergency_stop,
            "ping": self._handle_ping,
        }
    
    def start(self):
        """Start the mock LabVIEW server."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        print(f"🧪 Mock LabVIEW Server running on {self.host}:{self.port}")
        print(f"   Simulated devices: {list(self.devices.keys())}")
        print(f"   Waiting for Python Manager connections...")
        print(f"   Press Ctrl+C to stop\n")
        
        try:
            while self.running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, address = self.server_socket.accept()
                    print(f"📡 Connection from {address}")
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                    
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server."""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("✅ Server stopped")
    
    def _handle_client(self, client_socket, address):
        """Handle a client connection."""
        try:
            client_socket.settimeout(30.0)  # 30 second timeout
            
            while self.running:
                # Receive data
                data = b""
                while b"\n" not in data:
                    chunk = client_socket.recv(1024)
                    if not chunk:
                        print(f"👋 Client {address} disconnected")
                        return
                    data += chunk
                
                # Parse command
                lines = data.decode('utf-8').strip().split('\n')
                for line in lines:
                    if not line:
                        continue
                    
                    try:
                        command = json.loads(line)
                        print(f"➡️  Received: {command}")
                        
                        # Process command
                        response = self._process_command(command)
                        
                        # Send response
                        response_json = json.dumps(response) + "\n"
                        client_socket.sendall(response_json.encode('utf-8'))
                        print(f"⬅️  Sent: {response}\n")
                        
                    except json.JSONDecodeError as e:
                        print(f"❌ Invalid JSON: {e}")
                        error_response = {
                            "request_id": "error",
                            "status": "error",
                            "device": "unknown",
                            "value": None,
                            "message": f"Invalid JSON: {e}"
                        }
                        client_socket.sendall((json.dumps(error_response) + "\n").encode('utf-8'))
                        
        except socket.timeout:
            print(f"⏱️  Client {address} timeout")
        except Exception as e:
            print(f"❌ Error handling client {address}: {e}")
        finally:
            client_socket.close()
    
    def _process_command(self, command: dict) -> dict:
        """Process a command and return response."""
        cmd_type = command.get("command", "")
        request_id = command.get("request_id", "unknown")
        device = command.get("device", "")
        value = command.get("value")
        
        # Find handler
        handler = self.handlers.get(cmd_type)
        
        if handler:
            try:
                result = handler(device, value)
                return {
                    "request_id": request_id,
                    "status": "ok",
                    "device": device,
                    "value": result,
                    "timestamp": time.time()
                }
            except Exception as e:
                return {
                    "request_id": request_id,
                    "status": "error",
                    "device": device,
                    "value": None,
                    "message": str(e),
                    "timestamp": time.time()
                }
        else:
            return {
                "request_id": request_id,
                "status": "error",
                "device": device,
                "value": None,
                "message": f"Unknown command: {cmd_type}",
                "timestamp": time.time()
            }
    
    def _handle_set_voltage(self, device: str, value: float) -> float:
        """Handle set_voltage command."""
        if device not in ["U_RF", "piezo"]:
            raise ValueError(f"Unknown voltage device: {device}")
        
        # Validate ranges
        if device == "U_RF" and not (0 <= value <= 1000):
            raise ValueError(f"U_RF voltage {value} out of range [0, 1000]")
        if device == "piezo" and not (-10 <= value <= 10):
            raise ValueError(f"Piezo voltage {value} out of range [-10, 10]")
        
        self.devices[device] = float(value)
        print(f"   [VOLTAGE] {device} = {value} V")
        return self.devices[device]
    
    def _handle_set_toggle(self, device: str, value: bool) -> bool:
        """Handle set_toggle command."""
        valid_devices = ["be_oven", "b_field", "bephi", "uv3", "e_gun"]
        
        if device not in valid_devices:
            raise ValueError(f"Unknown toggle device: {device}")
        
        self.devices[device] = bool(value)
        state_str = "ON" if value else "OFF"
        print(f"   [TOGGLE] {device} = {state_str}")
        return self.devices[device]
    
    def _handle_set_shutter(self, device: str, value: bool) -> bool:
        """Handle set_shutter command."""
        if not device.startswith("hd_"):
            raise ValueError(f"Invalid shutter device: {device}")
        
        self.devices[device] = bool(value)
        state_str = "OPEN" if value else "CLOSED"
        print(f"   [SHUTTER] {device} = {state_str}")
        return self.devices[device]
    
    def _handle_set_frequency(self, device: str, value: float) -> float:
        """Handle set_frequency command."""
        if device != "dds":
            raise ValueError(f"Unknown frequency device: {device}")
        
        self.devices["dds"] = float(value)
        print(f"   [FREQUENCY] DDS = {value} MHz")
        return self.devices["dds"]
    
    def _handle_get_status(self, device: str, value) -> dict:
        """Handle get_status command."""
        return self.devices.copy()
    
    def _handle_emergency_stop(self, device: str, value) -> str:
        """Handle emergency_stop command."""
        print("   [EMERGENCY STOP] All devices reset to safe state")
        
        # Reset all to safe defaults
        self.devices["U_RF"] = 0.0
        self.devices["piezo"] = 0.0
        self.devices["be_oven"] = False
        self.devices["b_field"] = False
        self.devices["bephi"] = False
        self.devices["uv3"] = False
        self.devices["e_gun"] = False
        self.devices["hd_shutter_1"] = False
        self.devices["hd_shutter_2"] = False
        
        return "emergency_stop_executed"
    
    def _handle_ping(self, device: str, value) -> str:
        """Handle ping command."""
        return "pong"


def test_with_manager():
    """Test the mock server with the actual LabVIEW interface."""
    import time
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from server.communications.labview_interface import LabVIEWInterface
    
    print("\n" + "="*60)
    print("Testing with LabVIEWInterface...")
    print("="*60 + "\n")
    
    # Create interface (connects to localhost:5559)
    lv = LabVIEWInterface(host="127.0.0.1", port=5559)
    lv.start()
    
    # Wait for connection
    time.sleep(1)
    
    try:
        # Test RF voltage
        print("1. Setting U_RF to 500V...")
        if lv.set_rf_voltage(500.0):
            print("   ✓ Success\n")
        else:
            print("   ✗ Failed\n")
        
        time.sleep(0.5)
        
        # Test piezo
        print("2. Setting Piezo to 2.5V...")
        if lv.set_piezo_voltage(2.5):
            print("   ✓ Success\n")
        else:
            print("   ✗ Failed\n")
        
        time.sleep(0.5)
        
        # Test toggles
        print("3. Turning on B-field...")
        if lv.set_b_field(True):
            print("   ✓ Success\n")
        else:
            print("   ✗ Failed\n")
        
        time.sleep(0.5)
        
        print("4. Turning on Be+ Oven...")
        if lv.set_be_oven(True):
            print("   ✓ Success\n")
        else:
            print("   ✗ Failed\n")
        
        time.sleep(0.5)
        
        # Test status query
        print("5. Querying status...")
        status = lv.get_status()
        if status:
            print(f"   ✓ Status: {status}\n")
        else:
            print("   ✗ Failed\n")
        
        time.sleep(0.5)
        
        # Test emergency stop
        print("6. Testing emergency stop...")
        if lv.emergency_stop():
            print("   ✓ Success\n")
        else:
            print("   ✗ Failed\n")
        
        print("="*60)
        print("Test complete!")
        print("="*60)
        
    finally:
        lv.stop()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Mock LabVIEW Server")
    parser.add_argument("--test", action="store_true", 
                       help="Run automated test with LabVIEWInterface")
    parser.add_argument("--port", type=int, default=5559,
                       help="TCP port to listen on (default: 5559)")
    
    args = parser.parse_args()
    
    if args.test:
        # Start server in background thread
        server = MockLabVIEWServer(port=args.port)
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        
        # Wait for server to start
        time.sleep(0.5)
        
        # Run tests
        test_with_manager()
        
        # Stop server
        server.stop()
    else:
        # Run interactive server
        server = MockLabVIEWServer(port=args.port)
        server.start()
