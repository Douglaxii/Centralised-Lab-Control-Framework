# camera_server.py
import os
import sys

# Pfad zu `Camera_Control` hinzufügen
camera_control_path = os.path.abspath(os.path.dirname(__file__))
if camera_control_path not in sys.path:
    sys.path.insert(0, camera_control_path)
import socket
import threading
from camera_logic import start_camera, start_camera_inf, stop_camera  # Dummy für jetzt
import logging
from logging.handlers import RotatingFileHandler
import cv2

HOST = '127.0.0.1'  # Nur lokal
PORT = 5555

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# Logging-Datei einrichten
log_handler = RotatingFileHandler("camera.log", maxBytes=1000000, backupCount=1)
log_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
log_handler.setLevel(logging.INFO)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

current_frame = None
capture_active = False

def handle_client(conn, addr):
    logging.info(f"Verbindung von {addr}")
    with conn:
        while True:
            data = conn.recv(1024).decode().strip()
            if not data:
                break

            logging.info(f"Befehl empfangen: {data}")
            if data == "START":
                start_camera()
                conn.sendall(b"OK: Aufnahme gestartet\n")
            elif data == "START_INF":
                start_camera_inf()
                conn.sendall(b"OK:Inf Aufnahme gestartet\n")
            elif data == "STOP":
                stop_camera()
                conn.sendall(b"OK: Aufnahme gestoppt\n")
            elif data == "STATUS":
                conn.sendall(b"Kamera bereit\n")
            else:
                conn.sendall(b"FEHLER: Unbekannter Befehl\n")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        logging.info(f"TCP Kamera-Server läuft auf {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
