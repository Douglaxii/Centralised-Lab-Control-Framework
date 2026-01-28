import os
import time
import json
import threading
import queue
import cv2
import numpy as np
from datetime import datetime
import shutil
from image_handler import Image_Handler


# New unified camera paths (matches camera_server.py)
# For folder-watching mode (alternative to TCP mode)
WATCH_DIR = "Y:/Xi/Data/jpg_frames"   # Monitor raw frames directory
BASE_SERVER_PATH = "Y:/Xi/Data"

POLL_INTERVAL = 0.2 # Check for new files every 20ms

# Thread-safe Queue
job_queue = queue.Queue()
stop_event = threading.Event()

def watcher_thread():
    """
    PRODUCER: Monitors the WATCH_DIR for new image files.
    """
    print(f"[Watcher] Started monitoring: {WATCH_DIR}")
    
    # Initialize with current files so we only process *new* ones
    known_files = set(os.listdir(WATCH_DIR))
    
    while not stop_event.is_set():
        try:
            current_files = set(os.listdir(WATCH_DIR))
            new_files = current_files - known_files
            
            for filename in new_files:
                # Add extensions relevant to your camera
                if filename.lower().endswith(('.tif', '.png', '.jpg', '.bmp')):
                    full_path = os.path.join(WATCH_DIR, filename)
                    
                    # Small wait to ensure file write is complete by camera
                    time.sleep(0.02)
                    
                    job_queue.put(full_path)
                    
            known_files = current_files
            time.sleep(POLL_INTERVAL)
            
        except Exception as e:
            print(f"[Watcher] Error: {e}")
            time.sleep(1)

def processor_thread():
    """
    CONSUMER: Takes files from queue, runs analysis, saves output.
    
    New structure:
    - Raw frames: Y:/Xi/Data/jpg_frames/YYMMDD/
    - Annotated frames: Y:/Xi/Data/jpg_frames_labelled/YYMMDD/
    - JSON data: Y:/Xi/Data/YYMMDD/cam_json/
    """
    print("[Processor] Ready to analyze.")
    print(f"[Processor] Watch dir: {WATCH_DIR}")
    print(f"[Processor] Output base: {BASE_SERVER_PATH}")
    
    while not stop_event.is_set():
        try:
            # Get file from queue (blocks for 1 sec then loops to check stop_event)
            file_path = job_queue.get(timeout=1)
        except queue.Empty:
            continue
            
        filename = os.path.basename(file_path)
        
        # --- DYNAMIC PATH GENERATION ---
        current_date_str = datetime.now().strftime("%y%m%d")
        timestamp = datetime.now().strftime("%H-%M-%S_%f")[:-3]  # milliseconds
        
        # Output directories
        labelled_folder = os.path.join(BASE_SERVER_PATH, "jpg_frames_labelled", current_date_str)
        json_folder = os.path.join(BASE_SERVER_PATH, current_date_str, "cam_json")
        
        # Create directories
        for folder in [labelled_folder, json_folder]:
            if not os.path.exists(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                except OSError as e:
                    print(f"[Processor] Error creating folder {folder}: {e}")
                    job_queue.task_done()
                    continue
        
        try:
            # --- 1. RUN ANALYSIS ---
            handler = Image_Handler(file_path, 
                                  xstart=0, xfinish=300, 
                                  ystart=0, yfinish=300, 
                                  analysis=2,
                                  radius=20)
            
            # --- 2. SAVE ANNOTATED JPG ---
            jpg_name = f"{timestamp}_labelled.jpg"
            jpg_path = os.path.join(labelled_folder, jpg_name)
            
            if handler.operation_array is not None and handler.operation_array.size > 0:
                if handler.annotated_frame is not None:
                    # Save annotated frame with circles and fit parameters
                    cv2.imwrite(jpg_path, cv2.cvtColor(handler.annotated_frame, cv2.COLOR_RGB2BGR))
                else:
                    # No ions detected - save normalized raw image
                    img_norm = cv2.normalize(handler.operation_array, None, 0, 255, cv2.NORM_MINMAX).astype('uint8')
                    cv2.imwrite(jpg_path, img_norm)

            # --- 3. SAVE JSON (Only if ions are detected) ---
            if handler.atom_count > 0:
                result_data = {
                    "timestamp": timestamp,
                    "date": current_date_str,
                    "original_filename": filename,
                    "atom_count": handler.atom_count,
                    "atoms": []
                }
                
                for i in range(len(handler.Popt)):
                    popt = handler.Popt[i]
                    perr = handler.Perr[i]
                    
                    if np.all(popt == 0):
                        continue
                    
                    # New fit parameters structure:
                    # [x0, y0, sigma_x, R_y, A_x, A_y, offset_x, offset_y]
                    atom_data = {
                        "id": i + 1,
                        "x0": float(popt[0]),           # x position in original image
                        "y0": float(popt[1]),           # y position in original image
                        "sigma_x": float(popt[2]),      # Gaussian width (horizontal)
                        "R_y": float(popt[3]),          # SHM turning point (vertical)
                        "A_x": float(popt[4]),          # Amplitude from horizontal fit
                        "A_y": float(popt[5]),          # Amplitude from vertical fit
                        "offset_x": float(popt[6]),     # Offset from horizontal fit
                        "offset_y": float(popt[7]),     # Offset from vertical fit
                        "fit_error": [float(e) for e in perr]
                    }
                    result_data["atoms"].append(atom_data)

                # Save the JSON file
                json_name = f"{timestamp}_data.json"
                json_path = os.path.join(json_folder, json_name)
                
                with open(json_path, 'w') as f:
                    json.dump(result_data, f, indent=4)
                    
                print(f"[Processor] Saved {filename} -> {handler.atom_count} atoms, "
                      f"labelled: {jpg_path}")
            
            else:
                # Logic for 0 atoms
                print(f"[Processor] {filename}: No ions detected. Saved: {jpg_path}")

        except Exception as e:
            print(f"[Processor] Error processing {filename}: {e}")
        
        finally:
            job_queue.task_done()
            
            
            

# --- MAIN EXECUTION BLOCK ---
if __name__ == "__main__":
    # Ensure Base Path exists
    if not os.path.exists(BASE_SERVER_PATH):
        print(f"WARNING: Base path {BASE_SERVER_PATH} not found. Attempting to create...")
        try:
            os.makedirs(BASE_SERVER_PATH, exist_ok=True)
        except:
            print("CRITICAL ERROR: Cannot access network drive Y:/")

    # Start Threads
    t_watcher = threading.Thread(target=watcher_thread, daemon=True)
    t_processor = threading.Thread(target=processor_thread, daemon=True)
    
    t_watcher.start()
    t_processor.start()
    
    print("=" * 60)
    print("Image Handler Server (Folder Watcher Mode)")
    print("=" * 60)
    print(f"Watching: {WATCH_DIR}")
    print(f"Annotated frames: {BASE_SERVER_PATH}/jpg_frames_labelled/[YYMMDD]/")
    print(f"JSON data: {BASE_SERVER_PATH}/[YYMMDD]/cam_json/")
    print("=" * 60)
    print("Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping threads...")
        stop_event.set()
        t_watcher.join()
        t_processor.join()
        print("System Halted.")
