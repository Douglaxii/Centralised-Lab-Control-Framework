"""
Applet Fragments

Fragments for managing experiment applets:
- AutoCompApplet: Auto-compensation optimization
- CamSweepApplet: Camera-synchronized sweep
- SecularSweepApplet: Secular frequency sweep
- PMTMeasureApplet: PMT photon counting
"""

import time
from typing import Any, Dict, Optional

from .base import BaseFragment, FragmentPriority


class AutoCompApplet(BaseFragment):
    """
    Auto-compensation applet for optimizing electrode voltages.
    
    Iteratively adjusts compensation electrodes to minimize ion motion.
    """
    
    NAME = "applet_autocomp"
    PRIORITY = FragmentPriority.LOW
    
    def _do_initialize(self):
        """Initialize auto-comp applet."""
        self._running = False
        self._max_iterations = self.config.get('applet.auto_comp.max_iterations', 50)
        self._convergence_threshold = self.config.get('applet.auto_comp.convergence_threshold', 0.01)
    
    def _do_shutdown(self):
        """Shutdown auto-comp applet."""
        self._running = False
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle auto-comp requests."""
        if action == "AUTOCOMP_START":
            return self._start(request)
        elif action == "AUTOCOMP_STOP":
            return self._stop(request)
        elif action == "AUTOCOMP_STATUS":
            return self._get_status(request)
        return None
    
    def _start(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Start auto-compensation."""
        if self._running:
            return {"status": "error", "message": "Already running"}
        
        self._running = True
        self.log_info("Auto-compensation started")
        
        return {
            "status": "success",
            "message": "Auto-compensation started",
            "max_iterations": self._max_iterations,
            "convergence_threshold": self._convergence_threshold
        }
    
    def _stop(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Stop auto-compensation."""
        self._running = False
        self.log_info("Auto-compensation stopped")
        return {"status": "success", "message": "Auto-compensation stopped"}
    
    def _get_status(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Get auto-comp status."""
        return {
            "status": "success",
            "running": self._running,
            "max_iterations": self._max_iterations,
            "convergence_threshold": self._convergence_threshold
        }


class CamSweepApplet(BaseFragment):
    """
    Camera sweep applet for synchronized camera + sweep experiments.
    
    Handles:
    - Starting camera recording
    - Running secular sweep with TTL triggers
    - Collecting results
    """
    
    NAME = "applet_camsweep"
    PRIORITY = FragmentPriority.LOW
    
    def _do_initialize(self):
        """Initialize cam sweep applet."""
        self._default_exposure = self.config.get('applet.cam_sweep.default_exposure_ms', 100)
        self._default_frames = self.config.get('applet.cam_sweep.default_frames', 10)
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle cam sweep requests."""
        if action == "CAM_SWEEP":
            return self._handle_cam_sweep(request)
        return None
    
    def _handle_cam_sweep(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle CAM_SWEEP request.
        
        Workflow:
        1. Stop camera infinity mode if running
        2. Start camera recording
        3. Send CAM_SWEEP command to ARTIQ
        4. Return immediately (results come via data packets)
        """
        params = request.get("params", {})
        exp_id = request.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        # Extract parameters
        target_freq = params.get("target_frequency_khz", 400.0)
        span_khz = params.get("span_khz", 40.0)
        steps = int(params.get("steps", 41))
        on_time_ms = params.get("on_time_ms", 100.0)
        off_time_ms = params.get("off_time_ms", 100.0)
        att_db = params.get("attenuation_db", 25.0)
        
        self.log_info(f"CAM_SWEEP: {target_freq}kHz ± {span_khz/2}kHz, {steps} steps")
        
        # Get camera fragment
        camera = self.manager.fragments.get("camera")
        if camera and camera.is_recording:
            self.log_info("Stopping camera infinity mode...")
            camera.stop_recording()
            time.sleep(0.5)
        
        # Start camera recording
        if camera:
            camera.start_recording(mode="single", exp_id=exp_id)
        
        # Get ARTIQ fragment and start sweep
        artiq = self.manager.fragments.get("artiq")
        if not artiq:
            return {"status": "error", "message": "ARTIQ fragment not available"}
        
        sweep_params = {
            "target_frequency_khz": target_freq,
            "span_khz": span_khz,
            "steps": steps,
            "on_time_ms": on_time_ms,
            "off_time_ms": off_time_ms,
            "attenuation_db": att_db
        }
        
        return artiq.start_cam_sweep(sweep_params, exp_id)


class SecularSweepApplet(BaseFragment):
    """
    Secular sweep applet for frequency scans.
    
    Similar to CamSweepApplet but without camera synchronization.
    """
    
    NAME = "applet_secularsweep"
    PRIORITY = FragmentPriority.LOW
    
    def _do_initialize(self):
        """Initialize secular sweep applet."""
        self._default_span = self.config.get('applet.secular_sweep.default_span_khz', 40)
        self._default_steps = self.config.get('applet.secular_sweep.default_steps', 41)
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle secular sweep requests."""
        if action == "SECULAR_SWEEP":
            return self._handle_secular_sweep(request)
        return None
    
    def _handle_secular_sweep(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle SECULAR_SWEEP request.
        
        Workflow:
        1. Extract sweep parameters
        2. Send SECULAR_SWEEP command to ARTIQ
        3. Return immediately (results come via data packets)
        """
        params = request.get("params", {})
        exp_id = request.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        # Extract parameters
        target_freq = params.get("target_frequency_khz", 400.0)
        span_khz = params.get("span_khz", 40.0)
        steps = int(params.get("steps", 41))
        on_time_ms = params.get("on_time_ms", 100.0)
        off_time_ms = params.get("off_time_ms", 100.0)
        att_db = params.get("attenuation_db", 25.0)
        dds_choice = params.get("dds_choice", "axial")
        
        self.log_info(f"SECULAR_SWEEP: {target_freq}kHz ± {span_khz/2}kHz, {steps} steps, DDS={dds_choice}")
        
        # Get ARTIQ fragment
        artiq = self.manager.fragments.get("artiq")
        if not artiq:
            return {"status": "error", "message": "ARTIQ fragment not available"}
        
        sweep_params = {
            "target_frequency_khz": target_freq,
            "span_khz": span_khz,
            "steps": steps,
            "on_time_ms": on_time_ms,
            "off_time_ms": off_time_ms,
            "attenuation_db": att_db,
            "dds_choice": dds_choice
        }
        
        return artiq.start_secular_sweep(sweep_params, exp_id)


class PMTMeasureApplet(BaseFragment):
    """
    PMT measurement applet for photon counting.
    
    Requests gated PMT count from ARTIQ worker.
    """
    
    NAME = "applet_pmtmeasure"
    PRIORITY = FragmentPriority.LOW
    
    def _do_initialize(self):
        """Initialize PMT measure applet."""
        self._default_duration = 100.0  # ms
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle PMT measure requests."""
        if action == "PMT_MEASURE":
            return self._handle_pmt_measure(request)
        return None
    
    def _handle_pmt_measure(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle PMT_MEASURE request.
        
        Sends PMT_MEASURE command to ARTIQ and waits for result.
        """
        duration_ms = request.get("duration_ms", self._default_duration)
        exp_id = request.get("exp_id") or (self.current_exp.exp_id if self.current_exp else None)
        
        self.log_info(f"PMT measure requested: duration={duration_ms}ms")
        
        # Get ARTIQ fragment
        artiq = self.manager.fragments.get("artiq")
        if not artiq:
            return {"status": "error", "message": "ARTIQ fragment not available"}
        
        # Send request
        artiq.request_pmt_measure(duration_ms, exp_id)
        
        # Wait for response with timeout
        timeout = duration_ms / 1000.0 + 2.0
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Poll for result
                import zmq
                self.manager.pull_socket.setsockopt(zmq.RCVTIMEO, 100)
                packet = self.manager.pull_socket.recv_json()
                
                if packet.get("category") == "PMT_MEASURE_RESULT" and packet.get("exp_id") == exp_id:
                    payload = packet.get("payload", {})
                    counts = payload.get("counts", 0)
                    self.log_info(f"PMT measurement complete: {counts} counts")
                    return {
                        "status": "success",
                        "counts": counts,
                        "duration_ms": duration_ms
                    }
                    
            except zmq.Again:
                continue
            except Exception as e:
                self.log_error(f"Error waiting for PMT result: {e}")
                break
        
        return {
            "status": "error",
            "message": "PMT measurement timeout",
            "code": "PMT_TIMEOUT"
        }
