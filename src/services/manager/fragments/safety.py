"""
Safety Fragments

Fragments for safety management:
- KillSwitchFragment: Manager-level kill switches
- SafetyFragment: Safety defaults application
"""

import threading
import time
from typing import Any, Callable, Dict, Optional

from .base import BaseFragment, FragmentPriority


class KillSwitchFragment(BaseFragment):
    """
    Manager-level kill switch for time-limited hardware outputs.
    
    Time limits:
    - piezo: 10 seconds max
    - e-gun: 30 seconds max
    
    On timeout: Automatically commands LabVIEW to set voltage to 0V.
    """
    
    NAME = "kill_switch"
    PRIORITY = FragmentPriority.CRITICAL
    
    TIME_LIMITS = {
        "piezo": 10.0,
        "e_gun": 30.0,
    }
    
    def _do_initialize(self):
        """Initialize kill switch manager."""
        self._active: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._running = True
        
        # Start watchdog thread
        self._watchdog = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name="KillSwitchWatchdog"
        )
        self._watchdog.start()
        
        self.log_info("Kill Switch initialized")
    
    def _do_shutdown(self):
        """Shutdown kill switch manager."""
        self._running = False
        # Trigger all active kill switches
        for device in list(self._active.keys()):
            self.trigger(device, "SHUTDOWN")
    
    def register_callback(self, device: str, callback: Callable):
        """Register a callback to be called when kill switch triggers."""
        self._callbacks[device] = callback
    
    def arm(self, device: str, metadata: Dict[str, Any] = None) -> bool:
        """Arm the kill switch for a device."""
        if device not in self.TIME_LIMITS:
            self.log_warning(f"Unknown device: {device}")
            return False
        
        self._active[device] = {
            "start_time": time.time(),
            "metadata": metadata or {},
            "killed": False,
        }
        self.log_warning(f"KILL SWITCH ARMED for {device} (limit: {self.TIME_LIMITS[device]}s)")
        return True
    
    def disarm(self, device: str) -> bool:
        """Disarm the kill switch (safe turn-off by user)."""
        if device in self._active:
            elapsed = time.time() - self._active[device]["start_time"]
            self.log_info(f"Kill switch disarmed for {device} (was active for {elapsed:.1f}s)")
            del self._active[device]
            return True
        return False
    
    def is_armed(self, device: str) -> bool:
        """Check if kill switch is armed for a device."""
        return device in self._active and not self._active[device].get("killed", False)
    
    def trigger(self, device: str, reason: str = "manual") -> bool:
        """Manually trigger the kill switch."""
        if device not in self._active:
            return False
        
        info = self._active[device]
        if info.get("killed"):
            return False
        
        info["killed"] = True
        elapsed = time.time() - info["start_time"]
        
        self.log_error(f"KILL SWITCH TRIGGERED for {device}: {reason} (was on for {elapsed:.1f}s)")
        
        # Execute callback if registered
        if device in self._callbacks:
            try:
                self._callbacks[device]()
            except Exception as e:
                self.log_error(f"Kill switch callback failed: {e}")
        
        del self._active[device]
        return True
    
    def trigger_all(self, reason: str = "emergency"):
        """Trigger all active kill switches."""
        for device in list(self._active.keys()):
            self.trigger(device, reason)
    
    def _watchdog_loop(self):
        """Monitor active devices and enforce time limits."""
        while self._running:
            try:
                now = time.time()
                to_kill = []
                
                for device, info in self._active.items():
                    if info.get("killed"):
                        continue
                    elapsed = now - info["start_time"]
                    limit = self.TIME_LIMITS[device]
                    
                    if elapsed > limit:
                        to_kill.append(device)
                
                for device in to_kill:
                    self.trigger(device, f"TIME LIMIT EXCEEDED ({self.TIME_LIMITS[device]}s)")
                
                time.sleep(0.1)  # 10 Hz check rate
                
            except Exception as e:
                self.log_error(f"Kill switch watchdog error: {e}")
                time.sleep(1)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current kill switch status."""
        status = {}
        for device, limit in self.TIME_LIMITS.items():
            if device in self._active:
                info = self._active[device]
                elapsed = time.time() - info["start_time"]
                status[device] = {
                    "armed": True,
                    "elapsed": elapsed,
                    "remaining": max(0, limit - elapsed),
                    "limit": limit,
                    "killed": info.get("killed", False),
                }
            else:
                status[device] = {"armed": False, "limit": limit}
        return status
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle kill switch requests."""
        if action == "KILL_SWITCH_STATUS":
            return {"status": "success", "kill_switch": self.get_status()}
        elif action == "KILL_SWITCH_ARM":
            device = request.get("device")
            success = self.arm(device, request.get("metadata", {}))
            return {"status": "success" if success else "error"}
        elif action == "KILL_SWITCH_DISARM":
            device = request.get("device")
            success = self.disarm(device)
            return {"status": "success" if success else "error"}
        return None


class SafetyFragment(BaseFragment):
    """
    Safety fragment for applying safety defaults.
    
    Handles emergency shutdown and safe state application.
    """
    
    NAME = "safety"
    PRIORITY = FragmentPriority.CRITICAL
    
    # Safe state values
    SAFETY_DEFAULTS = {
        "u_rf_volts": 0.0,
        "ec1": 0.0,
        "ec2": 0.0,
        "comp_h": 0.0,
        "comp_v": 0.0,
        "piezo": 0.0,
        "sw0": 0,
        "sw1": 0,
        "bephi": 0,
        "b_field": 0,
        "be_oven": 0,
        "e_gun": 0,
        "uv3": 0,
        "hd_valve": 0,
    }
    
    def _do_initialize(self):
        """Initialize safety fragment."""
        self._safety_triggered = False
        self.log_info("Safety fragment initialized")
    
    def apply_safety_defaults(self, notify: bool = True):
        """
        Apply safety defaults to hardware.
        
        Args:
            notify: If True, publish updates to workers
        """
        self.log_warning("Applying safety defaults!")
        
        # Update manager params
        self.manager.params.update(self.SAFETY_DEFAULTS)
        
        # Publish to ARTIQ
        if notify:
            artiq = self.manager.fragments.get("artiq")
            if artiq:
                artiq.publish_dc_update(
                    ec1=self.SAFETY_DEFAULTS["ec1"],
                    ec2=self.SAFETY_DEFAULTS["ec2"],
                    comp_h=self.SAFETY_DEFAULTS["comp_h"],
                    comp_v=self.SAFETY_DEFAULTS["comp_v"]
                )
                artiq.publish_cooling_update(
                    amp0=0.05,  # Safe default
                    amp1=0.05,
                    sw0=self.SAFETY_DEFAULTS["sw0"],
                    sw1=self.SAFETY_DEFAULTS["sw1"]
                )
                artiq.publish_rf_update(self.SAFETY_DEFAULTS["u_rf_volts"])
                artiq.publish_piezo_update(self.SAFETY_DEFAULTS["piezo"])
        
        # Apply to LabVIEW
        labview = self.manager.fragments.get("labview")
        if labview and labview.is_connected:
            self.log_info("Applying safety defaults to LabVIEW...")
            results = labview.apply_safety_defaults()
            failed = [k for k, v in results.items() if not v]
            if failed:
                self.log_warning(f"Failed to apply safety defaults to LabVIEW devices: {failed}")
            else:
                self.log_info("Safety defaults applied to LabVIEW successfully")
        
        self._safety_triggered = True
    
    def emergency_stop(self, source: str = "UNKNOWN", reason: str = "Emergency stop") -> Dict[str, Any]:
        """
        Execute emergency stop.
        
        Args:
            source: Source of the stop command
            reason: Reason for the stop
            
        Returns:
            Response dictionary
        """
        self.log_warning(f"EMERGENCY STOP from {source}: {reason}")
        
        # Enter SAFE mode
        from core import SystemMode
        self.manager.mode = SystemMode.SAFE
        
        # Trigger kill switches
        kill_switch = self.manager.fragments.get("kill_switch")
        if kill_switch:
            kill_switch.trigger_all(f"STOP from {source}")
        
        # Apply safety defaults
        self.apply_safety_defaults(notify=False)
        
        # Log safety event
        from core import log_safety_trigger
        log_safety_trigger(
            self.log_info,
            trigger_type="emergency_stop",
            previous_state=self.manager.params.copy(),
            safety_state=self.SAFETY_DEFAULTS,
            exp_id=self.current_exp.exp_id if self.current_exp else None
        )
        
        return {
            "status": "success",
            "message": "STOP executed. Algorithm halted, safe defaults applied.",
            "mode": self.manager.mode.value
        }
    
    def handle_request(self, action: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle safety requests."""
        if action == "STOP":
            source = request.get("source", "UNKNOWN")
            reason = request.get("reason", "Emergency stop")
            return self.emergency_stop(source, reason)
        elif action == "APPLY_SAFETY_DEFAULTS":
            self.apply_safety_defaults()
            return {"status": "success", "message": "Safety defaults applied"}
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get safety status."""
        return {
            "safety_triggered": self._safety_triggered,
            "safety_defaults": self.SAFETY_DEFAULTS.copy()
        }
