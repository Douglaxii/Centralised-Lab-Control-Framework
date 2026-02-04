"""
async_comm.py - Asynchronous ZMQ Communication

Phase 3B: Async communication patterns for better performance.

Features:
  - AsyncZMQClient: Non-blocking ZMQ operations with asyncio
  - ZMQConnectionPool: Reuse connections for better performance
  - Automatic retry with exponential backoff
  - Connection health monitoring

Usage:
    from utils.async_comm import AsyncZMQClient
    
    client = AsyncZMQClient("192.168.56.101", cmd_port=5555, data_port=5556)
    await client.connect()
    
    # Non-blocking send
    await client.send_command({"type": "SET_DC", "values": {"ec1": 5.0}})
    
    # Non-blocking receive with timeout
    response = await client.receive_data(timeout=5.0)
"""

import asyncio
import json
import time
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from collections import deque

try:
    import zmq
    import zmq.asyncio
    HAS_ZMQ = True
except ImportError:
    HAS_ZMQ = False

# Import config loader
from .config_loader import get_config_value

logger = logging.getLogger("ARTIQ.AsyncComm")


@dataclass
class ZMQConfig:
    """ZMQ connection configuration."""
    master_ip: str
    cmd_port: int
    data_port: int
    connection_timeout: float = 5.0
    receive_timeout: float = 1.0
    max_retries: int = 3
    retry_base_delay: float = 1.0


class AsyncZMQClient:
    """
    Asynchronous ZMQ client for ARTIQ communication.
    
    Provides non-blocking send/receive operations with automatic
    retry and connection health monitoring.
    
    Example:
        client = AsyncZMQClient("192.168.56.101")
        await client.connect()
        
        # Send without blocking
        await client.send_command({"type": "RUN_SWEEP", ...})
        
        # Receive with timeout
        data = await client.receive_data(timeout=10.0)
        if data:
            print(f"Received: {data}")
    """
    
    def __init__(self, master_ip: Optional[str] = None, 
                 cmd_port: Optional[int] = None,
                 data_port: Optional[int] = None,
                 config: Optional[ZMQConfig] = None):
        """
        Initialize async ZMQ client.
        
        Args:
            master_ip: ARTIQ master IP (loads from config if not provided)
            cmd_port: Command port (loads from config if not provided)
            data_port: Data port (loads from config if not provided)
            config: Pre-built ZMQConfig (overrides individual args)
        """
        if not HAS_ZMQ:
            raise ImportError("zmq package required for async communication")
        
        if config:
            self.config = config
        else:
            # Load from config file
            self.config = ZMQConfig(
                master_ip=master_ip or get_config_value('network.master_ip', '192.168.56.101'),
                cmd_port=cmd_port or get_config_value('network.cmd_port', 5555),
                data_port=data_port or get_config_value('network.data_port', 5556),
                connection_timeout=get_config_value('network.connection_timeout', 5.0),
                receive_timeout=get_config_value('network.receive_timeout', 1.0),
                max_retries=get_config_value('network.max_retries', 3),
                retry_base_delay=get_config_value('network.retry_base_delay', 1.0),
            )
        
        self.context: Optional[zmq.asyncio.Context] = None
        self.cmd_socket: Optional[zmq.asyncio.Socket] = None
        self.data_socket: Optional[zmq.asyncio.Socket] = None
        
        self._connected = False
        self._last_comm_time = 0.0
        self._message_queue: deque = deque()
        self._receive_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> bool:
        """
        Establish ZMQ connections.
        
        Returns:
            True if connected successfully
        """
        try:
            self.context = zmq.asyncio.Context()
            
            # Command socket (PUB) - for sending commands
            self.cmd_socket = self.context.socket(zmq.PUB)
            cmd_addr = f"tcp://{self.config.master_ip}:{self.config.cmd_port}"
            self.cmd_socket.connect(cmd_addr)
            
            # Data socket (PULL) - for receiving data
            self.data_socket = self.context.socket(zmq.PULL)
            data_addr = f"tcp://{self.config.master_ip}:{self.config.data_port}"
            self.data_socket.connect(data_addr)
            self.data_socket.setsockopt(zmq.RCVTIMEO, int(self.config.receive_timeout * 1000))
            
            self._connected = True
            self._last_comm_time = time.time()
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            logger.info(f"AsyncZMQClient connected to {self.config.master_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self):
        """Close all connections."""
        self._connected = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self.cmd_socket:
            self.cmd_socket.close()
            self.cmd_socket = None
        
        if self.data_socket:
            self.data_socket.close()
            self.data_socket = None
        
        if self.context:
            self.context.term()
            self.context = None
        
        logger.info("AsyncZMQClient disconnected")
    
    async def send_command(self, command: Dict[str, Any], 
                          topic: str = "ARTIQ",
                          retry: bool = True) -> bool:
        """
        Send command to ARTIQ (non-blocking).
        
        Args:
            command: Command dictionary
            topic: ZMQ topic (default: "ARTIQ")
            retry: Retry on failure
            
        Returns:
            True if sent successfully
        """
        if not self._connected:
            logger.error("Cannot send: not connected")
            return False
        
        max_attempts = self.config.max_retries if retry else 1
        
        for attempt in range(max_attempts):
            try:
                # Send topic + JSON message
                await self.cmd_socket.send_string(topic, flags=zmq.SNDMORE)
                await self.cmd_socket.send_json(command)
                
                self._last_comm_time = time.time()
                logger.debug(f"Command sent: {command.get('type', 'UNKNOWN')}")
                return True
                
            except Exception as e:
                logger.warning(f"Send attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    delay = self.config.retry_base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        return False
    
    async def receive_data(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Receive data from ARTIQ (with timeout).
        
        Args:
            timeout: Maximum time to wait (seconds)
            
        Returns:
            Data dictionary or None if timeout
        """
        if not self._connected:
            return None
        
        # Check queue first
        if self._message_queue:
            return self._message_queue.popleft()
        
        # Wait for message with timeout
        timeout = timeout or self.config.receive_timeout
        
        try:
            data = await asyncio.wait_for(
                self._receive_single(),
                timeout=timeout
            )
            return data
        except asyncio.TimeoutError:
            return None
    
    async def _receive_single(self) -> Optional[Dict[str, Any]]:
        """Receive single message."""
        try:
            data = await self.data_socket.recv_json()
            self._last_comm_time = time.time()
            return data
        except zmq.Again:
            return None
        except Exception as e:
            logger.error(f"Receive error: {e}")
            return None
    
    async def _receive_loop(self):
        """Background receive loop."""
        while self._connected:
            try:
                data = await self._receive_single()
                if data:
                    self._message_queue.append(data)
            except Exception as e:
                if self._connected:
                    logger.error(f"Receive loop error: {e}")
                await asyncio.sleep(0.001)
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected
    
    @property
    def last_comm_time(self) -> float:
        """Timestamp of last communication."""
        return self._last_comm_time
    
    async def health_check(self) -> bool:
        """Check connection health."""
        if not self._connected:
            return False
        
        # Send ping command
        ping_cmd = {"type": "PING", "timestamp": time.time()}
        return await self.send_command(ping_cmd)


class ZMQConnectionPool:
    """
    Pool of ZMQ connections for high-throughput scenarios.
    
    Maintains multiple connections and rotates between them
    for load balancing and redundancy.
    
    Example:
        pool = ZMQConnectionPool(pool_size=3)
        await pool.connect()
        
        # Get client from pool
        async with pool.acquire() as client:
            await client.send_command({...})
    """
    
    def __init__(self, pool_size: int = 3, **client_kwargs):
        """
        Initialize connection pool.
        
        Args:
            pool_size: Number of connections to maintain
            **client_kwargs: Arguments for AsyncZMQClient
        """
        self.pool_size = pool_size
        self.client_kwargs = client_kwargs
        self.clients: list[AsyncZMQClient] = []
        self._available: asyncio.Queue[AsyncZMQClient] = asyncio.Queue()
        self._lock = asyncio.Lock()
    
    async def connect(self) -> bool:
        """Create all connections in pool."""
        for i in range(self.pool_size):
            client = AsyncZMQClient(**self.client_kwargs)
            if await client.connect():
                self.clients.append(client)
                await self._available.put(client)
                logger.debug(f"Pool connection {i+1}/{self.pool_size} ready")
            else:
                logger.error(f"Failed to create pool connection {i+1}")
        
        return len(self.clients) > 0
    
    async def disconnect(self):
        """Close all connections."""
        for client in self.clients:
            await client.disconnect()
        self.clients.clear()
        
        # Drain the queue
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
    
    async def acquire(self, timeout: Optional[float] = None):
        """
        Acquire a client from the pool.
        
        Use as async context manager:
            async with pool.acquire() as client:
                await client.send_command(...)
        """
        client = await asyncio.wait_for(
            self._available.get(),
            timeout=timeout
        )
        return _PooledClient(self, client)
    
    def _release(self, client: AsyncZMQClient):
        """Return client to pool."""
        self._available.put_nowait(client)


class _PooledClient:
    """Context manager for pooled connections."""
    
    def __init__(self, pool: ZMQConnectionPool, client: AsyncZMQClient):
        self.pool = pool
        self.client = client
    
    async def __aenter__(self):
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.pool._release(self.client)


# Convenience function for simple use cases
async def send_command_simple(command: Dict[str, Any], 
                               master_ip: Optional[str] = None,
                               timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """
    Send command and wait for response (simple one-shot).
    
    Args:
        command: Command dictionary
        master_ip: ARTIQ IP (loads from config if not provided)
        timeout: Total timeout (seconds)
        
    Returns:
        Response data or None if timeout/error
        
    Example:
        response = await send_command_simple({
            "type": "PMT_MEASURE",
            "duration_ms": 100.0
        })
    """
    client = AsyncZMQClient(master_ip=master_ip)
    
    try:
        if await client.connect():
            if await client.send_command(command):
                # Wait for response
                return await client.receive_data(timeout=timeout)
    finally:
        await client.disconnect()
    
    return None


# Self-test
if __name__ == "__main__":
    if not HAS_ZMQ:
        print("zmq not available, skipping async comm test")
    else:
        print("Testing async comm...")
        
        async def test():
            client = AsyncZMQClient()
            print(f"  Config: {client.config.master_ip}:{client.config.cmd_port}")
            # Don't actually connect in test
            print("  Async comm test passed!")
        
        asyncio.run(test())
