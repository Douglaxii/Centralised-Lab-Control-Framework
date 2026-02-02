"""
Camera Fragment - Advanced camera control for ARTIQ experiments.

Provides:
- TTL trigger pulses for frame synchronization
- HTTP-based camera control (start/stop infinity mode)
- Settings configuration
- Integration with MLS camera server

This fragment replicates and extends the functionality from:
- artiq/artiq-master/repository/Camera/orca_quest.py (Cam class)
- artiq/artiq-master/repository/Camera/auto_cam.py (AutoCam class)

Architecture:
- Hardware trigger: TTL pulses via camera_trigger device
- Software control: HTTP requests to Flask/camera server
"""

from ndscan.experiment import Fragment, FloatParam, IntParam, BoolParam
from artiq.experiment import *
from oitg.units import us, ms
import requests
import json
import time


class Camera(Fragment):
    """
    Fragment for comprehensive camera control.
    
    Combines hardware TTL triggering with HTTP-based camera control,
    similar to the Cam class in orca_quest.py.
    
    Features:
    - TTL trigger pulses for frame synchronization
    - Start/stop infinity mode recording
    - Camera settings configuration
    - Image analysis control
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        # Camera trigger TTL (ttl4 as defined in device_db.py)
        self.setattr_device("camera_trigger")
        
        # HTTP configuration for camera control
        # Default to localhost Flask server
        self.base_url = "http://127.0.0.1:5000"
        self.camera_server_host = "127.0.0.1"
        self.camera_server_port = 5558
        
        # Default pulse duration
        self.default_pulse_us = 100.0
        
        # State tracking
        self.is_recording = False
        
        # Route definitions (matching orca_quest.py structure)
        self._update_routes()
    
    def _update_routes(self):
        """Update URL routes based on current base_url."""
        base = self.base_url.rstrip("/")
        self.routes = {
            "start": f"{base}/start_camera",
            "stop": f"{base}/stop_camera",
            "inf": f"{base}/start_camera_inf",
            "save_settings": f"{base}/save_camera_settings",
            "set_analysis": f"{base}/set_live_analysis_params",
            "start_analysis": f"{base}/start_live_analysis",
            "stop_analysis": f"{base}/stop_live_analysis",
            "save_analysis": f"{base}/save_live_analysis",
            "clear_analysis": f"{base}/clear_live_analysis",
        }
    
    def set_server_url(self, url: str):
        """
        Set the Flask server URL for camera control.
        
        Args:
            url: Base URL of the Flask server (e.g., "http://127.0.0.1:5000")
        """
        self.base_url = url
        self._update_routes()
    
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
    
    @kernel
    def trigger_multiple(self, n_triggers: TInt, delay_ms: TFloat, 
                         pulse_duration_us: TFloat = 100.0) -> None:
        """
        Send multiple TTL trigger pulses.
        
        Args:
            n_triggers: Number of trigger pulses to send
            delay_ms: Delay between pulses in milliseconds
            pulse_duration_us: Duration of each pulse in microseconds
        """
        self.core.break_realtime()
        for i in range(n_triggers):
            self.camera_trigger.pulse(pulse_duration_us * us)
            delay(delay_ms * ms)
    
    # ========================================================================
    # Host-side HTTP control (runs on host computer, not on ARTIQ core)
    # ========================================================================
    
    @rpc
    def start_cam_inf(self) -> bool:
        """
        Start camera in infinite capture mode.
        
        Replicates orca_quest.py start_cam_inf() method.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.get(self.routes["inf"], timeout=5)
            print(f"Camera start_inf response: {response.text}")
            self.is_recording = True
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error starting camera infinity mode: {e}")
            return False
    
    @rpc
    def start_cam_recording(self) -> bool:
        """
        Start camera in single recording mode (DCIMG + JPG).
        
        Replicates orca_quest.py start_cam_recording() method.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.get(self.routes["start"], timeout=5)
            print(f"Camera start response: {response.text}")
            self.is_recording = True
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error starting camera recording: {e}")
            return False
    
    @rpc
    def stop_cam(self) -> bool:
        """
        Stop camera recording.
        
        Replicates orca_quest.py stop_cam() method.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.get(self.routes["stop"], timeout=5)
            print(f"Camera stop response: {response.text}")
            self.is_recording = False
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error stopping camera: {e}")
            return False
    
    @rpc
    def send_cam_settings(self, n_frames: int, exposure_time_ms: float, 
                          trigger_mode: str = "extern") -> bool:
        """
        Send camera settings to the server.
        
        Replicates orca_quest.py send_cam_settings() method.
        
        Args:
            n_frames: Maximum number of frames to capture
            exposure_time_ms: Exposure time in milliseconds
            trigger_mode: "extern" or "software"
            
        Returns:
            True if successful, False otherwise
        """
        data = {
            "max_frames": int(n_frames),
            "exposure": exposure_time_ms,
            "trigger_mode": trigger_mode
        }
        
        try:
            response = requests.post(
                self.routes["save_settings"], 
                json=data, 
                timeout=5
            )
            print(f"Camera settings response: {response.status_code}")
            print(f"Response: {response.text}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error sending camera settings: {e}")
            return False
    
    @rpc
    def set_analysis_params(self, xstart: int, xfinish: int, 
                           ystart: int, yfinish: int, radius: int) -> bool:
        """
        Set image analysis parameters.
        
        Replicates orca_quest.py set_analysis() method.
        
        Args:
            xstart: ROI x start
            xfinish: ROI x finish
            ystart: ROI y start
            yfinish: ROI y finish
            radius: Low-pass filter radius
            
        Returns:
            True if successful, False otherwise
        """
        settings = {
            "xstart": int(xstart),
            "xfinish": int(xfinish),
            "ystart": int(ystart),
            "yfinish": int(yfinish),
            "radius": int(radius)
        }
        
        try:
            response = requests.post(
                self.routes["set_analysis"],
                json=settings,
                timeout=5
            )
            print(f"Analysis settings response: {response.text}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error setting analysis params: {e}")
            return False
    
    @rpc
    def start_analysis(self) -> bool:
        """
        Start live image analysis.
        
        Replicates orca_quest.py start_analysis() method.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(self.routes["start_analysis"], timeout=5)
            print(f"Start analysis response: {response.text}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error starting analysis: {e}")
            return False
    
    @rpc
    def stop_analysis(self) -> bool:
        """
        Stop live image analysis.
        
        Replicates orca_quest.py stop_analysis() method.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(self.routes["stop_analysis"], timeout=5)
            print(f"Stop analysis response: {response.text}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error stopping analysis: {e}")
            return False
    
    @rpc
    def save_analysis(self) -> bool:
        """
        Save current analysis results.
        
        Replicates orca_quest.py save_analysis() method.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(self.routes["save_analysis"], timeout=5)
            print(f"Save analysis response: {response.text}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error saving analysis: {e}")
            return False
    
    @rpc
    def clear_analysis(self) -> bool:
        """
        Clear analysis data.
        
        Replicates orca_quest.py clear_analysis() method.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(self.routes["clear_analysis"], timeout=5)
            print(f"Clear analysis response: {response.text}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error clearing analysis: {e}")
            return False


class AutoCamera(Fragment):
    """
    Automated camera control fragment.
    
    Replicates functionality from auto_cam.py AutoCam class.
    Provides automated camera boot and analysis configuration.
    """
    
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment("camera", Camera)
        
        # Auto-control parameters
        self.setattr_param("auto_cam", BoolParam, "Auto camera", default=True)
        self.setattr_param("auto_ana", BoolParam, "Auto camera analysis", default=True)
        
        # Camera settings
        self.setattr_param("n_frames", IntParam, "Expected number of cam frames", default=100)
        self.setattr_param("t_exposure", FloatParam, "Exposure time", default=300.0, unit="ms")
        
        # Analysis settings (ROI for ion detection)
        self.setattr_param("xstart", IntParam, "ROI xstart", default=180)
        self.setattr_param("xfinish", IntParam, "ROI xfinish", default=220)
        self.setattr_param("ystart", IntParam, "ROI ystart", default=425)
        self.setattr_param("yfinish", IntParam, "ROI yfinish", default=495)
        self.setattr_param("radius", IntParam, "Lowpass filter radius", default=6)
    
    @rpc
    def host_setup(self):
        """
        Setup camera and analysis automatically.
        
        Called automatically by ndscan host_setup().
        """
        if self.auto_cam.get():
            print("AutoCamera: Booting camera...")
            self.boot_camera()
        
        if self.auto_ana.get():
            print("AutoCamera: Booting analysis...")
            self.boot_analysis()
        
        # Wait for camera to stabilize
        time.sleep(6)
        
        # Continue with parent setup
        super().host_setup()
    
    @rpc
    def host_cleanup(self):
        """
        Cleanup camera and analysis on experiment end.
        """
        print("AutoCamera: Cleaning up...")
        if self.auto_ana.get():
            self.save_close_analysis()
        
        super().host_cleanup()
    
    @rpc
    def boot_camera(self):
        """
        Boot camera with configured settings.
        
        Replicates auto_cam.py boot_camera() method.
        """
        print("AutoCamera: Close potential camera operations and reboot...")
        
        # Stop any existing recording
        self.camera.stop_cam()
        time.sleep(0.5)
        
        # Send settings
        self.camera.send_cam_settings(
            self.n_frames.get(),
            self.t_exposure.get(),
            trigger_mode="extern"
        )
        time.sleep(0.5)
        
        # Start recording
        self.camera.start_cam_recording()
        print("AutoCamera: Camera booted successfully")
    
    @rpc
    def boot_analysis(self):
        """
        Configure and start auto analysis.
        
        Replicates auto_cam.py boot_analysis() method.
        """
        print("AutoCamera: Configure and start auto analysis...")
        
        # Stop any existing analysis
        self.camera.stop_analysis()
        time.sleep(0.2)
        
        # Set parameters
        self.camera.set_analysis_params(
            int(self.xstart.get()),
            int(self.xfinish.get()),
            int(self.ystart.get()),
            int(self.yfinish.get()),
            int(self.radius.get())
        )
        time.sleep(0.2)
        
        # Start analysis
        self.camera.start_analysis()
        print("AutoCamera: Analysis started successfully")
    
    @rpc
    def save_close_analysis(self):
        """
        Stop and save analysis results.
        
        Replicates auto_cam.py save_close_analysis() method.
        """
        print("AutoCamera: Stop and save auto analysis...")
        
        self.camera.stop_analysis()
        time.sleep(0.2)
        
        self.camera.save_analysis()
        time.sleep(0.2)
        
        self.camera.clear_analysis()
        time.sleep(0.2)
        
        print("AutoCamera: Analysis cleanup complete")
