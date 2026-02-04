"""
camera_trigger.py - Camera trigger control fragment for ARTIQ.

Simple fragment for triggering Hamamatsu camera via TTL output.
Lightweight and focused only on camera trigger operations.
"""

from ndscan.experiment import Fragment
from artiq.experiment import *
from artiq.language.types import TFloat, TInt32


class camera_trigger(Fragment):
    """
    Camera trigger fragment.
    
    Controls TTL output for triggering Hamamatsu ORCA camera.
    
    Usage:
        # In parent fragment:
        self.setattr_fragment("cam", camera_trigger)
        
        # In kernel:
        self.cam.trigger(10.0)  # 10ms trigger pulse
    """
    
    def build_fragment(self, device_name: str = "ttl4") -> None:
        """
        Build the camera trigger fragment.
        
        Args:
            device_name: Name of the TTL device in device_db.py
                        (default: "ttl4")
        """
        self.setattr_device("core")
        self.setattr_device(device_name)
        
        # Store reference to the TTL device
        self.ttl = getattr(self, device_name)
    
    @kernel
    def trigger(self, duration_ms: TFloat) -> None:
        """
        Send a single trigger pulse to camera.
        
        Args:
            duration_ms: Pulse duration in milliseconds
        """
        self.core.break_realtime()
        self.ttl.pulse(duration_ms * ms)
    
    @kernel
    def trigger_us(self, duration_us: TFloat) -> None:
        """
        Send a single trigger pulse to camera (microseconds).
        
        Args:
            duration_us: Pulse duration in microseconds
        """
        self.core.break_realtime()
        self.ttl.pulse(duration_us * us)
    
    @kernel
    def on(self) -> None:
        """Set trigger output high (continuous trigger)."""
        self.core.break_realtime()
        self.ttl.on()
    
    @kernel
    def off(self) -> None:
        """Set trigger output low."""
        self.core.break_realtime()
        self.ttl.off()
    
    @kernel
    def trigger_multiple(self, n_triggers: TInt32, delay_ms: TFloat, pulse_ms: TFloat) -> None:
        """
        Send multiple trigger pulses.
        
        Args:
            n_triggers: Number of trigger pulses
            delay_ms: Delay between pulses in milliseconds
            pulse_ms: Duration of each pulse in milliseconds
        """
        self.core.break_realtime()
        for i in range(n_triggers):
            self.ttl.pulse(pulse_ms * ms)
            delay(delay_ms * ms)
