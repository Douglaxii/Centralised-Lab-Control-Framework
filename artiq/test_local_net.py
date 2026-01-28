import socket
import sys

#Server PC's IP address
SERVER_IP = "192.168.1.50" 
PORT = 5555

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5) # 5 second timeout
    print(f"Attempting to connect to {SERVER_IP}:{PORT}...")
    
    # Check if we can reach the port
    result = s.connect_ex((SERVER_IP, PORT))
    
    if result == 0:
        print("SUCCESS! Connection Established.")
        print("ZeroMQ will work on this system.")
    else:
        print(f"FAILED. Error code: {result}")
        print("Check Windows Firewall on Server PC.")
        
    s.close()
except Exception as e:
    print(f"Connection Failed: {e}")