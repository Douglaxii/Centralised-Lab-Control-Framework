"""
Script for capturing DCIMG images with an external trigger.
Requires Hamamatsu Python API for DCAM and DCIMG.
"""

import os
import sys

# Pfad zu `Camera_Control` hinzufügen
camera_control_path = os.path.abspath(os.path.dirname(__file__))
if camera_control_path not in sys.path:
    sys.path.insert(0, camera_control_path)

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
from threading import Thread
# from queue import Queue
# from multiprocessing import Manager
from multiprocessing.managers import BaseManager

# Mit dem existierenden Manager verbinden
class QueueManager(BaseManager): pass



sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


# Globale Konfiguration
TARGET_TEMPERATURE = -20.0  # Zieltemperatur in Celsius
COOLER_CHECK_TIMEOUT = 300  # Zeitlimit in Sekunden für das Erreichen der Zieltemperatur
#EXTERNAL_TRIGGER_MODE = DCAMPROP.TRIGGERACTIVE.EXTERNAL

# Settings path
SETTINGS_PATH = "Y:/Stein/Server/Camera_Settings"

# Global variable for handling Ctrl+C signal
signaled_sigint = False

# Queue zur Weitergabe von Frames an Flask
# frame_queue = Queue(maxsize=10)

# Wandelt das Frame in ein picklbares bytes-Format um
def frame_to_bytes(frame):
    success, encoded_image = cv2.imencode('.jpg', frame)
    if success:
        return encoded_image.tobytes()
    return None

def extract_frame_as_numpy(frame):
    """Konvertiert ein DCAMBUF_FRAME in ein NumPy-Array für OpenCV."""
    if not frame.buf:
        print("Fehler: frame.buf ist NULL!")
        return None

    # Bestimme die Anzahl der Bytes im Bild
    img_size = frame.height * frame.width  # rowbytes enthält die Breite in Bytes -> chat gpt Fehler, Antelle rowbytes: width
    buffer_type = ctypes.c_ubyte * img_size  # Erstellt einen ctypes-Array-Typ

    # Konvertiere den Pointer in ein NumPy-Array
    c_buf = ctypes.cast(frame.buf, ctypes.POINTER(buffer_type)).contents
    np_frame = np.frombuffer(c_buf, dtype=np.uint8)

    # Reshape entsprechend der Bildgröße (Mono-Format: 1 Kanal)
    np_frame = np_frame.reshape((frame.height, frame.width))

    return np_frame


def setup_cooling(dcamcon):
    """Prüft und aktiviert die Sensorkühlung, falls nötig."""
    cooler_status = dcamcon.get_propertyvalue(DCAM_IDPROP.SENSORCOOLERSTATUS)
    if cooler_status == DCAMPROP.SENSORCOOLERSTATUS.OFF:
        print("Kühlung ist ausgeschaltet. Aktiviere sie jetzt...")
        if not dcamcon.set_propertyvalue(DCAM_IDPROP.SENSORCOOLER, DCAMPROP.SENSORCOOLER.ON):
            print("Fehler: Kühler konnte nicht aktiviert werden.")
            return False
    else:
        print("Kühlung ist bereits aktiviert.")

    # current_target_temp = dcamcon.get_propertyvalue(DCAM_IDPROP.SENSORTEMPERATURETARGET)
    # if current_target_temp != TARGET_TEMPERATURE:
    #     print(f"Setze Zieltemperatur auf {TARGET_TEMPERATURE} °C.")
    #     if not dcamcon.set_propertyvalue(DCAM_IDPROP.SENSORTEMPERATURETARGET, TARGET_TEMPERATURE):
    #         print("Fehler: Zieltemperatur konnte nicht gesetzt werden.")
    #         return False

    start_time = time.time()
    while time.time() - start_time < COOLER_CHECK_TIMEOUT:
        current_temp = dcamcon.get_propertyvalue(DCAM_IDPROP.SENSORTEMPERATURE)
        if current_temp <= TARGET_TEMPERATURE:
            print(f"Zieltemperatur erreicht: {current_temp:.2f} °C.")
            return True
        print(f"Aktuelle Temperatur: {current_temp:.2f} °C. Warte...")
        time.sleep(10)

    print("Warnung: Zieltemperatur wurde nicht innerhalb des Zeitlimits erreicht.")
    return False

def setup_properties(dcamcon):
    """
    Setup basic properties for capturing with external trigger.
    
    Documentation for all property values can be found in the DCAM-API Property Reference
    """

    # Sensormode
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SENSORMODE, DCAMPROP.SENSORMODE.AREA):
        print("Fehler: Sensormode konnte nicht gesetzt werden.")
        return False
    
    # Readoutspeed
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.READOUTSPEED, DCAMPROP.READOUTSPEED.FASTEST):
        print("Fehler: Readoutspeed konnte nicht gesetzt werden.")
        return False
    
    # Image Pixeltype
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.IMAGE_PIXELTYPE, DCAM_PIXELTYPE.MONO16):
        print("Fehler: Image-pixeltype konnte nicht gesetzt werden.")
        return False
    
    # Trigger Source -> externes Signal
    if Settings["trigger_mode"] == "extern":
        triggersource = DCAMPROP.TRIGGERSOURCE.EXTERNAL
    else:
        triggersource = DCAMPROP.TRIGGERSOURCE.SOFTWARE
    
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERSOURCE, triggersource):
        print("Fehler: Trigger-Quelle konnte nicht gesetzt werden.")
        return False
    
    # Triggermodus einstellen
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGER_MODE, DCAMPROP.TRIGGER_MODE.NORMAL):
        print("Fehler: Trigger-Modus konnte nicht gesetzt werden.")
        return False
    
    # Triggeraktivität auf EDGE setzen
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERACTIVE, DCAMPROP.TRIGGERACTIVE.EDGE):
        print("Fehler: Trigger-Aktivität konnte nicht gesetzt werden.")
        return False

    # Trigger-Polarität auf POSITIVE setzen
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERPOLARITY, DCAMPROP.TRIGGERPOLARITY.POSITIVE):
        print("Fehler: Trigger-Polarität konnte nicht gesetzt werden.")
        return False

    # Binning
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.BINNING, 1):
        print("Fehler: Binning konnte nicht gesetzt werden.")
        return False
    
    # Subarray Einstellungen, Werte entnommen aus Hokawo -> Multi Camera Plug in - Control -> Image Format
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYMODE, DCAMPROP.MODE.ON):
        print("Fehler: SUbarray-Modus konnte nicht gesetzt werden.")
        return False

    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYHSIZE, 300):
        print("Fehler: Subarray-Horizontale-Ausdehnung konnte nicht gesetzt werden.")
        return False
    
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYHPOS, 1624):
        #1624
        print("Fehler: Subarray-Horizontale-Position konnte nicht gesetzt werden.")
        return False
    
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYVSIZE, 600):
        print("Fehler: Subarray-Vertikale-Ausdehnung konnte nicht gesetzt werden.")
        return False
    
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.SUBARRAYVPOS, 1396):
        print("Fehler: Subarray-Vertikale-Position konnte nicht gesetzt werden.")
        return False
    
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.EXPOSURETIME, float(Settings["exposure"])):
        print("Fehler: Exposuretime konnte nicht gesetzt werden.")
        return False
 
    # Trigger-Delay einstellen
    if not dcamcon.set_propertyvalue(DCAM_IDPROP.TRIGGERDELAY, 0.033138):  # In Sekunden
        print("Fehler: Trigger-Delay konnte nicht gesetzt werden.")
        return False
    
    # # Contrasgain (irrelevant)
    # if not dcamcon.set_propertyvalue(DCAM_IDPROP.CONTRASTGAIN, 1):
    #     print("Fehler: Contrastgain konnte nicht gesetzt werden.")
    #     return False

    # Debugging: Auslesen der gesetzten Eigenschaften
    # trigger_source = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERSOURCE)
    # trigger_mode = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGER_MODE)
    # trigger_polarity = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERPOLARITY)
    # trigger_delay = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERDELAY)
    # trigger_active = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERACTIVE)
    # trigger_connector = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGER_CONNECTOR)
    # triggerenable_active = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERENABLE_ACTIVE)
    # trigger_firstexposure = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGER_FIRSTEXPOSURE)
    # global_exposure = dcamcon.get_propertyvalue(DCAM_IDPROP.GLOBALEXPOSURE)

    # print(f"Triggerquelle: {trigger_source}")
    # print(f"Triggermodus: {trigger_mode}")
    # print(f"Triggerpolarität: {trigger_polarity}")
    # print(f"Trigger-Delay: {trigger_delay}")
    # print(f"Trigger-active: {trigger_active}")
    # print(f"Trigger-connector: {trigger_connector}")
    # print(f"Triggerenable-active: {triggerenable_active}")
    # print(f"Trigger-firstexposure: {trigger_firstexposure}")
    # print(f"Global Exposure: {global_exposure}")
    print("Properties set.")
    return True

def start_dcimg_recording(dcamcon, hdcam, output_path, num_frames=10):
    # hdcam
    """Startet die Aufnahme und speichert die Frames in einer DCIMG-Datei."""
    print("Initialisiere DCIMG-Aufnahme...")
    
    # get property value used
    exposuretime = dcamcon.get_propertyvalue(DCAM_IDPROP.EXPOSURETIME)
    if exposuretime is False:
        # should be able to get the value
        return
    
    triggersource = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGERSOURCE)
    if triggersource is False:
        # should be able to get the value
        return
    
    trigger_mode = dcamcon.get_propertyvalue(DCAM_IDPROP.TRIGGER_MODE)
    if trigger_mode is False:
        # should be able to get the value
        return


    # Puffer initialisieren (Buffer-Allocation für num_frames)
    print("Allocieren von Speicherplatz für Frames...")
    err = dcambuf_alloc(hdcam, num_frames)
    if err != 1:  # SUCCESS = 1
        print(f"Fehler beim Allocieren des Puffers: {err}")
        return False

    print("Speicherplatz erfolgreich allokiert.")

    # calculate timeout time
    timeout_millisec = 2
    
    frameinterval = dcamcon.get_propertyvalue(DCAM_IDPROP.INTERNAL_FRAMEINTERVAL, False)
    if frameinterval is not False:
        # set timeout waiting for a frame to arrive to exposure time + internal frame interval + 500 ms
        timeout_millisec = int((exposuretime + frameinterval) * 1000.0) + 500
    else:
        # set timeout waiting for a frame to arrive to exposure time + 1 second
        timeout_millisec = int(exposuretime * 1000.0) + 1000
    
    # let's use 2ms minimum timeout
    if timeout_millisec < 2:
        timeout_millisec = 2

    # Überprüfen, ob die Kamera bereit ist
    cap_status = dcamcon.is_capstaus_ready()
    if not cap_status:
        print("Die Kamera ist nicht im Ready-Zustand.")
        return False
    print("Die Kamera ist bereit für die Aufnahme.")

    # DCAMREC_OPEN-Struktur erstellen und initialisieren
    recopen = DCAMREC_OPEN() # Klasse aus dcamapi4.py
    recopen.setpath(output_path)  # Pfad der DCIMG-Datei
    recopen.ext = 'dcimg' # Dateiendung
    recopen.maxframepersession = num_frames

    # Debugging info
    # print(f"DCAMREC_OPEN:")
    # print(f"    path: {recopen.path}")
    # print(f"    ext: {recopen.ext}")
    # print(f"    maxframepersession: {recopen.maxframepersession}")

    # DCIMG-Datei erstellen
    err = dcamrec_open(ctypes.byref(recopen))
    print(f"    Handle: {recopen.hrec}")
    if err != 1:  # Prüfen, ob ein Fehler zurückgegeben wurde. code 1 für success?
        print(f"Fehler beim Erstellen der DCIMG-Datei: {err}")
        return False

    global hrec
    hrec = recopen.hrec  # Aufnahme-Handle
    global hrec_check
    print(f"DCIMG-Datei erstellt: {output_path}.dcimg")

    # Aufnahme vorbereiten
    err = dcamcap_record(hdcam, hrec)
    if err != 1:
        print(f"Fehler beim Vorbereiten der Aufnahme: {err}")
        dcamrec_close(hrec)
        return False

    # Aufnahme starten
    print("Starte Aufnahme...")
    if not dcamcap_start(hdcam, -1): # -1 für sequentielles Aufnehmen von Bildern. Die Kamera wartet auf ein internes oder externes Triggersignal
        print("Fehler beim Start der Aufnahme")
        dcamrec_close(hrec)
        return False
    
    print("Aufnahme gestartet. Warte auf Trigger...")
    
    # Triggerzyklus aus "dcamcon_live_capturing.py". Nur relevant für Softwaretrigger. Kann später noch relevant werden
    firetrigger_cycle = 0
    framecount_till_firetrigger = 0
    if triggersource == DCAMPROP.TRIGGERSOURCE.SOFTWARE:
        if trigger_mode == DCAMPROP.TRIGGER_MODE.START:
            # Software Start requires only one firetrigger at beginning
            firetrigger_cycle = 0
        elif trigger_mode == DCAMPROP.TRIGGER_MODE.PIV:
            # PIV require firetrigger for 2 frames
            firetrigger_cycle = 2
        else:
            # standard software trigger requires one firetrigger for one frame
            firetrigger_cycle = 1
        
        # we'll fire a trigger to initiate capturing for this sample
        dcamcon.firetrigger()
        framecount_till_firetrigger = firetrigger_cycle
    
    global cv_window_status
    global signaled_sigint
    timeout_happened = 0
    frame_counter = 0
    while signaled_sigint == False:
        res = dcamcon.wait_capevent_frameready(timeout_millisec)
        if res is not True:
            # frame does not come
            if res != DCAMERR.TIMEOUT:
                print('-NG: Dcam.wait_event() failed with error {}'.format(res))
                break

            # TIMEOUT error happens
            timeout_happened += 1
            if timeout_happened == 1:
                print('Waiting for a frame to arrive.', end='')
                if triggersource == DCAMPROP.TRIGGERSOURCE.EXTERNAL:
                    print(' Check your trigger source.', end ='')
                else:
                    print(' Check your <timeout_millisec> calculation in the code.', end='')
                print(' Press Ctrl+C to abort.')
            elif first_success == True:
                print(".")
                if timeout_happened > 5:
                    print("No more trigger signals detected after 5s. Recording has been stopped.")
                    timeout_happened = 0
                    break            
            else:
                print('.')
                if timeout_happened > 5:
                    timeout_happened = 0
            
            continue

        # wait_capevent_frameready() succeeded
        first_success = True # Wird True sobald erstes Frame erfolgreich getriggered wurde
        frame_counter +=1
        print(f"Recording frame number {frame_counter}")
        if frame_counter == num_frames:
            frame_counter = 0
            print("Maximum number of frames has been reached. Recording has been stopped.")
            break
        

        frame = DCAMBUF_FRAME()
        frame.size = sizeof(DCAMBUF_FRAME)
        err = dcambuf_lockframe(dcamcon.dcam._Dcam__hdcam, frame)
        if err != 1:
            print(f"Fehler: dcambuf_lockframe() fehlgeschlagen mit Error-Code {err}")
            continue  # Überspringe diesen Durchlauf

        err = dcambuf_copyframe(dcamcon.dcam._Dcam__hdcam, frame)
        if err != 1:
            print(f"Fehler: dcambuf_copyframe() fehlgeschlagen mit Error-Code {err}")
            continue  # Überspringe diesen Durchlauf 

        # Konvertiere das Frame in ein NumPy-Array
        np_frame = extract_frame_as_numpy(frame)

        if np_frame is not None:
            #print(f"succesfully copied frame, size: {frame.size}")
            # lastdata = dcamcon.get_lastframedata() # error: INVALIDPARAM -> Schleife bricht hier ab
            #if lastdata is not False:

            

            # print("Hello there!")
            # Live bild zum Server einrichten
            # Frame in die Queue einfügen
            if frame_queue.full():
                frame_queue.get()  # Älteste Frames entfernen
            frame_queue.put(np_frame)
            print(f"frame added to queue. size: {np_frame.shape}")
            # print(frame_queue.get())

            # frame_bytes = frame_to_bytes(frame)  # In bytes konvertieren
            # if frame_bytes is not None:
            #     frame_queue.put(frame_bytes)
            #     print("Frame in Queue gespeichert.")
            # show_framedata(dcamcon.device_title, lastdata)
            # print("displayed frame.")
            
        
        if framecount_till_firetrigger > 0:
            framecount_till_firetrigger -= 1
            if framecount_till_firetrigger == 0:
                dcamcon.firetrigger()
                framecount_till_firetrigger = firetrigger_cycle
        
        timeout_happened = 0


    # Aufnahme beenden
    # End live
    cv2.destroyAllWindows()
    
    dcamcap_stop(hdcam)
    dcamrec_close(hrec)
    print("Aufnahme abgeschlossen und Datei gespeichert.")
    return True

def sigint_handler(signum, frame):
    """Handle Ctrl+C signal."""
    global signaled_sigint
    signaled_sigint = True

def sigterm_handler(signum, frame):
    print("SIGTERM empfangen. Kameraaufzeichnung wird beendet.")
    # Aufräumarbeiten hier durchführen (z. B. dcamrec_close())
    cv2.destroyAllWindows()
    
    if hdcam_check:
        dcamcap_stop(hdcam)

    if hrec_check:  # Sicherstellen, dass HDCAMREC vorhanden ist
        dcamrec_close(hrec)
    exit(0)

def get_latest_folder(directory):
    """Gibt den vollständigen Pfad des zuletzt hinzugefügten Ordners im angegebenen Verzeichnis zurück."""
    # Alle Einträge im Verzeichnis auflisten und filtern, sodass nur Ordner übrig bleiben
    folders = [f for f in os.listdir(directory) if os.path.isdir(os.path.join(directory, f))]

    if not folders:
        return None  # Kein Ordner gefunden

    # Vollständige Pfade mit Erstellungszeit abrufen
    full_paths = [(os.path.join(directory, f), os.path.getctime(os.path.join(directory, f))) for f in folders]

    # Den Ordner mit dem neuesten Erstellungszeitstempel finden
    latest_folder = max(full_paths, key=lambda x: x[1])[0]

    return latest_folder + "/"

# Find name of the latest added file to a directory
def get_latest_file(directory):
    files = [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    if not files:
        return None  # Falls keine Dateien vorhanden sind
    return max(files, key=os.path.getmtime) # mtime -> file timestamp

def read_settings():
    latest_folder = get_latest_folder(SETTINGS_PATH)
    latest_file = get_latest_file(latest_folder)

    # Open and read the JSON file
    with open(latest_file, 'r') as file:
        data = json.load(file)
        
    return data
    
def main():
    """Hauptfunktion für die kombinierte Kühlung und Aufnahme."""
    ownname = os.path.basename(__file__)
    print(f"Start {ownname}")
    
    # output_path = "C:/Users/Hamamatsu/Developer/recording"
    
    signal.signal(signal.SIGINT, sigint_handler)
    signal.signal(signal.SIGTERM, sigterm_handler)
    print("Starting DCIMG capture script.")
    
    # Load newest settings from jason file
    global Settings
    Settings = read_settings()

    # Initialize DCAM API
    if not dcamcon_init():
        print("Failed to initialize DCAM API.")
        return

    # Choose and open camera
    dcamcon = dcamcon_choose_and_open()
    if dcamcon is None:
        print("No camera selected or failed to open.")
        dcamcon_uninit()
        return
    
    


    try:    
        # Sensorkühlung sicherstellen
        if not setup_cooling(dcamcon):
            print("Abbruch: Kühlung konnte nicht eingerichtet werden.")
            return

        # Configure properties
        if not setup_properties(dcamcon):
            print("Failed to configure camera properties.")
            dcamcon.close()
            dcamcon_uninit()
            return
        
        # Aufnahme starten
        today = datetime.now().strftime("%Y-%m-%d")
        right_now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        ordner_pfad = f"Y:/Stein/dcimg/{today}"
        # Überprüfen, ob der Ordner existiert, und wenn nicht, erstelle ihn
        if not os.path.exists(ordner_pfad):
            os.makedirs(ordner_pfad)

        output_filename = f"{ordner_pfad}/record_{right_now}"
        print(f"output filename: {output_filename}")

        # print(dir(dcamcon))
        # print(f"dcam: {dcamcon.dcam}")
        # print(f"dcam type: {type(dcamcon.dcam)}")
        global hdcam
        hdcam = dcamcon.dcam._Dcam__hdcam
        global hdcam_check
        max_frames = int(Settings["max_frames"]) # all other user settings are handled inside the setup properties function
        # print(hdcam)
        if not start_dcimg_recording(dcamcon, hdcam, output_filename, max_frames):
            print("Fehler: Aufnahme konnte nicht abgeschlossen werden.")
        
        print("Aufnahme erfolgreich abgeschlossen.")

    finally:
        # Clean up
        dcamcon.close()
        dcamcon_uninit()
    
    print(f"End {ownname}")

if __name__ == "__main__":
    # manager = Manager()
    # frame_queue = manager.Queue(maxsize=10)
    QueueManager.register('get_frame_queue')

    print("Verbindung zu Manager auf 127.0.0.1:5001 herstellen...")
    manager = QueueManager(address=('127.0.0.1', 5002), authkey=b'secret')
    manager.connect()

    # Die bestehende Queue abrufen
    frame_queue = manager.get_frame_queue()
    print("Erfolgreich mit frame_queue verbunden.")

    # run main program
    main()