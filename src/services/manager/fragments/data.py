"""
Data Fragments

Fragments for data management:
- TelemetryFragment: Telemetry data collection and storage
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .base import BaseFragment, FragmentPriority


class TelemetryFragment(BaseFragment):
    """
    Fragment for telemetry data collection.
    
    Reads data files written by LabVIEW and stores in telemetry.
    
    Expected directory structure:
        telemetry/
        ├── wavemeter/*.dat      - CSV: timestamp,frequency_mhz
        ├── smile/pmt/*.dat      - CSV: timestamp,pmt_counts
        ├── smile/pressure/*.dat - CSV: timestamp,pressure_mbar
        └── camera/*.json        - JSON: pos_x, pos_y, sig_x, sig_y
    """
    
    NAME = "telemetry"
    PRIORITY = FragmentPriority.BACKGROUND
    
    def _do_initialize(self):
        """Initialize telemetry reader."""
        self._base_path = Path(self.config.get_path('logs')).parent / "telemetry"
        self._base_path.mkdir(parents=True, exist_ok=True)
        
        self._poll_interval = self.config.get('telemetry.poll_interval', 1.0)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._known_files: Dict[str, Set[str]] = {}
        
        self._stats = {
            "wavemeter": {"count": 0, "last_value": None},
            "smile_pmt": {"count": 0, "last_value": None},
            "smile_pressure": {"count": 0, "last_value": None},
            "camera": {"count": 0, "last_value": None},
        }
        
        # Start reader thread
        self._start()
    
    def _do_shutdown(self):
        """Shutdown telemetry reader."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _start(self):
        """Start the file reader thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name="TelemetryReader"
        )
        self._thread.start()
        self.log_info(f"Telemetry reader started - watching {self._base_path}")
    
    def _read_loop(self):
        """Main loop - poll directories and read new files."""
        # Initialize known files
        for subdir in ["wavemeter", "smile/pmt", "smile/pressure", "camera"]:
            path = self._base_path / subdir
            if path.exists():
                self._known_files[subdir] = set(p.name for p in path.glob("*"))
            else:
                self._known_files[subdir] = set()
        
        while self._running:
            try:
                self._check_wavemeter()
                self._check_smile_pmt()
                self._check_smile_pressure()
                self._check_camera()
                
                time.sleep(self._poll_interval)
            except Exception as e:
                self.log_error(f"File read error: {e}")
                time.sleep(self._poll_interval)
    
    def _check_wavemeter(self):
        """Check for new wavemeter files."""
        watch_dir = self._base_path / "wavemeter"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.dat"))
        new_files = current_files - self._known_files.get("wavemeter", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                timestamp, value = self._read_csv_file(filepath)
                if timestamp and value is not None:
                    self._store_data_point("laser_freq", value, timestamp)
                    self._stats["wavemeter"]["count"] += 1
                    self._stats["wavemeter"]["last_value"] = value
            except Exception as e:
                self.log_debug(f"Failed to read {fname}: {e}")
        
        self._known_files["wavemeter"] = current_files
    
    def _check_smile_pmt(self):
        """Check for new SMILE PMT files."""
        watch_dir = self._base_path / "smile" / "pmt"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.dat"))
        new_files = current_files - self._known_files.get("smile/pmt", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                timestamp, value = self._read_csv_file(filepath)
                if timestamp and value is not None:
                    self._store_data_point("pmt", value, timestamp)
                    self._stats["smile_pmt"]["count"] += 1
                    self._stats["smile_pmt"]["last_value"] = value
            except Exception as e:
                self.log_debug(f"Failed to read {fname}: {e}")
        
        self._known_files["smile/pmt"] = current_files
    
    def _check_smile_pressure(self):
        """Check for new SMILE pressure files."""
        watch_dir = self._base_path / "smile" / "pressure"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.dat"))
        new_files = current_files - self._known_files.get("smile/pressure", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                timestamp, value = self._read_csv_file(filepath)
                if timestamp and value is not None:
                    self._store_data_point("pressure", value, timestamp)
                    self._stats["smile_pressure"]["count"] += 1
                    self._stats["smile_pressure"]["last_value"] = value
            except Exception as e:
                self.log_debug(f"Failed to read {fname}: {e}")
        
        self._known_files["smile/pressure"] = current_files
    
    def _check_camera(self):
        """Check for new camera JSON files."""
        watch_dir = self._base_path / "camera"
        if not watch_dir.exists():
            return
        
        current_files = set(p.name for p in watch_dir.glob("*.json"))
        new_files = current_files - self._known_files.get("camera", set())
        
        for fname in new_files:
            try:
                filepath = watch_dir / fname
                data = self._read_json_file(filepath)
                if data:
                    timestamp = data.get("timestamp", time.time())
                    
                    for key in ["pos_x", "pos_y", "sig_x", "sig_y"]:
                        if key in data:
                            self._store_data_point(key, data[key], timestamp)
                    
                    self._stats["camera"]["count"] += 1
            except Exception as e:
                self.log_debug(f"Failed to read {fname}: {e}")
        
        self._known_files["camera"] = current_files
    
    def _read_csv_file(self, filepath: Path) -> tuple:
        """Read CSV file: timestamp,value."""
        try:
            with open(filepath, 'r') as f:
                line = f.readline().strip()
                if ',' in line:
                    parts = line.split(',')
                    timestamp = float(parts[0])
                    value = float(parts[1])
                    return timestamp, value
        except Exception:
            pass
        return None, None
    
    def _read_json_file(self, filepath: Path) -> dict:
        """Read JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _store_data_point(self, key: str, value: float, timestamp: float):
        """Store a data point in telemetry."""
        try:
            from ..data_server import store_data_point, update_data_source
            store_data_point(key, value, timestamp)
            update_data_source(key, timestamp)
        except ImportError:
            pass  # data_server not available
    
    def get_stats(self) -> Dict[str, Any]:
        """Get reader statistics."""
        return {
            "running": self._running,
            "base_path": str(self._base_path),
            "stats": self._stats.copy(),
            "known_files": {k: len(v) for k, v in self._known_files.items()}
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get fragment status."""
        return self.get_stats()
