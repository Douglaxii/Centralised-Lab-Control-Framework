import socket
import re
import time
import matplotlib.pyplot as plt
from collections import deque

# --- CONFIGURATION ---
HOST = '134.99.120.141'
PORT = 1790
DURATION = 300          # 5 Minutes
EXPECTED_FREQ = 239.3   # The approximate THz value we are looking for
TOLERANCE = 5.0         # +/- 5.0 THz window (Plots anything from 234 to 244)

# --- PLOT SETUP ---
plt.ion()
fig, ax = plt.subplots(figsize=(10, 6))
line, = ax.plot([], [], 'b.-', linewidth=1, label='Laser Frequency')
ax.set_xlabel("Time (seconds)")
ax.set_ylabel("Frequency (GHz)") # We will convert THz to GHz for the plot
ax.set_title(f"Live Laser Monitor (Filter: {EXPECTED_FREQ} +/- {TOLERANCE} THz)")
ax.grid(True, linestyle='--', alpha=0.6)
ax.legend()

status_text = ax.text(0.02, 0.95, "Scanning stream...", transform=ax.transAxes, fontsize=12, color='blue')

# Buffers
x_data = deque(maxlen=200)
y_data = deque(maxlen=200)
start_time = time.time()

def run_regex_monitor():
    print(f"Connecting to {HOST}:{PORT}...")
    print(f"Looking for text numbers around {EXPECTED_FREQ}...")
    
    # Regex pattern: Matches numbers like "239.34912" 
    # Logic: Look for digit(s) + dot + digit(s)
    number_pattern = re.compile(r'(\d+\.\d+)')
    
    stream_buffer = "" # String buffer, not bytes
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            s.settimeout(2.0)
            print("Connected! Graphing...")
            
            while (time.time() - start_time) < DURATION:
                try:
                    # Receive data
                    chunk = s.recv(4096)
                    if not chunk: break
                    
                    # Decode bytes to string (ignore errors to handle binary headers)
                    text_chunk = chunk.decode('utf-8', errors='ignore')
                    stream_buffer += text_chunk
                    
                    # Search for all numbers in the chunk
                    matches = number_pattern.findall(stream_buffer)
                    
                    for m in matches:
                        try:
                            val_thz = float(m)
                            
                            # --- THE FILTER ---
                            # Only accept if it's near our target (239.3)
                            # This rejects Temperature (27.3) and Pressure (985.9) automatically
                            if abs(val_thz - EXPECTED_FREQ) < TOLERANCE:
                                
                                t_now = time.time() - start_time
                                
                                # Convert THz to GHz (x1000)
                                val_ghz = val_thz * 1000.0
                                
                                x_data.append(t_now)
                                y_data.append(val_ghz)
                                
                                status_text.set_text(f"Locked: {val_ghz:.4f} GHz")
                                status_text.set_color("green")
                                print(f"[{t_now:.1f}s] MATCH: {val_ghz:.5f} GHz (Raw: {val_thz})")
                                
                        except ValueError:
                            pass
                    
                    # Keep buffer small (keep last 50 chars for split numbers)
                    if len(stream_buffer) > 1000:
                        stream_buffer = stream_buffer[-50:]
                        
                    # Update Plot
                    if len(x_data) > 0:
                        line.set_data(x_data, y_data)
                        ax.set_xlim(max(0, x_data[-1]-60), x_data[-1]+5)
                        
                        valid_y = list(y_data)
                        if valid_y:
                            avg = sum(valid_y) / len(valid_y)
                            # Zoom range: +/- 2 GHz
                            ax.set_ylim(avg - 2.0, avg + 2.0) 
                            
                        plt.pause(0.01)

                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    break

    except Exception as e:
        print(f"Error: {e}")

    plt.ioff()
    plt.show()

if __name__ == "__main__":
    run_regex_monitor()
