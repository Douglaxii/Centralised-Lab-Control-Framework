"""
Camera Client - TCP client for communicating with the camera server.

This module provides both low-level command sending and a high-level
CameraInterface class for integration with the MLS manager.

Usage:
    # Low-level
    response = send_command("START_INF")
    
    # High-level
    camera = CameraInterface()
    camera.start_recording(mode="inf")
    camera.stop_recording()
"""

import socket
import threading
import logging
from typing import Optional, Dict, Any, Tuple


# Default connection settings
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 5558
DEFAULT_TIMEOUT = 5.0


def send_command(command: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, 
                 timeout: float = DEFAULT_TIMEOUT) -> str:
    """
    Send a command to the camera server.
    
    Args:
        command: Command string (START, START_INF, STOP, STATUS)
        host: Camera server host
        port: Camera server port
        timeout: Socket timeout in seconds
        
    Returns:
        Response string from the server
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            s.sendall(command.encode() + b'\n')
            response = s.recv(1024).decode().strip()
            return response
    except socket.timeout:
        return "ERROR: Connection timeout"
    except ConnectionRefusedError:
        return "ERROR: Connection refused - camera server not running"
    except Exception as e:
        return f"ERROR: {e}"


class CameraInterface:
    """
    High-level interface to the camera server.
    
    Provides simplified camera control without going through Flask.
    Communicates directly with camera_server via TCP.
    
    This eliminates the chain:
    ARTIQ -> Flask -> TCP -> camera_server -> camera_logic
    
    And replaces it with:
    Manager -> camera_server (direct TCP)
    ARTIQ TTL trigger -> camera (hardware trigger)
    """
    
    def __init__(self, host: str = DEFAULT_HOST, port: Optional[int] = None):
        """
        Initialize camera interface.
        
        Args:
            host: Camera server host (default: localhost)
            port: Camera server port (default: 5558)
        """
        self.logger = logging.getLogger("CameraInterface")
        
        # Load configuration if available
        try:
            from core import get_config
            config = get_config()
            self.host = host
            self.port = port or config.get('network.camera_port', DEFAULT_PORT)
        except ImportError:
            self.host = host
            self.port = port or DEFAULT_PORT
        
        self.timeout = DEFAULT_TIMEOUT
        
        # Camera state
        self.is_recording = False
        self.lock = threading.RLock()
        
        self.logger.info(f"Camera Interface initialized ({self.host}:{self.port})")
    
    def _send_command(self, command: str) -> Tuple[bool, str]:
        """
        Send command to camera server.
        
        Args:
            command: Command string (START, START_INF, STOP, STATUS)
            
        Returns:
            Tuple of (success, response_message)
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect((self.host, self.port))
                s.sendall(command.encode() + b'\n')
                response = s.recv(1024).decode().strip()
                
                if response.startswith("OK:"):
                    return True, response
                else:
                    return False, response
                    
        except socket.timeout:
            self.logger.error(f"Camera server timeout")
            return False, "Timeout"
        except ConnectionRefusedError:
            self.logger.error(f"Camera server not available at {self.host}:{self.port}")
            return False, "Connection refused"
        except Exception as e:
            self.logger.error(f"Camera communication error: {e}")
            return False, str(e)
    
    def start_recording(self, mode: str = "inf", exp_id: Optional[str] = None) -> bool:
        """
        Start camera recording.
        
        Args:
            mode: Recording mode - "inf" for infinite capture, "single" for DCIMG recording
            exp_id: Optional experiment ID for metadata
            
        Returns:
            True if successful
        """
        with self.lock:
            if mode == "inf":
                success, msg = self._send_command("START_INF")
            else:
                success, msg = self._send_command("START")
            
            if success:
                self.is_recording = True
                self.logger.info(f"Camera recording started ({mode} mode)")
                
                # Send experiment ID if provided
                if exp_id:
                    self._send_command(f"EXP_ID:{exp_id}")
            else:
                self.logger.error(f"Failed to start camera: {msg}")
            
            return success
    
    def stop_recording(self) -> bool:
        """
        Stop camera recording.
        
        Returns:
            True if successful
        """
        with self.lock:
            success, msg = self._send_command("STOP")
            
            if success:
                self.is_recording = False
                self.logger.info("Camera recording stopped")
            else:
                self.logger.error(f"Failed to stop camera: {msg}")
            
            return success
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get camera status.
        
        Returns:
            Dictionary with status information
        """
        success, msg = self._send_command("STATUS")
        
        with self.lock:
            return {
                "connected": success,
                "recording": self.is_recording,
                "status_message": msg if success else "Unknown",
                "server": f"{self.host}:{self.port}"
            }
    
    def is_camera_available(self) -> bool:
        """
        Check if camera server is available.
        
        Returns:
            True if camera server responds
        """
        success, _ = self._send_command("STATUS")
        return success


# Legacy compatibility
def listen_for_commands(server_ip='127.0.0.1', port=5001):
    """
    Legacy function for backward compatibility.
    Connects to camera server and listens for commands.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((server_ip, port))
        print(f"Verbunden mit Server {server_ip}:{port}")
        
        while True:
            data = s.recv(4096)
            if not data:
                break
            
            command = data.decode('utf-8')
            print(f"Empfangenes Kommando: {command}")

            if command.startswith("START_RECORDING"):
                from camera_recording import handle_recording_request
                result = handle_recording_request()
                s.sendall(f"RECORDING_DONE: {result}\n".encode('utf-8'))


if __name__ == "__main__":
    # Test the camera interface
    logging.basicConfig(level=logging.INFO)
    
    camera = CameraInterface()
    
    print("Testing camera interface...")
    print(f"Status: {camera.get_status()}")
    
    # Test start
    print("\nStarting camera...")
    if camera.start_recording(mode="inf"):
        print("Camera started successfully")
        
        import time
        time.sleep(2)
        
        print("\nStopping camera...")
        if camera.stop_recording():
            print("Camera stopped successfully")
    else:
        print("Failed to start camera")
