from camera_recording import handle_recording_request, stop_recording, handle_infinite_capture_request
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
    global recording_thread_inf
    if recording_thread_inf and recording_thread_inf.is_alive():
        logging.info("Kamera läuft bereits.")
        return
    recording_thread_inf = threading.Thread(target=handle_infinite_capture_request, daemon=True)
    recording_thread_inf.start()

def stop_camera():
    logging.info("Signal zum Stoppen der Kamera wird gesendet...")
    stop_recording()