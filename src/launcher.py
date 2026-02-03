#!/usr/bin/env python3
"""
Unified Launcher - Starts all MLS services

Services started:
1. Control Manager (ZMQ hub) - Port 5557
2. Main Flask Dashboard - Port 5000
3. Applet Flask Server - Port 5051  
4. Optimizer Flask Server - Port 5050

Usage:
    python -m src.launcher                    # Start all services
    python -m src.launcher --status           # Check status
    python -m src.launcher --stop             # Stop all services
    python -m src.launcher --restart          # Restart all services
    python -m src.launcher --service manager  # Start only manager
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
import threading

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

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

# Load and display configuration info
try:
    from core import get_config
    _config = get_config()
    _env = _config.environment
    _master_ip = _config.master_ip
    logger.info(f"Configuration loaded: {_env} (master_ip: {_master_ip})")
except Exception as e:
    logger.warning(f"Could not load configuration: {e}")


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
    url: str
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
        url: str,
        env_vars: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None
    ):
        self.name = name
        self.command = command
        self.port = port
        self.url = url
        self.env_vars = env_vars or {}
        self.cwd = cwd
        self.process: Optional[subprocess.Popen] = None
        self.info = ServiceInfo(
            name=name,
            status=ServiceStatus.STOPPED,
            pid=None,
            port=port,
            url=url,
            start_time=None,
            restart_count=0,
            last_error=None
        )
        self._lock = threading.Lock()
    
    def start(self) -> bool:
        """Start the service."""
        with self._lock:
            if self.is_running():
                logger.warning(f"{self.name} is already running (PID: {self.info.pid})")
                return True
            
            try:
                self.info.status = ServiceStatus.STARTING
                env = os.environ.copy()
                env.update(self.env_vars)
                
                # Log file for this service
                log_file = open(f'logs/{self.name}.log', 'a')
                
                self.process = subprocess.Popen(
                    self.command,
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=self.cwd
                )
                
                self.info.pid = self.process.pid
                self.info.start_time = time.time()
                self.info.status = ServiceStatus.RUNNING
                
                logger.info(f"Started {self.name} (PID: {self.info.pid}) on port {self.port}")
                logger.info(f"  URL: {self.url}")
                return True
                
            except Exception as e:
                self.info.status = ServiceStatus.ERROR
                self.info.last_error = str(e)
                logger.error(f"Failed to start {self.name}: {e}")
                return False
    
    def stop(self, timeout: float = 10.0) -> bool:
        """Stop the service gracefully."""
        with self._lock:
            if self.process is None:
                return True
            
            try:
                logger.info(f"Stopping {self.name} (PID: {self.info.pid})...")
                
                # Try graceful termination first
                self.process.terminate()
                try:
                    self.process.wait(timeout=timeout)
                    logger.info(f"Stopped {self.name} gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful fails
                    logger.warning(f"{self.name} did not stop gracefully, killing...")
                    self.process.kill()
                    self.process.wait(timeout=5)
                    logger.info(f"Killed {self.name}")
                
                self.info.status = ServiceStatus.STOPPED
                self.info.pid = None
                self.process = None
                return True
                
            except Exception as e:
                logger.error(f"Error stopping {self.name}: {e}")
                return False
    
    def is_running(self) -> bool:
        """Check if service is running."""
        if self.process is None:
            return False
        return self.process.poll() is None
    
    def check_health(self) -> bool:
        """Check if service is healthy."""
        if not self.is_running():
            self.info.status = ServiceStatus.ERROR
            self.info.last_error = "Process not running"
            return False
        return True


class UnifiedLauncher:
    """Unified launcher for all MLS services."""
    
    # Service definitions
    SERVICES = {
        'manager': {
            'module': 'src.server.manager.manager',
            'port': 5557,
            'url': 'tcp://localhost:5557',
            'description': 'ZMQ Control Manager'
        },
        'flask': {
            'module': 'src.server.api.flask_server',
            'port': 5000,
            'url': 'http://localhost:5000',
            'description': 'Main Dashboard Flask Server'
        },
        'applet': {
            'module': 'src.applet.app',
            'port': 5051,
            'url': 'http://localhost:5051',
            'description': 'Applet Experiment Flask Server'
        },
        'optimizer': {
            'module': 'src.optimizer.flask_optimizer.app',
            'port': 5050,
            'url': 'http://localhost:5050',
            'description': 'Optimizer Flask Server'
        }
    }
    
    # Data paths that need to be created on startup
    DATA_PATHS = [
        'E:/data',
        'E:/data/jpg_frames',
        'E:/data/jpg_frames_labelled', 
        'E:/data/ion_data',
        'E:/data/camera',
        'E:/data/logs',
        'logs',
        'logs/server'
    ]
    
    def __init__(self):
        self.services: Dict[str, ServiceManager] = {}
        self.state_file = Path(".launcher_state.json")
        self.running = False
        self._shutdown_event = threading.Event()
        
    def _ensure_data_directories(self):
        """Ensure all required data directories exist."""
        import os
        for path in self.DATA_PATHS:
            try:
                os.makedirs(path, exist_ok=True)
                logger.debug(f"Ensured directory exists: {path}")
            except Exception as e:
                logger.warning(f"Could not create directory {path}: {e}")
        
    def register_services(self, service_names: Optional[List[str]] = None):
        """Register services to be managed."""
        names = service_names or list(self.SERVICES.keys())
        
        for name in names:
            if name not in self.SERVICES:
                logger.warning(f"Unknown service: {name}")
                continue
            
            config = self.SERVICES[name]
            command = [sys.executable, "-m", config['module']]
            
            self.services[name] = ServiceManager(
                name=name,
                command=command,
                port=config['port'],
                url=config['url'],
                env_vars={
                    'PYTHONPATH': str(Path(__file__).parent.parent),
                    'MLS_ENV': os.environ.get('MLS_ENV', 'development')
                }
            )
            logger.debug(f"Registered service: {name}")
    
    def start_all(self, stagger: float = 2.0) -> bool:
        """Start all registered services with staggered delays."""
        # Ensure data directories exist
        self._ensure_data_directories()
        
        # Get config info for display
        try:
            from core import get_config
            config = get_config()
            env = config.environment
            master_ip = config.master_ip
            data_path = config.get('paths.output_base', './data')
        except:
            env = "unknown"
            master_ip = "unknown"
            data_path = "unknown"
        
        logger.info("=" * 60)
        logger.info("Starting MLS Services")
        logger.info("=" * 60)
        logger.info(f"Environment: {env}")
        logger.info(f"Master IP: {master_ip}")
        logger.info(f"Data Path: {data_path}")
        logger.info("=" * 60)
        
        # Start order matters: manager first, then Flask servers
        start_order = ['manager', 'flask', 'applet', 'optimizer']
        
        for name in start_order:
            if name not in self.services:
                continue
            
            service = self.services[name]
            logger.info(f"\nStarting {name}...")
            
            if not service.start():
                logger.error(f"Failed to start {name}, stopping all services...")
                self.stop_all()
                return False
            
            # Stagger starts to avoid resource contention
            if stagger > 0 and name != start_order[-1]:
                logger.info(f"  Waiting {stagger}s before next service...")
                time.sleep(stagger)
        
        self.running = True
        self.save_state()
        
        logger.info("\n" + "=" * 60)
        logger.info("All services started successfully!")
        logger.info("=" * 60)
        self._print_urls()
        return True
    
    def stop_all(self):
        """Stop all services."""
        logger.info("\nStopping all services...")
        
        # Stop in reverse order
        for name in reversed(list(self.services.keys())):
            if name in self.services:
                self.services[name].stop()
        
        self.running = False
        self.save_state()
        logger.info("All services stopped.")
    
    def status(self) -> Dict:
        """Get status of all services."""
        return {
            name: {
                "status": service.info.status.value,
                "pid": service.info.pid,
                "port": service.info.port,
                "url": service.info.url,
                "running": service.is_running()
            }
            for name, service in self.services.items()
        }
    
    def print_status(self):
        """Print formatted status."""
        print("\n" + "=" * 60)
        print("MLS Service Status")
        print("=" * 60)
        
        for name, info in self.status().items():
            status_icon = "[RUNNING]" if info['running'] else "[STOPPED]"
            print(f"{status_icon} {name:<15} | Port: {info['port']} | PID: {info['pid'] or 'N/A'}")
            print(f"   URL: {info['url']}")
            print(f"   Status: {info['status']}")
            print()
        
        print("=" * 60)
    
    def _print_urls(self):
        """Print access URLs."""
        print("\nService URLs:")
        print("-" * 40)
        for name, config in self.SERVICES.items():
            if name in self.services:
                print(f"  {config['description']:<35} {config['url']}")
        print("-" * 40)
        print()
    
    def save_state(self):
        """Save launcher state to file."""
        state = {
            "timestamp": datetime.now().isoformat(),
            "running": self.running,
            "services": self.status()
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def load_state(self) -> Optional[Dict]:
        """Load launcher state from file."""
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load state file: {e}")
            return None
    
    def monitor(self):
        """Monitor services and restart if needed."""
        logger.info("Monitoring services (Press Ctrl+C to stop)...")
        
        try:
            while not self._shutdown_event.is_set():
                for name, service in self.services.items():
                    if not service.check_health():
                        logger.warning(f"{name} is not healthy, restarting...")
                        service.info.restart_count += 1
                        service.stop(timeout=5)
                        time.sleep(1)
                        service.start()
                
                self.save_state()
                time.sleep(5)  # Check every 5 seconds
                
        except KeyboardInterrupt:
            logger.info("\nShutdown signal received...")
        finally:
            self.stop_all()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MLS Unified Launcher - Start all services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.launcher                    # Start all services
    python -m src.launcher --service manager  # Start only manager
    python -m src.launcher --status           # Check status
    python -m src.launcher --stop             # Stop all services
    python -m src.launcher --restart          # Restart all services
        """
    )
    
    parser.add_argument(
        "--service", "-s",
        choices=['manager', 'flask', 'applet', 'optimizer', 'all'],
        default='all',
        help="Service to start (default: all)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show service status"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop all services"
    )
    parser.add_argument(
        "--restart", "-r",
        action="store_true",
        help="Restart all services"
    )
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run in daemon mode (no interactive console)"
    )
    parser.add_argument(
        "--stagger",
        type=float,
        default=2.0,
        help="Delay between service starts (seconds, default: 2.0)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    launcher = UnifiedLauncher()
    
    # Determine which services to manage
    if args.service == 'all':
        service_names = list(UnifiedLauncher.SERVICES.keys())
    else:
        service_names = [args.service]
    
    launcher.register_services(service_names)
    
    if args.status:
        launcher.print_status()
        return
    
    if args.stop:
        launcher.stop_all()
        return
    
    if args.restart:
        launcher.stop_all()
        time.sleep(2)
        if launcher.start_all(stagger=args.stagger):
            if not args.daemon:
                launcher.monitor()
        else:
            sys.exit(1)
        return
    
    # Start services
    if launcher.start_all(stagger=args.stagger):
        if args.daemon:
            logger.info("Running in daemon mode. Use --status to check, --stop to stop.")
        else:
            launcher.monitor()
    else:
        logger.error("Failed to start services.")
        sys.exit(1)


if __name__ == "__main__":
    main()
