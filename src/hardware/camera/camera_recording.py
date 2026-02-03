"""
Camera Recording Module
Handles DCIMG recording and infinite capture modes for Hamamatsu cameras.

Features:
- Automatic camera initialization and cooling
- External/software trigger support
- Frame cleanup management
- Experiment metadata tracking
- Graceful shutdown on signals
"""

import os
import sys

# Add camera control path
_camera_control_path = os.path.abspath(os.path.dirname(__file__))
if _camera_control_path not in sys.path:
    sys.path.insert(0, _camera_control_path)

# Add project root for core imports
_project_root = os.path.abspath(os.path.join(_camera_control_path, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import signal
import cv2
import json
from dcamcon import *
from dcimgnp import *
import time
import ctypes
from dcamapi4 import DCAMREC_OPEN, dcamrec_open, dcamrec_close, dcamcap_record, dcamcap_start, dcamcap_stop
from dcamcon_live_capturing import show_framedata
from screeninfo import get_monitors
from datetime import datetime
import threading
import logging
from pathlib import Path

# Import core utilities
try:
    from core import get_config, setup_logging, ExperimentContext
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False

# Threading events for coordination
capture_stop_event = threading.Event()
cleanup_stop_event = threading.Event()

# Reconfigure stdout/stderr for line buffering
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuration
if CORE_AVAILABLE:
    _config = get_config()
    TARGET_TEMPERATURE = _config.get_camera_setting('target_temperature')
    COOLER_CHECK_TIMEOUT = _config.get_camera_setting('cooler_timeout')
    SETTINGS_PATH = _config.get('camera.camera_settings') or _config.get('paths.camera_settings') or "./data/camera/settings"
    FRAME_PATH = _config.get('camera.raw_frames_path') or _config.get('paths.jpg_frames') or "./data/jpg_frames"
    DEBUG_PATH = _config.get_path('debug_path') if hasattr(_config, 'get_path') else "./data/debug"
else:
    TARGET_TEMPERATURE = -20.0
    COOLER_CHECK_TIMEOUT = 300
    SETTINGS_PATH = "./data/camera/settings"
    FRAME_PATH = "./data/jpg_frames"
    DEBUG_PATH = "./data/debug"

# Global signal handling
signaled_sigint = False

# Camera handles for signal handlers
hdcam = None
hdcam_check = False
hrec = None
hrec_check = False

# Global settings cache
Settings = {}

# Logger
logger = logging.getLogger("CameraRecorder")


def stop_recording():
    """Signal the recording to stop."""
    global capture_stop_event, cleanup_stop_event
    if capture_stop_event:
        capture_stop_event.set()
    if cleanup_stop_event:
        cleanup_stop_event.set()
    logger.info("Stop recording signal sent")


def extract_timestamp_from_name(filename):
    """Extract timestamp from frame filename."""
    try:
        # Format: frame99_2025-07-11_14-09-55_564213.jpg
        name = os.path.splitext(filename)[0]
        parts = name.split('_')
        datetime_str = '_'.join(parts[-3:])
        return datetime.strptime(datetime_str, "%Y-%m-%d_%H-%M-%S_%f")
    except Exception:
        return datetime.min


def cleanup_worker(folder, max_frames, stop_event, interval=5):
    """
    Background worker that cleans up old frames.
    
    Args:
        folder: Directory to clean
        max_frames: Maximum number of frames to keep
        stop_event: Threading event to signal stop
        interval: Check interval in seconds
    """
    stop_event.clear()
    
    while not stop_event.is_set():
        try:
            files = [f for f in os.listdir(folder) if f.lower().endswith(".jpg")]
            if len(files) > max_frames:
                files_sorted = sorted(files, key=extract_timestamp_from_name)
                to_delete = files_sorted[:len(files) - max_frames]
                for f in to_delete:
                    try:
                        os.remove(os.path.join(folder, f))
                    except Exception as e:
                        logger.error(f"Error deleting {f}: {e}")
            time.sleep(interval)
        except Exception as e:
            logger.error(f"Cleanup worker error: {e}")
            time.sleep(interval)


def start_cleanup_thread(folder, max_frames, interval=5):
    """Start the cleanup thread."""
    global cleanup_stop_event
    cleanup_stop_event.clear()
    t = threading.Thread(
        target=cleanup_worker, 
        args=(folder, max_frames, cleanup_stop_event, interval), 
        daemon=True
    )
    t.start()
    return t


def frame_to_bytes(frame):
    """Convert frame to JPEG bytes."""
    success, encoded_image = cv2.imencode('.jpg', frame)
    if success:
        return encoded_image.tobytes()
    return None


def save_frame_as_jpg(path, frame_np, counter, exp_id=None):
    """
    Save numpy frame as JPG.
    
    Args:
        path: Directory path
        frame_np: Image data
        counter: Frame counter
        exp_id: Optional experiment ID for metadata
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    file_name = f"frame{counter}_{timestamp}"
    if exp_id:
        file_name += f"_{exp_id}"
    
    Path(path).mkdir(parents=True, exist_ok=True)
    
    full_path = os.path.join(path, file_name + ".jpg")
    cv2.imwrite(full_path, frame_np)
    
    # Save metadata if exp_id provided
    if exp_id:
        meta_path = os.path.join(path, file_name + ".json")
        with open(meta_path, 'w') as f:
            json.dump({
                "timestamp": timestamp,
                "exp_id": exp_id,
                "counter": counter
            }, f)
    
    return full_path


def convert_16bit_to_8bit_dynamic(np_frame_16bit, clip_min=None, clip_max=None):
    """Convert 16-bit frame to 8-bit with optional clipping."""
    frame = np_frame_16bit.astype(np.float32)
    
    if clip_min is not None and clip_max is not None:
        frame = np.clip(frame, clip_min, clip_max)
    else:
        clip_min = frame.min()
        clip_max = frame.max()
    
    if clip_max - clip_min > 0:
        frame = (frame - clip_min) / (clip_max - clip_min) * 255.0
    else:
        frame = np.zeros_like(frame)
    
    return frame.astype(np.uint8)


def extract_frame_as_numpy(frame, bitdepth=16):
    """Convert DCAMBUF_FRAME to NumPy array."""
    if not frame.buf:
        logger.error("frame.buf is NULL!")
        return None
    
    img_size = frame.height * frame.width
    
    if bitdepth == 8:
        buffer_type = ctypes.c_ubyte * img_size
        c_buf = ctypes.cast(frame.buf, ctypes.POINTER(buffer_type)).contents
        np_frame = np.frombuffer(c_buf, dtype=np.uint8)
    elif bitdepth == 16:
        buffer_type = ctypes.c_ushort * img_size
        c_buf = ctypes.cast(frame.buf, ctypes.POINTER(buffer_type)).contents
        np_frame = np.frombuffer(c_buf, dtype=np.uint16)
        np_frame = convert_16bit_to_8bit_dynamic(np_frame)
    else:
        raise ValueError(f"Unsupported bitdepth: {bitdepth}")
    
    np_frame = np_frame.reshape((frame.height, frame.width))
    return np_frame


def setup_cooling(dcamcon):
    """Setup and verify camera cooling."""
    cooler_status = dcamcon.get_propertyvalue(DCAM_IDPROP.SENSORCOOLERSTATUS)
    if cooler_status == DCAMPROP.SENSORCOOLERSTATUS.OFF:
        print("Cooling is OFF. Activating...")
        logger.info("Activating camera cooling")
        if not dcamcon.set_propertyvalue(DCAM_IDPROP.SENSORCOOLER, DCAMPROP.SENSORCOOLER.ON):
            logger.error("Failed to activate cooler")
            return False
    else:
        print("Cooling already active")
    
    start_time = time.time()
    while time.time() - start_time < COOLER_CHECK_TIMEOUT:
        current_temp = dcamcon.get_propertyvalue(DCAM_IDPROP.SENSORTEMPERATURE)
        if current_temp <= TARGET_TEMPERATURE:
            print(f"Target temperature reached: {current_temp:.2f}°C")
            logger.info(f"Target temperature reached: {current_temp:.2f}°C")
            return True
        print(f"Current temperature: {current_temp:.2f}°C...")
        time.sleep(10)
    
    logger.warning("Target temperature not reached within timeout")
    return False


def setup_properties(dcamcon):
    """Configure camera properties."""
    global Settings
    
    # Sensormode
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SENSORMODE, DCAMPROP.SENSORMODE.AREA):
        logger.error("Failed to set sensormode")
        return False
    
    # Readout speed
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.READOUTSPEED, DCAMPROP.READOUTSPEED.FASTEST):
        logger.error("Failed to set readout speed")
        return False
    
    # Pixel type
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.IMAGE_PIXELTYPE, DCAM_PIXELTYPE.MONO16):
        logger.error("Failed to set pixel type")
        return False
    
    # Trigger source
    if Settings.get("trigger_mode") == "extern":
        trigger_source = DCAMPROP.TRIGGERSOURCE.EXTERNAL
    else:
        trigger_source = DCAMPROP.TRIGGERSOURCE.SOFTWARE
    
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERSOURCE, trigger_source):
        logger.error("Failed to set trigger source")
        return False
    
    # Trigger mode
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGER_MODE, DCAMPROP.TRIGGER_MODE.NORMAL):
        logger.error("Failed to set trigger mode")
        return False
    
    # Trigger active
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERACTIVE, DCAMPROP.TRIGGERACTIVE.EDGE):
        logger.error("Failed to set trigger active")
        return False
    
    # Trigger polarity
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERPOLARITY, DCAMPROP.TRIGGERPOLARITY.POSITIVE):
        logger.error("Failed to set trigger polarity")
        return False
    
    # Binning
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.BINNING, 1):
        logger.error("Failed to set binning")
        return False
    
    # Subarray settings
    if CORE_AVAILABLE:
        subarray = _config.get_camera_setting('subarray')
        hsize = subarray.get('hsize', 300)
        hpos = subarray.get('hpos', 1624)
        vsize = subarray.get('vsize', 600)
        vpos = subarray.get('vpos', 1396)
        trigger_delay = _config.get_camera_setting('trigger_delay', 0.033138)
    else:
        hsize, hpos, vsize, vpos = 300, 1624, 600, 1396
        trigger_delay = 0.033138
    
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYMODE, DCAMPROP.MODE.ON):
        logger.error("Failed to set subarray mode")
        return False
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYHSIZE, hsize):
        logger.error("Failed to set subarray hsize")
        return False
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYHPOS, hpos):
        logger.error("Failed to set subarray hpos")
        return False
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYVSIZE, vsize):
        logger.error("Failed to set subarray vsize")
        return False
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYVPOS, vpos):
        logger.error("Failed to set subarray vpos")
        return False
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.EXPOSURETIME, float(Settings.get("exposure", 0.3))):
        logger.error("Failed to set exposure time")
        return False
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERDELAY, trigger_delay):
        logger.error("Failed to set trigger delay")
        return False
    
    logger.info("Camera properties configured successfully")
    return True


def start_dcimg_recording(dcamcon, hdcam_local, output_path, frame_path, num_frames=10, exp_id=None):
    """
    Start DCIMG recording with frame capture.
    
    Args:
        dcamcon: DCAM connection object
        hdcam_local: Camera handle
        output_path: Path for DCIMG file
        frame_path: Path for JPG frames
        num_frames: Maximum frames to record
        exp_id: Optional experiment ID
    """
    global hrec, hrec_check, hdcam, hdcam_check
    
    hdcam = hdcam_local
    hdcam_check = True
    
    print("Initializing DCIMG recording...")
    logger.info(f"Starting recording: {output_path}, frames={num_frames}")
    
    # Get properties
    exposuretime = dcamcon.get_propertyvalue(DCAM_IDPROP.EXPOSURETIME)
    if exposuretime is False:
        return False
    
    triggersource = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERSOURCE)
    trigger_mode = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGER_MODE)
    
    print(f"Trigger source: {triggersource}, mode: {trigger_mode}")
    
    # Allocate buffer
    print("Allocating frame buffer...")
    err = dcambuf_alloc(hdcam, num_frames)
    if err != 1:
        logger.error(f"Buffer allocation failed: {err}")
        return False
    
    # Calculate timeout
    frameinterval = dcamcon.get_propertyvalue(DCAM_IDPROP.INTERNAL_FRAMEINTERVAL, False)
    if frameinterval is not False:
        timeout_millisec = int((exposuretime + frameinterval) * 1000.0) + 500
    else:
        timeout_millisec = int(exposuretime * 1000.0) + 1000
    
    if timeout_millisec < 2:
        timeout_millisec = 2
    
    # Check camera ready
    if not dcamcon.is_capstaus_ready():
        logger.error("Camera not ready")
        return False
    
    # Setup recording
    recopen = DCAMREC_OPEN()
    recopen.setpath(output_path)
    recopen.ext = 'dcimg'
    recopen.maxframepersession = num_frames
    
    err = dcamrec_open(ctypes.byref(recopen))
    if err != 1:
        logger.error(f"Failed to create DCIMG file: {err}")
        return False
    
    hrec = recopen.hrec
    hrec_check = True
    print(f"DCIMG file created: {output_path}.dcimg")
    logger.info(f"DCIMG file created: {output_path}.dcimg")
    
    # Start recording
    err = dcamcap_record(hdcam, hrec)
    if err != 1:
        logger.error(f"Failed to prepare recording: {err}")
        dcamrec_close(hrec)
        return False
    
    if not dcamcap_start(hdcam, -1):
        logger.error("Failed to start capture")
        dcamrec_close(hrec)
        return False
    
    print("Recording started. Waiting for triggers...")
    logger.info("Recording started")
    
    # Trigger handling for software trigger
    firetrigger_cycle = 0
    framecount_till_firetrigger = 0
    if triggersource == DCAMPROP.TRIGGERSOURCE.SOFTWARE:
        if trigger_mode == DCAMPROP.TRIGGER_MODE.START:
            firetrigger_cycle = 0
        elif trigger_mode == DCAMPROP.TRIGGER_MODE.PIV:
            firetrigger_cycle = 2
        else:
            firetrigger_cycle = 1
        dcamcon.firetrigger()
        framecount_till_firetrigger = firetrigger_cycle
    
    global signaled_sigint
    timeout_happened = 0
    frame_counter = 0
    first_success = False
    
    while not signaled_sigint and not capture_stop_event.is_set():
        res = dcamcon.wait_capevent_frameready(timeout_millisec)
        
        if res is not True:
            if res != DCAMERR.TIMEOUT:
                logger.error(f"wait_capevent_frameready failed: {res}")
                break
            
            timeout_happened += 1
            if timeout_happened == 1:
                print('Waiting for frame...', end='')
            elif first_success and timeout_happened > 5:
                print("\nNo triggers detected for 5s. Stopping.")
                break
            else:
                print('.', end='')
            continue
        
        first_success = True
        print(f"\nRecording frame {frame_counter}")
        
        if frame_counter >= num_frames:
            print("Maximum frames reached. Stopping.")
            break
        
        # Lock and copy frame
        frame = DCAMBUF_FRAME()
        frame.size = sizeof(DCAMBUF_FRAME)
        frame.iFrame = -1
        
        err = dcambuf_lockframe(dcamcon.dcam._Dcam__hdcam, frame)
        if err != 1:
            logger.error(f"dcambuf_lockframe failed: {err}")
            continue
        
        err = dcambuf_copyframe(dcamcon.dcam._Dcam__hdcam, frame)
        if err != 1:
            logger.error(f"dcambuf_copyframe failed: {err}")
            continue
        
        # Convert and save
        np_frame = extract_frame_as_numpy(frame)
        if np_frame is not None:
            rotated_image = cv2.rotate(np_frame, cv2.ROTATE_90_CLOCKWISE)
            save_frame_as_jpg(frame_path, rotated_image, frame_counter, exp_id)
        
        # Handle software trigger
        if framecount_till_firetrigger > 0:
            framecount_till_firetrigger -= 1
            if framecount_till_firetrigger == 0:
                dcamcon.firetrigger()
                framecount_till_firetrigger = firetrigger_cycle
        
        timeout_happened = 0
        frame_counter += 1
    
    # Cleanup
    dcamcap_stop(hdcam)
    dcamrec_close(hrec)
    hrec_check = False
    logger.info("Recording completed")
    print("Recording completed.")
    return True


def start_infinite_capture(dcamcon, hdcam_local, frame_path, num_frames=10, exp_id=None):
    """
    Start infinite capture mode (no DCIMG recording).
    
    Args:
        dcamcon: DCAM connection object
        hdcam_local: Camera handle
        frame_path: Path for JPG frames
        num_frames: Maximum frames to keep in buffer
        exp_id: Optional experiment ID
    """
    global hdcam, hdcam_check
    
    hdcam = hdcam_local
    hdcam_check = True
    
    print("Initializing infinite capture...")
    logger.info(f"Starting infinite capture, max_frames={num_frames}")
    
    exposuretime = dcamcon.get_propertyvalue(DCAM_IDPROP.EXPOSURETIME)
    triggersource = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERSOURCE)
    trigger_mode = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGER_MODE)
    
    # Allocate buffer
    err = dcambuf_alloc(hdcam, num_frames)
    if err != 1:
        logger.error(f"Buffer allocation failed: {err}")
        return False
    
    # Calculate timeout
    frameinterval = dcamcon.get_propertyvalue(DCAM_IDPROP.INTERNAL_FRAMEINTERVAL, False)
    if frameinterval is not False:
        timeout_millisec = int((exposuretime + frameinterval) * 1000.0) + 500
    else:
        timeout_millisec = int(exposuretime * 1000.0) + 1000
    
    if timeout_millisec < 2:
        timeout_millisec = 2
    
    # Start capture
    if not dcamcap_start(hdcam, -1):
        logger.error("Failed to start capture")
        return False
    
    print("Capture started. Waiting for triggers...")
    
    # Software trigger handling
    firetrigger_cycle = 0
    framecount_till_firetrigger = 0
    if triggersource == DCAMPROP.TRIGGERSOURCE.SOFTWARE:
        if trigger_mode == DCAMPROP.TRIGGER_MODE.START:
            firetrigger_cycle = 0
        elif trigger_mode == DCAMPROP.TRIGGER_MODE.PIV:
            firetrigger_cycle = 2
        else:
            firetrigger_cycle = 1
        dcamcon.firetrigger()
        framecount_till_firetrigger = firetrigger_cycle
    
    global signaled_sigint
    timeout_happened = 0
    frame_counter = 0
    first_success = False
    
    while not signaled_sigint and not capture_stop_event.is_set():
        res = dcamcon.wait_capevent_frameready(timeout_millisec)
        
        if res is not True:
            if res != DCAMERR.TIMEOUT:
                logger.error(f"wait_capevent_frameready failed: {res}")
                break
            
            timeout_happened += 1
            if timeout_happened == 1:
                print('Waiting for frame...', end='')
            elif first_success and timeout_happened > 5:
                print("\nNo triggers detected. Stopping.")
                break
            else:
                print('.', end='')
            continue
        
        first_success = True
        
        # Cycle frame counter
        if frame_counter >= num_frames:
            frame_counter = 0
        
        # Lock and copy frame
        frame = DCAMBUF_FRAME()
        frame.size = sizeof(DCAMBUF_FRAME)
        frame.iFrame = -1
        
        err = dcambuf_lockframe(dcamcon.dcam._Dcam__hdcam, frame)
        if err != 1:
            continue
        
        err = dcambuf_copyframe(dcamcon.dcam._Dcam__hdcam, frame)
        if err != 1:
            continue
        
        # Convert and save
        np_frame = extract_frame_as_numpy(frame)
        if np_frame is not None:
            rotated_image = cv2.rotate(np_frame, cv2.ROTATE_90_CLOCKWISE)
            save_frame_as_jpg(frame_path, rotated_image, frame_counter, exp_id)
        
        # Handle software trigger
        if framecount_till_firetrigger > 0:
            framecount_till_firetrigger -= 1
            if framecount_till_firetrigger == 0:
                dcamcon.firetrigger()
                framecount_till_firetrigger = firetrigger_cycle
        
        timeout_happened = 0
        frame_counter += 1
    
    # Cleanup
    dcamcap_stop(hdcam)
    logger.info("Infinite capture stopped")
    print("Capture stopped.")
    return True


def sigint_handler(signum, frame):
    """Handle Ctrl+C."""
    global signaled_sigint
    signaled_sigint = True
    capture_stop_event.set()
    print("\nStop signal received")


def sigterm_handler(signum, frame):
    """Handle termination signal."""
    global signaled_sigint, hdcam_check, hrec_check
    print("SIGTERM received. Stopping camera...")
    logger.info("SIGTERM received, shutting down")
    
    capture_stop_event.set()
    
    # Stop capture if active
    if hdcam_check and hdcam:
        try:
            dcamcap_stop(hdcam)
            print("Camera capture stopped")
        except Exception as e:
            logger.error(f"Error stopping capture: {e}")
    
    # Close recording if active
    if hrec_check and hrec:
        try:
            dcamrec_close(hrec)
            print("Recording file closed")
        except Exception as e:
            logger.error(f"Error closing recording: {e}")
    
    signaled_sigint = True


def get_latest_folder(directory):
    """Get most recently created folder in directory."""
    folders = [f for f in os.listdir(directory) 
               if os.path.isdir(os.path.join(directory, f))]
    if not folders:
        return None
    
    full_paths = [(os.path.join(directory, f), 
                   os.path.getctime(os.path.join(directory, f))) for f in folders]
    latest_folder = max(full_paths, key=lambda x: x[1])[0]
    return latest_folder + "/"


def get_latest_file(directory):
    """Get most recently modified file in directory."""
    files = [os.path.join(directory, f) for f in os.listdir(directory) 
             if os.path.isfile(os.path.join(directory, f))]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def read_settings():
    """Read latest camera settings from JSON file."""
    latest_folder = get_latest_folder(SETTINGS_PATH)
    if not latest_folder:
        logger.warning("No settings folder found, using defaults")
        return {
            "max_frames": 100,
            "exposure": 0.3,
            "trigger_mode": "extern"
        }
    
    latest_file = get_latest_file(latest_folder)
    if not latest_file:
        logger.warning("No settings file found, using defaults")
        return {
            "max_frames": 100,
            "exposure": 0.3,
            "trigger_mode": "extern"
        }
    
    try:
        with open(latest_file, 'r') as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error reading settings: {e}")
        return {
            "max_frames": 100,
            "exposure": 0.3,
            "trigger_mode": "extern"
        }


# Register signal handlers
signal.signal(signal.SIGINT, sigint_handler)
signal.signal(signal.SIGTERM, sigterm_handler)


def handle_recording_request(exp_id=None):
    """
    Main recording handler.
    
    Args:
        exp_id: Optional experiment ID for metadata
    """
    global Settings, hdcam_check, hrec_check
    
    ownname = os.path.basename(__file__)
    print(f"Start {ownname}")
    logger.info("Recording request started")
    
    capture_stop_event.clear()
    hdcam_check = False
    hrec_check = False
    
    # Load settings
    Settings = read_settings()
    
    # Initialize DCAM
    if not dcamcon_init():
        logger.error("DCAM initialization failed")
        return
    
    # Open camera
    dcamcon = dcamcon_choose_and_open()
    if dcamcon is None:
        logger.error("Failed to open camera")
        dcamcon_uninit()
        return
    
    try:
        # Setup cooling
        if not setup_cooling(dcamcon):
            logger.error("Cooling setup failed")
            return
        
        # Setup properties
        if not setup_properties(dcamcon):
            logger.error("Property setup failed")
            return
        
        # Setup paths
        today = datetime.now().strftime("%Y-%m-%d")
        right_now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        if CORE_AVAILABLE:
            dcimg_base = _config.get_path('camera_dcimg')
        else:
            dcimg_base = "Y:/Stein/dcimg"
        
        ordner_pfad = f"{dcimg_base}/{today}"
        Path(ordner_pfad).mkdir(parents=True, exist_ok=True)
        
        output_filename = f"{ordner_pfad}/record_{right_now}"
        frame_pfad = f"{FRAME_PATH}/{today}/"
        
        # Get handle
        global hdcam
        hdcam = dcamcon.dcam._Dcam__hdcam
        max_frames = int(Settings.get("max_frames", 100))
        
        # Start recording
        if not start_dcimg_recording(dcamcon, hdcam, output_filename, 
                                      frame_pfad, max_frames, exp_id):
            logger.error("Recording failed")
        else:
            logger.info("Recording completed successfully")
            
    finally:
        dcamcon.close()
        dcamcon_uninit()
        hdcam_check = False
        hrec_check = False
        logger.info("Recording handler finished")
    
    print(f"End {ownname}")


def handle_infinite_capture_request(exp_id=None):
    """
    Infinite capture handler.
    
    Args:
        exp_id: Optional experiment ID for metadata
    """
    global Settings, hdcam_check
    
    ownname = os.path.basename(__file__)
    print(f"Start {ownname}")
    logger.info("Infinite capture request started")
    
    capture_stop_event.clear()
    hdcam_check = False
    
    # Default settings for infinite mode
    Settings = {
        "max_frames": 100,
        "exposure": 0.3,
        "trigger_mode": "software"
    }
    
    max_frames = int(Settings["max_frames"])
    
    if CORE_AVAILABLE:
        ordner_pfad = str(_config.get_path('live_frames'))
    else:
        ordner_pfad = "Y:/Stein/Server/Live_Frames/"
    
    Path(ordner_pfad).mkdir(parents=True, exist_ok=True)
    
    # Start cleanup thread
    t = start_cleanup_thread(ordner_pfad, max_frames, interval=5)
    
    # Initialize DCAM
    if not dcamcon_init():
        logger.error("DCAM initialization failed")
        return
    
    # Open camera
    dcamcon = dcamcon_choose_and_open()
    if dcamcon is None:
        logger.error("Failed to open camera")
        dcamcon_uninit()
        return
    
    try:
        # Setup cooling
        if not setup_cooling(dcamcon):
            logger.error("Cooling setup failed")
            return
        
        # Setup properties
        if not setup_properties(dcamcon):
            logger.error("Property setup failed")
            return
        
        # Get handle
        global hdcam
        hdcam = dcamcon.dcam._Dcam__hdcam
        
        # Start capture
        if not start_infinite_capture(dcamcon, hdcam, ordner_pfad, max_frames, exp_id):
            logger.error("Capture failed")
        else:
            logger.info("Capture completed")
            
    finally:
        dcamcon.close()
        dcamcon_uninit()
        hdcam_check = False
        
        # Stop cleanup thread
        cleanup_stop_event.set()
        t.join(timeout=10)
        logger.info("Infinite capture handler finished")
    
    print(f"End {ownname}")


if __name__ == "__main__":
    # Setup logging if running standalone
    if CORE_AVAILABLE:
        setup_logging(component="camera")
    
    # Default to infinite capture when run directly
    handle_infinite_capture_request()
