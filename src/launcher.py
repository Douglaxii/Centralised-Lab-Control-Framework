#!/usr/bin/env python3
"""
MLS Launcher - Main entry point for starting all services.

Usage:
    python -m src.launcher                    # Start all services
    python -m src.launcher --services manager,api  # Start specific services
    python -m src.launcher --status           # Check service status
    python -m src.launcher --stop             # Stop all services

Services:
    manager     - ControlManager (ZMQ coordinator, port 5555-5558)
    api         - Flask REST API (port 5000)
    camera      - Camera server (port 5558)
    optimizer   - Bayesian optimization UI (port 5050)
    applet      - Applet server (port 5051)
"""

import argparse
import logging
import subprocess
import sys
import time
import socket
import signal
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from core import get_config, setup_logging


@dataclass
class Service:
    """Service definition."""
    name: str
    port: int
    cmd: List[str]
    color: str
    depends_on: List[str] = None
    
    def __post_init__(self):
        if self.depends_on is None:
            self.depends_on = []


# Service colors for terminal output
COLORS = {
    'manager': '\033[92m',    # Green
    'api': '\033[94m',        # Blue
    'camera': '\033[96m',     # Cyan
    'optimizer': '\033[93m',  # Yellow
    'applet': '\033[95m',     # Magenta
    'launcher': '\033[97m',   # White
    'error': '\033[91m',      # Red
    'reset': '\033[0m'
}


def log(service: str, message: str):
    """Log a message with service color."""
    color = COLORS.get(service, '')
    reset = COLORS['reset']
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"{color}[{timestamp}] [{service.upper():8}] {message}{reset}")


def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result != 0  # Port is available if connect fails
    except:
        return False


def is_port_in_use(host: str, port: int) -> bool:
    """Check if a port is in use."""
    return not is_port_available(host, port)


def wait_for_port(host: str, port: int, timeout: float = 30.0, expected: bool = True) -> bool:
    """Wait for a port to be in expected state (True=in use, False=available)."""
    start = time.time()
    while time.time() - start < timeout:
        current = is_port_in_use(host, port)
        if current == expected:
            return True
        time.sleep(0.1)
    return False


def get_service_config(name: str) -> Service:
    """Get service configuration."""
    config = get_config()
    python = sys.executable
    project_root = Path(__file__).parent.parent
    
    services = {
        'manager': Service(
            name='manager',
            port=config.client_port,  # 5557 - client port for checking
            cmd=[python, "-m", "src.services.manager.manager"],
            color=COLORS['manager']
        ),
        'api': Service(
            name='api',
            port=config.flask_port,  # 5000
            cmd=[python, "-m", "src.services.api.flask_server"],
            color=COLORS['api'],
            depends_on=['manager']
        ),
        'optimizer': Service(
            name='optimizer',
            port=config.optimizer_port,  # 5050
            cmd=[python, "-m", "src.services.optimizer.flask_optimizer.app", "--host", "0.0.0.0", "--port", str(config.optimizer_port)],
            color=COLORS['optimizer'],
            depends_on=['manager']
        ),
        'applet': Service(
            name='applet',
            port=config.get('services.applet.port', 5051),
            cmd=[python, "-m", "src.services.applet.app", "--host", "0.0.0.0", "--port", str(config.get('services.applet.port', 5051))],
            color=COLORS['applet'],
            depends_on=['manager']
        ),
        'camera': Service(
            name='camera',
            port=config.camera_port,  # 5558
            cmd=[python, "-m", "src.services.camera.camera_server"],
            color=COLORS['camera']
        ),
    }
    
    return services[name]


class ServiceManager:
    """Manages service processes."""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.logger = logging.getLogger("launcher")
        self._shutdown = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        signame = signal.Signals(signum).name
        log('launcher', f"Received {signame}, shutting down...")
        self._shutdown = True
        self.stop_all()
    
    def start_service(self, name: str, wait: bool = True) -> bool:
        """Start a single service."""
        config = get_config()
        service = get_service_config(name)
        host = config.bind_host if name != 'camera' else '0.0.0.0'
        
        # Check if already running
        if name in self.processes:
            proc = self.processes[name]
            if proc.poll() is None:
                log(name, "Already running")
                return True
            else:
                # Process died, remove it
                del self.processes[name]
        
        # Check port availability
        if is_port_in_use(host, service.port):
            log(name, f"Port {service.port} already in use!")
            return False
        
        # Start dependencies first
        for dep in service.depends_on:
            if dep not in self.processes:
                log(name, f"Starting dependency: {dep}")
                if not self.start_service(dep, wait=True):
                    log(name, f"Failed to start dependency: {dep}")
                    return False
        
        try:
            log(name, f"Starting on port {service.port}...")
            
            # Create process
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            proc = subprocess.Popen(
                service.cmd,
                cwd=str(Path(__file__).parent.parent),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes[name] = proc
            
            # Wait for service to be ready
            if wait:
                if wait_for_port(host, service.port, timeout=30, expected=True):
                    log(name, f"[OK] Ready on port {service.port}")
                    return True
                else:
                    # Check if process died
                    if proc.poll() is not None:
                        stdout, _ = proc.communicate()
                        log(name, f"[EXIT] Failed to start (exit code {proc.returncode})")
                        if stdout:
                            print(f"  Output: {stdout[-500:]}")  # Last 500 chars
                    else:
                        log(name, "[FAIL] Timeout waiting for startup")
                    return False
            else:
                return True
                
        except Exception as e:
            log(name, f"[FAIL] Error starting: {e}")
            return False
    
    def stop_service(self, name: str) -> bool:
        """Stop a single service."""
        if name not in self.processes:
            return True
        
        proc = self.processes[name]
        
        if proc.poll() is not None:
            # Already stopped
            del self.processes[name]
            return True
        
        log(name, "Stopping...")
        
        try:
            # Try graceful shutdown first
            proc.terminate()
            
            # Wait for process to exit
            try:
                proc.wait(timeout=5)
                log(name, "[OK] Stopped")
            except subprocess.TimeoutExpired:
                # Force kill
                proc.kill()
                proc.wait()
                log(name, "[OK] Killed")
            
            del self.processes[name]
            return True
            
        except Exception as e:
            log(name, f"[FAIL] Error stopping: {e}")
            return False
    
    def stop_all(self):
        """Stop all services."""
        log('launcher', "Stopping all services...")
        
        # Stop in reverse order
        for name in list(self.processes.keys())[::-1]:
            self.stop_service(name)
    
    def poll_outputs(self):
        """Poll service outputs and print to console."""
        for name, proc in list(self.processes.items()):
            if proc.poll() is not None:
                # Process died
                log(name, f"[EXIT] Process exited with code {proc.returncode}")
                del self.processes[name]
                continue
            
            # Try to read output (non-blocking)
            try:
                import select
                if proc.stdout in select.select([proc.stdout], [], [], 0)[0]:
                    line = proc.stdout.readline()
                    if line:
                        # Print with service color
                        color = COLORS.get(name, '')
                        reset = COLORS['reset']
                        print(f"{color}[{name}] {line.rstrip()}{reset}")
            except:
                pass
    
    def get_status(self) -> Dict[str, str]:
        """Get status of all services."""
        status = {}
        config = get_config()
        
        for name in ['manager', 'api', 'optimizer', 'applet', 'camera']:
            service = get_service_config(name)
            host = config.bind_host if name != 'camera' else '0.0.0.0'
            
            if is_port_in_use(host, service.port):
                status[name] = 'running'
            else:
                status[name] = 'stopped'
        
        return status
    
    def monitor(self):
        """Monitor running services."""
        log('launcher', "Monitoring services (Ctrl+C to stop)...")
        
        try:
            while not self._shutdown and self.processes:
                self.poll_outputs()
                
                # Check if any process died
                for name, proc in list(self.processes.items()):
                    if proc.poll() is not None:
                        log(name, f"[EXIT] Process exited (code {proc.returncode})")
                        del self.processes[name]
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            log('launcher', "Interrupted by user")
        finally:
            self.stop_all()


def print_status():
    """Print service status."""
    config = get_config()
    manager = ServiceManager()
    status = manager.get_status()
    
    print("\n" + "=" * 60)
    print("                    SERVICE STATUS")
    print("=" * 60)
    
    for name, state in status.items():
        service = get_service_config(name)
        host = config.bind_host if name != 'camera' else '0.0.0.0'
        
        if state == 'running':
            icon = '[OK]'
            color = '\033[92m'  # Green
        else:
            icon = '[--]'
            color = '\033[91m'  # Red
        
        reset = '\033[0m'
        print(f"  {color}{icon} {name:12}{reset} {state:8}  port {service.port}")
    
    print("=" * 60)


def stop_all_services():
    """Stop all running services."""
    log('launcher', "Stopping all MLS services...")
    
    # Try to find and kill processes by port
    import subprocess as sp
    
    config = get_config()
    ports = [5000, 5050, 5051, 5555, 5556, 5557, 5558]
    
    for port in ports:
        try:
            # Find process using port (Windows)
            result = sp.run(
                ['netstat', '-ano', '|', 'findstr', f':{port}'],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.splitlines():
                    if 'LISTENING' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            pid = parts[-1]
                            log('launcher', f"Killing process {pid} on port {port}")
                            sp.run(['taskkill', '/F', '/PID', pid], capture_output=True)
                            
        except Exception as e:
            pass
    
    log('launcher', "Done!")


def main():
    parser = argparse.ArgumentParser(description='MLS Service Launcher')
    parser.add_argument(
        '--services',
        type=str,
        default='all',
        help='Comma-separated list of services to start (default: all)'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Check service status'
    )
    parser.add_argument(
        '--stop',
        action='store_true',
        help='Stop all services'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run in daemon mode (don\'t wait for services)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    if args.status:
        print_status()
        return
    
    if args.stop:
        stop_all_services()
        return
    
    # Determine which services to start
    if args.services == 'all':
        services = ['manager', 'api', 'optimizer', 'applet', 'camera']
    else:
        services = [s.strip() for s in args.services.split(',')]
    
    # Check if launcher can run these services
    valid_services = ['manager', 'api', 'camera', 'optimizer', 'applet']
    for service in services:
        if service not in valid_services:
            log('launcher', f"Unknown service: {service}")
            log('launcher', f"Valid services: {', '.join(valid_services)}")
            return
    
    # Filter to only enabled services from config
    config = get_config()
    enabled_services = []
    for service in services:
        if service == 'manager' and config.get('services.manager.enabled', True):
            enabled_services.append(service)
        elif service == 'api' and config.get('services.flask.enabled', True):
            enabled_services.append(service)
        elif service == 'camera' and config.get('services.camera.enabled', True):
            enabled_services.append(service)
        elif service == 'optimizer' and config.get('services.optimizer.enabled', True):
            enabled_services.append(service)
        elif service == 'applet' and config.get('services.applet.enabled', True):
            enabled_services.append(service)
    
    services = enabled_services
    
    if not services:
        log('launcher', "No services enabled in config!")
        return
    
    log('launcher', f"Starting services: {', '.join(services)}")
    
    # Start services
    manager = ServiceManager()
    failed = []
    
    for service in services:
        if not manager.start_service(service, wait=True):
            failed.append(service)
    
    if failed:
        log('launcher', f"Failed to start: {', '.join(failed)}")
        log('launcher', "Stopping all services...")
        manager.stop_all()
        return
    
    log('launcher', f"All services started successfully!")
    
    # Monitor or exit
    if args.daemon:
        log('launcher', "Running in daemon mode. Use --status to check, --stop to stop.")
    else:
        manager.monitor()


if __name__ == "__main__":
    main()
