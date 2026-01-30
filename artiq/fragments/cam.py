from ndscan.experiment import Fragment
from artiq.experiment import *
from oitg.units import us


class Camera(Fragment):
    """
    Fragment for camera trigger control.
    
    Provides TTL trigger pulses to synchronize camera frame capture
    with ARTIQ experiment timing.
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        # Camera trigger TTL (ttl4 as defined in device_db.py)
        self.setattr_device("camera_trigger")
        
        # Default pulse duration
        self.default_pulse_us = 100.0
    
    @kernel
    def device_setup(self) -> None:
        """Initialize camera trigger device."""
        self.core.break_realtime()
        # No specific initialization needed for TTL output
        
    @kernel
    def trigger(self, pulse_duration_us: TFloat = 100.0) -> None:
        """
        Send TTL pulse to trigger camera.
        
        Args:
            pulse_duration_us: Duration of the trigger pulse in microseconds.
                              Default is 100us (same as orca_quest.py).
        """
        self.core.break_realtime()
        self.camera_trigger.pulse(pulse_duration_us * us)
    
    @kernel
    def trigger_short(self, pulse_duration_us: TFloat = 10.0) -> None:
        """
        Send short TTL pulse to trigger camera.
        
        Args:
            pulse_duration_us: Duration of the trigger pulse in microseconds.
                              Default is 10us (for sweep operations).
        """
        self.core.break_realtime()
        self.camera_trigger.pulse(pulse_duration_us * us)
