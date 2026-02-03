"""
ZMQ communication utilities with retry logic and timeout handling.
"""

import time
import zmq
from typing import Optional, Any, Dict, Union
import logging

from ..config import get_config
from ..exceptions import ConnectionError, TimeoutError


logger = logging.getLogger(__name__)


def connect_with_retry(
    socket: zmq.Socket,
    addr: str,
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None
) -> bool:
    """
    Connect to a ZMQ endpoint with exponential backoff retry.
    
    Args:
        socket: ZMQ socket to connect
        addr: Address to connect to (e.g., "tcp://192.168.1.100:5555")
        max_retries: Maximum number of retry attempts (default from config)
        base_delay: Initial delay between retries in seconds (default from config)
        
    Returns:
        True if connection successful
        
    Raises:
        ConnectionError: If all retries exhausted
    """
    config = get_config()
    
    if max_retries is None:
        max_retries = config.get_network('max_retries')
    if base_delay is None:
        base_delay = config.get_network('retry_base_delay')
    
    for attempt in range(max_retries):
        try:
            socket.connect(addr)
            logger.debug(f"Successfully connected to {addr}")
            return True
        except zmq.ZMQError as e:
            delay = base_delay * (2 ** attempt)  # Exponential backoff
            logger.warning(
                f"Connection attempt {attempt + 1}/{max_retries} to {addr} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)
    
    raise ConnectionError(
        f"Failed to connect to {addr} after {max_retries} attempts",
        endpoint=addr,
        retries=max_retries
    )


def create_zmq_socket(
    context: zmq.Context,
    socket_type: int,
    name: str
) -> zmq.Socket:
    """
    Create a ZMQ socket with common settings.
    
    Args:
        context: ZMQ context
        socket_type: ZMQ socket type (e.g., zmq.PUB, zmq.SUB)
        name: Socket name for logging
        
    Returns:
        Configured ZMQ socket
    """
    socket = context.socket(socket_type)
    
    # Set socket options based on type
    if socket_type in (zmq.SUB, zmq.PULL):
        # Set receive timeout
        config = get_config()
        timeout_ms = int(config.get_network('receive_timeout') * 1000)
        socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        socket.setsockopt(zmq.LINGER, 0)  # Don't wait on close
    
    if socket_type == zmq.SUB:
        # Subscribe to all by default
        socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    logger.debug(f"Created {name} socket (type={socket_type})")
    return socket


def send_with_timeout(
    socket: zmq.Socket,
    data: Union[bytes, str, dict],
    timeout_ms: int = 5000,
    flags: int = 0
) -> bool:
    """
    Send data with timeout.
    
    Args:
        socket: ZMQ socket
        data: Data to send (bytes, string, or dict for JSON)
        timeout_ms: Timeout in milliseconds
        flags: ZMQ flags
        
    Returns:
        True if sent successfully
        
    Raises:
        TimeoutError: If send times out
    """
    # Convert data to bytes
    if isinstance(data, dict):
        import json
        data = json.dumps(data).encode('utf-8')
    elif isinstance(data, str):
        data = data.encode('utf-8')
    
    # Set send timeout
    original_timeout = socket.getsockopt(zmq.SNDTIMEO)
    socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
    
    try:
        socket.send(data, flags=flags)
        return True
    except zmq.Again:
        raise TimeoutError(
            "Send operation timed out",
            timeout_seconds=timeout_ms / 1000.0,
            operation="zmq_send"
        )
    finally:
        socket.setsockopt(zmq.SNDTIMEO, original_timeout)


def recv_with_timeout(
    socket: zmq.Socket,
    timeout_ms: Optional[int] = None,
    json_decode: bool = False
) -> Optional[Any]:
    """
    Receive data with timeout.
    
    Args:
        socket: ZMQ socket
        timeout_ms: Timeout in milliseconds (None = use config default)
        json_decode: Whether to decode as JSON
        
    Returns:
        Received data, or None if timeout
        
    Raises:
        TimeoutError: If receive times out (when timeout_ms is explicitly set)
    """
    if timeout_ms is None:
        config = get_config()
        timeout_ms = int(config.get_network('receive_timeout') * 1000)
    
    # Set receive timeout
    original_timeout = socket.getsockopt(zmq.RCVTIMEO)
    socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    
    try:
        data = socket.recv()
        
        if json_decode:
            import json
            return json.loads(data.decode('utf-8'))
        return data
        
    except zmq.Again:
        # Timeout - return None for non-blocking, raise for blocking
        if timeout_ms > 0:
            return None
        raise TimeoutError(
            "Receive operation timed out",
            timeout_seconds=timeout_ms / 1000.0,
            operation="zmq_recv"
        )
    finally:
        socket.setsockopt(zmq.RCVTIMEO, original_timeout)


class ZMQConnection:
    """
    Managed ZMQ connection with automatic cleanup.
    
    Usage:
        with ZMQConnection(context, zmq.PUB, "tcp://*:5555") as conn:
            conn.send(data)
    """
    
    def __init__(
        self,
        context: zmq.Context,
        socket_type: int,
        addr: str,
        bind: bool = False,
        name: str = "zmq_conn"
    ):
        self.context = context
        self.socket_type = socket_type
        self.addr = addr
        self.bind = bind
        self.name = name
        self.socket = None
    
    def __enter__(self):
        self.socket = create_zmq_socket(self.context, self.socket_type, self.name)
        
        if self.bind:
            self.socket.bind(self.addr)
            logger.debug(f"[{self.name}] Bound to {self.addr}")
        else:
            connect_with_retry(self.socket, self.addr)
            logger.debug(f"[{self.name}] Connected to {self.addr}")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.socket:
            self.socket.close()
            logger.debug(f"[{self.name}] Socket closed")
    
    def send(self, data: Union[bytes, str, dict], timeout_ms: int = 5000) -> bool:
        """Send data through the connection."""
        return send_with_timeout(self.socket, data, timeout_ms)
    
    def recv(self, timeout_ms: Optional[int] = None, json_decode: bool = False) -> Any:
        """Receive data from the connection."""
        return recv_with_timeout(self.socket, timeout_ms, json_decode)
    
    def send_json(self, data: dict, timeout_ms: int = 5000) -> bool:
        """Send JSON data."""
        return self.send(data, timeout_ms)
    
    def recv_json(self, timeout_ms: Optional[int] = None) -> Optional[dict]:
        """Receive JSON data."""
        return self.recv(timeout_ms, json_decode=True)


class HeartbeatSender:
    """
    Background heartbeat sender for worker processes.
    Sends periodic heartbeat messages to indicate liveness.
    """
    
    def __init__(
        self,
        context: zmq.Context,
        endpoint: str,
        device_name: str,
        interval_seconds: Optional[float] = None
    ):
        self.context = context
        self.endpoint = endpoint
        self.device_name = device_name
        self.interval = interval_seconds or get_config().get_network('heartbeat_interval')
        self.socket = None
        self.running = False
        self._thread = None
    
    def start(self):
        """Start the heartbeat thread."""
        import threading
        
        self.socket = self.context.socket(zmq.PUSH)
        connect_with_retry(self.socket, self.endpoint)
        
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"[{self.device_name}] Heartbeat started (interval={self.interval}s)")
    
    def stop(self):
        """Stop the heartbeat thread."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self.socket:
            self.socket.close()
        logger.info(f"[{self.device_name}] Heartbeat stopped")
    
    def _run(self):
        """Main heartbeat loop."""
        while self.running:
            try:
                heartbeat = {
                    "type": "HEARTBEAT",
                    "source": self.device_name,
                    "timestamp": time.time()
                }
                self.socket.send_json(heartbeat, flags=zmq.NOBLOCK)
            except zmq.Again:
                pass  # Don't block if send buffer full
            except Exception as e:
                logger.error(f"[{self.device_name}] Heartbeat error: {e}")
            
            # Sleep with early exit check
            for _ in range(int(self.interval * 10)):
                if not self.running:
                    break
                time.sleep(0.1)
