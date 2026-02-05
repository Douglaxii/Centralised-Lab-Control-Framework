"""
Shared Telemetry Storage - Simple data structures for Flask display

LabVIEW programs save data directly to E:/Data/
Manager reads these files and populates the shared buffers below.
Flask reads from these buffers for real-time display.

No server/threading here - just shared storage.
"""

import threading
import time
from collections import deque
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field


# =============================================================================
# CONFIGURATION
# =============================================================================

TELEMETRY_MAX_POINTS = 1000
TELEMETRY_WINDOW_SECONDS = 300

# =============================================================================
# SHARED TELEMETRY BUFFERS
# =============================================================================

_shared_telemetry_data = {
    "pressure": deque(maxlen=TELEMETRY_MAX_POINTS),
    "laser_freq": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pmt": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_fitted": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_predicted": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_diff": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_snr": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pos_x": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pos_y": deque(maxlen=TELEMETRY_MAX_POINTS),
    "sig_x": deque(maxlen=TELEMETRY_MAX_POINTS),
    "sig_y": deque(maxlen=TELEMETRY_MAX_POINTS),
}

_telemetry_lock = threading.RLock()

# Data source tracking
_data_sources = {
    "wavemeter": {"last_seen": None, "connected": False, "file_count": 0},
    "smile": {"last_seen": None, "connected": False, "file_count": 0},
    "camera": {"last_seen": None, "connected": False, "file_count": 0},
    "artiq": {"last_seen": None, "connected": False, "file_count": 0},
}
_sources_lock = threading.Lock()


# =============================================================================
# PUBLIC API (for Manager and Flask)
# =============================================================================

def get_telemetry_data():
    """Get reference to shared telemetry data (for flask_server)."""
    return _shared_telemetry_data, _telemetry_lock


def get_data_sources():
    """Get data source status (for flask_server)."""
    with _sources_lock:
        return {
            name: {
                "last_seen": info["last_seen"],
                "connected": info["connected"],
                "file_count": info["file_count"]
            }
            for name, info in _data_sources.items()
        }


def store_data_point(channel: str, value: float, timestamp: float):
    """Store a single data point (called by Manager after reading files)."""
    if channel not in _shared_telemetry_data:
        return False
    
    with _telemetry_lock:
        _shared_telemetry_data[channel].append((timestamp, float(value)))
    return True


def update_data_source(source: str, timestamp: float, increment_count: int = 1):
    """Update data source status (called by Manager)."""
    with _sources_lock:
        if source in _data_sources:
            _data_sources[source]["last_seen"] = timestamp
            _data_sources[source]["connected"] = True
            _data_sources[source]["file_count"] += increment_count


def get_recent_data(channel: str, window_seconds: float = 300.0) -> List[Dict[str, Any]]:
    """Get recent data for a specific channel."""
    if channel not in _shared_telemetry_data:
        return []
    
    cutoff = time.time() - window_seconds
    
    with _telemetry_lock:
        return [
            {"timestamp": ts, "value": val}
            for ts, val in _shared_telemetry_data[channel]
            if ts >= cutoff
        ]


def get_channel_list() -> List[str]:
    """Get list of available telemetry channels."""
    return list(_shared_telemetry_data.keys())


def clear_all_data():
    """Clear all telemetry data (for testing)."""
    with _telemetry_lock:
        for buf in _shared_telemetry_data.values():
            buf.clear()


def get_statistics() -> Dict[str, Any]:
    """Get storage statistics."""
    with _telemetry_lock:
        return {
            "channels": {
                ch: {"points": len(buf), "maxlen": buf.maxlen}
                for ch, buf in _shared_telemetry_data.items()
            },
            "sources": get_data_sources()
        }
