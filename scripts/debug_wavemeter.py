"""
Debug script to test wavemeter TCP connection and data format.
Run this to diagnose wavemeter connectivity issues.
"""

import socket
import struct
import re
import time
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import get_config

def test_wavemeter_connection(host: str = None, port: int = None, duration: int = 10):
    """
    Test wavemeter TCP connection and display raw data.
    
    Args:
        host: Wavemeter PC IP (default from config)
        port: Wavemeter port (default from config)
        duration: How long to listen for data (seconds)
    """
    # Get config
    config = get_config()
    host = host or config.get('wavemeter.host', '134.99.120.141')
    port = port or config.get('wavemeter.port', 1790)
    
    print(f"\n{'='*70}")
    print(f"Wavemeter Connection Test")
    print(f"{'='*70}")
    print(f"Target: {host}:{port}")
    print(f"Duration: {duration} seconds")
    print(f"{'='*70}\n")
    
    # Try to connect
    print(f"[1] Connecting to {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        print(f"    ✓ Connected successfully!\n")
    except socket.error as e:
        print(f"    ✗ Connection failed: {e}")
        print(f"\nTROUBLESHOOTING:")
        print(f"  - Check if wavemeter PC ({host}) is reachable: ping {host}")
        print(f"  - Check if wavemeter software is running and broadcasting")
        print(f"  - Check firewall settings on wavemeter PC")
        print(f"  - Verify the port number ({port}) is correct")
        return
    
    # Read data
    print(f"[2] Reading data for {duration} seconds...")
    print(f"    (Press Ctrl+C to stop early)\n")
    
    buffer = b""
    freq_pattern = re.compile(r'(\d{3,}\.\d+)')
    start_time = time.time()
    bytes_received = 0
    messages_found = 0
    
    try:
        while time.time() - start_time < duration:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    print(f"    ! Connection closed by server")
                    break
                
                bytes_received += len(chunk)
                buffer += chunk
                
                # Try to decode and show some data
                try:
                    text = chunk.decode('utf-8', errors='ignore')
                    # Look for frequency patterns
                    matches = freq_pattern.findall(text)
                    if matches:
                        messages_found += 1
                        for m in matches[:3]:  # Show first 3 matches
                            val = float(m)
                            print(f"    Raw value: {val:.3f}", end="")
                            # Classify the value
                            if 900 < val < 980:
                                print(f" -> UV frequency: {val/4:.3f} THz fundamental")
                            elif 200 < val < 260:
                                print(f" -> Fundamental: {val:.3f} THz")
                            elif 20 < val < 35:
                                print(f" -> Temperature: {val:.1f} °C")
                            elif 900 < val < 1100:
                                print(f" -> Pressure: {val:.1f} mbar")
                            else:
                                print(f" -> Unknown")
                except:
                    pass
                
                # Check for channel ID
                c_idx = buffer.find(b'channelId')
                if c_idx != -1 and len(buffer) > c_idx + 30:
                    print(f"    Found 'channelId' at offset {c_idx}")
                    # Try to extract channel number
                    for offset in range(9, 25):
                        try:
                            candidate = buffer[c_idx + offset:c_idx + offset + 8]
                            if len(candidate) < 8:
                                break
                            val = struct.unpack('>d', candidate)[0]
                            if 1.0 <= val <= 8.0 and val.is_integer():
                                print(f"    → Channel detected: {int(val)}")
                                break
                        except:
                            pass
                    buffer = buffer[c_idx + 20:]
                
                # Keep buffer manageable
                if len(buffer) > 8192:
                    buffer = buffer[-2048:]
                    
            except socket.timeout:
                continue
                
    except KeyboardInterrupt:
        print(f"\n    Stopped by user")
    finally:
        sock.close()
    
    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"Summary:")
    print(f"  Duration: {elapsed:.1f} seconds")
    print(f"  Bytes received: {bytes_received}")
    print(f"  Frequency readings found: {messages_found}")
    print(f"  Rate: {bytes_received/elapsed:.1f} bytes/sec")
    
    if bytes_received == 0:
        print(f"\n  ✗ NO DATA RECEIVED!")
        print(f"    The connection succeeded but no data was sent.")
        print(f"    Check if the wavemeter software is broadcasting data.")
    elif messages_found == 0:
        print(f"\n  ! Data received but no frequency readings parsed")
        print(f"    The data format might be different than expected.")
        print(f"    Check the raw data format from the wavemeter.")
    else:
        print(f"\n  ✓ Wavemeter is working correctly!")
    
    print(f"{'='*70}\n")

def test_raw_capture(host: str = None, port: int = None, duration: int = 5):
    """
    Capture and display raw bytes from wavemeter for debugging.
    """
    config = get_config()
    host = host or config.get('wavemeter.host', '134.99.120.141')
    port = port or config.get('wavemeter.port', 1790)
    
    print(f"\n{'='*70}")
    print(f"Raw Data Capture (for debugging)")
    print(f"{'='*70}")
    print(f"Capturing raw bytes from {host}:{port} for {duration} seconds...\n")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
    except socket.error as e:
        print(f"Connection failed: {e}")
        return
    
    all_data = b""
    start_time = time.time()
    
    try:
        while time.time() - start_time < duration:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                all_data += chunk
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    
    # Display raw data
    print(f"Total bytes captured: {len(all_data)}\n")
    
    if len(all_data) > 0:
        print("First 500 bytes (hex):")
        print(all_data[:500].hex())
        print("\nFirst 500 bytes (text, ignore errors):")
        print(all_data[:500].decode('utf-8', errors='ignore'))
        
        # Look for patterns
        if b'channelId' in all_data:
            print("\n✓ Found 'channelId' pattern in data")
        else:
            print("\n! Did not find 'channelId' pattern - data format may differ")
    else:
        print("No data captured!")
    
    print(f"{'='*70}\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Wavemeter Connection Debugger")
    parser.add_argument("--host", help="Wavemeter PC IP address")
    parser.add_argument("--port", type=int, help="Wavemeter port")
    parser.add_argument("--duration", type=int, default=10, help="Test duration in seconds")
    parser.add_argument("--raw", action="store_true", help="Capture raw bytes only")
    args = parser.parse_args()
    
    if args.raw:
        test_raw_capture(args.host, args.port, args.duration)
    else:
        test_wavemeter_connection(args.host, args.port, args.duration)
