"""
Shared Telemetry Storage - Multi-Ion Data Support

LabVIEW programs save data directly to E:/Data/
Manager reads these files and populates the shared buffers below.
Flask reads from these buffers for real-time display.

Supports:
    - Single scalar telemetry (pressure, laser_freq, pmt, etc.)
    - Multi-ion data (pos_x, pos_y, sig_x, sig_y for 0-20 ions)

No server/threading here - just shared storage.
"""

import threading
import time
from collections import deque
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field

try:
    from .ion_data_handler import (
        IonParameters, FrameData, MultiIonTelemetry, IonDataManager
    )
    HAS_ION_HANDLER = True
except ImportError:
    HAS_ION_HANDLER = False


# =============================================================================
# CONFIGURATION
# =============================================================================

TELEMETRY_MAX_POINTS = 1000
TELEMETRY_WINDOW_SECONDS = 300

# =============================================================================
# SHARED TELEMETRY BUFFERS (Scalar data)
# =============================================================================

_shared_telemetry_data = {
    # Scalar channels (existing)
    "pressure": deque(maxlen=TELEMETRY_MAX_POINTS),
    "laser_freq": deque(maxlen=TELEMETRY_MAX_POINTS),
    "pmt": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_fitted": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_predicted": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_diff": deque(maxlen=TELEMETRY_MAX_POINTS),
    "secular_snr": deque(maxlen=TELEMETRY_MAX_POINTS),
    
    # Multi-ion channels (new) - aggregated statistics
    # These store overall trap statistics, not individual ions
    "ion_count": deque(maxlen=TELEMETRY_MAX_POINTS),      # Number of ions detected
    "avg_pos_x": deque(maxlen=TELEMETRY_MAX_POINTS),      # Average X position
    "avg_pos_y": deque(maxlen=TELEMETRY_MAX_POINTS),      # Average Y position
    "avg_sig_x": deque(maxlen=TELEMETRY_MAX_POINTS),      # Average sigma X
    "avg_sig_y": deque(maxlen=TELEMETRY_MAX_POINTS),      # Average sigma Y
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
# MULTI-ION DATA (Per-ion storage)
# =============================================================================

# Initialize multi-ion telemetry buffer
_multi_ion_telemetry = None  # type: Optional[Any]
if HAS_ION_HANDLER:
    _multi_ion_telemetry = MultiIonTelemetry(max_frames=TELEMETRY_MAX_POINTS)

_multi_ion_lock = threading.RLock()


@dataclass
class IonSnapshot:
    """Lightweight snapshot of ion data for real-time display."""
    timestamp: float
    frame_id: str
    ion_count: int
    # Per-ion data stored as parallel arrays for efficiency
    ion_ids: List[int] = field(default_factory=list)
    pos_x_list: List[float] = field(default_factory=list)
    pos_y_list: List[float] = field(default_factory=list)
    sig_x_list: List[float] = field(default_factory=list)
    sig_y_list: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/Flask."""
        return {
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "ion_count": self.ion_count,
            "ions": [
                {
                    "ion_id": self.ion_ids[i],
                    "pos_x": self.pos_x_list[i],
                    "pos_y": self.pos_y_list[i],
                    "sig_x": self.sig_x_list[i],
                    "sig_y": self.sig_y_list[i],
                }
                for i in range(self.ion_count)
            ]
        }
    
    @classmethod
    def from_frame_data(cls, frame: 'FrameData') -> "IonSnapshot":
        """Create snapshot from FrameData."""
        return cls(
            timestamp=frame.timestamp,
            frame_id=frame.frame_id,
            ion_count=frame.ion_count,
            ion_ids=[ion.ion_id for ion in frame.ions],
            pos_x_list=[ion.pos_x for ion in frame.ions],
            pos_y_list=[ion.pos_y for ion in frame.ions],
            sig_x_list=[ion.sig_x for ion in frame.ions],
            sig_y_list=[ion.sig_y for ion in frame.ions],
        )


# Simple circular buffer for latest ion snapshots
_ion_snapshots: deque = deque(maxlen=TELEMETRY_MAX_POINTS)


def store_multi_ion_frame(frame_data: Dict[str, Any]):
    """
    Store multi-ion frame data from camera/image handler.
    
    Args:
        frame_data: Dictionary with keys:
            - timestamp: float
            - frame_id: str
            - ion_count: int
            - ions: List[Dict] with pos_x, pos_y, sig_x, sig_y
    """
    timestamp = frame_data.get("timestamp", time.time())
    ion_count = frame_data.get("ion_count", 0)
    
    with _telemetry_lock:
        # Store ion count
        _shared_telemetry_data["ion_count"].append((timestamp, ion_count))
        
        # Calculate and store averages
        if ion_count > 0:
            ions = frame_data.get("ions", [])
            avg_pos_x = sum(i.get("pos_x", 0) for i in ions) / ion_count
            avg_pos_y = sum(i.get("pos_y", 0) for i in ions) / ion_count
            avg_sig_x = sum(i.get("sig_x", 0) for i in ions) / ion_count
            avg_sig_y = sum(i.get("sig_y", 0) for i in ions) / ion_count
            
            _shared_telemetry_data["avg_pos_x"].append((timestamp, avg_pos_x))
            _shared_telemetry_data["avg_pos_y"].append((timestamp, avg_pos_y))
            _shared_telemetry_data["avg_sig_x"].append((timestamp, avg_sig_x))
            _shared_telemetry_data["avg_sig_y"].append((timestamp, avg_sig_y))
        else:
            # Store NaN for empty trap
            _shared_telemetry_data["avg_pos_x"].append((timestamp, float('nan')))
            _shared_telemetry_data["avg_pos_y"].append((timestamp, float('nan')))
            _shared_telemetry_data["avg_sig_x"].append((timestamp, float('nan')))
            _shared_telemetry_data["avg_sig_y"].append((timestamp, float('nan')))
    
    # Store detailed per-ion data
    with _multi_ion_lock:
        snapshot = IonSnapshot(
            timestamp=timestamp,
            frame_id=frame_data.get("frame_id", ""),
            ion_count=ion_count,
            ion_ids=[i.get("ion_id", idx) for idx, i in enumerate(frame_data.get("ions", []))],
            pos_x_list=[i.get("pos_x", 0) for i in frame_data.get("ions", [])],
            pos_y_list=[i.get("pos_y", 0) for i in frame_data.get("ions", [])],
            sig_x_list=[i.get("sig_x", 0) for i in frame_data.get("ions", [])],
            sig_y_list=[i.get("sig_y", 0) for i in frame_data.get("ions", [])],
        )
        _ion_snapshots.append(snapshot)
        
        # Also add to new handler if available
        if HAS_ION_HANDLER and _multi_ion_telemetry:
            try:
                frame = FrameData.from_dict(frame_data)
                _multi_ion_telemetry.add_frame(frame)
            except Exception:
                pass  # Graceful fallback


def get_latest_ion_snapshot() -> Optional[IonSnapshot]:
    """Get the most recent ion snapshot."""
    with _multi_ion_lock:
        return _ion_snapshots[-1] if _ion_snapshots else None


def get_ion_trajectory(ion_id: int, param: str, 
                       window_seconds: float = 300.0) -> List[Tuple[float, float]]:
    """
    Get time-series trajectory for a specific ion parameter.
    
    Args:
        ion_id: Index of ion (0-19)
        param: One of 'pos_x', 'pos_y', 'sig_x', 'sig_y'
        window_seconds: Time window to retrieve
    
    Returns:
        List of (timestamp, value) tuples
    """
    cutoff = time.time() - window_seconds
    
    with _multi_ion_lock:
        if HAS_ION_HANDLER and _multi_ion_telemetry:
            # Use new handler if available
            return _multi_ion_telemetry.get_ion_trajectory(ion_id, param, window_seconds)
        
        # Fallback: scan through snapshots
        trajectory = []
        for snapshot in _ion_snapshots:
            if snapshot.timestamp < cutoff:
                continue
            
            # Find ion_id in this snapshot
            try:
                idx = snapshot.ion_ids.index(ion_id)
                if param == 'pos_x':
                    value = snapshot.pos_x_list[idx]
                elif param == 'pos_y':
                    value = snapshot.pos_y_list[idx]
                elif param == 'sig_x':
                    value = snapshot.sig_x_list[idx]
                elif param == 'sig_y':
                    value = snapshot.sig_y_list[idx]
                else:
                    continue
                trajectory.append((snapshot.timestamp, value))
            except (ValueError, IndexError):
                # Ion not present in this frame
                continue
        
        return trajectory


def get_all_ion_trajectories(param: str,
                              window_seconds: float = 300.0) -> Dict[int, List[Tuple[float, float]]]:
    """
    Get trajectories for ALL ions at once.
    More efficient than calling get_ion_trajectory multiple times.
    
    Returns:
        Dict mapping ion_id -> list of (timestamp, value)
    """
    cutoff = time.time() - window_seconds
    trajectories: Dict[int, List[Tuple[float, float]]] = {}
    
    param_map = {
        'pos_x': lambda s, idx: s.pos_x_list[idx],
        'pos_y': lambda s, idx: s.pos_y_list[idx],
        'sig_x': lambda s, idx: s.sig_x_list[idx],
        'sig_y': lambda s, idx: s.sig_y_list[idx],
    }
    
    if param not in param_map:
        return trajectories
    
    getter = param_map[param]
    
    with _multi_ion_lock:
        for snapshot in _ion_snapshots:
            if snapshot.timestamp < cutoff:
                continue
            
            for idx, ion_id in enumerate(snapshot.ion_ids):
                try:
                    value = getter(snapshot, idx)
                    if ion_id not in trajectories:
                        trajectories[ion_id] = []
                    trajectories[ion_id].append((snapshot.timestamp, value))
                except IndexError:
                    continue
    
    return trajectories


# =============================================================================
# LEGACY SCALAR API (For backward compatibility)
# =============================================================================

def get_telemetry_data():
    """Get reference to shared scalar telemetry data (for flask_server)."""
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
    """Store a single scalar data point (called by Manager after reading files)."""
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
    """Get recent scalar data for a specific channel."""
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
    
    with _multi_ion_lock:
        _ion_snapshots.clear()
        if _multi_ion_telemetry:
            _multi_ion_telemetry.frames.clear()


def get_statistics() -> Dict[str, Any]:
    """Get storage statistics."""
    with _telemetry_lock:
        scalar_stats = {
            ch: {"points": len(buf), "maxlen": buf.maxlen}
            for ch, buf in _shared_telemetry_data.items()
        }
    
    with _multi_ion_lock:
        multi_stats = {
            "ion_snapshots": len(_ion_snapshots),
            "max_snapshots": _ion_snapshots.maxlen,
        }
        if _multi_ion_telemetry:
            multi_stats.update(_multi_ion_telemetry.get_summary())
    
    return {
        "scalar_channels": scalar_stats,
        "multi_ion": multi_stats,
        "sources": get_data_sources()
    }


# =============================================================================
# FLASK API HELPERS
# =============================================================================

def get_flask_telemetry_packet() -> Dict[str, Any]:
    """
    Get complete telemetry packet for Flask SSE stream.
    Includes both scalar and multi-ion data.
    """
    now = time.time()
    cutoff = now - TELEMETRY_WINDOW_SECONDS
    
    packet = {"timestamp": now}
    
    # Scalar data
    with _telemetry_lock:
        for channel, buf in _shared_telemetry_data.items():
            points = [{"t": ts, "v": val} for ts, val in buf if ts >= cutoff]
            if points:
                packet[channel] = points
    
    # Multi-ion data - latest snapshot
    with _multi_ion_lock:
        latest = get_latest_ion_snapshot()
        if latest:
            packet["ions"] = latest.to_dict()
        
        # Per-ion trajectories (last 60 seconds only to save bandwidth)
        recent_cutoff = now - 60.0
        ion_trajs = {}
        for snapshot in _ion_snapshots:
            if snapshot.timestamp < recent_cutoff:
                continue
            for idx, ion_id in enumerate(snapshot.ion_ids):
                if ion_id not in ion_trajs:
                    ion_trajs[ion_id] = {"pos_x": [], "pos_y": [], "sig_x": [], "sig_y": []}
                ion_trajs[ion_id]["pos_x"].append({"t": snapshot.timestamp, "v": snapshot.pos_x_list[idx]})
                ion_trajs[ion_id]["pos_y"].append({"t": snapshot.timestamp, "v": snapshot.pos_y_list[idx]})
                ion_trajs[ion_id]["sig_x"].append({"t": snapshot.timestamp, "v": snapshot.sig_x_list[idx]})
                ion_trajs[ion_id]["sig_y"].append({"t": snapshot.timestamp, "v": snapshot.sig_y_list[idx]})
        
        if ion_trajs:
            packet["ion_trajectories"] = ion_trajs
    
    return packet
