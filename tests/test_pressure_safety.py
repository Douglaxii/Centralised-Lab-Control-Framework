#!/usr/bin/env python3
"""
Pressure Safety System Test

Tests the pressure monitoring safety system that:
1. Monitors pressure from SMILE/LabVIEW (via Y:/ telemetry files)
2. Triggers immediate kill switch when threshold exceeded
3. Switches off piezo voltage and e-gun immediately
4. Notifies server (Control Manager) of alert

Usage:
    python test_pressure_safety.py
    python test_pressure_safety.py --simulate-pressure
    python test_pressure_safety.py --threshold 1e-8
"""

import sys
import os
import time
import argparse
import json
import tempfile
from pathlib import Path

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from server.communications.labview_interface import (
    LabVIEWInterface, LabVIEWKillSwitch, PressureMonitor
)
from core import get_config


def simulate_pressure_spike(monitor: PressureMonitor, pressure_dir: Path, final_pressure: float):
    """
    Simulate a pressure spike by writing telemetry files.
    
    Args:
        monitor: Pressure monitor instance
        pressure_dir: Directory for pressure files
        final_pressure: Target pressure to simulate (mbar)
    """
    print(f"\n🧪 Simulating pressure spike to {final_pressure:.2e} mbar...")
    
    # Create pressure directory if needed
    pressure_dir.mkdir(parents=True, exist_ok=True)
    
    # Write pressure file
    timestamp = time.time()
    filename = f"pressure_{int(timestamp * 1000)}.dat"
    filepath = pressure_dir / filename
    
    with open(filepath, 'w') as f:
        f.write(f"{timestamp},{final_pressure}\n")
    
    print(f"   Written: {filepath}")
    print(f"   Waiting for monitor to detect...")
    
    # Wait for detection
    time.sleep(0.2)
    
    return filepath


def test_pressure_monitor_standalone(threshold_mbar: float = 5e-9, simulate: bool = False):
    """Test pressure monitor in standalone mode (no LabVIEW connection)."""
    
    print("="*70)
    print("Pressure Monitor Standalone Test")
    print("="*70)
    print(f"Threshold: {threshold_mbar:.2e} mbar")
    print(f"Simulate:  {simulate}")
    print()
    
    # Create temp directory for pressure files
    temp_dir = Path(tempfile.mkdtemp(prefix="pressure_test_"))
    pressure_dir = temp_dir / "telemetry" / "smile" / "pressure"
    pressure_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Temp directory: {temp_dir}")
    
    # Track alerts
    alerts_received = []
    
    def alert_callback(pressure, threshold, timestamp, action):
        alerts_received.append({
            "pressure": pressure,
            "threshold": threshold,
            "timestamp": timestamp,
            "action": action
        })
        print(f"\n🔔 ALERT CALLBACK RECEIVED!")
        print(f"   Pressure:  {pressure:.2e} mbar")
        print(f"   Threshold: {threshold:.2e} mbar")
        print(f"   Action:    {action}")
    
    # Create mock LabVIEW interface (we don't need real connection for this test)
    class MockLabVIEWInterface:
        def __init__(self):
            self.kill_switch = LabVIEWKillSwitch(self)
            
        def set_piezo_voltage(self, voltage, bypass_kill_switch=False):
            print(f"   [Mock] set_piezo_voltage({voltage}V)")
            return True
            
        def set_e_gun(self, state, bypass_kill_switch=False):
            print(f"   [Mock] set_e_gun({state})")
            return True
    
    mock_lv = MockLabVIEWInterface()
    
    # Create and start pressure monitor
    monitor = PressureMonitor(
        labview_interface=mock_lv,
        threshold_mbar=threshold_mbar,
        pressure_file_path=str(pressure_dir),
        alert_callback=alert_callback,
        check_interval=0.05  # 20 Hz for fast testing
    )
    
    print("\n🚀 Starting pressure monitor...")
    monitor.start()
    
    try:
        # Test 1: Normal pressure (safe)
        print("\n--- Test 1: Normal Pressure (Safe) ---")
        safe_pressure = 1e-10  # Good vacuum
        simulate_pressure_spike(monitor, pressure_dir, safe_pressure)
        
        time.sleep(0.3)
        
        status = monitor.get_status()
        print(f"Status: alert_active={status['alert_active']}, last_pressure={status['last_pressure_mbar']}")
        
        assert not status['alert_active'], "Alert should NOT be active for safe pressure"
        assert status['last_pressure_mbar'] == safe_pressure, f"Expected {safe_pressure}, got {status['last_pressure_mbar']}"
        print("✓ Test 1 PASSED: No alert for safe pressure")
        
        # Test 2: High pressure (dangerous)
        print("\n--- Test 2: High Pressure (Dangerous) ---")
        dangerous_pressure = 1e-8  # Above threshold
        simulate_pressure_spike(monitor, pressure_dir, dangerous_pressure)
        
        time.sleep(0.3)
        
        status = monitor.get_status()
        print(f"Status: alert_active={status['alert_active']}, last_pressure={status['last_pressure_mbar']}")
        print(f"Alerts received: {len(alerts_received)}")
        
        assert status['alert_active'], "Alert SHOULD be active for dangerous pressure"
        assert len(alerts_received) > 0, "Alert callback should have been called"
        print("✓ Test 2 PASSED: Alert triggered for dangerous pressure")
        
        # Test 3: Pressure returns to safe
        print("\n--- Test 3: Pressure Returns to Safe ---")
        simulate_pressure_spike(monitor, pressure_dir, 1e-10)
        
        time.sleep(0.5)  # Wait for hysteresis check
        
        status = monitor.get_status()
        print(f"Status: alert_active={status['alert_active']}, last_pressure={status['last_pressure_mbar']}")
        
        # With hysteresis, alert may still be active
        print(f"✓ Test 3: Pressure returned to {status['last_pressure_mbar']:.2e} mbar")
        
        # Test 4: Statistics
        print("\n--- Test 4: Statistics ---")
        print(f"Monitor stats: {json.dumps(status['stats'], indent=2)}")
        assert status['stats']['checks'] >= 3, "Should have multiple checks"
        assert status['stats']['alerts_triggered'] >= 1, "Should have at least 1 alert"
        print("✓ Test 4 PASSED: Statistics tracking working")
        
        print("\n" + "="*70)
        print("ALL TESTS PASSED!")
        print("="*70)
        
    finally:
        print("\n🛑 Stopping monitor...")
        monitor.stop()
        
        # Cleanup temp files
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"Cleaned up: {temp_dir}")


def test_with_real_labview(threshold_mbar: float = 5e-9):
    """Test pressure monitoring with real LabVIEW connection."""
    
    print("="*70)
    print("Pressure Safety Test with Real LabVIEW")
    print("="*70)
    print(f"Threshold: {threshold_mbar:.2e} mbar")
    print()
    
    # Create LabVIEW interface
    lv = LabVIEWInterface()
    
    # Track alerts
    alerts_received = []
    
    def alert_callback(pressure, threshold, timestamp, action):
        alerts_received.append({
            "pressure": pressure,
            "threshold": threshold,
            "timestamp": timestamp,
            "action": action
        })
        print(f"\n🔔 MANAGER ALERT CALLBACK!")
        print(f"   Pressure:  {pressure:.2e} mbar")
        print(f"   Threshold: {threshold:.2e} mbar")
        print(f"   Action:    {action}")
    
    # Register callback
    lv.set_pressure_alert_callback(alert_callback)
    
    # Start interface
    lv.start()
    
    try:
        # Connect to LabVIEW
        if not lv.connect():
            print("❌ Could not connect to LabVIEW. Is it running?")
            return
        
        print("✓ Connected to LabVIEW")
        
        # Get pressure status
        status = lv.get_pressure_status()
        print(f"\nPressure Monitor Status:")
        print(f"  Running:     {status['running']}")
        print(f"  Threshold:   {status['threshold_mbar']:.2e} mbar")
        print(f"  Last Pressure: {status.get('last_pressure_mbar', 'N/A')}")
        print(f"  Check Interval: {status['check_interval_seconds']}s")
        
        # Wait and monitor
        print("\n📊 Monitoring pressure for 10 seconds...")
        print("(Simulate pressure spike in LabVIEW or wait for natural change)")
        
        for i in range(10):
            time.sleep(1)
            status = lv.get_pressure_status()
            pressure = status.get('last_pressure_mbar')
            if pressure:
                print(f"  [{i+1}/10] Pressure: {pressure:.2e} mbar, Alert: {status['alert_active']}")
            else:
                print(f"  [{i+1}/10] No pressure data yet...")
        
        # Final status
        print(f"\nFinal Status:")
        print(f"  Alerts received: {len(alerts_received)}")
        print(f"  Max pressure seen: {status['stats']['max_pressure_seen']:.2e} mbar")
        
        if alerts_received:
            print("\n⚠️  ALERTS WERE TRIGGERED DURING TEST!")
        else:
            print("\n✓ No alerts (pressure remained within safe limits)")
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    finally:
        print("\n🛑 Stopping...")
        lv.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Test Pressure Safety System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run standalone test (no LabVIEW needed)
  python test_pressure_safety.py
  
  # Test with real LabVIEW connection
  python test_pressure_safety.py --real-labview
  
  # Use custom threshold
  python test_pressure_safety.py --threshold 1e-8
        """
    )
    
    parser.add_argument('--real-labview', action='store_true',
                       help='Test with real LabVIEW connection (default: standalone)')
    parser.add_argument('--threshold', type=float, default=5e-9,
                       help='Pressure threshold in mbar (default: 5e-9)')
    
    args = parser.parse_args()
    
    try:
        if args.real_labview:
            test_with_real_labview(args.threshold)
        else:
            test_pressure_monitor_standalone(args.threshold, simulate=True)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
