#!/usr/bin/env python3
"""
Manager PC Connection Test Suite

Tests connectivity between:
- Camera (Flask HTTP + ZMQ)
- ARTIQ Master/Worker (ZMQ)
- LabVIEW (ZMQ)
- Manager Server (ZMQ)

Usage:
    python test_connections.py              # Run all tests
    python test_connections.py --camera     # Test camera only
    python test_connections.py --artiq      # Test ARTIQ only
    python test_connections.py --labview    # Test LabVIEW only
    python test_connections.py --manager    # Test manager only
    python test_connections.py --verbose    # Detailed output
"""

import sys
import time
import socket
import argparse
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from enum import Enum

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Optional imports - tests will be skipped if not available
try:
    import zmq
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    WARN = "WARN"


@dataclass
class TestResult:
    name: str
    status: TestStatus
    message: str
    details: Optional[Dict] = None
    duration_ms: float = 0.0


class ConnectionTester:
    """Comprehensive connection tester for Manager PC."""
    
    # Default configuration matching MLS config
    DEFAULT_CONFIG = {
        # Camera Flask HTTP Server
        "camera_flask_host": "127.0.0.1",
        "camera_flask_port": 5000,
        
        # Camera ZMQ Server
        "camera_zmq_host": "127.0.0.1",
        "camera_zmq_port": 5558,
        
        # Camera Command Listener
        "camera_cmd_host": "127.0.0.1",
        "camera_cmd_port": 5001,
        
        # Manager ZMQ Server
        "manager_host": "127.0.0.1",
        "manager_cmd_port": 5557,    # Client commands
        
        # ARTIQ Master
        "artiq_master_host": "127.0.0.1",
        "artiq_master_cmd_port": 5555,   # PUB socket
        "artiq_master_data_port": 5556,  # PULL socket
        
        # LabVIEW
        "labview_host": "172.17.1.217",  # SMILE PC
        "labview_port": 5559,
        
        # Timeouts
        "timeout": 5.0,
    }
    
    def __init__(self, config: Optional[Dict] = None, verbose: bool = False):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.verbose = verbose
        self.results: List[TestResult] = []
        self._zmq_context: Optional[zmq.Context] = None
        
    @property
    def zmq_context(self) -> zmq.Context:
        """Lazy initialization of ZMQ context."""
        if self._zmq_context is None:
            if not ZMQ_AVAILABLE:
                raise RuntimeError("ZMQ not available. Install with: pip install pyzmq")
            self._zmq_context = zmq.Context()
        return self._zmq_context
    
    def _log(self, message: str, level: str = "INFO"):
        """Print log message if verbose."""
        if self.verbose:
            print(f"  [{level}] {message}")
    
    def _test_tcp_port(self, host: str, port: int, name: str) -> TestResult:
        """Test if a TCP port is open."""
        start = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.config["timeout"])
            result = sock.connect_ex((host, port))
            sock.close()
            duration = (time.time() - start) * 1000
            
            if result == 0:
                return TestResult(
                    name=name,
                    status=TestStatus.PASS,
                    message=f"Port {port} on {host} is open",
                    duration_ms=duration
                )
            else:
                return TestResult(
                    name=name,
                    status=TestStatus.FAIL,
                    message=f"Port {port} on {host} is closed (error {result})",
                    duration_ms=duration
                )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TestResult(
                name=name,
                status=TestStatus.FAIL,
                message=f"Failed to connect to {host}:{port} - {e}",
                duration_ms=duration
            )
    
    def _test_zmq_req(self, host: str, port: int, name: str, 
                      message: Optional[Dict] = None) -> TestResult:
        """Test ZMQ REQ socket connection."""
        if not ZMQ_AVAILABLE:
            return TestResult(
                name=name,
                status=TestStatus.SKIP,
                message="ZMQ not installed (pip install pyzmq)"
            )
        
        start = time.time()
        socket = None
        try:
            socket = self.zmq_context.socket(zmq.REQ)
            socket.setsockopt(zmq.RCVTIMEO, int(self.config["timeout"] * 1000))
            socket.connect(f"tcp://{host}:{port}")
            
            # Send test message
            test_msg = message or {"command": "ping", "timestamp": time.time()}
            socket.send_json(test_msg)
            
            # Try to receive response
            try:
                response = socket.recv_json()
                duration = (time.time() - start) * 1000
                return TestResult(
                    name=name,
                    status=TestStatus.PASS,
                    message=f"ZMQ REQ/REP on {host}:{port} working",
                    details={"response": response},
                    duration_ms=duration
                )
            except zmq.Again:
                duration = (time.time() - start) * 1000
                return TestResult(
                    name=name,
                    status=TestStatus.WARN,
                    message=f"Connected to {host}:{port} but no response (may be normal)",
                    duration_ms=duration
                )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TestResult(
                name=name,
                status=TestStatus.FAIL,
                message=f"ZMQ connection to {host}:{port} failed - {e}",
                duration_ms=duration
            )
        finally:
            if socket:
                socket.close()
    
    def _test_zmq_pub_sub(self, host: str, port: int, name: str) -> TestResult:
        """Test ZMQ PUB socket (can connect, but no guarantee of data)."""
        if not ZMQ_AVAILABLE:
            return TestResult(
                name=name,
                status=TestStatus.SKIP,
                message="ZMQ not installed (pip install pyzmq)"
            )
        
        start = time.time()
        socket = None
        try:
            socket = self.zmq_context.socket(zmq.SUB)
            socket.setsockopt(zmq.RCVTIMEO, int(self.config["timeout"] * 1000))
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            socket.connect(f"tcp://{host}:{port}")
            
            # Try to receive (may timeout, which is ok for PUB)
            try:
                data = socket.recv_json()
                duration = (time.time() - start) * 1000
                return TestResult(
                    name=name,
                    status=TestStatus.PASS,
                    message=f"ZMQ PUB/SUB on {host}:{port} receiving data",
                    details={"sample": str(data)[:100]},
                    duration_ms=duration
                )
            except zmq.Again:
                duration = (time.time() - start) * 1000
                return TestResult(
                    name=name,
                    status=TestStatus.PASS,
                    message=f"ZMQ PUB/SUB on {host}:{port} connected (no data yet)",
                    duration_ms=duration
                )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TestResult(
                name=name,
                status=TestStatus.FAIL,
                message=f"ZMQ PUB/SUB to {host}:{port} failed - {e}",
                duration_ms=duration
            )
        finally:
            if socket:
                socket.close()
    
    def _test_http_endpoint(self, url: str, name: str, 
                           method: str = "GET", 
                           json_data: Optional[Dict] = None) -> TestResult:
        """Test HTTP endpoint."""
        if not REQUESTS_AVAILABLE:
            return TestResult(
                name=name,
                status=TestStatus.SKIP,
                message="requests not installed (pip install requests)"
            )
        
        start = time.time()
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=self.config["timeout"])
            else:
                response = requests.post(url, json=json_data, 
                                        timeout=self.config["timeout"])
            
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                return TestResult(
                    name=name,
                    status=TestStatus.PASS,
                    message=f"HTTP {method} {url} - OK ({response.status_code})",
                    details={
                        "status_code": response.status_code,
                        "content_preview": response.text[:200] if response.text else None
                    },
                    duration_ms=duration
                )
            else:
                return TestResult(
                    name=name,
                    status=TestStatus.WARN,
                    message=f"HTTP {method} {url} - Status {response.status_code}",
                    details={"status_code": response.status_code},
                    duration_ms=duration
                )
        except requests.exceptions.ConnectionError as e:
            duration = (time.time() - start) * 1000
            return TestResult(
                name=name,
                status=TestStatus.FAIL,
                message=f"HTTP {method} {url} - Connection refused",
                duration_ms=duration
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TestResult(
                name=name,
                status=TestStatus.FAIL,
                message=f"HTTP {method} {url} - {type(e).__name__}: {e}",
                duration_ms=duration
            )
    
    # ========================================================================
    # Camera Tests
    # ========================================================================
    
    def test_camera_flask(self) -> List[TestResult]:
        """Test Camera Flask HTTP server."""
        print("\n📷 Testing Camera Flask Server...")
        results = []
        
        host = self.config["camera_flask_host"]
        port = self.config["camera_flask_port"]
        base_url = f"http://{host}:{port}"
        
        # Test basic connectivity
        results.append(self._test_tcp_port(host, port, "Camera Flask TCP Port"))
        
        # Test HTTP endpoints
        endpoints = [
            ("/", "Camera Flask Root"),
            ("/health", "Camera Flask Health"),
            ("/api/status", "Camera Flask API Status"),
        ]
        
        for endpoint, name in endpoints:
            results.append(self._test_http_endpoint(
                f"{base_url}{endpoint}", name
            ))
        
        return results
    
    def test_camera_zmq(self) -> List[TestResult]:
        """Test Camera ZMQ server."""
        print("\n📡 Testing Camera ZMQ Server...")
        results = []
        
        host = self.config["camera_zmq_host"]
        port = self.config["camera_zmq_port"]
        
        # Test TCP port
        results.append(self._test_tcp_port(host, port, "Camera ZMQ TCP Port"))
        
        # Test ZMQ connection (assuming REQ/REP)
        results.append(self._test_zmq_req(
            host, port, "Camera ZMQ REQ/REP",
            message={"command": "get_status"}
        ))
        
        return results
    
    def test_camera_command_listener(self) -> List[TestResult]:
        """Test Camera command listener (TCP socket)."""
        print("\n🎧 Testing Camera Command Listener...")
        results = []
        
        host = self.config["camera_cmd_host"]
        port = self.config["camera_cmd_port"]
        
        results.append(self._test_tcp_port(host, port, "Camera Command TCP Port"))
        
        return results
    
    # ========================================================================
    # Manager Tests
    # ========================================================================
    
    def test_manager(self) -> List[TestResult]:
        """Test Manager ZMQ server."""
        print("\n🎯 Testing Manager Server...")
        results = []
        
        host = self.config["manager_host"]
        port = self.config["manager_cmd_port"]
        
        # Test TCP port
        results.append(self._test_tcp_port(host, port, "Manager ZMQ TCP Port"))
        
        # Test ZMQ REQ/REP
        results.append(self._test_zmq_req(
            host, port, "Manager ZMQ REQ/REP",
            message={"command": "ping"}
        ))
        
        return results
    
    # ========================================================================
    # ARTIQ Tests
    # ========================================================================
    
    def test_artiq(self) -> List[TestResult]:
        """Test ARTIQ Master ZMQ connections."""
        print("\n⚛️  Testing ARTIQ Master...")
        results = []
        
        host = self.config["artiq_master_host"]
        
        # Test command port (PUB) - we can SUB to it
        results.append(self._test_tcp_port(
            host, self.config["artiq_master_cmd_port"], 
            "ARTIQ Master Command Port (TCP)"
        ))
        results.append(self._test_zmq_pub_sub(
            host, self.config["artiq_master_cmd_port"],
            "ARTIQ Master Command Port (ZMQ PUB)"
        ))
        
        # Test data port (PULL) - this accepts PUSH from workers
        results.append(self._test_tcp_port(
            host, self.config["artiq_master_data_port"],
            "ARTIQ Master Data Port (TCP)"
        ))
        
        return results
    
    # ========================================================================
    # LabVIEW Tests
    # ========================================================================
    
    def test_labview(self) -> List[TestResult]:
        """Test LabVIEW ZMQ connection."""
        print("\n🔬 Testing LabVIEW Interface...")
        results = []
        
        host = self.config["labview_host"]
        port = self.config["labview_port"]
        
        # Test TCP port
        results.append(self._test_tcp_port(host, port, "LabVIEW ZMQ TCP Port"))
        
        # Test ZMQ (LabVIEW typically uses REQ/REP)
        results.append(self._test_zmq_req(
            host, port, "LabVIEW ZMQ REQ/REP",
            message={"command": "get_status"}
        ))
        
        return results
    
    # ========================================================================
    # Run All Tests
    # ========================================================================
    
    def run_all_tests(self, 
                      camera: bool = True,
                      manager: bool = True, 
                      artiq: bool = True,
                      labview: bool = True) -> List[TestResult]:
        """Run all enabled tests."""
        all_results = []
        
        print("=" * 70)
        print("🔌 Manager PC Connection Test Suite")
        print("=" * 70)
        print(f"\nConfiguration:")
        print(f"  Camera Flask:  {self.config['camera_flask_host']}:{self.config['camera_flask_port']}")
        print(f"  Camera ZMQ:    {self.config['camera_zmq_host']}:{self.config['camera_zmq_port']}")
        print(f"  Camera CMD:    {self.config['camera_cmd_host']}:{self.config['camera_cmd_port']}")
        print(f"  Manager:       {self.config['manager_host']}:{self.config['manager_cmd_port']}")
        print(f"  ARTIQ Master:  {self.config['artiq_master_host']}:{self.config['artiq_master_cmd_port']}")
        print(f"  LabVIEW:       {self.config['labview_host']}:{self.config['labview_port']}")
        
        if camera:
            all_results.extend(self.test_camera_flask())
            all_results.extend(self.test_camera_zmq())
            all_results.extend(self.test_camera_command_listener())
        
        if manager:
            all_results.extend(self.test_manager())
        
        if artiq:
            all_results.extend(self.test_artiq())
        
        if labview:
            all_results.extend(self.test_labview())
        
        return all_results
    
    def print_summary(self, results: List[TestResult]):
        """Print test summary."""
        print("\n" + "=" * 70)
        print("📊 Test Summary")
        print("=" * 70)
        
        # Group by status
        passed = [r for r in results if r.status == TestStatus.PASS]
        failed = [r for r in results if r.status == TestStatus.FAIL]
        warnings = [r for r in results if r.status == TestStatus.WARN]
        skipped = [r for r in results if r.status == TestStatus.SKIP]
        
        # Print failed tests first
        if failed:
            print(f"\n❌ FAILED ({len(failed)}):")
            for r in failed:
                print(f"   • {r.name}")
                print(f"     → {r.message}")
        
        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)}):")
            for r in warnings:
                print(f"   • {r.name}")
                print(f"     → {r.message}")
        
        if skipped:
            print(f"\n⏭️  SKIPPED ({len(skipped)}):")
            for r in skipped:
                print(f"   • {r.name}: {r.message}")
        
        # Print passed tests
        if passed:
            print(f"\n✅ PASSED ({len(passed)}):")
            for r in passed:
                status = "🟢" if r.duration_ms < 100 else "🟡"
                print(f"   {status} {r.name} ({r.duration_ms:.1f}ms)")
        
        # Overall summary
        print("\n" + "-" * 70)
        total = len(results)
        pass_rate = len(passed) / total * 100 if total > 0 else 0
        
        if failed:
            status_emoji = "❌"
            status_text = "SOME TESTS FAILED"
        elif warnings:
            status_emoji = "⚠️"
            status_text = "TESTS PASSED WITH WARNINGS"
        else:
            status_emoji = "✅"
            status_text = "ALL TESTS PASSED"
        
        print(f"{status_emoji} {status_text}")
        print(f"   Total: {total} | Passed: {len(passed)} | Failed: {len(failed)} | "
              f"Warnings: {len(warnings)} | Skipped: {len(skipped)}")
        print(f"   Pass Rate: {pass_rate:.1f}%")
        print("=" * 70)
    
    def export_results(self, results: List[TestResult], filepath: str):
        """Export results to JSON."""
        data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config": self.config,
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                    "duration_ms": r.duration_ms
                }
                for r in results
            ],
            "summary": {
                "total": len(results),
                "passed": len([r for r in results if r.status == TestStatus.PASS]),
                "failed": len([r for r in results if r.status == TestStatus.FAIL]),
                "warnings": len([r for r in results if r.status == TestStatus.WARN]),
                "skipped": len([r for r in results if r.status == TestStatus.SKIP]),
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n📝 Results exported to: {filepath}")


def load_config_from_file(config_path: str) -> Dict:
    """Load configuration from YAML file."""
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"Warning: Could not load config from {config_path}: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(
        description="Test connections between Manager PC services"
    )
    parser.add_argument("--camera", action="store_true", 
                       help="Test camera only")
    parser.add_argument("--manager", action="store_true",
                       help="Test manager only")
    parser.add_argument("--artiq", action="store_true",
                       help="Test ARTIQ only")
    parser.add_argument("--labview", action="store_true",
                       help="Test LabVIEW only")
    parser.add_argument("--all", action="store_true",
                       help="Run all tests (default)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")
    parser.add_argument("--config", "-c", type=str,
                       help="Path to config file (YAML)")
    parser.add_argument("--export", "-e", type=str,
                       help="Export results to JSON file")
    parser.add_argument("--camera-host", type=str,
                       help="Override camera host")
    parser.add_argument("--camera-port", type=int,
                       help="Override camera Flask port")
    parser.add_argument("--labview-host", type=str,
                       help="Override LabVIEW host")
    
    args = parser.parse_args()
    
    # Determine which tests to run
    run_camera = args.camera or args.all or not any([args.manager, args.artiq, args.labview])
    run_manager = args.manager or args.all or not any([args.camera, args.artiq, args.labview])
    run_artiq = args.artiq or args.all or not any([args.camera, args.manager, args.labview])
    run_labview = args.labview or args.all or not any([args.camera, args.manager, args.artiq])
    
    # Build config
    config = {}
    if args.config:
        config = load_config_from_file(args.config)
    
    # Apply command-line overrides
    if args.camera_host:
        config["camera_flask_host"] = args.camera_host
        config["camera_zmq_host"] = args.camera_host
    if args.camera_port:
        config["camera_flask_port"] = args.camera_port
    if args.labview_host:
        config["labview_host"] = args.labview_host
    
    # Create tester and run
    tester = ConnectionTester(config=config, verbose=args.verbose)
    
    try:
        results = tester.run_all_tests(
            camera=run_camera,
            manager=run_manager,
            artiq=run_artiq,
            labview=run_labview
        )
        
        tester.print_summary(results)
        
        if args.export:
            tester.export_results(results, args.export)
        
        # Exit with error code if any tests failed
        failed = [r for r in results if r.status == TestStatus.FAIL]
        return 1 if failed else 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        return 130
    finally:
        if tester._zmq_context:
            tester._zmq_context.destroy()


if __name__ == "__main__":
    sys.exit(main())
