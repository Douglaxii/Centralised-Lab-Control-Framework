#!/usr/bin/env python3
"""
ARTIQ & LabVIEW Calibration Test Script

This script provides automated testing and calibration for:
- ARTIQ (via ZMQ Control Manager): DC electrodes, RF, DDS, Cooling parameters
- LabVIEW (via TCP): U_RF, Piezo, Toggles (oven, B-field, UV3, E-gun, etc.)

Features:
- Latency measurement for command round-trips
- Signal sweep tests
- Safety limit verification
- Response plotting and analysis

Usage:
    python calibration_test.py --all
    python calibration_test.py --latency
    python calibration_test.py --sweep
    python calibration_test.py --toggle-test
    python calibration_test.py --limits

Requirements:
    pip install matplotlib numpy pyzmq pyyaml
"""

import sys
import os
import time
import json
import socket
import argparse
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from datetime import datetime

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import numpy as np
    import matplotlib.pyplot as plt
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    print("Warning: matplotlib/numpy not available. Plots will be skipped.")

try:
    import zmq
    HAS_ZMQ = True
except ImportError:
    HAS_ZMQ = False
    print("Warning: pyzmq not available. ARTIQ tests will be skipped.")

import pytest
from core import get_config
from core.enums import u_rf_mv_to_U_RF_V, U_RF_V_to_u_rf_mv


# ==============================================================================
# Data Structures
# ==============================================================================

@dataclass
class LatencyMeasurement:
    """Stores latency measurement data."""
    command_type: str
    timestamp: float
    latency_ms: float
    success: bool
    details: Dict = field(default_factory=dict)


# ==============================================================================
# Connection Classes
# ==============================================================================

class ARTIQConnection:
    """ZMQ connection to Control Manager for ARTIQ commands."""
    
    def __init__(self, host: str = None, port: int = None):
        config = get_config()
        self.host = host or config.master_ip
        self.port = port or config.client_port
        self.ctx = None
        self.socket = None
        self.connected = False
        self.latency_history: List[LatencyMeasurement] = []
        
    def connect(self) -> bool:
        """Connect to Control Manager."""
        if not HAS_ZMQ:
            print("✗ ZMQ not available")
            return False
            
        try:
            self.ctx = zmq.Context()
            self.socket = self.ctx.socket(zmq.REQ)
            self.socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5s timeout
            self.socket.connect(f"tcp://{self.host}:{self.port}")
            self.connected = True
            print(f"✓ Connected to Control Manager at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close connection."""
        if self.socket:
            self.socket.close()
        if self.ctx:
            self.ctx.term()
        self.connected = False
        print("Disconnected from Control Manager")
    
    def send_command(self, action: str, params: Dict = None, 
                     source: str = "CALIBRATION", exp_id: str = None) -> Tuple[Dict, float]:
        """Send command and measure latency."""
        if not self.connected:
            raise RuntimeError("Not connected")
        
        request = {
            "action": action,
            "source": source,
            "params": params or {},
        }
        if exp_id:
            request["exp_id"] = exp_id
        
        start_time = time.time()
        self.socket.send_json(request)
        response = self.socket.recv_json()
        latency_ms = (time.time() - start_time) * 1000
        
        measurement = LatencyMeasurement(
            command_type=action,
            timestamp=start_time,
            latency_ms=latency_ms,
            success=response.get("status") == "success",
            details={"request": request, "response": response}
        )
        self.latency_history.append(measurement)
        
        return response, latency_ms
    
    def set_parameters(self, params: Dict) -> Tuple[Dict, float]:
        """Set ARTIQ parameters."""
        return self.send_command("SET", params)
    
    def get_parameters(self, param_names: List[str] = None) -> Tuple[Dict, float]:
        """Get current parameter values."""
        params = {"params": param_names} if param_names else {}
        return self.send_command("GET", params)
    
    def get_status(self) -> Tuple[Dict, float]:
        """Get system status."""
        return self.send_command("STATUS")


class LabVIEWConnection:
    """TCP connection to LabVIEW SMILE interface."""
    
    def __init__(self, host: str = None, port: int = None):
        config = get_config()
        self.host = host or config.get('labview.host', '127.0.0.1')
        self.port = port or config.get('labview.port', 5559)
        self.timeout = config.get('labview.timeout', 5.0)
        self.socket = None
        self.connected = False
        self.latency_history: List[LatencyMeasurement] = []
        self._lock = threading.Lock()
        self._request_counter = 0
    
    def connect(self) -> bool:
        """Connect to LabVIEW."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            self.connected = True
            print(f"✓ Connected to LabVIEW at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close connection."""
        if self.socket:
            self.socket.close()
        self.connected = False
        print("Disconnected from LabVIEW")
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        with self._lock:
            self._request_counter += 1
            return f"CAL_{self._request_counter:06d}_{int(time.time() * 1000)}"
    
    def send_command(self, command: str, device: str, value: Any) -> Tuple[Dict, float]:
        """Send command to LabVIEW and measure latency."""
        if not self.connected:
            raise RuntimeError("Not connected")
        
        request = {
            "command": command,
            "device": device,
            "value": value,
            "timestamp": time.time(),
            "request_id": self._generate_request_id()
        }
        
        start_time = time.time()
        try:
            message = json.dumps(request) + "\n"
            self.socket.sendall(message.encode('utf-8'))
            response_data = self.socket.recv(4096).decode('utf-8').strip()
            latency_ms = (time.time() - start_time) * 1000
            
            response = json.loads(response_data) if response_data else {"status": "error"}
            success = response.get("status") == "ok"
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            response = {"status": "error", "message": str(e)}
            success = False
            self.connected = False
        
        measurement = LatencyMeasurement(
            command_type=f"{command}:{device}",
            timestamp=start_time,
            latency_ms=latency_ms,
            success=success,
            details={"request": request, "response": response}
        )
        self.latency_history.append(measurement)
        
        return response, latency_ms
    
    def set_rf_voltage(self, voltage: float) -> Tuple[Dict, float]:
        """Set U_RF voltage (0-1000V)."""
        return self.send_command("set_voltage", "U_RF", round(voltage, 3))
    
    def set_piezo_voltage(self, voltage: float) -> Tuple[Dict, float]:
        """Set piezo voltage (0-4V)."""
        return self.send_command("set_voltage", "piezo", round(voltage, 3))
    
    def set_toggle(self, device: str, state: bool) -> Tuple[Dict, float]:
        """Set toggle device."""
        return self.send_command("set_toggle", device, bool(state))
    
    def set_dds_frequency(self, freq_mhz: float) -> Tuple[Dict, float]:
        """Set DDS frequency in MHz."""
        return self.send_command("set_frequency", "dds", round(freq_mhz, 6))
    
    def emergency_stop(self) -> Tuple[Dict, float]:
        """Send emergency stop."""
        return self.send_command("emergency_stop", "all", None)


# ==============================================================================
# Test Functions
# ==============================================================================

def run_latency_test(connection, test_commands: List[Tuple], num_iterations: int = 10) -> Dict:
    """Run latency test for given commands."""
    results = defaultdict(list)
    
    print(f"Running {num_iterations} iterations for {len(test_commands)} commands...")
    
    for i in range(num_iterations):
        for cmd in test_commands:
            cmd_type = cmd[0]
            try:
                if isinstance(connection, ARTIQConnection):
                    if cmd_type == "SET":
                        _, latency = connection.set_parameters(cmd[1])
                    elif cmd_type == "GET":
                        _, latency = connection.get_parameters()
                    elif cmd_type == "STATUS":
                        _, latency = connection.get_status()
                elif isinstance(connection, LabVIEWConnection):
                    if cmd_type == "SET_RF":
                        _, latency = connection.set_rf_voltage(cmd[1])
                    elif cmd_type == "SET_PIEZO":
                        _, latency = connection.set_piezo_voltage(cmd[1])
                    elif cmd_type == "SET_TOGGLE":
                        _, latency = connection.set_toggle(cmd[1], cmd[2])
                    elif cmd_type == "STATUS":
                        _, latency = connection.get_status()
                
                results[cmd_type].append(latency)
                
            except Exception as e:
                print(f"Error in {cmd_type}: {e}")
                results[cmd_type].append(None)
        
        if (i + 1) % 5 == 0:
            print(f"  Completed {i + 1}/{num_iterations} iterations")
    
    # Calculate statistics
    stats = {}
    for cmd_type, latencies in results.items():
        valid_latencies = [l for l in latencies if l is not None]
        if valid_latencies:
            stats[cmd_type] = {
                'mean': np.mean(valid_latencies),
                'std': np.std(valid_latencies),
                'min': np.min(valid_latencies),
                'max': np.max(valid_latencies),
                'median': np.median(valid_latencies),
                'p95': np.percentile(valid_latencies, 95),
                'p99': np.percentile(valid_latencies, 99),
                'samples': len(valid_latencies)
            }
    
    return stats


def print_stats(stats: Dict, name: str):
    """Print latency statistics."""
    print(f"\n=== {name} Latency Statistics ===")
    for cmd, stat in stats.items():
        print(f"\n{cmd}:")
        print(f"  Mean: {stat['mean']:.2f} ms")
        print(f"  Std:  {stat['std']:.2f} ms")
        print(f"  Min:  {stat['min']:.2f} ms")
        print(f"  Max:  {stat['max']:.2f} ms")
        print(f"  P95:  {stat['p95']:.2f} ms")
        print(f"  P99:  {stat['p99']:.2f} ms")


def plot_latency_comparison(artiq_stats: Dict, lv_stats: Dict, artiq, labview, save_path: str = None):
    """Plot latency comparison."""
    if not HAS_PLOTTING:
        print("Plotting not available (matplotlib/numpy missing)")
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Bar chart of mean latencies
    ax1 = axes[0, 0]
    
    artiq_cmds = list(artiq_stats.keys())
    artiq_means = [artiq_stats[k]['mean'] for k in artiq_cmds]
    artiq_stds = [artiq_stats[k]['std'] for k in artiq_cmds]
    
    lv_cmds = list(lv_stats.keys())
    lv_means = [lv_stats[k]['mean'] for k in lv_cmds]
    lv_stds = [lv_stats[k]['std'] for k in lv_cmds]
    
    x = np.arange(max(len(artiq_cmds), len(lv_cmds)))
    width = 0.35
    
    # Only plot if we have data
    if artiq_cmds:
        ax1.bar(x[:len(artiq_cmds)] - width/2, artiq_means, width, yerr=artiq_stds,
                label='ARTIQ', alpha=0.8, capsize=5)
    if lv_cmds:
        ax1.bar(x[:len(lv_cmds)] + width/2, lv_means, width, yerr=lv_stds,
                label='LabVIEW', alpha=0.8, capsize=5, color='orange')
    
    ax1.set_ylabel('Latency (ms)')
    ax1.set_title('Mean Command Latency')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Percentile comparison
    ax2 = axes[0, 1]
    
    percentiles = ['mean', 'p95', 'p99']
    x = np.arange(len(percentiles))
    
    if artiq_stats:
        artiq_avg = [np.mean([artiq_stats[k][p] for k in artiq_stats]) for p in percentiles]
        ax2.bar(x - width/2, artiq_avg, width, label='ARTIQ', alpha=0.8)
    
    if lv_stats:
        lv_avg = [np.mean([lv_stats[k][p] for k in lv_stats]) for p in percentiles]
        ax2.bar(x + width/2, lv_avg, width, label='LabVIEW', alpha=0.8, color='orange')
    
    ax2.set_ylabel('Latency (ms)')
    ax2.set_title('Average Latency Percentiles')
    ax2.set_xticks(x)
    ax2.set_xticklabels(percentiles)
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Summary table as text
    ax3 = axes[1, 0]
    ax3.axis('off')
    
    table_text = "Latency Summary\n" + "="*40 + "\n\n"
    table_text += "ARTIQ Commands:\n"
    for cmd, stat in artiq_stats.items():
        table_text += f"  {cmd:12s}: {stat['mean']:6.1f} ± {stat['std']:5.1f} ms\n"
    
    table_text += "\nLabVIEW Commands:\n"
    for cmd, stat in lv_stats.items():
        table_text += f"  {cmd:12s}: {stat['mean']:6.1f} ± {stat['std']:5.1f} ms\n"
    
    ax3.text(0.1, 0.9, table_text, transform=ax3.transAxes, 
             verticalalignment='top', fontfamily='monospace', fontsize=10)
    
    # Latency over time
    ax4 = axes[1, 1]
    
    if artiq.latency_history:
        artiq_times = [m.timestamp - artiq.latency_history[0].timestamp for m in artiq.latency_history]
        artiq_lats = [m.latency_ms for m in artiq.latency_history]
        ax4.plot(artiq_times, artiq_lats, 'b.', alpha=0.5, label='ARTIQ')
    
    if labview.latency_history:
        lv_times = [m.timestamp - labview.latency_history[0].timestamp for m in labview.latency_history]
        lv_lats = [m.latency_ms for m in labview.latency_history]
        ax4.plot(lv_times, lv_lats, 'orange', marker='.', linestyle='None', alpha=0.5, label='LabVIEW')
    
    ax4.set_xlabel('Time (s)')
    ax4.set_ylabel('Latency (ms)')
    ax4.set_title('Latency Over Time')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\n✓ Plot saved to: {save_path}")
    
    plt.show()


def run_rf_sweep_test(artiq: ARTIQConnection, labview: LabVIEWConnection,
                      start_v: float, stop_v: float, steps: int, dwell_ms: float = 100) -> Dict:
    """Run RF voltage sweep and measure latency at each step."""
    voltages = np.linspace(start_v, stop_v, steps)
    results = {
        'voltages': [],
        'artiq_latencies': [],
        'labview_latencies': [],
        'set_times': []
    }
    
    print(f"Running RF sweep: {start_v}V to {stop_v}V in {steps} steps")
    
    for i, v in enumerate(voltages):
        print(f"  Step {i+1}/{steps}: Setting {v:.1f}V...", end='\r')
        
        if artiq.connected:
            _, artiq_lat = artiq.set_parameters({'u_rf_volts': v})
            results['artiq_latencies'].append(artiq_lat)
        
        if labview.connected:
            _, lv_lat = labview.set_rf_voltage(v)
            results['labview_latencies'].append(lv_lat)
        
        results['voltages'].append(v)
        results['set_times'].append(time.time())
        
        if dwell_ms > 0:
            time.sleep(dwell_ms / 1000.0)
    
    print("\n✓ Sweep complete!")
    return results


def plot_sweep_results(results: Dict, save_path: str = None):
    """Plot sweep results."""
    if not HAS_PLOTTING:
        return
    
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))
    
    # Voltage vs Time
    ax1 = axes[0]
    times = np.array(results['set_times']) - results['set_times'][0]
    ax1.plot(times, results['voltages'], 'b.-', linewidth=2, markersize=8)
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('RF Voltage (V)')
    ax1.set_title('RF Voltage Sweep Profile')
    ax1.grid(True, alpha=0.3)
    
    # Latency vs Voltage
    ax2 = axes[1]
    if results['artiq_latencies']:
        ax2.plot(results['voltages'], results['artiq_latencies'],
                 'b.-', label='ARTIQ', linewidth=2, markersize=8)
    if results['labview_latencies']:
        ax2.plot(results['voltages'], results['labview_latencies'],
                 'orange', marker='.', linestyle='-', label='LabVIEW', linewidth=2, markersize=8)
    ax2.set_xlabel('RF Voltage (V)')
    ax2.set_ylabel('Command Latency (ms)')
    ax2.set_title('Command Latency vs RF Voltage')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"✓ Sweep plot saved to: {save_path}")
    
    plt.show()


def run_toggle_test(labview: LabVIEWConnection, device: str = 'b_field',
                    cycles: int = 10, on_time_ms: float = 100) -> Dict:
    """Test toggle response time."""
    results = {
        'cycle': [],
        'on_latency': [],
        'off_latency': [],
        'total_cycle_time': []
    }
    
    print(f"Testing {device} toggle response ({cycles} cycles)...")
    
    for i in range(cycles):
        cycle_start = time.time()
        
        _, on_lat = labview.set_toggle(device, True)
        time.sleep(on_time_ms / 1000.0)
        _, off_lat = labview.set_toggle(device, False)
        
        cycle_time = (time.time() - cycle_start) * 1000
        
        results['cycle'].append(i + 1)
        results['on_latency'].append(on_lat)
        results['off_latency'].append(off_lat)
        results['total_cycle_time'].append(cycle_time)
        
        print(f"  Cycle {i+1}: ON={on_lat:.1f}ms, OFF={off_lat:.1f}ms, Total={cycle_time:.1f}ms")
    
    print("\n✓ Toggle test complete!")
    return results


def plot_toggle_results(results: Dict, save_path: str = None):
    """Plot toggle results."""
    if not HAS_PLOTTING:
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Latency per cycle
    ax1 = axes[0]
    x = results['cycle']
    ax1.plot(x, results['on_latency'], 'g.-', label='ON latency', linewidth=2, markersize=10)
    ax1.plot(x, results['off_latency'], 'r.-', label='OFF latency', linewidth=2, markersize=10)
    ax1.set_xlabel('Cycle Number')
    ax1.set_ylabel('Latency (ms)')
    ax1.set_title('Toggle Response Latency')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(x)
    
    # Histogram
    ax2 = axes[1]
    ax2.hist(results['on_latency'], bins=10, alpha=0.6, label='ON', color='green')
    ax2.hist(results['off_latency'], bins=10, alpha=0.6, label='OFF', color='red')
    ax2.set_xlabel('Latency (ms)')
    ax2.set_ylabel('Count')
    ax2.set_title('Toggle Latency Distribution')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    mean_on = np.mean(results['on_latency'])
    mean_off = np.mean(results['off_latency'])
    std_on = np.std(results['on_latency'])
    std_off = np.std(results['off_latency'])
    
    stats_text = f"ON:  {mean_on:.1f} ± {std_on:.1f} ms\nOFF: {mean_off:.1f} ± {std_off:.1f} ms"
    ax2.text(0.95, 0.95, stats_text, transform=ax2.transAxes,
             verticalalignment='top', horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"✓ Toggle plot saved to: {save_path}")
    
    plt.show()


@pytest.mark.skip(reason="Requires ARTIQ hardware fixture")
def test_parameter_limits():
    """Test that parameter limits are enforced."""
    
    # This test requires an ARTIQ connection fixture which is not available
    # in the standard test environment. Run manually with hardware connected.
    pass


def _test_parameter_limits_impl(artiq) -> List[Dict]:
    """Actual implementation of parameter limits test."""
    
    test_cases = [
        ('u_rf_volts', 600, 'rejected'),
        ('u_rf_volts', 200, 'success'),
        ('ec1', 150, 'rejected'),
        ('ec1', 50, 'success'),
        ('piezo', 5, 'rejected'),
        ('piezo', 2, 'success'),
        ('freq0', 250, 'rejected'),
        ('freq0', 210, 'success'),
    ]
    
    print("Testing Parameter Safety Limits\n" + "="*50)
    
    results = []
    for param, value, expected in test_cases:
        response, latency = artiq.set_parameters({param: value})
        actual = response.get('status', 'unknown')
        passed = (actual == expected) or (expected == 'rejected' and actual == 'error')
        
        status_symbol = "✓" if passed else "✗"
        print(f"{status_symbol} {param}={value}: {actual} (expected: {expected}, {latency:.1f}ms)")
        
        results.append({
            'param': param,
            'value': value,
            'expected': expected,
            'actual': actual,
            'passed': passed,
            'latency_ms': latency
        })
    
    passed_count = sum(1 for r in results if r['passed'])
    print(f"\n{passed_count}/{len(results)} tests passed")
    
    return results


def generate_test_report(artiq_stats: Dict, lv_stats: Dict, 
                         sweep_results: Dict, toggle_results: Dict,
                         limit_results: List[Dict], artiq, labview) -> Tuple[Dict, str]:
    """Generate and save test report."""
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'artiq_connected': artiq.connected if artiq else False,
        'labview_connected': labview.connected if labview else False,
        'latency_statistics': {
            'artiq': artiq_stats,
            'labview': lv_stats
        },
        'sweep_test': {
            'voltage_range': [min(sweep_results['voltages']), max(sweep_results['voltages'])] if sweep_results else None,
            'steps': len(sweep_results['voltages']) if sweep_results else 0,
            'avg_artiq_latency_ms': np.mean(sweep_results['artiq_latencies']) if sweep_results and sweep_results['artiq_latencies'] else None,
            'avg_labview_latency_ms': np.mean(sweep_results['labview_latencies']) if sweep_results and sweep_results['labview_latencies'] else None,
        } if sweep_results else None,
        'toggle_test': {
            'avg_on_latency_ms': np.mean(toggle_results['on_latency']) if toggle_results else None,
            'avg_off_latency_ms': np.mean(toggle_results['off_latency']) if toggle_results else None,
        } if toggle_results else None,
        'limit_tests': limit_results if limit_results else [],
    }
    
    filename = f"calibration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✓ Test report saved to: {filename}")
    return report, filename


def cleanup(artiq: ARTIQConnection, labview: LabVIEWConnection):
    """Apply safety defaults and disconnect."""
    print("\nApplying safety defaults...")
    
    if artiq and artiq.connected:
        artiq.set_parameters({
            'u_rf_volts': 0,
            'ec1': 0, 'ec2': 0,
            'comp_h': 0, 'comp_v': 0,
            'piezo': 0,
            'be_oven': False,
            'e_gun': False,
            'uv3': False,
        })
        print("✓ ARTIQ parameters reset")
    
    if labview and labview.connected:
        labview.set_rf_voltage(0)
        labview.set_piezo_voltage(0)
        labview.set_toggle('be_oven', False)
        labview.set_toggle('e_gun', False)
        labview.set_toggle('uv3', False)
        print("✓ LabVIEW parameters reset")
    
    print("\nDisconnecting...")
    if artiq:
        artiq.disconnect()
    if labview:
        labview.disconnect()
    
    print("\n✓ Cleanup complete!")


# ==============================================================================
# Main
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='ARTIQ & LabVIEW Calibration Test',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python calibration_test.py --all
  python calibration_test.py --latency --iterations 20
  python calibration_test.py --sweep --start 100 --stop 300 --steps 20
  python calibration_test.py --toggle-test --cycles 5
  python calibration_test.py --limits
        """
    )
    
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--latency', action='store_true', help='Run latency tests')
    parser.add_argument('--sweep', action='store_true', help='Run RF sweep test')
    parser.add_argument('--toggle-test', action='store_true', help='Run toggle response test')
    parser.add_argument('--limits', action='store_true', help='Test parameter limits')
    
    parser.add_argument('--iterations', type=int, default=10, help='Latency test iterations')
    parser.add_argument('--start', type=float, default=100, help='Sweep start voltage')
    parser.add_argument('--stop', type=float, default=300, help='Sweep stop voltage')
    parser.add_argument('--steps', type=int, default=20, help='Sweep steps')
    parser.add_argument('--cycles', type=int, default=10, help='Toggle test cycles')
    parser.add_argument('--no-plots', action='store_true', help='Skip plotting')
    parser.add_argument('--no-cleanup', action='store_true', help='Skip safety cleanup')
    
    args = parser.parse_args()
    
    # If no tests specified, show help
    if not any([args.all, args.latency, args.sweep, args.toggle_test, args.limits]):
        parser.print_help()
        return
    
    # Initialize connections
    artiq = ARTIQConnection()
    labview = LabVIEWConnection()
    
    # Connect
    print("="*60)
    print("ARTIQ & LabVIEW Calibration Test")
    print("="*60 + "\n")
    
    print("Connecting to systems...")
    artiq.connect()
    labview.connect()
    
    if not artiq.connected and not labview.connected:
        print("\n✗ No systems connected! Exiting.")
        return
    
    # Run tests
    artiq_stats = {}
    lv_stats = {}
    sweep_results = None
    toggle_results = None
    limit_results = []
    
    try:
        if args.all or args.latency:
            print("\n" + "="*60)
            print("LATENCY TESTS")
            print("="*60)
            
            if artiq.connected:
                artiq_test_commands = [
                    ("STATUS",),
                    ("GET",),
                    ("SET", {'ec1': 10.0}),
                    ("SET", {'u_rf_volts': 200.0}),
                ]
                artiq_stats = run_latency_test(artiq, artiq_test_commands, args.iterations)
                print_stats(artiq_stats, "ARTIQ")
            
            if labview.connected:
                lv_test_commands = [
                    ("STATUS",),
                    ("SET_RF", 100.0),
                    ("SET_PIEZO", 1.0),
                    ("SET_TOGGLE", "b_field", True),
                ]
                lv_stats = run_latency_test(labview, lv_test_commands, args.iterations)
                print_stats(lv_stats, "LabVIEW")
            
            # Plot comparison
            if HAS_PLOTTING and not args.no_plots and (artiq_stats or lv_stats):
                plot_latency_comparison(artiq_stats, lv_stats, artiq, labview, 
                                        save_path='latency_comparison.png')
        
        if args.all or args.sweep:
            print("\n" + "="*60)
            print("RF SWEEP TEST")
            print("="*60)
            
            sweep_results = run_rf_sweep_test(
                artiq, labview,
                start_v=args.start,
                stop_v=args.stop,
                steps=args.steps,
                dwell_ms=50
            )
            
            if HAS_PLOTTING and not args.no_plots:
                plot_sweep_results(sweep_results, save_path='rf_sweep_test.png')
        
        if args.all or args.toggle_test:
            print("\n" + "="*60)
            print("TOGGLE RESPONSE TEST")
            print("="*60)
            
            if labview.connected:
                toggle_results = run_toggle_test(labview, 'b_field', args.cycles, 200)
                
                if HAS_PLOTTING and not args.no_plots:
                    plot_toggle_results(toggle_results, save_path='toggle_test.png')
            else:
                print("LabVIEW not connected, skipping toggle test")
        
        if args.all or args.limits:
            print("\n" + "="*60)
            print("SAFETY LIMIT TEST")
            print("="*60)
            
            if artiq.connected:
                limit_results = test_parameter_limits(artiq)
            else:
                print("ARTIQ not connected, skipping limit test")
        
        # Generate report
        print("\n" + "="*60)
        print("GENERATING REPORT")
        print("="*60)
        
        report, filename = generate_test_report(
            artiq_stats, lv_stats,
            sweep_results, toggle_results,
            limit_results, artiq, labview
        )
        
        # Print summary
        print("\n=== Test Summary ===")
        print(f"Timestamp: {report['timestamp']}")
        print(f"ARTIQ Connected: {report['artiq_connected']}")
        print(f"LabVIEW Connected: {report['labview_connected']}")
        
        if report['latency_statistics']['artiq']:
            print("\nARTIQ Avg Latency: {:.1f} ms".format(
                np.mean([s['mean'] for s in report['latency_statistics']['artiq'].values()])
            ))
        if report['latency_statistics']['labview']:
            print("LabVIEW Avg Latency: {:.1f} ms".format(
                np.mean([s['mean'] for s in report['latency_statistics']['labview'].values()])
            ))
    
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user!")
    
    finally:
        # Cleanup
        if not args.no_cleanup:
            cleanup(artiq, labview)
        else:
            print("\nSkipping cleanup (--no-cleanup specified)")
            artiq.disconnect()
            labview.disconnect()


if __name__ == "__main__":
    main()
