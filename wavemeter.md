This is a comprehensive manual for collecting frequency data from your HighFinesse/Angstrom WS7 Wavemeter via the LabVIEW TCP broadcast.

It documents the protocol we discovered, the system setup, and provides the final, production-ready software for data logging.

---

# **WS7 Wavemeter Data Collection Manual**

**Version:** 1.0
**Target Device:** HighFinesse/Angstrom WS7 Wavemeter (LabVIEW Server)
**Protocol:** TCP/IP Broadcast

## **1. System Overview**

The wavemeter runs a LabVIEW program that broadcasts measurement data over a local network connection (TCP/IP). The data stream is a hybrid format:

* **Frequency Data:** Sent as **ASCII Text** (e.g., `239.34912...`). The unit is **Terahertz (THz)**.
* **Channel ID:** Sent as **Binary Double Precision** (e.g., `1.0` or `2.0`).
* **Other Data:** The stream also contains Temperature (`27.3 C`) and Pressure (`985 mBar`), which must be filtered out.

This manual provides a Python-based client to connect, filter, visualize, and save this data.

---

## **2. Prerequisites**

### **Hardware**

* **Wavemeter PC:** Must be running the manufacturer's software/LabVIEW server.
* **Client PC:** Any computer (Windows/Mac/Linux) connected to the same network as the Wavemeter PC.

### **Software**

* **Python 3.x:** Installed on the Client PC.
* **Libraries:** The standard library is sufficient for logging. For plotting, `matplotlib` is required.
```bash
pip install matplotlib

```



### **Network Configuration**

1. Find the **IP Address** of the Wavemeter PC (e.g., `134.99.120.141`).
2. Ensure **Port 1790** is open (this is the default broadcast port).

---

## **3. The Data Protocol (Technical Reference)**

*Use this section if you need to rewrite the driver in C++ or MATLAB in the future.*

The data stream is a continuous byte stream without fixed packet lengths.

1. **Text Keys:** The stream contains keys like `ws7.frequency`, `ws7.temperature`, and `ws7.switch.channelId`.
2. **Frequency Values:** Immediately following the `frequency` key, the value appears as a plain text string (e.g., `239.349125`).
3. **Channel IDs:** The Channel ID is **not** text. It is a Big-Endian 64-bit Floating Point number (8 bytes) located approximately 15-25 bytes after the `channelId` text tag.

**Filtering Logic:**
To ensure data integrity, the software must:

1. Scan for text numbers.
2. Reject numbers near `27.0` (Temperature) and `985.0` (Pressure).
3. Accept numbers in the `239.0` (Fundamental) or `957.0` (UV) range.

---

## **4. Production Code**

Save the following code as `wavemeter_logger.py`. This script includes:

* **Hybrid Parsing:** Reads both Text frequency and Binary channel.
* **CSV Logging:** Saves data to a file (`wavemeter_data.csv`).
* **Auto-Conversion:** Converts THz to GHz automatically.

```python
import socket
import struct
import re
import time
import csv
import os

# --- CONFIGURATION ---
HOST = '134.99.120.141'   # Wavemeter IP Address
PORT = 1790               # Wavemeter Port
FILENAME = "wavemeter_data.csv"
DIVIDER = 4.0             # UV (957 THz) -> Fundamental (239 THz). Set to 1.0 if not needed.

def run_logger():
    print(f"--- WAVEMETER DATA COLLECTOR ---")
    print(f"Target IP:   {HOST}:{PORT}")
    print(f"Saving to:   {FILENAME}")
    print(f"Stop:        Press Ctrl+C")
    print("-" * 40)

    # 1. Setup CSV File
    file_exists = os.path.isfile(FILENAME)
    csv_file = open(FILENAME, 'a', newline='')
    writer = csv.writer(csv_file)
    
    if not file_exists:
        writer.writerow(["Timestamp_Epoch", "Rel_Time_s", "Channel", "Frequency_GHz", "Raw_Reading_THz", "Status"])
        csv_file.flush()

    # 2. Setup Network Connection
    freq_pattern = re.compile(r'(\d{3,}\.\d+)') 
    current_channel = 1 
    start_time = time.time()
    last_print = 0

    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0) # 5 second timeout
                s.connect((HOST, PORT))
                print(f"Connected! Logging data...")
                
                buffer = b""
                
                while True:
                    try:
                        chunk = s.recv(4096)
                        if not chunk: break
                        buffer += chunk
                        
                        # --- A. DETECT CHANNEL (Binary Search) ---
                        c_idx = buffer.find(b'channelId')
                        if c_idx != -1 and len(buffer) > c_idx + 30:
                            for offset in range(9, 25):
                                try:
                                    candidate = buffer[c_idx + offset : c_idx + offset + 8]
                                    val = struct.unpack('>d', candidate)[0]
                                    if 1.0 <= val <= 8.0 and val.is_integer():
                                        current_channel = int(val)
                                        break
                                except: pass
                            # Clear buffer up to here to stay fresh
                            buffer = buffer[c_idx + 20:]

                        # --- B. DETECT FREQUENCY (Text Search) ---
                        try:
                            text_view = buffer.decode('utf-8', errors='ignore')
                            matches = freq_pattern.findall(text_view)
                            
                            for m in matches:
                                val_thz = float(m)
                                status = "Unknown"
                                final_freq = 0.0
                                valid_reading = False

                                # Filter: UV Range (~957 THz)
                                if 900 < val_thz < 980:
                                    final_freq = (val_thz * 1000.0) / DIVIDER
                                    status = "LOCKED (UV)"
                                    valid_reading = True
                                    
                                # Filter: Fundamental Range (~239 THz)
                                elif 200 < val_thz < 260:
                                    final_freq = val_thz * 1000.0
                                    status = "LOCKED (Fund)"
                                    valid_reading = True

                                if valid_reading:
                                    t_now = time.time()
                                    t_rel = t_now - start_time
                                    
                                    # Write to CSV
                                    writer.writerow([f"{t_now:.4f}", f"{t_rel:.2f}", current_channel, f"{final_freq:.6f}", f"{val_thz:.6f}", status])
                                    csv_file.flush()
                                    
                                    # Print to Screen (throttled)
                                    if time.time() - last_print > 0.2:
                                        print(f"CH {current_channel} | {t_rel:6.1f}s | {final_freq:.5f} GHz")
                                        last_print = time.time()
                                    
                                    # Clear buffer aggressively to prevent lag
                                    buffer = b"" 
                                    break
                                    
                        except Exception:
                            pass
                        
                        # Prevent memory leaks
                        if len(buffer) > 8192: buffer = buffer[-2048:]
                        
                    except socket.timeout:
                        print("Timeout... waiting for stream.")
                        continue
                        
        except (ConnectionRefusedError, OSError):
            print("Connection lost/refused. Retrying in 3s...")
            time.sleep(3)
        except KeyboardInterrupt:
            print("\nStopped by user.")
            csv_file.close()
            break

if __name__ == "__main__":
    run_logger()

```

---

## **5. Operating Instructions**

### **Start Collection**

1. Open your terminal or Anaconda prompt.
2. Navigate to the folder containing `wavemeter_logger.py`.
3. Run the script:
```bash
python wavemeter_logger.py

```


4. You should see the console output:
```text
CH 1 |    2.5s | 239349.12102 GHz
CH 1 |    2.7s | 239349.12162 GHz

```



### **Data Output**

The script creates a file named **`wavemeter_data.csv`** in the same folder.
You can open this directly in Excel, Origin, or Python/Pandas.

**CSV Format:**
| Timestamp_Epoch | Rel_Time_s | Channel | Frequency_GHz | Raw_Reading_THz | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1709283.123 | 0.52 | 1 | 239349.121 | 239.349 | LOCKED (Fund) |

### **Troubleshooting**

| Symptom | Cause | Solution |
| --- | --- | --- |
| **Connection Refused** | Wavemeter PC is offline or LabVIEW is closed. | Check if the LabVIEW "Server" button is active on the wavemeter PC. |
| **Timeout...** | Firewall blocking Port 1790. | Add an exception for TCP Port 1790 in Windows Firewall on the Wavemeter PC. |
| **Empty Data / No Lock** | Laser is blocked or unlocked. | Check the physical fiber coupling. Ensure the Wavemeter exposure bar is not red (overexposed) or empty. |
| **Wrong Frequency** | Reading UV instead of Fundamental? | Adjust the `DIVIDER` variable in the script (Set to 4.0 for UV->Fund, or 1.0 for Raw). |