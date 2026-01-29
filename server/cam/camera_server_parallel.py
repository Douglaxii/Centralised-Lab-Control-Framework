"""
Parallel Camera Server - Optimized for Intel Core i9 + NVIDIA Quadro P400
Uses ProcessPoolExecutor for true multi-core image processing.
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
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
from functools import partial

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core import get_config

# ==============================================================================
# CONFIGURATION
# ==============================================================================
config = get_config()
BASE_OUTPUT_PATH = config.get_path('output_base')
RAW_FRAMES_DIR = os.path.join(BASE_OUTPUT_PATH, 'jpg_frames')
LABELLED_FRAMES_DIR = os.path.join(BASE_OUTPUT_PATH, 'jpg_frames_labelled')
JSON_DIR = os.path.join(BASE_OUTPUT_PATH, 'cam_json')

# Use 75% of available cores for image processing (leave some for system/Flask)
MAX_WORKERS = max(2, int(mp.cpu_count() * 0.75))
print(f"[ParallelServer] Intel Core i9 detected: {mp.cpu_count()} cores, using {MAX_WORKERS} workers")

# TCP Server settings
HOST = '0.0.0.0'
PORT = config.get('network.camera_port', 5558)

# Threading
frame_queue = queue.Queue(maxsize=200)  # Larger buffer for parallel processing
result_queue = queue.Queue()
stop_event = threading.Event()

# Ensure output directories exist
os.makedirs(RAW_FRAMES_DIR, exist_ok=True)
os.makedirs(LABELLED_FRAMES_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)


# ==============================================================================
# WORKER PROCESS FUNCTIONS (must be at module level for pickling)
# ==============================================================================
def init_worker():
    """Initialize worker process - import numba-optimized handler."""
    global Image_Handler
    try:
        from server.cam.image_handler_optimized import Image_Handler as IH
        Image_Handler = IH
    except ImportError:
        from server.cam.image_handler import Image_Handler as IH
        Image_Handler = IH

def process_frame_worker(args):
    """
    Worker function that runs in separate process.
    Processes a single frame and returns results.
    
    Args:
        args: (image_data, timestamp_str, date_str, frame_id)
    
    Returns:
        dict with processing results
    """
    image_data, timestamp_str, date_str, frame_id = args
    
    try:
        # Decode image
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        
        if img is None:
            return {'frame_id': frame_id, 'error': 'Failed to decode image'}
        
        # Create temporary file path
        temp_path = os.path.join(RAW_FRAMES_DIR, f"temp_{frame_id}.jpg")
        cv2.imwrite(temp_path, img)
        
        # Process with Image_Handler (Numba-optimized)
        handler = Image_Handler(
            filename=temp_path,
            xstart=0, xfinish=min(300, img.shape[0]),
            ystart=0, yfinish=min(300, img.shape[1]),
            analysis=2,
            radius=20,
            use_gpu=False  # GPU doesn't work well across processes
        )
        
        # Clean up temp file
        try:
            os.remove(temp_path)
        except:
            pass
        
        # Prepare output
        result = {
            'frame_id': frame_id,
            'timestamp': timestamp_str,
            'date': date_str,
            'atom_count': handler.atom_count,
            'centers': handler.Centers,
            'popt': [p.tolist() for p in handler.Popt] if handler.Popt else [],
            'perr': [p.tolist() for p in handler.Perr] if handler.Perr else [],
        }
        
        # Get annotated image if available
        if handler.annotated_frame is not None:
            result['annotated'] = handler.annotated_frame
        elif handler.operation_array is not None:
            result['annotated'] = cv2.normalize(
                handler.operation_array, None, 0, 255, cv2.NORM_MINMAX
            ).astype(np.uint8)
        
        return result
        
    except Exception as e:
        return {'frame_id': frame_id, 'error': str(e)}


# ==============================================================================
# NETWORK & I/O THREADS
# ==============================================================================
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
    """Handle incoming camera connection."""
    print(f"[Camera] Connection from {addr}")
    
    try:
        while not stop_event.is_set():
            # Receive image size
            size_data = receive_all(conn, 4)
            if not size_data:
                break
            
            image_size = struct.unpack('>I', size_data)[0]
            
            # Receive image data
            image_data = receive_all(conn, image_size)
            if not image_data:
                break
            
            # Put in queue
            try:
                frame_queue.put({
                    'data': image_data,
                    'timestamp': datetime.now(),
                    'source': addr[0],
                    'size': image_size
                }, block=False)
            except queue.Full:
                print("[Camera] Queue full, dropping frame")
                
    except Exception as e:
        print(f"[Camera] Client error: {e}")
    finally:
        conn.close()
        print(f"[Camera] Connection closed: {addr}")


def result_writer_thread():
    """
    Dedicated thread for writing results to disk.
    This keeps I/O off the processing threads.
    """
    print("[ResultWriter] Started")
    
    while not stop_event.is_set():
        try:
            result = result_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        
        try:
            if 'error' in result:
                print(f"[ResultWriter] Frame {result['frame_id']} error: {result['error']}")
                continue
            
            date_str = result['date']
            timestamp_str = result['timestamp']
            
            # Ensure directories exist
            labelled_dir = os.path.join(LABELLED_FRAMES_DIR, date_str)
            json_dir = os.path.join(BASE_OUTPUT_PATH, date_str, 'cam_json')
            os.makedirs(labelled_dir, exist_ok=True)
            os.makedirs(json_dir, exist_ok=True)
            
            # Save annotated image
            if 'annotated' in result:
                annotated_path = os.path.join(labelled_dir, f"{timestamp_str}_labelled.jpg")
                if len(result['annotated'].shape) == 3:
                    cv2.imwrite(annotated_path, cv2.cvtColor(result['annotated'], cv2.COLOR_RGB2BGR))
                else:
                    cv2.imwrite(annotated_path, result['annotated'])
            
            # Save JSON if atoms detected
            if result['atom_count'] > 0:
                json_path = os.path.join(json_dir, f"{timestamp_str}_data.json")
                json_data = {
                    'timestamp': timestamp_str,
                    'date': date_str,
                    'atom_count': result['atom_count'],
                    'atoms': []
                }
                
                for i, (popt, perr) in enumerate(zip(result['popt'], result['perr'])):
                    if all(v == 0 for v in popt):
                        continue
                    
                    json_data['atoms'].append({
                        'id': i + 1,
                        'x0': popt[0],
                        'y0': popt[1],
                        'sigma_x': popt[2],
                        'R_y': popt[3],
                        'A_x': popt[4],
                        'A_y': popt[5],
                        'offset_x': popt[6],
                        'offset_y': popt[7],
                        'fit_error': perr
                    })
                
                with open(json_path, 'w') as f:
                    json.dump(json_data, f, indent=2)
            
            print(f"[ResultWriter] Frame {result['frame_id']}: {result['atom_count']} atoms")
            
        except Exception as e:
            print(f"[ResultWriter] Error: {e}")


def main():
    """Main server with parallel processing."""
    print("=" * 60)
    print("Parallel Camera Server - Intel Core i9 Optimized")
    print("=" * 60)
    print(f"Workers: {MAX_WORKERS}")
    print(f"Data port: {PORT}")
    print(f"Raw frames: {RAW_FRAMES_DIR}")
    print(f"Labelled frames: {LABELLED_FRAMES_DIR}")
    print("=" * 60)
    
    # Start result writer thread
    t_writer = threading.Thread(target=result_writer_thread, daemon=True)
    t_writer.start()
    
    # Frame ID counter
    frame_counter = 0
    pending_futures = {}
    
    # Create process pool
    with ProcessPoolExecutor(max_workers=MAX_WORKERS, initializer=init_worker) as executor:
        print("[Server] Process pool ready")
        
        # Start socket server in background thread
        def socket_server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, PORT))
                s.listen(5)
                print(f"[Socket] Listening on {HOST}:{PORT}")
                
                while not stop_event.is_set():
                    try:
                        s.settimeout(1.0)
                        conn, addr = s.accept()
                        t_client = threading.Thread(
                            target=handle_camera_client,
                            args=(conn, addr),
                            daemon=True
                        )
                        t_client.start()
                    except socket.timeout:
                        continue
        
        t_socket = threading.Thread(target=socket_server, daemon=True)
        t_socket.start()
        
        try:
            while not stop_event.is_set():
                # Submit new frames to process pool
                while not frame_queue.empty() and len(pending_futures) < MAX_WORKERS * 2:
                    try:
                        frame = frame_queue.get_nowait()
                        frame_counter += 1
                        
                        timestamp = frame['timestamp']
                        date_str = timestamp.strftime("%y%m%d")
                        timestamp_str = timestamp.strftime("%H-%M-%S_%f")[:-3]
                        
                        # Submit to process pool
                        future = executor.submit(
                            process_frame_worker,
                            (frame['data'], timestamp_str, date_str, frame_counter)
                        )
                        pending_futures[future] = frame_counter
                        
                    except queue.Empty:
                        break
                
                # Collect completed results
                done_futures = [f for f in pending_futures if f.done()]
                for future in done_futures:
                    frame_id = pending_futures.pop(future)
                    try:
                        result = future.result()
                        result_queue.put(result)
                    except Exception as e:
                        print(f"[Processor] Frame {frame_id} failed: {e}")
                
                time.sleep(0.001)  # Small sleep to prevent CPU spinning
                
        except KeyboardInterrupt:
            print("\n[Server] Shutting down...")
        finally:
            stop_event.set()
            print("[Server] Waiting for workers...")
            executor.shutdown(wait=True)
            print("[Server] Stopped")


if __name__ == "__main__":
    # Required for Windows multiprocessing
    mp.set_start_method('spawn', force=True)
    main()
