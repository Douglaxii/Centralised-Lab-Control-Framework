#!/usr/bin/env python3
"""
Unified Launcher - Run Camera Server, Manager, and Flask in Parallel

Optimizations for same-PC execution:
- Single process manager with proper lifecycle control
- Shared configuration monitoring
- Automatic restart on failure
- Health checking and status reporting
- Clean shutdown handling

Usage:
    python launcher.py              # Start all services
    python launcher.py --status     # Check status
    python launcher.py --stop       # Stop all services
    python launcher.py --restart    # Restart all services
"""

import os
import sys
import time
import signal
import subprocess
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/launcher.log', mode='a')
    ]
)
logger = logging.getLogger("Launcher")

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)


class ServiceStatus(Enum):
    """Service status states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    RESTARTING = "restarting"


@dataclass
class ServiceInfo:
    """Information about a managed service."""
    name: str
    status: ServiceStatus
    pid: Optional[int]
    port: int
    start_time: Optional[float]
    restart_count: int
    last_error: Optional[str]


class ServiceManager:
    """Manages a single service process."""
    
    def __init__(
        self,
        name: str,
        command: List[str],
        port: int,
        health_check_url: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.command = command
        self.port = port
        self.health_check_url = health_check_url
        self.env_vars = env_vars or {}
        self.process: Optional[subprocess.Popen] = None
        self.info = ServiceInfo(
            name=name,
            status=ServiceStatus.STOPPED,
            pid=None,
            port=port,
            start_time=None,
            restart_count=0,
            last_error=None
        )
    
    def start(self) -> bool:
        """Start the service."""
        if self.process and self.process.poll() is None:
            logger.info(f"[{self.name}] Already running (PID: {self.process.pid})")
            return True
        
        try:
            self.info.status = ServiceStatus.STARTING
            logger.info(f"[{self.name}] Starting: {' '.join(self.command)}")
            
            # Merge environment variables
            env = os.environ.copy()
            env.update(self.env_vars)
            
            # Start process
            self.process = subprocess.Popen(
                self.command,
                stdout=open(f'logs/{self.name.lower()}.log', 'a'),
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            self.info.pid = self.process.pid
            self.info.start_time = time.time()
            self.info.status = ServiceStatus.RUNNING
            
            logger.info(f"[{self.name}] Started with PID {self.process.pid}")
            return True
            
        except Exception as e:
            self.info.status = ServiceStatus.ERROR
            self.info.last_error = str(e)
            logger.error(f"[{self.name}] Failed to start: {e}")
            return False
    
    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the service gracefully."""
        if not self.process or self.process.poll() is not None:
            self.info.status = ServiceStatus.STOPPED
            return True
        
        try:
            logger.info(f"[{self.name}] Stopping (PID: {self.process.pid})...")
            
            # Try graceful termination first
            if os.name == 'nt':
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.process.terminate()
            
            # Wait for graceful shutdown
            try:
                self.process.wait(timeout=timeout)
                logger.info(f"[{self.name}] Stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill
                logger.warning(f"[{self.name}] Force killing...")
                self.process.kill()
                self.process.wait()
            
            self.info.status = ServiceStatus.STOPPED
            self.info.pid = None
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] Error stopping: {e}")
            return False
    
    def check_health(self) -> bool:
        """Check if service is healthy."""
        if not self.process:
            return False
        
        # Check if process is running
        if self.process.poll() is not None:
            return False
        
        # For Camera and Manager, just check process is alive
        # Camera uses custom TCP protocol, Manager uses ZMQ
        if self.name in ['Camera', 'Manager']:
            return True
        
        # For Flask (HTTP), check port
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', self.port))
            sock.close()
            return result == 0
        except:
            return False
    
    def restart(self) -> bool:
        """Restart the service."""
        self.info.status = ServiceStatus.RESTARTING
        self.stop()
        time.sleep(0.5)
        self.info.restart_count += 1
        return self.start()


class UnifiedLauncher:
    """
    Manages all three services for parallel execution on same PC.
    
    Services:
    - Camera Server (TCP:5558, CMD:5559)
    - Control Manager (ZMQ:5555, 5556, REQ/REP:5557)
    - Flask Web Server (HTTP:5000)
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceManager] = {}
        self.running = False
        self.monitor_thread = None
        self._setup_services()
    
    def _setup_services(self):
        """Configure all services."""
        project_root = Path(__file__).parent
        
        # 1. Camera Server
        self.services['camera'] = ServiceManager(
            name="Camera",
            command=[sys.executable, str(project_root / "server" / "cam" / "camera_server.py")],
            port=5558,
            env_vars={'PYTHONPATH': str(project_root)}
        )
        
        # 2. Control Manager
        self.services['manager'] = ServiceManager(
            name="Manager",
            command=[sys.executable, str(project_root / "server" / "communications" / "manager.py")],
            port=5557,  # ZMQ client port
            env_vars={'PYTHONPATH': str(project_root)}
        )
        
        # 3. Flask Server
        self.services['flask'] = ServiceManager(
            name="Flask",
            command=[sys.executable, str(project_root / "server" / "Flask" / "flask_server.py")],
            port=5000,
            env_vars={'PYTHONPATH': str(project_root), 'FLASK_ENV': 'production'}
        )
    
    def start_all(self, stagger: float = 2.0):
        """Start all services with staggered startup."""
        logger.info("=" * 60)
        logger.info("Starting all services...")
        logger.info("=" * 60)
        
        # Start order: Camera -> Manager -> Flask
        start_order = ['camera', 'manager', 'flask']
        
        for name in start_order:
            service = self.services[name]
            if not service.start():
                logger.error(f"Failed to start {name}!")
                return False
            
            # Wait longer for initialization (especially Camera)
            logger.info(f"Waiting {stagger}s for {name} to initialize...")
            time.sleep(stagger)
        
        self.running = True
        logger.info("=" * 60)
        logger.info("All services started!")
        logger.info("=" * 60)
        
        # Start monitoring
        self._start_monitoring()
        return True
    
    def stop_all(self):
        """Stop all services in reverse order."""
        logger.info("=" * 60)
        logger.info("Stopping all services...")
        logger.info("=" * 60)
        
        # Stop in reverse order
        for name in reversed(['camera', 'manager', 'flask']):
            self.services[name].stop()
        
        self.running = False
        logger.info("All services stopped")
    
    def restart_all(self):
        """Restart all services."""
        self.stop_all()
        time.sleep(1)
        return self.start_all()
    
    def restart_service(self, name: str):
        """Restart a specific service."""
        if name in self.services:
            logger.info(f"Restarting {name}...")
            self.services[name].restart()
        else:
            logger.error(f"Unknown service: {name}")
    
    def get_status(self) -> Dict:
        """Get status of all services."""
        status = {
            'timestamp': datetime.now().isoformat(),
            'running': self.running,
            'services': {}
        }
        
        for name, service in self.services.items():
            # Check actual health
            healthy = service.check_health()
            if not healthy and service.info.status == ServiceStatus.RUNNING:
                service.info.status = ServiceStatus.ERROR
            
            status['services'][name] = {
                'status': service.info.status.value,
                'pid': service.info.pid,
                'port': service.info.port,
                'healthy': healthy,
                'uptime': time.time() - service.info.start_time if service.info.start_time else 0,
                'restarts': service.info.restart_count,
                'last_error': service.info.last_error
            }
        
        return status
    
    def print_status(self):
        """Print formatted status."""
        status = self.get_status()
        
        print("\n" + "=" * 70)
        print(f"{'Service':<15} {'Status':<12} {'PID':<8} {'Port':<6} {'Health':<8} {'Uptime':<10}")
        print("-" * 70)
        
        for name, info in status['services'].items():
            uptime = info['uptime']
            uptime_str = f"{int(uptime//60)}m{int(uptime%60)}s" if uptime > 0 else "N/A"
            
            print(f"{name:<15} {info['status']:<12} {str(info['pid'] or 'N/A'):<8} "
                  f"{info['port']:<6} {'✓' if info['healthy'] else '✗':<8} {uptime_str:<10}")
        
        print("=" * 70)
        
        # Show recent errors
        errors = [(n, s.info.last_error) for n, s in self.services.items() if s.info.last_error]
        if errors:
            print("\nRecent Errors:")
            for name, error in errors:
                print(f"  {name}: {error}")
    
    def _start_monitoring(self):
        """Start background health monitoring."""
        import threading
        
        def monitor():
            # Wait longer initially for all services to start
            initial_delay = 10
            logger.info(f"Health monitoring starts in {initial_delay}s...")
            time.sleep(initial_delay)
            
            while self.running:
                for name, service in self.services.items():
                    if service.info.status == ServiceStatus.RUNNING:
                        healthy = service.check_health()
                        if not healthy:
                            logger.warning(f"[{name}] Health check failed, restarting...")
                            service.restart()
                        else:
                            logger.debug(f"[{name}] Health check OK")
                
                time.sleep(10)  # Check every 10 seconds (was 5)
        
        self.monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.monitor_thread.start()
    
    def run_interactive(self):
        """Run in interactive mode with command prompt."""
        self.start_all()
        
        print("\n" + "=" * 60)
        print("Interactive Mode - Commands:")
        print("  status, restart <service>, stop, quit")
        print("=" * 60 + "\n")
        
        try:
            while self.running:
                try:
                    cmd = input("launcher> ").strip().lower()
                    
                    if cmd == "status":
                        self.print_status()
                    
                    elif cmd == "stop":
                        self.stop_all()
                        break
                    
                    elif cmd == "quit":
                        self.stop_all()
                        break
                    
                    elif cmd.startswith("restart "):
                        service_name = cmd.split()[1]
                        self.restart_service(service_name)
                    
                    elif cmd == "restart":
                        self.restart_all()
                    
                    elif cmd == "help":
                        print("Commands: status, restart [service], stop, quit, help")
                    
                    else:
                        print(f"Unknown command: {cmd}")
                
                except KeyboardInterrupt:
                    print("\nUse 'quit' or 'stop' to exit")
        
        finally:
            if self.running:
                self.stop_all()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Unified Launcher for Lab Control System")
    parser.add_argument('--start', action='store_true', help='Start all services')
    parser.add_argument('--stop', action='store_true', help='Stop all services')
    parser.add_argument('--restart', action='store_true', help='Restart all services')
    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode')
    parser.add_argument('--daemon', '-d', action='store_true', help='Run in background')
    parser.add_argument('--stagger', type=float, default=1.0, help='Startup stagger (seconds)')
    
    args = parser.parse_args()
    
    launcher = UnifiedLauncher()
    
    # Check for existing PID file
    pid_file = Path('launcher.pid')
    
    if args.stop:
        if pid_file.exists():
            pid = int(pid_file.read_text())
            try:
                if os.name == 'nt':
                    # Windows: use taskkill
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                                 capture_output=True, check=False)
                else:
                    # Unix: use SIGTERM
                    os.kill(pid, signal.SIGTERM)
                print(f"Sent stop signal to launcher (PID: {pid})")
            except (ProcessLookupError, OSError):
                print("Launcher not running")
            try:
                pid_file.unlink()
            except FileNotFoundError:
                pass
        launcher.stop_all()
    
    elif args.status:
        launcher.print_status()
    
    elif args.restart:
        launcher.restart_all()
        if args.interactive:
            launcher.run_interactive()
    
    elif args.interactive or args.start or (not any([args.stop, args.status, args.restart])):
        # Default: start all in interactive mode
        if args.daemon:
            # Daemon mode - write PID file
            pid_file.write_text(str(os.getpid()))
            launcher.start_all(stagger=args.stagger)
            # Keep running
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                launcher.stop_all()
        else:
            launcher.run_interactive()


if __name__ == "__main__":
    main()
