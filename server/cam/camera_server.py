"""
Unified Camera Server

Receives camera frames via TCP, saves raw JPGs, processes images,
and saves annotated JPGs for Flask streaming.

Data Flow:
1. Receive frame data via TCP (port 5558)
2. Save raw JPG to Y:/Xi/Data/jpg_frames/
3. Process with Image_Handler
4. Save annotated JPG to Y:/Xi/Data/jpg_frames_labelled/
5. Flask streams from jpg_frames_labelled/
"""

import os
import sys
import socket
import threading
import struct
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import time
import queue

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core import get_config
from server.cam.image_handler import Image_Handler

# Configuration
config = get_config()
BASE_OUTPUT_PATH = config.get_path('output_base')
RAW_FRAMES_DIR = os.path.join(BASE_OUTPUT_PATH, 'jpg_frames')
LABELLED_FRAMES_DIR = os.path.join(BASE_OUTPUT_PATH, 'jpg_frames_labelled')

# TCP Server settings
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = config.get('network.camera_port', 5558)

# Threading
frame_queue = queue.Queue(maxsize=100)
stop_event = threading.Event()

# Ensure output directories exist
os.makedirs(RAW_FRAMES_DIR, exist_ok=True)
os.makedirs(LABELLED_FRAMES_DIR, exist_ok=True)


def receive_all(conn, n):
    """Receive exactly n bytes from socket."""
    data = bytearray()
    while len(data) < n:
        packet = conn.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)


def handle_camera_client(conn, addr):
    """
    Handle incoming camera connection.
    Protocol: [4 bytes: image_size][image_data]
    """
    print(f"[Camera] Connection from {addr}")
    
    try:
        while not stop_event.is_set():
            # Receive image size (4 bytes, big-endian)
            size_data = receive_all(conn, 4)
            if not size_data:
                break
            
            image_size = struct.unpack('>I', size_data)[0]
            
            # Receive image data
            image_data = receive_all(conn, image_size)
            if not image_data:
                break
            
            # Put in queue for processing
            try:
                frame_queue.put({
                    'data': image_data,
                    'timestamp': datetime.now(),
                    'source': addr[0]
                }, block=False)
            except queue.Full:
                print("[Camera] Queue full, dropping frame")
                
    except Exception as e:
        print(f"[Camera] Client error: {e}")
    finally:
        conn.close()
        print(f"[Camera] Connection closed: {addr}")


def save_raw_frame(image_data, timestamp):
    """Save raw JPG frame to jpg_frames directory."""
    date_str = timestamp.strftime("%y%m%d")
    time_str = timestamp.strftime("%H-%M-%S_%f")[:-3]  # milliseconds
    
    # Create date subdirectory
    raw_dir = os.path.join(RAW_FRAMES_DIR, date_str)
    os.makedirs(raw_dir, exist_ok=True)
    
    # Save raw JPG
    filename = f"{time_str}.jpg"
    filepath = os.path.join(raw_dir, filename)
    
    with open(filepath, 'wb') as f:
        f.write(image_data)
    
    return filepath


def process_and_save_annotated(raw_path, timestamp):
    """Process image and save annotated version."""
    date_str = timestamp.strftime("%y%m%d")
    time_str = timestamp.strftime("%H-%M-%S_%f")[:-3]
    
    # Create date subdirectory
    labelled_dir = os.path.join(LABELLED_FRAMES_DIR, date_str)
    os.makedirs(labelled_dir, exist_ok=True)
    
    try:
        # Process with Image_Handler
        handler = Image_Handler(
            filename=raw_path,
            xstart=0, xfinish=300,
            ystart=0, yfinish=300,
            analysis=2,
            radius=20
        )
        
        # Determine output image
        if handler.annotated_frame is not None:
            # Use annotated frame with circles and fit info
            output_img = cv2.cvtColor(handler.annotated_frame, cv2.COLOR_RGB2BGR)
        elif handler.operation_array is not None:
            # No ions detected - save normalized raw image
            output_img = cv2.normalize(
                handler.operation_array, None, 0, 255, cv2.NORM_MINMAX
            ).astype('uint8')
        else:
            return None, 0
        
        # Save annotated JPG
        filename = f"{time_str}_labelled.jpg"
        filepath = os.path.join(labelled_dir, filename)
        cv2.imwrite(filepath, output_img)
        
        return filepath, handler.atom_count
        
    except Exception as e:
        print(f"[Processor] Error processing {raw_path}: {e}")
        return None, 0


def processor_thread():
    """
    Consumer thread: processes frames from queue.
    Saves raw JPG, creates annotated JPG.
    """
    print(f"[Processor] Started")
    print(f"[Processor] Raw frames: {RAW_FRAMES_DIR}")
    print(f"[Processor] Labelled frames: {LABELLED_FRAMES_DIR}")
    
    while not stop_event.is_set():
        try:
            # Get frame from queue (blocks for 1 sec)
            frame = frame_queue.get(timeout=1)
        except queue.Empty:
            continue
        
        try:
            timestamp = frame['timestamp']
            image_data = frame['data']
            
            # 1. Save raw JPG
            raw_path = save_raw_frame(image_data, timestamp)
            
            # 2. Process and save annotated JPG
            labelled_path, atom_count = process_and_save_annotated(raw_path, timestamp)
            
            if labelled_path:
                print(f"[Processor] Saved: {os.path.basename(raw_path)} -> "
                      f"{atom_count} atoms")
            else:
                print(f"[Processor] Saved raw: {os.path.basename(raw_path)}")
                
        except Exception as e:
            print(f"[Processor] Error: {e}")
        finally:
            frame_queue.task_done()


def command_handler_thread():
    """
    Handle simple TCP commands for camera control.
    Port: 5559 (camera commands)
    """
    cmd_port = 5559
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, cmd_port))
        s.listen(5)
        print(f"[Command] Listening on {HOST}:{cmd_port}")
        
        while not stop_event.is_set():
            try:
                s.settimeout(1.0)
                conn, addr = s.accept()
                
                with conn:
                    data = conn.recv(1024).decode().strip()
                    if not data:
                        continue
                    
                    print(f"[Command] Received: {data}")
                    
                    if data == "START":
                        conn.sendall(b"OK: Camera server running\n")
                    elif data == "STATUS":
                        queue_size = frame_queue.qsize()
                        conn.sendall(f"OK: Queue size: {queue_size}\n".encode())
                    elif data == "STOP":
                        conn.sendall(b"OK: Stopping...\n")
                        stop_event.set()
                    else:
                        conn.sendall(b"ERROR: Unknown command\n")
                        
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Command] Error: {e}")


def main():
    """Main camera server."""
    print("=" * 60)
    print("Unified Camera Server")
    print("=" * 60)
    print(f"Data port (frames): {PORT}")
    print(f"Command port: 5559")
    print(f"Raw frames: {RAW_FRAMES_DIR}")
    print(f"Labelled frames: {LABELLED_FRAMES_DIR}")
    print("=" * 60)
    
    # Start processor thread
    t_processor = threading.Thread(target=processor_thread, daemon=True)
    t_processor.start()
    
    # Start command handler thread
    t_command = threading.Thread(target=command_handler_thread, daemon=True)
    t_command.start()
    
    # Main frame receiver loop
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        print(f"[Server] Listening for camera data on {HOST}:{PORT}")
        
        try:
            while not stop_event.is_set():
                s.settimeout(1.0)
                try:
                    conn, addr = s.accept()
                    # Handle each client in a new thread
                    t_client = threading.Thread(
                        target=handle_camera_client,
                        args=(conn, addr),
                        daemon=True
                    )
                    t_client.start()
                except socket.timeout:
                    continue
                    
        except KeyboardInterrupt:
            print("\n[Server] Shutting down...")
        finally:
            stop_event.set()
            t_processor.join(timeout=2)
            print("[Server] Stopped")


if __name__ == "__main__":
    main()
