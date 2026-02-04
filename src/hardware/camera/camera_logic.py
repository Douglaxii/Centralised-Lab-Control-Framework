from camera_recording import (
    handle_recording_request, stop_recording, handle_infinite_capture_request,
    cleanup_all_inf_folders, cleanup_stop_event
)
import threading
import logging

recording_thread = None
recording_thread_inf = None

def start_camera():
    global recording_thread
    if recording_thread and recording_thread.is_alive():
        logging.info("Kamera läuft bereits.")
        return
    recording_thread = threading.Thread(target=handle_recording_request, daemon=True)
    recording_thread.start()
    
def start_camera_inf():
    """Start camera infinity mode with auto-cleanup."""
    global recording_thread_inf
    if recording_thread_inf and recording_thread_inf.is_alive():
        logging.info("Kamera läuft bereits.")
        return
    
    # Clear any existing stop event
    cleanup_stop_event.clear()
    
    recording_thread_inf = threading.Thread(target=handle_infinite_capture_request, daemon=True)
    recording_thread_inf.start()
    logging.info("Infinity mode started with auto-cleanup (max 100 files per folder)")

def stop_camera(clear_files=False):
    """
    Stop camera and optionally clear all JPG files.
    
    Args:
        clear_files: If True, clear all JPG files from infinity mode folders
    """
    logging.info("Signal zum Stoppen der Kamera wird gesendet...")
    stop_recording()
    
    # Signal cleanup thread to stop
    cleanup_stop_event.set()
    
    if clear_files:
        logging.info("Clearing all JPG files from infinity mode folders...")
        deleted = cleanup_all_inf_folders(max_frames=0)  # 0 = delete all
        logging.info(f"Deleted {deleted} files")

def clear_inf_frames():
    """Clear all JPG frames from infinity mode folders."""
    logging.info("Clearing infinity mode frame folders...")
    deleted = cleanup_all_inf_folders(max_frames=0)
    logging.info(f"Cleared {deleted} files")
    return deleted