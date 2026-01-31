"""
Multi-Ion Data Handler - Efficient storage for variable ion count data

Data Model:
    - Frame: Single camera capture with timestamp
    - Ion: Individual ion with pos_x, pos_y, sig_x, sig_y
    - Trap: Contains 0-20 ions per frame

Storage Strategy:
    1. Real-time: In-memory buffers (fast display)
    2. Short-term: Apache Parquet (efficient analytics)
    3. Long-term: HDF5 (compressed, research-grade)

Recommended Formats:
    - HDF5: Best for numerical arrays, compression, attributes
    - Parquet: Best for columnar queries, pandas integration
    - MessagePack: Best for real-time streaming (ZMQ/WebSocket)
"""

import numpy as np
import json
import time
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple, Union
from datetime import datetime
from pathlib import Path
import pandas as pd
import logging

# Optional dependencies - gracefully degrade if not available
try:
    import h5py
    HAS_H5PY = True
except ImportError:
    HAS_H5PY = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class IonParameters:
    """Single ion parameters - 32 bytes per ion."""
    ion_id: int          # Ion index in frame (0-19)
    pos_x: float         # X position (pixels)
    pos_y: float         # Y position (pixels)
    sig_x: float         # Gaussian sigma X
    sig_y: float         # SHM turning point Y
    
    def to_array(self) -> np.ndarray:
        """Convert to compact numpy array for storage."""
        return np.array([self.ion_id, self.pos_x, self.pos_y, self.sig_x, self.sig_y], 
                       dtype=np.float32)
    
    @classmethod
    def from_array(cls, arr: np.ndarray) -> "IonParameters":
        """Create from numpy array."""
        return cls(
            ion_id=int(arr[0]),
            pos_x=float(arr[1]),
            pos_y=float(arr[2]),
            sig_x=float(arr[3]),
            sig_y=float(arr[4])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/MsgPack."""
        return asdict(self)


@dataclass
class FrameData:
    """Single frame with variable number of ions."""
    timestamp: float                    # Unix timestamp (seconds)
    frame_id: str                       # Unique frame identifier
    ion_count: int                      # Number of ions (0-20)
    ions: List[IonParameters] = field(default_factory=list)
    
    # Optional metadata
    temperature: Optional[float] = None
    pressure: Optional[float] = None
    laser_freq: Optional[float] = None
    pmt_signal: Optional[float] = None
    
    def validate(self) -> bool:
        """Validate frame data."""
        if self.ion_count != len(self.ions):
            return False
        if self.ion_count > 20:
            return False
        return True
    
    def to_compact_array(self) -> np.ndarray:
        """
        Convert to compact 2D numpy array for efficient storage.
        Shape: (ion_count, 5) where columns are [ion_id, pos_x, pos_y, sig_x, sig_y]
        """
        if self.ion_count == 0:
            return np.zeros((0, 5), dtype=np.float32)
        return np.array([ion.to_array() for ion in self.ions], dtype=np.float32)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "ion_count": self.ion_count,
            "ions": [ion.to_dict() for ion in self.ions],
            "temperature": self.temperature,
            "pressure": self.pressure,
            "laser_freq": self.laser_freq,
            "pmt_signal": self.pmt_signal,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FrameData":
        """Create from dictionary."""
        ions = [IonParameters(**ion_data) for ion_data in data.get("ions", [])]
        return cls(
            timestamp=data["timestamp"],
            frame_id=data["frame_id"],
            ion_count=data.get("ion_count", len(ions)),
            ions=ions,
            temperature=data.get("temperature"),
            pressure=data.get("pressure"),
            laser_freq=data.get("laser_freq"),
            pmt_signal=data.get("pmt_signal"),
        )
    
    def to_msgpack(self) -> bytes:
        """Serialize to MessagePack (most efficient for streaming)."""
        if HAS_MSGPACK:
            return msgpack.packb(self.to_dict(), use_bin_type=True)
        else:
            # Fallback to JSON
            return json.dumps(self.to_dict()).encode('utf-8')
    
    @classmethod
    def from_msgpack(cls, data: bytes) -> "FrameData":
        """Deserialize from MessagePack."""
        if HAS_MSGPACK:
            return cls.from_dict(msgpack.unpackb(data, raw=False))
        else:
            return cls.from_dict(json.loads(data.decode('utf-8')))


# =============================================================================
# STORAGE FORMATS
# =============================================================================

class HDF5Storage:
    """
    HDF5 storage for long-term archival.
    
    Advantages:
        - Binary compression (blosc, gzip)
        - Chunked storage for fast random access
        - Hierarchical organization
        - Standard in scientific computing
    
    File Structure:
        /frames/timestamps     (N,) float64
        /frames/ion_counts     (N,) uint8
        /frames/ion_data       (N, 20, 5) float32  # [frame, ion, params]
        /metadata/attributes   # frame_id, etc.
    """
    
    def __init__(self, filepath: str, compression: str = 'gzip'):
        if not HAS_H5PY:
            raise ImportError("h5py required. Install: pip install h5py")
        
        self.filepath = Path(filepath)
        self.compression = compression
        self._lock = threading.Lock()
        
        # Create file if not exists
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_structure()
    
    def _ensure_structure(self):
        """Initialize HDF5 structure."""
        with h5py.File(self.filepath, 'a') as f:
            if 'frames' not in f:
                frames = f.create_group('frames')
                # Create extendable datasets
                max_frames = None  # Unlimited
                
                # Timestamps
                frames.create_dataset(
                    'timestamps', shape=(0,), maxshape=(max_frames,),
                    dtype='float64', compression=self.compression,
                    chunks=True
                )
                
                # Ion counts per frame
                frames.create_dataset(
                    'ion_counts', shape=(0,), maxshape=(max_frames,),
                    dtype='uint8', compression=self.compression,
                    chunks=True
                )
                
                # Ion data: (frame, max_ions, params)
                # params: [ion_id, pos_x, pos_y, sig_x, sig_y]
                frames.create_dataset(
                    'ion_data', shape=(0, 20, 5), maxshape=(max_frames, 20, 5),
                    dtype='float32', compression=self.compression,
                    chunks=(100, 20, 5), fillvalue=0
                )
                
                # Frame IDs stored as variable-length strings
                frames.create_dataset(
                    'frame_ids', shape=(0,), maxshape=(max_frames,),
                    dtype=h5py.string_dtype(), chunks=True
                )
    
    def append_frame(self, frame: FrameData):
        """Append a single frame to HDF5."""
        with self._lock:
            with h5py.File(self.filepath, 'a') as f:
                frames = f['frames']
                n = frames['timestamps'].shape[0]
                
                # Resize datasets
                frames['timestamps'].resize((n + 1,))
                frames['ion_counts'].resize((n + 1,))
                frames['ion_data'].resize((n + 1, 20, 5))
                frames['frame_ids'].resize((n + 1,))
                
                # Write data
                frames['timestamps'][n] = frame.timestamp
                frames['ion_counts'][n] = frame.ion_count
                frames['frame_ids'][n] = frame.frame_id
                
                # Write ion data (pad with zeros if < 20 ions)
                ion_array = frame.to_compact_array()
                padded = np.zeros((20, 5), dtype=np.float32)
                padded[:frame.ion_count, :] = ion_array
                frames['ion_data'][n, :, :] = padded
    
    def get_frame(self, index: int) -> FrameData:
        """Retrieve a single frame by index."""
        with h5py.File(self.filepath, 'r') as f:
            frames = f['frames']
            
            timestamp = float(frames['timestamps'][index])
            ion_count = int(frames['ion_counts'][index])
            frame_id = str(frames['frame_ids'][index])
            ion_data = frames['ion_data'][index, :ion_count, :]
            
            ions = [IonParameters.from_array(ion_data[i]) for i in range(ion_count)]
            
            return FrameData(
                timestamp=timestamp,
                frame_id=frame_id,
                ion_count=ion_count,
                ions=ions
            )
    
    def get_time_range(self, start_time: float, end_time: float) -> List[FrameData]:
        """Get all frames within a time range."""
        frames = []
        with h5py.File(self.filepath, 'r') as f:
            timestamps = f['frames']['timestamps'][:]
            mask = (timestamps >= start_time) & (timestamps <= end_time)
            indices = np.where(mask)[0]
            
            for idx in indices:
                frames.append(self.get_frame(int(idx)))
        
        return frames


class ParquetStorage:
    """
    Parquet storage for analytics and pandas integration.
    
    Advantages:
        - Columnar compression (very efficient)
        - Fast queries on subsets
        - Native pandas support
        - Good for time-series analysis
    
    Schema (flattened):
        timestamp | frame_id | ion_id | pos_x | pos_y | sig_x | sig_y
    
    One row per ion (multiple rows per frame with same timestamp)
    """
    
    def __init__(self, directory: str):
        if not HAS_PANDAS:
            raise ImportError("pandas required. Install: pip install pandas")
        if not HAS_PYARROW:
            raise ImportError("pyarrow required. Install: pip install pyarrow")
        
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._buffer: List[Dict] = []
        self._buffer_lock = threading.Lock()
        self._buffer_size = 1000  # Flush every N frames
    
    def append_frame(self, frame: FrameData):
        """Append frame to buffer (flushes automatically)."""
        rows = []
        base_data = {
            'timestamp': frame.timestamp,
            'frame_id': frame.frame_id,
            'ion_count': frame.ion_count,
        }
        
        if frame.ion_count == 0:
            # Still record frame even with no ions
            rows.append({**base_data, 'ion_id': -1, 'pos_x': np.nan, 
                        'pos_y': np.nan, 'sig_x': np.nan, 'sig_y': np.nan})
        else:
            for ion in frame.ions:
                rows.append({
                    **base_data,
                    'ion_id': ion.ion_id,
                    'pos_x': ion.pos_x,
                    'pos_y': ion.pos_y,
                    'sig_x': ion.sig_x,
                    'sig_y': ion.sig_y,
                })
        
        with self._buffer_lock:
            self._buffer.extend(rows)
            
            if len(self._buffer) >= self._buffer_size:
                self._flush()
    
    def _flush(self):
        """Write buffered data to Parquet file."""
        if not self._buffer:
            return
        
        df = pd.DataFrame(self._buffer)
        
        # Create filename based on timestamp
        now = datetime.now()
        filename = f"ion_data_{now.strftime('%Y%m%d_%H%M%S')}.parquet"
        filepath = self.directory / filename
        
        # Write with compression
        table = pa.Table.from_pandas(df)
        pq.write_table(table, filepath, compression='zstd')
        
        # Clear buffer
        self._buffer = []
        
        logging.info(f"Flushed {len(df)} rows to {filepath}")
    
    def read_all(self) -> pd.DataFrame:
        """Read all Parquet files into a single DataFrame."""
        files = list(self.directory.glob("*.parquet"))
        if not files:
            return pd.DataFrame()
        
        dfs = [pd.read_parquet(f) for f in files]
        return pd.concat(dfs, ignore_index=True)
    
    def query_time_range(self, start: float, end: float) -> pd.DataFrame:
        """Query data within time range using Parquet filtering."""
        df = self.read_all()
        return df[(df['timestamp'] >= start) & (df['timestamp'] <= end)]


# =============================================================================
# REAL-TIME BUFFERS (For Flask Display)
# =============================================================================

class MultiIonTelemetry:
    """
    Thread-safe circular buffers for real-time multi-ion telemetry.
    Optimized for the Flask display showing scatter plots.
    """
    
    def __init__(self, max_frames: int = 1000):
        self.max_frames = max_frames
        self._lock = threading.RLock()
        
        # Store frames as list of FrameData
        self.frames: deque = deque(maxlen=max_frames)
        
        # Per-ion circular buffers for individual parameter tracking
        # Structure: {ion_id: {param_name: deque}}
        self.ion_buffers: Dict[int, Dict[str, deque]] = {}
        
        # Pre-initialize buffers for max 20 ions
        for ion_id in range(20):
            self.ion_buffers[ion_id] = {
                'pos_x': deque(maxlen=max_frames),
                'pos_y': deque(maxlen=max_frames),
                'sig_x': deque(maxlen=max_frames),
                'sig_y': deque(maxlen=max_frames),
            }
    
    def add_frame(self, frame: FrameData):
        """Add a new frame and update all buffers."""
        with self._lock:
            self.frames.append(frame)
            
            # Update per-ion parameter buffers
            for ion in frame.ions:
                ion_id = ion.ion_id
                if ion_id < 20:  # Safety check
                    self.ion_buffers[ion_id]['pos_x'].append((frame.timestamp, ion.pos_x))
                    self.ion_buffers[ion_id]['pos_y'].append((frame.timestamp, ion.pos_y))
                    self.ion_buffers[ion_id]['sig_x'].append((frame.timestamp, ion.sig_x))
                    self.ion_buffers[ion_id]['sig_y'].append((frame.timestamp, ion.sig_y))
    
    def get_ion_trajectory(self, ion_id: int, param: str, 
                           window_seconds: float = 300.0) -> List[Tuple[float, float]]:
        """Get time-series data for a specific ion parameter."""
        cutoff = time.time() - window_seconds
        
        with self._lock:
            if ion_id not in self.ion_buffers:
                return []
            
            buffer = self.ion_buffers[ion_id].get(param, deque())
            return [(ts, val) for ts, val in buffer if ts >= cutoff]
    
    def get_all_ions_latest(self) -> List[IonParameters]:
        """Get the most recent frame's ion data."""
        with self._lock:
            if not self.frames:
                return []
            return self.frames[-1].ions
    
    def get_summary(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        with self._lock:
            return {
                'total_frames': len(self.frames),
                'max_frames': self.max_frames,
                'latest_frame_time': self.frames[-1].timestamp if self.frames else None,
                'ion_counts': [f.ion_count for f in list(self.frames)[-10:]],  # Last 10
            }


# =============================================================================
# UNIFIED DATA MANAGER
# =============================================================================

class IonDataManager:
    """
    Unified manager that coordinates real-time buffers, Parquet, and HDF5 storage.
    
    Usage:
        manager = IonDataManager(data_dir="E:/Data/ion_tracking")
        
        # From camera processing
        frame = FrameData(
            timestamp=time.time(),
            frame_id="frame_001",
            ion_count=3,
            ions=[IonParameters(0, 100.5, 200.3, 2.1, 3.4), ...]
        )
        
        manager.ingest(frame)
    """
    
    def __init__(self, data_dir: str, enable_hdf5: bool = True, enable_parquet: bool = True):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger("ion_data")
        
        # Real-time buffers for Flask
        self.telemetry = MultiIonTelemetry(max_frames=1000)
        
        # Persistent storage
        self.hdf5: Optional[HDF5Storage] = None
        self.parquet: Optional[ParquetStorage] = None
        
        if enable_hdf5 and HAS_H5PY:
            hdf5_path = self.data_dir / "ion_archive.h5"
            self.hdf5 = HDF5Storage(str(hdf5_path))
            self.logger.info(f"HDF5 storage: {hdf5_path}")
        
        if enable_parquet and HAS_PANDAS and HAS_PYARROW:
            parquet_dir = self.data_dir / "parquet"
            self.parquet = ParquetStorage(str(parquet_dir))
            self.logger.info(f"Parquet storage: {parquet_dir}")
    
    def ingest(self, frame: FrameData):
        """Ingest a frame into all enabled storage backends."""
        if not frame.validate():
            self.logger.warning(f"Invalid frame data: {frame.frame_id}")
            return
        
        # Always update real-time buffers
        self.telemetry.add_frame(frame)
        
        # Async storage (could be threaded for performance)
        if self.hdf5:
            try:
                self.hdf5.append_frame(frame)
            except Exception as e:
                self.logger.error(f"HDF5 write failed: {e}")
        
        if self.parquet:
            try:
                self.parquet.append_frame(frame)
            except Exception as e:
                self.logger.error(f"Parquet write failed: {e}")
    
    def get_current_frame(self) -> Optional[FrameData]:
        """Get the most recent frame (for Flask display)."""
        frames = self.telemetry.frames
        return frames[-1] if frames else None
    
    def get_ion_trajectory(self, ion_id: int, param: str, 
                          window_seconds: float = 300.0) -> List[Tuple[float, float]]:
        """Get trajectory data for plotting."""
        return self.telemetry.get_ion_trajectory(ion_id, param, window_seconds)
    
    def export_to_json(self, frame: FrameData) -> str:
        """Export frame to JSON string (for web API)."""
        return json.dumps(frame.to_dict())
    
    def close(self):
        """Flush buffers and close storage."""
        if self.parquet:
            self.parquet._flush()


# =============================================================================
# MESSAGEPACK SERIALIZATION (For ZMQ/Network)
# =============================================================================

def serialize_frame_compact(frame: FrameData) -> bytes:
    """
    Most compact serialization for network transmission.
    Uses MessagePack if available, falls back to JSON.
    """
    return frame.to_msgpack()


def deserialize_frame_compact(data: bytes) -> FrameData:
    """Deserialize from MessagePack or JSON."""
    return FrameData.from_msgpack(data)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Demo: Create sample multi-ion data
    
    print("=" * 60)
    print("Multi-Ion Data Handler Demo")
    print("=" * 60)
    
    # Create manager
    manager = IonDataManager("./demo_data", enable_hdf5=True, enable_parquet=True)
    
    # Simulate 100 frames with varying ion counts
    for i in range(100):
        # Random ion count 0-5
        ion_count = np.random.randint(0, 6)
        
        ions = []
        for j in range(ion_count):
            ions.append(IonParameters(
                ion_id=j,
                pos_x=320 + 50 * np.sin(i * 0.1 + j),
                pos_y=240 + 30 * np.cos(i * 0.15 + j),
                sig_x=2.0 + 0.5 * np.random.randn(),
                sig_y=3.0 + 0.8 * np.random.randn(),
            ))
        
        frame = FrameData(
            timestamp=time.time() + i * 0.1,
            frame_id=f"frame_{i:04d}",
            ion_count=ion_count,
            ions=ions
        )
        
        manager.ingest(frame)
    
    print(f"\nStored {len(manager.telemetry.frames)} frames")
    print(f"Buffer summary: {manager.telemetry.get_summary()}")
    
    # Get trajectory for ion 0
    traj = manager.get_ion_trajectory(0, 'pos_x', window_seconds=1000)
    print(f"\nIon 0 pos_x trajectory: {len(traj)} points")
    
    # Cleanup
    manager.close()
    print("\nDone!")
