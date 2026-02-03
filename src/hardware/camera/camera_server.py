"""
Unified Camera Server with CCD Camera Support

Initializes and controls Hamamatsu CCD camera via camera_logic module.
Receives commands via TCP, handles camera operations.

Commands:
- START: Start single recording (DCIMG + JPG)
- START_INF: Start infinite capture mode (JPG only, circular buffer)
- STOP: Stop current capture
- STATUS: Get camera status
"""

import os
import sys
from pathlib import Path

# Add camera control path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import socket
import threading
import time
import logging
from datetime import datetime

# Import camera logic module (wrapper around camera_recording)
from camera_logic import start_camera, start_camera_inf, stop_camera

# Add project root for core imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import core utilities
try:
    from core import get_config, setup_logging
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False

# Configuration
if CORE_AVAILABLE:
    config = get_config()
    PORT = config.get('network.camera_port', 5558)
else:
    PORT = 5558

# TCP Server settings
HOST = '0.0.0.0'  # Listen on all interfaces

# Camera state
camera_active = False
capture_start_time = None

# Logger setup
logger = logging.getLogger("CameraServer")


def init_logging():
    """Initialize logging."""
    log_format = '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    
    # Ensure log directory exists
    log_dir = Path('logs/server')
    log_dir.mkdir(parents=True, exist_ok=True)
    
    if CORE_AVAILABLE:
        setup_logging(component="camera")
    else:
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(str(log_dir / 'camera.log'), mode='a')
            ]
        )


def get_status():
    """Get current camera status."""
    global camera_active
    
    if camera_active:
        elapsed = ""
        if capture_start_time:
            duration = time.time() - capture_start_time
            elapsed = f" (running for {duration:.1f}s)"
        return f"Camera active{capture_start_time and elapsed or ''}"
    else:
        return "Camera ready (idle)"


def handle_client(conn, addr):
    """Handle incoming TCP client connection."""
    global camera_active, capture_start_time
    
    logger.info(f"Connection from {addr}")
    
    try:
        with conn:
            while True:
                data = conn.recv(1024).decode().strip()
                if not data:
                    break
                
                logger.info(f"Command received: {data}")
                
                if data == "START":
                    try:
                        start_camera()
                        camera_active = True
                        capture_start_time = time.time()
                        conn.sendall(b"OK: Recording started\n")
                        logger.info("Recording started")
                    except Exception as e:
                        logger.error(f"Failed to start recording: {e}")
                        conn.sendall(f"ERROR: {e}\n".encode())
                
                elif data == "START_INF":
                    try:
                        start_camera_inf()
                        camera_active = True
                        capture_start_time = time.time()
                        conn.sendall(b"OK: Infinite capture started\n")
                        logger.info("Infinite capture started")
                    except Exception as e:
                        logger.error(f"Failed to start infinite capture: {e}")
                        conn.sendall(f"ERROR: {e}\n".encode())
                
                elif data == "STOP":
                    try:
                        stop_camera()
                        camera_active = False
                        capture_start_time = None
                        conn.sendall(b"OK: Capture stopped\n")
                        logger.info("Capture stopped")
                    except Exception as e:
                        logger.error(f"Failed to stop capture: {e}")
                        conn.sendall(f"ERROR: {e}\n".encode())
                
                elif data == "STATUS":
                    status = get_status()
                    conn.sendall(f"STATUS: {status}\n".encode())
                
                elif data.startswith("EXP_ID:"):
                    # Handle experiment ID (for metadata)
                    exp_id = data.split(":", 1)[1].strip()
                    logger.info(f"Experiment ID set: {exp_id}")
                    conn.sendall(f"OK: Experiment ID set to {exp_id}\n".encode())
                
                else:
                    conn.sendall(b"ERROR: Unknown command\n")
                    
    except Exception as e:
        logger.error(f"Client handler error: {e}")
    finally:
        logger.info(f"Connection closed: {addr}")


def ensure_directories():
    """Ensure all required data directories exist."""
    import os
    
    # Try to get paths from config first
    try:
        from core import get_config
        cfg = get_config()
        data_paths = [
            cfg.get('camera.raw_frames_path') or cfg.get('paths.jpg_frames') or './data/jpg_frames',
            cfg.get('camera.labelled_frames_path') or cfg.get('paths.jpg_frames_labelled') or './data/jpg_frames_labelled',
            cfg.get('camera.ion_data_path') or cfg.get('paths.ion_data') or './data/ion_data',
            cfg.get('camera.ion_uncertainty_path') or cfg.get('paths.ion_uncertainty') or './data/ion_uncertainty',
            cfg.get('paths.camera_settings') or './data/camera/settings',
            'logs/server'
        ]
    except:
        # Fallback to default paths
        data_paths = [
            './data/jpg_frames',
            './data/jpg_frames_labelled',
            './data/ion_data',
            './data/ion_uncertainty',
            './data/camera/settings',
            'logs/server'
        ]
    
    for path in data_paths:
        try:
            os.makedirs(path, exist_ok=True)
            logger.debug(f"Ensured directory exists: {path}")
        except Exception as e:
            logger.warning(f"Could not create directory {path}: {e}")


def main():
    """Main camera server."""
    
    # Initialize logging
    init_logging()
    
    logger.info("=" * 60)
    logger.info("Camera Server Starting...")
    logger.info(f"Listen on {HOST}:{PORT}")
    logger.info("Commands: START, START_INF, STOP, STATUS")
    logger.info("=" * 60)
    
    # Ensure output directories exist
    ensure_directories()
    
    # Additional paths from config if available
    if CORE_AVAILABLE:
        try:
            from camera_recording import FRAME_PATH
            os.makedirs(FRAME_PATH, exist_ok=True)
            logger.info(f"Frame path ready: {FRAME_PATH}")
        except Exception as e:
            logger.warning(f"Could not create FRAME_PATH: {e}")
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen(5)
            logger.info(f"TCP Server running on {HOST}:{PORT}")
            
            while True:
                s.settimeout(1.0)
                try:
                    conn, addr = s.accept()
                    client_thread = threading.Thread(
                        target=handle_client,
                        args=(conn, addr),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                    
    except KeyboardInterrupt:
        logger.info("\nShutting down camera server...")
    finally:
        stop_camera()
        logger.info("Camera server stopped")


if __name__ == "__main__":
    main()
