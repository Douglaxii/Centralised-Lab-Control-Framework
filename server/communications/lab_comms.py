"""
Lab Communication Module
Standardized ZMQ communication for lab control framework.

Usage:
    # Master side
    from server.communications.lab_comms import LabComm
    comm = LabComm("MASTER", role="MASTER")
    comm.send_command("ARTIQ", {"type": "SET_DC", "params": {...}})
    
    # Worker side
    from server.communications.lab_comms import LabComm
    comm = LabComm("ARTIQ", role="WORKER")
    cmd = comm.check_for_command()
    comm.send_data({"counts": 100}, category="PMT")
"""

import zmq
import json
import time
import logging
from typing import Optional, Dict, Any, Union
from pathlib import Path
import sys

# Add project root to path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import core utilities
try:
    from core import (
        get_config, 
        connect_with_retry, 
        create_zmq_socket,
        ConnectionError,
        TimeoutError,
        ExperimentContext,
        get_tracker
    )
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False
    # Fallback for standalone usage
    logging.warning("Core utilities not available, using fallback configuration")


class LabComm:
    """
    Unified communication interface for lab components.
    
    Supports both MASTER and WORKER roles with appropriate
    socket patterns for each.
    """
    
    def __init__(
        self, 
        device_name: str, 
        role: str = "WORKER",
        context: Optional[zmq.Context] = None,
        exp_id: Optional[str] = None
    ):
        """
        Initialize LabComm.
        
        Args:
            device_name: Device identifier ("ARTIQ", "SMILE", "CAMERA", etc.)
            role: "MASTER" (sends commands) or "WORKER" (receives commands)
            context: Optional ZMQ context (creates new if None)
            exp_id: Optional experiment ID to include in messages
        """
        self.device_name = device_name
        self.role = role.upper()
        self.exp_id = exp_id
        
        # Load configuration
        if CORE_AVAILABLE:
            self.config = get_config()
            self.master_ip = self.config.master_ip
            self.cmd_port = self.config.cmd_port
            self.data_port = self.config.data_port
        else:
            # Fallback defaults
            self.master_ip = "192.168.1.100"
            self.cmd_port = 5555
            self.data_port = 5556
        
        # Create or use provided context
        self.context = context or zmq.Context()
        self._owns_context = context is None
        
        # Initialize sockets
        self.cmd_socket = None
        self.data_socket = None
        self._setup_sockets()
        
        # Logger
        self.logger = logging.getLogger(f"LabComm.{device_name}")
        self.logger.info(f"[{device_name}] Initialized as {role}")
    
    def _setup_sockets(self):
        """Setup ZMQ sockets based on role."""
        if self.role == "MASTER":
            self._setup_master_sockets()
        else:
            self._setup_worker_sockets()
    
    def _setup_master_sockets(self):
        """Setup sockets for MASTER role."""
        # Command socket: PUBLISH commands to workers
        self.cmd_socket = self.context.socket(zmq.PUB)
        self.cmd_socket.bind(f"tcp://*:{self.cmd_port}")
        self.logger.debug(f"[MASTER] Command socket bound to port {self.cmd_port}")
        
        # Data socket: PULL data from workers (CHANGED from SUB to match worker PUSH)
        self.data_socket = self.context.socket(zmq.PULL)
        self.data_socket.bind(f"tcp://*:{self.data_port}")
        # Set receive timeout for non-blocking checks
        timeout_ms = int(self.config.get_network('receive_timeout') * 1000) if CORE_AVAILABLE else 1000
        self.data_socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.logger.debug(f"[MASTER] Data socket bound to port {self.data_port} (PULL)")
    
    def _setup_worker_sockets(self):
        """Setup sockets for WORKER role."""
        # Command socket: SUBSCRIBE to commands from master
        self.cmd_socket = self.context.socket(zmq.SUB)
        
        # Connect with retry
        cmd_addr = f"tcp://{self.master_ip}:{self.cmd_port}"
        if CORE_AVAILABLE:
            connect_with_retry(self.cmd_socket, cmd_addr)
        else:
            self.cmd_socket.connect(cmd_addr)
        
        # Subscribe to messages for this device and broadcast messages
        self.cmd_socket.setsockopt_string(zmq.SUBSCRIBE, self.device_name)
        self.cmd_socket.setsockopt_string(zmq.SUBSCRIBE, "ALL")
        
        # Set timeout to allow watchdog checks
        timeout_ms = int(self.config.get_network('receive_timeout') * 1000) if CORE_AVAILABLE else 1000
        self.cmd_socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.logger.debug(f"[WORKER] Command socket connected to {cmd_addr}")
        
        # Data socket: PUSH data to master (CHANGED from PUB to match master PULL)
        self.data_socket = self.context.socket(zmq.PUSH)
        data_addr = f"tcp://{self.master_ip}:{self.data_port}"
        if CORE_AVAILABLE:
            connect_with_retry(self.data_socket, data_addr)
        else:
            self.data_socket.connect(data_addr)
        self.logger.debug(f"[WORKER] Data socket connected to {data_addr} (PUSH)")
    
    def send_data(
        self, 
        payload: Dict[str, Any], 
        category: str = "DATA",
        exp_id: Optional[str] = None
    ):
        """
        Send data payload to master.
        
        Args:
            payload: Dictionary containing data
            category: Data category ("DATA", "STATUS", "HEARTBEAT", etc.)
            exp_id: Optional experiment ID (overrides instance exp_id)
        """
        packet = {
            "timestamp": time.time(),
            "source": self.device_name,
            "category": category,
            "payload": payload,
            "exp_id": exp_id or self.exp_id
        }
        
        try:
            self.data_socket.send_json(packet, flags=zmq.NOBLOCK)
            self.logger.debug(f"Sent {category} data")
        except zmq.Again:
            self.logger.warning("Data send would block, dropping packet")
        except Exception as e:
            self.logger.error(f"Failed to send data: {e}")
    
    def send_command(
        self, 
        target_device: str, 
        params: Dict[str, Any],
        exp_id: Optional[str] = None
    ):
        """
        Send command to a worker (MASTER only).
        
        Args:
            target_device: Target device name
            params: Command parameters (should include "type" key)
            exp_id: Optional experiment ID
            
        Raises:
            PermissionError: If called by WORKER
        """
        if self.role != "MASTER":
            raise PermissionError("Only MASTER can send commands")
        
        packet = {
            "timestamp": time.time(),
            "target": target_device,
            "params": params,
            "exp_id": exp_id or self.exp_id
        }
        
        try:
            # Send multipart: [Topic, Data]
            self.cmd_socket.send_string(target_device, flags=zmq.SNDMORE)
            self.cmd_socket.send_json(packet)
            self.logger.debug(f"Sent command to {target_device}: {params.get('type', 'UNKNOWN')}")
        except Exception as e:
            self.logger.error(f"Failed to send command: {e}")
    
    def check_for_command(self, blocking: bool = False) -> Optional[Dict[str, Any]]:
        """
        Check for incoming command (WORKER only).
        
        Args:
            blocking: If True, block until message received (with timeout)
            
        Returns:
            Command parameters dict or None if no message
            
        Raises:
            PermissionError: If called by MASTER
        """
        if self.role == "MASTER":
            raise PermissionError("MASTER does not receive commands via this function")
        
        flags = 0 if blocking else zmq.NOBLOCK
        
        try:
            # Receive multipart: [Topic, Message]
            topic = self.cmd_socket.recv_string(flags=flags)
            msg = self.cmd_socket.recv_json(flags=flags)
            
            # Update exp_id if included in message
            if 'exp_id' in msg:
                self.exp_id = msg['exp_id']
            
            self.logger.debug(f"Received command: {msg['params'].get('type', 'UNKNOWN')}")
            return msg['params']
            
        except zmq.Again:
            return None
        except Exception as e:
            self.logger.error(f"Error receiving command: {e}")
            return None
    
    def check_for_data(self, timeout_ms: int = 0) -> Optional[Dict[str, Any]]:
        """
        Check for incoming data (MASTER only).
        
        Args:
            timeout_ms: Timeout in milliseconds (0 = non-blocking)
            
        Returns:
            Data packet dict or None if no message
        """
        if self.role != "MASTER":
            raise PermissionError("Only MASTER can receive data via this function")
        
        try:
            if timeout_ms > 0:
                # Temporarily set timeout
                old_timeout = self.data_socket.getsockopt(zmq.RCVTIMEO)
                self.data_socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
                
            packet = self.data_socket.recv_json(flags=zmq.NOBLOCK if timeout_ms == 0 else 0)
            
            if timeout_ms > 0:
                self.data_socket.setsockopt(zmq.RCVTIMEO, old_timeout)
            
            return packet
            
        except zmq.Again:
            return None
        except Exception as e:
            self.logger.error(f"Error receiving data: {e}")
            return None
    
    def send_heartbeat(self):
        """Send heartbeat message (WORKER only)."""
        if self.role == "WORKER":
            self.send_data({"status": "alive"}, category="HEARTBEAT")
    
    def close(self):
        """Clean up sockets and context."""
        if self.cmd_socket:
            self.cmd_socket.close()
        if self.data_socket:
            self.data_socket.close()
        if self._owns_context and self.context:
            self.context.term()
        self.logger.info("LabComm closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Legacy compatibility class for existing code
class LabCommLegacy(LabComm):
    """
    Legacy compatibility wrapper.
    Maintains the original interface for backwards compatibility.
    """
    
    def __init__(self, device_name: str, role: str = "WORKER"):
        super().__init__(device_name, role)
