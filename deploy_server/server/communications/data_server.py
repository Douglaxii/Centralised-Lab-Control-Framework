"""
Data Ingestion Server - Receives telemetry data from LabVIEW programs

Receives real-time data from:
- Wavemeter.vi: Laser frequency
- SMILE.vi: PMT counts, Pressure

Protocol: JSON over TCP (one sample per line)
Data is stored in shared telemetry buffers for Flask display.

Example data format from LabVIEW:
    {"source": "wavemeter", "channel": "laser_freq", "value": 212.456789, "timestamp": 1706380800.123}
    {"source": "smile", "channel": "pmt", "value": 1250.0, "timestamp": 1706380800.124}
    {"source": "smile", "channel": "pressure", "value": 1.2e-10, "timestamp": 1706380800.125}
"""

import socket
import json
import time
import threading
import logging
from typing import Dict, Any, Optional, Callable
from collections import deque
from pathlib import Path
from datetime import datetime

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core import get_config


# Shared telemetry storage (mirrors flask_server.py structure)
# These will be imported by flask_server to access real data
TELEMETRY_WINDOW_SECONDS = 300  # 5 minutes rolling window
TELEMETRY_MAX_POINTS = 1000

# Data storage - thread-safe with locks
_shared_telemetry_data = {
    "pos_x": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pos_y": deque(maxlen=TELEMETRY_MAX_POINTS),
    "sig_x": deque(maxlen=TELEMETRY_MAX_POINTS),
    "sig_y": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pressure": deque(maxlen=TELEMETRY_MAX_POINTS),
    "laser_freq": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pmt": deque(maxlen=TELEMETRY_MAX_POINTS),
    # Secular comparison channels
    "secular_fitted": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_predicted": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_diff": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_snr": deque(maxlen=TELEMETRY_MAX_POINTS),
}
_telemetry_lock = threading.RLock()

# Data source tracking (for UI display)
_data_sources = {
    "wavemeter": {"last_seen": 0, "connected": False},
    "smile": {"last_seen": 0, "connected": False},
    "camera": {"last_seen": 0, "connected": False},
}
_sources_lock = threading.Lock()


def get_telemetry_data():
    """Get reference to shared telemetry data (for flask_server)."""
    return _shared_telemetry_data, _telemetry_lock


def get_data_sources():
    """Get data source status (for flask_server)."""
    with _sources_lock:
        return _data_sources.copy()


def update_data_source(source: str, connected: bool = True):
    """Update data source status."""
    with _sources_lock:
        _data_sources[source] = {
            "last_seen": time.time(),
            "connected": connected
        }


class DataIngestionServer:
    """
    TCP Server that receives telemetry data from LabVIEW programs.
    
    Supports multiple simultaneous connections from different sources.
    Each data point is timestamped and stored in rolling buffers.
    """
    
    # Channel mapping from external names to internal names
    CHANNEL_MAP = {
        # Wavemeter channels
        "laser_freq": "laser_freq",
        "frequency": "laser_freq",
        "wavemeter": "laser_freq",
        "freq": "laser_freq",
        
        # SMILE PMT channels
        "pmt": "pmt",
        "pmt_counts": "pmt",
        "photon_counts": "pmt",
        
        # SMILE Pressure channels
        "pressure": "pressure",
        "chamber_pressure": "pressure",
        "vacuum": "pressure",
        
        # Camera/Image channels (from image_handler)
        "pos_x": "pos_x",
        "position_x": "pos_x",
        "ion_x": "pos_x",
        
        "pos_y": "pos_y",
        "position_y": "pos_y", 
        "ion_y": "pos_y",
        
        "sig_x": "sig_x",
        "sigma_x": "sig_x",
        "width_x": "sig_x",
        
        "sig_y": "sig_y",
        "sigma_y": "sig_y",
        "width_y": "sig_y",
        
        # Secular comparison channels
        "secular_fitted": "secular_fitted",
        "secular_predicted": "secular_predicted",
        "secular_diff": "secular_diff",
        "secular_snr": "secular_snr",
    }
    
    # Data source validation
    VALID_SOURCES = {"wavemeter", "smile", "camera", "artiq", "turbo"}
    
    def __init__(self, host: str = "0.0.0.0", port: Optional[int] = None):
        """
        Initialize data ingestion server.
        
        Args:
            host: Interface to bind to (default: all interfaces)
            port: TCP port to listen on (default from config)
        """
        self.logger = logging.getLogger("data_server")
        
        # Load configuration
        config = get_config()
        self.host = host
        self.port = port or config.get('data_ingestion.port', 5560)
        self.timeout = config.get('data_ingestion.timeout', 5.0)
        
        # Connection tracking
        self.connections = {}
        self.conn_lock = threading.Lock()
        
        # Server state
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.accept_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.stats = {
            "total_samples": 0,
            "samples_by_source": {},
            "samples_by_channel": {},
            "start_time": None
        }
        self.stats_lock = threading.Lock()
        
        self.logger.info(f"DataIngestionServer initialized ({self.host}:{self.port})")
    
    def start(self):
        """Start the data ingestion server."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        self.server_socket.settimeout(1.0)  # Allow periodic checks
        
        self.running = True
        self.stats["start_time"] = time.time()
        
        self.accept_thread = threading.Thread(
            target=self._accept_loop,
            daemon=True,
            name="DataAcceptThread"
        )
        self.accept_thread.start()
        
        self.logger.info(f"DataIngestionServer started on {self.host}:{self.port}")
        print(f"📊 Data Server listening on {self.host}:{self.port}")
        print(f"   Ready for LabVIEW connections (Wavemeter.vi, SMILE.vi)")
    
    def stop(self):
        """Stop the server."""
        self.logger.info("Stopping DataIngestionServer...")
        self.running = False
        
        # Close all client connections
        with self.conn_lock:
            for conn, info in list(self.connections.items()):
                try:
                    conn.close()
                except:
                    pass
            self.connections.clear()
        
        if self.server_socket:
            self.server_socket.close()
        
        self.logger.info("DataIngestionServer stopped")
    
    def _accept_loop(self):
        """Main accept loop for incoming connections."""
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                self.logger.info(f"Data connection from {addr}")
                
                # Handle client in new thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True,
                    name=f"DataClient-{addr[1]}"
                )
                client_thread.start()
                
                with self.conn_lock:
                    self.connections[conn] = {
                        "addr": addr,
                        "thread": client_thread,
                        "source": "unknown",
                        "connected_at": time.time()
                    }
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Accept error: {e}")
    
    def _handle_client(self, conn: socket.socket, addr: tuple):
        """Handle a single client connection."""
        source_name = "unknown"
        
        try:
            conn.settimeout(30.0)  # 30 second timeout
            buffer = ""
            
            while self.running:
                try:
                    # Receive data
                    data = conn.recv(4096).decode('utf-8')
                    if not data:
                        break  # Connection closed
                    
                    buffer += data
                    
                    # Process complete lines (JSON objects)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line:
                            self._process_data_line(line, addr)
                    
                except socket.timeout:
                    continue
                except UnicodeDecodeError as e:
                    self.logger.warning(f"Invalid UTF-8 from {addr}: {e}")
                    buffer = ""  # Reset buffer
                    continue
                    
        except Exception as e:
            self.logger.error(f"Client handler error for {addr}: {e}")
        finally:
            conn.close()
            with self.conn_lock:
                if conn in self.connections:
                    source_name = self.connections[conn].get("source", "unknown")
                    del self.connections[conn]
            
            # Mark source as disconnected
            if source_name != "unknown":
                update_data_source(source_name, connected=False)
            
            self.logger.info(f"Data client {addr} ({source_name}) disconnected")
    
    def _process_data_line(self, line: str, addr: tuple):
        """Process a single line of JSON data."""
        try:
            data = json.loads(line)
            
            # Extract fields
            source = data.get("source", "unknown").lower()
            channel = data.get("channel", data.get("type", "unknown")).lower()
            value = data.get("value")
            timestamp = data.get("timestamp", time.time())
            
            # Validate source
            if source not in self.VALID_SOURCES:
                self.logger.warning(f"Unknown source '{source}' from {addr}")
                return
            
            # Map channel name
            internal_channel = self.CHANNEL_MAP.get(channel, channel)
            
            if internal_channel not in _shared_telemetry_data:
                self.logger.warning(f"Unknown channel '{channel}' from {source}")
                return
            
            # Validate value
            if value is None or not isinstance(value, (int, float)):
                self.logger.warning(f"Invalid value from {source}/{channel}: {value}")
                return
            
            # Store data
            with _telemetry_lock:
                _shared_telemetry_data[internal_channel].append((timestamp, float(value)))
            
            # Update source tracking
            update_data_source(source, connected=True)
            
            # Update connection info with source name
            with self.conn_lock:
                for conn, info in self.connections.items():
                    if info["addr"] == addr:
                        info["source"] = source
                        break
            
            # Update statistics
            with self.stats_lock:
                self.stats["total_samples"] += 1
                self.stats["samples_by_source"][source] = \
                    self.stats["samples_by_source"].get(source, 0) + 1
                self.stats["samples_by_channel"][internal_channel] = \
                    self.stats["samples_by_channel"].get(internal_channel, 0) + 1
            
            self.logger.debug(f"Data: {source}/{internal_channel} = {value}")
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"Invalid JSON from {addr}: {e} - Line: {line[:100]}")
        except Exception as e:
            self.logger.error(f"Error processing data from {addr}: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get server statistics."""
        with self.stats_lock:
            uptime = time.time() - self.stats["start_time"] if self.stats["start_time"] else 0
            
            return {
                "uptime_seconds": uptime,
                "total_samples": self.stats["total_samples"],
                "samples_by_source": self.stats["samples_by_source"].copy(),
                "samples_by_channel": self.stats["samples_by_channel"].copy(),
                "active_connections": len(self.connections),
                "connection_details": [
                    {"addr": info["addr"], "source": info.get("source", "unknown")}
                    for info in self.connections.values()
                ]
            }
    
    def get_recent_data(self, channel: str, window_seconds: float = 300.0) -> list:
        """Get recent data for a specific channel."""
        if channel not in _shared_telemetry_data:
            return []
        
        cutoff = time.time() - window_seconds
        
        with _telemetry_lock:
            return [
                {"timestamp": ts, "value": val}
                for ts, val in _shared_telemetry_data[channel]
                if ts >= cutoff
            ]


class DataClient:
    """
    Client for sending data to the ingestion server.
    
    Can be used from Python scripts to send test data,
    or as a reference for LabVIEW implementation.
    """
    
    def __init__(self, server_host: str = "127.0.0.1", server_port: int = 5560):
        self.server_host = server_host
        self.server_port = server_port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.source_name = "unknown"
    
    def connect(self, source_name: str) -> bool:
        """Connect to data server and identify source."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.source_name = source_name
            self.connected = True
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def send_data(self, channel: str, value: float, timestamp: Optional[float] = None) -> bool:
        """Send a single data point."""
        if not self.connected:
            return False
        
        try:
            data = {
                "source": self.source_name,
                "channel": channel,
                "value": float(value),
                "timestamp": timestamp or time.time()
            }
            
            message = json.dumps(data) + "\n"
            self.socket.sendall(message.encode('utf-8'))
            return True
            
        except Exception as e:
            print(f"Send error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from server."""
        if self.socket:
            self.socket.close()
        self.connected = False


def start_data_server():
    """Standalone entry point for running the data server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Data Ingestion Server")
    parser.add_argument("--port", type=int, default=None, help="TCP port")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )
    
    server = DataIngestionServer(host=args.host, port=args.port)
    server.start()
    
    try:
        while True:
            time.sleep(5)
            stats = server.get_statistics()
            print(f"\r📈 Samples: {stats['total_samples']}, "
                  f"Connections: {stats['active_connections']}, "
                  f"Rate: {stats['total_samples'] / max(stats['uptime_seconds'], 1):.1f} Hz", 
                  end='', flush=True)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        server.stop()


if __name__ == "__main__":
    start_data_server()
