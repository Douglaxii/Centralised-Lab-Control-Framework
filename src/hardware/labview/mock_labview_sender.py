"""
Mock LabVIEW Data Sender - Simulates Wavemeter.vi and SMILE.vi

This script simulates the two LabVIEW programs sending data to the
Python Data Ingestion Server. Use this to test the Flask dashboard
without needing actual LabVIEW running.

Usage:
    python mock_labview_sender.py --wavemeter --smile
    python mock_labview_sender.py --wavemeter-only
    python mock_labview_sender.py --smile-only
    python mock_labview_sender.py --server 192.168.1.100 --port 5560
"""

import socket
import json
import time
import argparse
import threading
import numpy as np
from datetime import datetime


class MockLabVIEWSender:
    """Base class for mock LabVIEW data senders."""
    
    def __init__(self, server_host: str, server_port: int, source_name: str):
        self.server_host = server_host
        self.server_port = server_port
        self.source_name = source_name
        self.socket = None
        self.connected = False
        self.running = False
        self.samples_sent = 0
        
    def connect(self):
        """Connect to Python data server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.connected = True
            print(f"✓ {self.source_name} connected to {self.server_host}:{self.server_port}")
            return True
        except Exception as e:
            print(f"✗ {self.source_name} connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from server."""
        if self.socket:
            self.socket.close()
        self.connected = False
        print(f"{self.source_name} disconnected")
    
    def send_data(self, channel: str, value: float):
        """Send a single data point."""
        if not self.connected:
            return False
        
        try:
            data = {
                "source": self.source_name,
                "channel": channel,
                "value": float(value),
                "timestamp": time.time()
            }
            
            message = json.dumps(data) + "\n"
            self.socket.sendall(message.encode('utf-8'))
            self.samples_sent += 1
            return True
            
        except Exception as e:
            print(f"{self.source_name} send error: {e}")
            self.connected = False
            return False
    
    def run(self):
        """Main loop - override in subclass."""
        raise NotImplementedError


class MockWavemeter(MockLabVIEWSender):
    """Simulates Wavemeter.vi sending laser frequency data."""
    
    def __init__(self, server_host: str, server_port: int, 
                 base_freq: float = 212.5, noise: float = 0.01, rate: float = 2.0):
        super().__init__(server_host, server_port, "wavemeter")
        self.base_freq = base_freq  # MHz
        self.noise = noise          # MHz RMS
        self.rate = rate            # Hz
        self.drift = 0.0
        
    def run(self):
        """Generate and send frequency data with realistic noise and drift."""
        self.running = True
        
        while self.running:
            if not self.connected:
                if not self.connect():
                    time.sleep(5)
                    continue
            
            try:
                # Simulate frequency with drift and noise
                self.drift += np.random.randn() * 0.001  # Random walk drift
                self.drift *= 0.99  # Slow decay back to center
                
                freq = self.base_freq + self.drift + np.random.randn() * self.noise
                
                # Add occasional mode hops
                if np.random.random() < 0.001:
                    freq += np.random.choice([-0.1, 0.1])
                    print(f"[{self.source_name}] Mode hop detected!")
                
                success = self.send_data("laser_freq", freq)
                
                if success:
                    if self.samples_sent % int(self.rate * 10) == 0:  # Log every 10s
                        print(f"[{self.source_name}] Sent: {freq:.6f} MHz (total: {self.samples_sent})")
                else:
                    time.sleep(1)  # Wait before retry
                    continue
                
                time.sleep(1.0 / self.rate)
                
            except Exception as e:
                print(f"[{self.source_name}] Error: {e}")
                self.connected = False
                time.sleep(1)


class MockSMILE(MockLabVIEWSender):
    """Simulates SMILE.vi sending PMT and pressure data."""
    
    def __init__(self, server_host: str, server_port: int,
                 pmt_rate: float = 5.0, pressure_rate: float = 0.5):
        super().__init__(server_host, server_port, "smile")
        self.pmt_rate = pmt_rate           # Hz
        self.pressure_rate = pressure_rate # Hz
        self.pmt_samples = 0
        self.pressure_samples = 0
        
        # PMT state
        self.pmt_baseline = 100
        self.pmt_signal = 0
        
        # Pressure state
        self.pressure = 1.2e-10
        
    def generate_pmt(self) -> float:
        """Generate realistic PMT counts."""
        # Simulate signal turning on/off
        if np.random.random() < 0.01:
            self.pmt_signal = 1000 if self.pmt_signal < 100 else 0
        
        # Base + signal + shot noise
        counts = self.pmt_baseline + self.pmt_signal
        counts = np.random.poisson(counts)
        
        # Add occasional spikes
        if np.random.random() < 0.001:
            counts += int(np.random.exponential(5000))
            
        return float(counts)
    
    def generate_pressure(self) -> float:
        """Generate realistic pressure readings."""
        # Slow drift
        self.pressure *= (1 + np.random.randn() * 0.01)
        self.pressure = np.clip(self.pressure, 5e-11, 1e-9)
        
        # Occasional pressure bursts
        if np.random.random() < 0.0001:
            self.pressure *= 10
            print(f"[{self.source_name}] Pressure burst detected!")
            
        return self.pressure
    
    def run(self):
        """Generate and send PMT and pressure data."""
        self.running = True
        last_pressure = 0
        
        while self.running:
            if not self.connected:
                if not self.connect():
                    time.sleep(5)
                    continue
            
            try:
                loop_start = time.time()
                
                # Always send PMT at pmt_rate
                pmt = self.generate_pmt()
                if self.send_data("pmt", pmt):
                    self.pmt_samples += 1
                
                # Send pressure at pressure_rate (slower)
                if time.time() - last_pressure >= 1.0 / self.pressure_rate:
                    pressure = self.generate_pressure()
                    if self.send_data("pressure", pressure):
                        self.pressure_samples += 1
                    last_pressure = time.time()
                    
                    # Log status
                    total = self.pmt_samples + self.pressure_samples
                    if total % 20 == 0:
                        print(f"[{self.source_name}] PMT: {pmt:.0f}, Pressure: {pressure:.2e} mbar "
                              f"(sent: {total})")
                
                # Maintain rate
                elapsed = time.time() - loop_start
                sleep_time = max(0, 1.0 / self.pmt_rate - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"[{self.source_name}] Error: {e}")
                self.connected = False
                time.sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description="Mock LabVIEW Data Sender",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run both wavemeter and SMILE
  python mock_labview_sender.py --wavemeter --smile
  
  # Wavemeter only
  python mock_labview_sender.py --wavemeter-only
  
  # SMILE only
  python mock_labview_sender.py --smile-only
  
  # Connect to different server
  python mock_labview_sender.py --server 192.168.1.50 --port 5560 --wavemeter --smile
  
  # Adjust data rates
  python mock_labview_sender.py --wavemeter --freq-rate 5.0 --pmt-rate 10.0
        """
    )
    
    parser.add_argument("--server", default="127.0.0.1",
                       help="Python data server IP (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5560,
                       help="Python data server port (default: 5560)")
    parser.add_argument("--wavemeter", action="store_true",
                       help="Run wavemeter simulation")
    parser.add_argument("--smile", action="store_true",
                       help="Run SMILE simulation")
    parser.add_argument("--wavemeter-only", action="store_true",
                       help="Run only wavemeter")
    parser.add_argument("--smile-only", action="store_true",
                       help="Run only SMILE")
    parser.add_argument("--freq-rate", type=float, default=2.0,
                       help="Wavemeter update rate in Hz (default: 2)")
    parser.add_argument("--pmt-rate", type=float, default=5.0,
                       help="SMILE PMT update rate in Hz (default: 5)")
    parser.add_argument("--pressure-rate", type=float, default=0.5,
                       help="SMILE pressure update rate in Hz (default: 0.5)")
    
    args = parser.parse_args()
    
    # Determine what to run
    run_wavemeter = args.wavemeter or args.wavemeter_only
    run_smile = args.smile or args.smile_only
    
    if args.wavemeter_only:
        run_smile = False
    if args.smile_only:
        run_wavemeter = False
    
    if not (run_wavemeter or run_smile):
        print("Error: Must specify at least one sender (--wavemeter, --smile, --wavemeter-only, --smile-only)")
        parser.print_help()
        return
    
    print("=" * 60)
    print("Mock LabVIEW Data Sender")
    print("=" * 60)
    print(f"Server: {args.server}:{args.port}")
    print(f"Wavemeter: {'YES' if run_wavemeter else 'NO'}")
    print(f"SMILE: {'YES' if run_smile else 'NO'}")
    print("=" * 60)
    print()
    
    threads = []
    
    # Start wavemeter
    if run_wavemeter:
        wavemeter = MockWavemeter(args.server, args.port, rate=args.freq_rate)
        t = threading.Thread(target=wavemeter.run, daemon=True, name="Wavemeter")
        t.start()
        threads.append((t, wavemeter))
    
    # Start SMILE
    if run_smile:
        smile = MockSMILE(args.server, args.port, 
                         pmt_rate=args.pmt_rate, 
                         pressure_rate=args.pressure_rate)
        t = threading.Thread(target=smile.run, daemon=True, name="SMILE")
        t.start()
        threads.append((t, smile))
    
    # Wait for interrupt
    try:
        while True:
            time.sleep(1)
            # Print status every 10 seconds
            if int(time.time()) % 10 == 0:
                status = []
                for _, sender in threads:
                    if hasattr(sender, 'samples_sent'):
                        status.append(f"{sender.source_name}: {sender.samples_sent}")
                if status:
                    print(f"[Status] {', '.join(status)}")
                    
    except KeyboardInterrupt:
        print("\n\nStopping...")
        for _, sender in threads:
            sender.running = False
            sender.disconnect()
        print("Done!")


if __name__ == "__main__":
    main()
