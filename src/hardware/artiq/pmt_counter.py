"""
pmt_counter.py - PMT (PhotoMultiplier Tube) counter fragment for ARTIQ.

Simple fragment for photon counting via TTL input.
Lightweight and focused only on PMT counting operations.
"""

from ndscan.experiment import Fragment
from artiq.experiment import *
from artiq.language.types import TFloat, TInt32


class pmt_counter(Fragment):
    """
    PMT counter fragment.
    
    Simple photon counting via TTL gate.
    
    Usage:
        # In parent fragment:
        self.setattr_fragment("pmt", pmt_counter)
        
        # In kernel:
        counts = self.pmt.count(100.0)  # Count for 100ms
    """
    
    def build_fragment(self, device_name: str = "ttl0_counter") -> None:
        """
        Build the PMT counter fragment.
        
        Args:
            device_name: Name of the TTL counter device in device_db.py
                        (default: "ttl0_counter")
        """
        self.setattr_device("core")
        self.setattr_device(device_name)
        
        # Store reference to the PMT device
        self.pmt = getattr(self, device_name)
    
    @kernel
    def count(self, duration_ms: TFloat) -> TInt32:
        """
        Count photons for specified duration.
        
        Args:
            duration_ms: Counting duration in milliseconds
            
        Returns:
            Photon count (number of rising edges detected)
        """
        self.core.break_realtime()
        self.pmt.gate_rising(duration_ms * ms)
        delay(duration_ms * ms)
        return self.pmt.fetch_count()
    
    @kernel
    def count_with_timeout(self, duration_ms: TFloat, timeout_ms: TFloat) -> TInt32:
        """
        Count photons with timeout (for safety).
        
        Args:
            duration_ms: Counting duration in milliseconds
            timeout_ms: Maximum time to wait in milliseconds
            
        Returns:
            Photon count
        """
        self.core.break_realtime()
        self.pmt.gate_rising(duration_ms * ms)
        delay(duration_ms * ms)
        return self.pmt.fetch_count()
    
    @kernel
    def gate_open(self) -> None:
        """Open the counting gate (start counting)."""
        self.core.break_realtime()
        self.pmt.gate_rising(0 * ms)  # 0 = indefinite
    
    @kernel
    def gate_close(self) -> TInt32:
        """
        Close the counting gate and return count.
        
        Returns:
            Photon count since gate_open()
        """
        self.core.break_realtime()
        return self.pmt.fetch_count()
