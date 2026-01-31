"""
ARTIQ Worker - Hardware control experiment with ZMQ integration.

This experiment runs continuously as a worker process, receiving commands
from the Control Manager via ZMQ and executing them on ARTIQ hardware.

Features:
- Automatic hardware initialization with safe defaults
- Watchdog timer for connection loss detection
- Heartbeat to manager for health monitoring
- Graceful degradation to safe state on errors
- Experiment ID propagation
"""

import sys
import time
import json
import zmq
import threading
import logging
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from ndscan.experiment import *
from artiq.experiment import *
from oitg.units import V, MHz, kHz, ms, us, dB

from core import (
    get_config,
    setup_logging,
    connect_with_retry,
    create_zmq_socket,
    ExperimentContext,
    get_tracker,
    log_safety_trigger,
)
from core.exceptions import SafetyError, HardwareError

# Import hardware fragments
from compensation import Compensation
from endcaps import EndCaps
from Raman_board import RamanCooling
from secularsweep import SecularSweep
from cam import Camera


class MainWorker(ExpFragment):
    """
    Main ARTIQ Worker experiment.
    
    Manages hardware state and responds to ZMQ commands from the manager.
    """
    
    def build_fragment(self):
        """Build the experiment fragment."""
        # Core devices
        self.setattr_device("core")
        self.setattr_device("scheduler")
        
        # Initialize logger (will be properly set up in run())
        self.logger = logging.getLogger("ARTIQ.Worker")
        
        # Hardware fragments
        self.ec = self.setattr_fragment("endcaps", EndCaps)
        self.comp = self.setattr_fragment("compensation", Compensation)
        self.raman = self.setattr_fragment("raman", RamanCooling)
        self.secular = self.setattr_fragment("secular", SecularSweep)
        self.cam = self.setattr_fragment("camera", Camera)
        
        # Load configuration
        self.config = get_config()
        defaults = self.config.get_all_hardware_defaults()
        
        # State management
        self.defaults = defaults
        self.state = self.defaults.copy()
        
        # Safety tracking
        self.safety_triggered = False
        self.safety_count = 0
        
        # ZMQ setup
        self.zmq_ctx = zmq.Context()
        self.sub = None
        self.push = None
        
        # Experiment tracking
        self.current_exp: ExperimentContext = None
        self.tracker = get_tracker()
        
        # Watchdog
        self.last_comm_time = time.time()
        self.watchdog_timeout = self.config.get_network('watchdog_timeout')
        
        # Heartbeat
        self.heartbeat_interval = self.config.get_network('heartbeat_interval')
        self.last_heartbeat = 0
        
        # Threading control
        self.running = True
        self.command_lock = threading.Lock()

    def run(self):
        """Main worker loop."""
        # Setup logging now that we're in the experiment context
        self.logger = setup_logging(
            component="artiq_worker",
            enable_console=False  # ARTIQ has its own console handling
        )
        
        self.logger.info("=" * 50)
        self.logger.info("ARTIQ Worker: Starting up...")
        
        # Initialize ZMQ
        if not self._init_zmq():
            self.logger.error("Failed to initialize ZMQ, aborting")
            return
        
        # Initialize hardware
        self.logger.info("Initializing hardware...")
        self.init_hardware()
        
        self.logger.info("ARTIQ Worker: Online. Watchdog Active ({}s).".format(
            self.watchdog_timeout
        ))
        
        # Main command loop
        while self.running:
            try:
                # Process any pending commands
                self._process_commands()
                
                # Send heartbeat
                self._send_heartbeat()
                
                # Check watchdog
                self._check_watchdog()
                
                # Small delay to prevent busy-waiting
                time.sleep(0.001)
                
            except KeyboardInterrupt:
                self.logger.info("Worker stopped manually.")
                break
            except Exception as e:
                self.logger.error(f"Error in Worker Loop: {e}", exc_info=True)
                self._handle_error(e)
        
        # Cleanup
        self._cleanup()
    
    def _init_zmq(self) -> bool:
        """Initialize ZMQ sockets."""
        try:
            master_ip = self.config.master_ip
            cmd_port = self.config.cmd_port
            data_port = self.config.data_port
            
            # Command subscriber
            self.sub = self.zmq_ctx.socket(zmq.SUB)
            cmd_addr = f"tcp://{master_ip}:{cmd_port}"
            connect_with_retry(self.sub, cmd_addr)
            
            # Subscribe to messages for this device and ALL
            self.sub.setsockopt_string(zmq.SUBSCRIBE, "ARTIQ")
            self.sub.setsockopt_string(zmq.SUBSCRIBE, "ALL")
            
            # Set receive timeout for watchdog checks
            timeout_ms = int(self.config.get_network('receive_timeout') * 1000)
            self.sub.setsockopt(zmq.RCVTIMEO, timeout_ms)
            
            # Data publisher (PUSH to manager's PULL)
            self.push = self.zmq_ctx.socket(zmq.PUSH)
            data_addr = f"tcp://{master_ip}:{data_port}"
            connect_with_retry(self.push, data_addr)
            
            self.logger.info(f"ZMQ connected to {master_ip}")
            return True
            
        except Exception as e:
            self.logger.error(f"ZMQ initialization failed: {e}")
            return False
    
    def _process_commands(self):
        """Process incoming commands from manager."""
        try:
            # Non-blocking receive
            topic = self.sub.recv_string(flags=zmq.NOBLOCK)
            msg = self.sub.recv_json(flags=zmq.NOBLOCK)
            
            # Update communication time
            self.last_comm_time = time.time()
            
            # Extract command info
            cmd_type = msg.get("type")
            payload = msg.get("values", {})
            exp_id = msg.get("exp_id")
            
            self.logger.info(f"Executing: {cmd_type} (exp: {exp_id})")
            
            # Update experiment context
            if exp_id:
                self._set_experiment_context(exp_id)
            
            # Execute command
            with self.command_lock:
                if cmd_type == "SET_DC":
                    self._handle_set_dc(payload)
                elif cmd_type == "SET_COOLING":
                    self._handle_set_cooling(payload)
                elif cmd_type == "RUN_SWEEP":
                    self._handle_run_sweep(payload, exp_id)
                elif cmd_type == "CAMERA_TRIGGER":
                    self._handle_camera_trigger(exp_id)
                else:
                    self.logger.warning(f"Unknown command type: {cmd_type}")
                    
        except zmq.Again:
            # No message available
            pass
        except Exception as e:
            self.logger.error(f"Error processing command: {e}")
    
    def _set_experiment_context(self, exp_id: str):
        """Set current experiment context."""
        if self.current_exp is None or self.current_exp.exp_id != exp_id:
            exp = self.tracker.get_experiment(exp_id)
            if exp is None:
                # Create new context if not tracked
                exp = ExperimentContext(exp_id=exp_id)
                exp.start()
            self.current_exp = exp
            self.logger.info(f"Switched to experiment {exp_id}")
    
    def _handle_set_dc(self, payload: dict):
        """Handle SET_DC command."""
        # Update state with provided values
        self.state["ec1"] = payload.get("ec1", self.state["ec1"])
        self.state["ec2"] = payload.get("ec2", self.state["ec2"])
        self.state["comp_h"] = payload.get("comp_h", self.state["comp_h"])
        self.state["comp_v"] = payload.get("comp_v", self.state["comp_v"])
        
        # Apply to hardware
        self.update_dc_params()
        
        # Send acknowledgment
        self._send_status("DC_UPDATED", {
            "ec1": self.state["ec1"],
            "ec2": self.state["ec2"],
            "comp_h": self.state["comp_h"],
            "comp_v": self.state["comp_v"]
        })
    
    def _handle_set_cooling(self, payload: dict):
        """Handle SET_COOLING command."""
        # Update state (sw0, sw1 are integers: 0=off, 1=on)
        # freq0 and freq1 are constants (215.5 MHz) and not adjustable
        self.state["sw0"] = int(payload.get("sw0", self.state["sw0"]))
        self.state["sw1"] = int(payload.get("sw1", self.state["sw1"]))
        
        # Apply to hardware
        self.update_cooling()
        
        # Send acknowledgment
        self._send_status("COOLING_UPDATED", {
            "sw0": self.state["sw0"],
            "sw1": self.state["sw1"]
        })
    
    def _handle_run_sweep(self, payload: dict, exp_id: str):
        """Handle RUN_SWEEP command."""
        # Get parameters (use stored defaults if not provided)
        target = payload.get("target_frequency_khz", self.state["sweep_target"])
        span = payload.get("span_khz", self.state["sweep_span"])
        att = payload.get("attenuation_db", self.state["sweep_att"])
        on_t = payload.get("on_time_ms", self.state["sweep_on"])
        off_t = payload.get("off_time_ms", self.state["sweep_off"])
        steps = int(payload.get("steps", self.state["sweep_points"]))
        
        self.logger.info(f"Starting sweep: target={target}kHz, span={span}kHz, steps={steps}")
        
        # Update experiment phase
        if self.current_exp:
            self.current_exp.transition_to("sweep")
        
        try:
            # Execute sweep on hardware
            self.run_secular_sweep(target, span, steps, att, on_t, off_t)
            
            # Report completion
            self._send_data({
                "status": "SWEEP_COMPLETE",
                "exp_id": exp_id,
                "target": target,
                "span": span,
                "steps": steps
            }, category="SWEEP_COMPLETE")
            
            self.logger.info("Sweep completed successfully")
            
        except Exception as e:
            self.logger.error(f"Sweep failed: {e}")
            self._send_data({
                "status": "SWEEP_FAILED",
                "exp_id": exp_id,
                "error": str(e)
            }, category="ERROR")
            
            if self.current_exp:
                self.current_exp.add_error(str(e), "artiq_sweep")
    
    def _handle_camera_trigger(self, exp_id: str):
        """
        Handle CAMERA_TRIGGER command.
        
        Sends a TTL pulse to trigger the camera for frame capture.
        The camera must already be recording (infinite mode or DCIMG mode).
        """
        self.logger.info(f"Executing camera TTL trigger (exp: {exp_id})")
        
        try:
            # Execute the TTL pulse on hardware
            self.trigger_camera_ttl()
            
            # Send acknowledgment
            self._send_status("CAMERA_TRIGGERED", {
                "exp_id": exp_id,
                "timestamp": time.time()
            })
            
            self.logger.debug("Camera TTL trigger executed")
            
        except Exception as e:
            self.logger.error(f"Camera trigger failed: {e}")
            self._send_data({
                "status": "CAMERA_TRIGGER_FAILED",
                "exp_id": exp_id,
                "error": str(e)
            }, category="ERROR")
    
    @kernel
    def trigger_camera_ttl(self):
        """Send TTL pulse to trigger camera (executed on ARTIQ hardware)."""
        self.cam.trigger(100.0)
    
    def _send_heartbeat(self):
        """Send periodic heartbeat to manager."""
        now = time.time()
        if now - self.last_heartbeat >= self.heartbeat_interval:
            self._send_data({
                "status": "alive",
                "state": self.state,
                "safety_triggered": self.safety_triggered
            }, category="HEARTBEAT")
            self.last_heartbeat = now
    
    def _check_watchdog(self):
        """Check for connection loss and trigger safety if needed."""
        elapsed = time.time() - self.last_comm_time
        
        if elapsed > self.watchdog_timeout:
            if not self.safety_triggered:
                self.logger.error(f"WATCHDOG: Connection lost for {elapsed:.1f}s")
                self._trigger_safety("connection_loss")
    
    def _trigger_safety(self, trigger_type: str):
        """Trigger safety state."""
        self.safety_triggered = True
        self.safety_count += 1
        
        self.logger.warning(f"SAFETY TRIGGER: {trigger_type}")
        
        # Apply safety defaults
        self.apply_safety_defaults()
        
        # Log safety event
        log_safety_trigger(
            self.logger,
            trigger_type=trigger_type,
            previous_state=self.state.copy(),
            safety_state=self.defaults,
            exp_id=self.current_exp.exp_id if self.current_exp else None
        )
        
        # Report to manager
        self._send_data({
            "trigger_type": trigger_type,
            "safety_count": self.safety_count
        }, category="SAFETY_TRIGGER")
        
        # Reset timer to prevent spam
        self.last_comm_time = time.time()
    
    def _handle_error(self, error: Exception):
        """Handle an error condition."""
        self.logger.error(f"Handling error: {error}")
        
        # Depending on error severity, might trigger safety
        if isinstance(error, (SafetyError, HardwareError)):
            self._trigger_safety("error_condition")
    
    def _send_data(self, payload: dict, category: str = "DATA"):
        """Send data to manager."""
        try:
            packet = {
                "timestamp": time.time(),
                "source": "ARTIQ",
                "category": category,
                "payload": payload,
                "exp_id": self.current_exp.exp_id if self.current_exp else None
            }
            self.push.send_json(packet, flags=zmq.NOBLOCK)
        except zmq.Again:
            self.logger.warning("Data send would block, dropping")
        except Exception as e:
            self.logger.error(f"Failed to send data: {e}")
    
    def _send_status(self, status: str, data: dict):
        """Send status update to manager."""
        self._send_data({"status": status, **data}, category="STATUS")
    
    def _cleanup(self):
        """Cleanup resources."""
        self.logger.info("Cleaning up...")
        
        # Apply safety defaults
        self.apply_safety_defaults()
        
        # Close ZMQ
        if self.sub:
            self.sub.close()
        if self.push:
            self.push.close()
        self.zmq_ctx.term()
        
        self.logger.info("Worker shutdown complete")

    @kernel
    def init_hardware(self):
        """Initial hardware setup with safe defaults."""
        self.core.reset()
        self.core.break_realtime()
        self.ec.device_setup()
        self.comp.device_setup()
        self.raman.device_setup()
        self.secular.device_setup()
        self.cam.device_setup()
        # Apply the default safe state immediately
        self.apply_safety_defaults()

    @kernel
    def apply_safety_defaults(self):
        """
        Safety Trigger: Sets 0V and closes shutters.
        This is called on watchdog timeout or critical errors.
        """
        self.core.break_realtime()
        
        # Reset Voltages to 0V
        self.ec.set_ec(0.0 * V, 0.0 * V)
        self.comp.set_compensation(0.0 * V, 0.0 * V)
        
        # Turn off Cooling Shutters (sw0=0, sw1=0)
        self.raman.set_cooling_params(0.05, 0.05, 0, 0)
        
        # Reset state to defaults
        self.state = self.defaults.copy()
        self.safety_triggered = True

    @kernel
    def update_dc_params(self):
        """Applies current state to DC hardware."""
        self.core.break_realtime()
        self.ec.set_ec(self.state["ec1"] * V, self.state["ec2"] * V)
        self.comp.set_compensation(self.state["comp_h"] * V, self.state["comp_v"] * V)

    @kernel
    def update_cooling(self):
        """Applies current state to Raman hardware."""
        self.core.break_realtime()
        # Frequencies are constants (215.5 MHz), only amplitudes and switches are adjustable
        # sw0, sw1 are integers (0=off, 1=on)
        self.raman.set_cooling_params(
            self.state["amp0"], self.state["amp1"], 
            int(self.state["sw0"]), int(self.state["sw1"])
        )

    @kernel
    def run_secular_sweep(self, target_khz, span_khz, steps, att_db, on_ms, off_ms):
        """
        Executes scan with default or provided parameters.
        Default: 300ms on/off, Span +/-20kHz (Total 40).
        """
        self.core.break_realtime()

        # Calculate Start Frequency and Step Size
        start_f = (target_khz - span_khz/2.0) * kHz
        step_size = (span_khz * kHz) / (steps - 1)
        
        self.secular.dds.set_att(att_db * dB)
        
        self.set_dataset("sweep_freqs", np.full(steps, 0.0), broadcast=True)
        self.set_dataset("sweep_counts", np.full(steps, 0.0), broadcast=True)

        for i in range(steps):
            freq = start_f + (i * step_size)
            
            # Measurement
            self.secular.dds.set(frequency=freq)
            with parallel:
                self.secular.dds.cfg_sw(True)
                self.secular.pmt.gate_rising(on_ms * ms)
                self.secular.cam.pulse(10*us)

            self.secular.dds.cfg_sw(False)
            counts = self.secular.pmt.fetch_count()
            
            # Save
            self.mutate_dataset("sweep_freqs", i, freq)
            self.mutate_dataset("sweep_counts", i, counts)
            
            delay(off_ms * ms)


# Make this a standalone experiment
ARTIQWorker = make_fragment_scan_exp(MainWorker)
