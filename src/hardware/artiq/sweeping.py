"""
sweeping.py - Secular frequency sweep orchestrator for ARTIQ.

PHASE 2 REFACTOR: Lightweight orchestrator using focused sub-fragments.

This fragment coordinates:
  - dds_controller: For frequency generation
  - pmt_counter: For photon detection  
  - camera_trigger: For camera synchronization

Changes from Phase 1:
  - Uses sub-fragments instead of direct hardware access
  - Each hardware type is isolated in its own fragment
  - Easier to test, maintain, and reuse
"""

from ndscan.experiment import Fragment, FloatParam, EnumParam
from artiq.experiment import *
from artiq.language.types import TInt32, TFloat
from oitg.units import kHz, ms, MHz

# Import the lightweight sub-fragments
from dds_controller import dds_controller
from pmt_counter import pmt_counter
from camera_trigger import camera_trigger

# dB is not in oitg.units
dB = 1.0


class sweeping(Fragment):
    """
    Sweep orchestrator fragment.
    
    Coordinates DDS, PMT, and Camera for secular frequency sweeps.
    Uses lightweight sub-fragments for hardware control.
    """
    
    def build_fragment(self) -> None:
        """
        Build the sweep orchestrator with sub-fragments.
        
        Sub-fragments:
          - dds_axial: DDS controller for axial frequency (urukul0_ch0)
          - dds_radial: DDS controller for radial frequency (urukul0_ch1)
          - pmt: PMT counter for photon detection
          - cam: Camera trigger for synchronization
        """
        self.setattr_device("core")
        
        # Sub-fragments (lightweight, focused)
        self.setattr_fragment("dds_axial", dds_controller, "urukul0_ch0")
        self.setattr_fragment("dds_radial", dds_controller, "urukul0_ch1")
        self.setattr_fragment("pmt", pmt_counter, "ttl0_counter")
        self.setattr_fragment("cam", camera_trigger, "ttl4")
        
        # Parameters (scannable)
        self.setattr_param("freq", FloatParam, "Frequency",
                          default=400.0 * kHz, unit="kHz")
        self.setattr_param("att", FloatParam, "Attenuation",
                          default=25.0, unit="dB")
        self.setattr_param("on_time", FloatParam, "ON time",
                          default=100.0 * ms, unit="ms")
        self.setattr_param("off_time", FloatParam, "OFF time",
                          default=100.0 * ms, unit="ms")
        
        # DDS selection using EnumParam (ndscan 0.5.x compatible)
        # default=0 means first choice ("axial")
        # choices must be a hashable tuple
        self.setattr_param("dds_choice", EnumParam, "DDS Select",
                          0,                          # Integer index default
                          ("axial", "radial"))        # Tuple of choices
        
        # Runtime state (set in host_setup)
        self.selected_dds = None
    
    def host_setup(self):
        """
        Select which DDS to use based on parameter.
        Called before each scan (host-side, no hardware access).
        """
        # Get returns string "axial" or "radial" based on integer index
        choice = self.dds_choice.get()
        if choice == "axial":
            self.selected_dds = self.dds_axial
        else:
            self.selected_dds = self.dds_radial
    
    @kernel
    def device_setup(self):
        """
        Initialize hardware - called once per scan.
        Delegates to sub-fragments.
        """
        self.core.break_realtime()
        # Initialize only the selected DDS
        self.selected_dds.device_setup()
        self.selected_dds.set_att(self.att.get() * dB)
    
    @kernel
    def sweep_point(self, freq_hz: TFloat, on_ms: TFloat, off_ms: TFloat) -> TInt32:
        """
        Execute a single sweep point.
        
        Args:
            freq_hz: Frequency in Hz
            on_ms: RF on time in milliseconds
            off_ms: RF off time in milliseconds
            
        Returns:
            PMT photon count
        """
        self.core.break_realtime()
        
        # Set frequency
        self.selected_dds.set_frequency(freq_hz)
        
        # Turn on RF and count photons simultaneously
        with parallel:
            self.selected_dds.cfg_sw(True)
            self.pmt.count(on_ms)  # This also delays for on_ms
        
        # Turn off RF
        self.selected_dds.cfg_sw(False)
        
        # Get count and delay for off_time
        counts = self.pmt.pmt.fetch_count()
        delay(off_ms * ms)
        
        return counts
    
    @kernel
    def sweep_point_with_cam(self, freq_hz: TFloat, on_ms: TFloat, off_ms: TFloat) -> TInt32:
        """
        Execute a single sweep point with camera trigger.
        
        Args:
            freq_hz: Frequency in Hz
            on_ms: RF on time in milliseconds
            off_ms: RF off time in milliseconds
            
        Returns:
            PMT photon count
        """
        self.core.break_realtime()
        
        # Set frequency
        self.selected_dds.set_frequency(freq_hz)
        
        # Turn on RF, count photons, and trigger camera simultaneously
        with parallel:
            with sequential:
                self.selected_dds.cfg_sw(True)
                self.pmt.count(on_ms)
            self.cam.trigger(on_ms)
        
        # Turn off RF
        self.selected_dds.cfg_sw(False)
        
        # Get count and delay for off_time
        counts = self.pmt.pmt.fetch_count()
        delay(off_ms * ms)
        
        return counts
    
    @kernel
    def pmt_measure(self, duration_ms: TFloat) -> TInt32:
        """
        Simple PMT measurement without DDS.
        
        Args:
            duration_ms: Measurement duration in milliseconds
            
        Returns:
            PMT photon count
        """
        self.core.break_realtime()
        return self.pmt.count(duration_ms)
    
    # Convenience property for backward compatibility
    @property
    def dds(self):
        """Access the selected DDS device."""
        return self.selected_dds
