"""
ZmqWorker.py - ARTIQ Worker with ZMQ integration (STANDALONE EXPERIMENT)

This is a standalone EnvExperiment (not an ExpFragment) that runs continuously
as a long-running worker, receiving commands via ZMQ.

Receives commands from manager via ZMQ and executes on ARTIQ hardware.
Sends data/results back to manager via ZMQ.

Usage:
    # From ARTIQ dashboard: Submit as a regular experiment
    # Or from command line: artiq_run Artiq_Worker.py
"""

import sys
import time
import json
import logging
import traceback

# Add repository to path for imports
sys.path.insert(0, "/home/artiq/Developer/artiq/artiq-master/repository")

from artiq.experiment import *
from artiq.language.types import TInt32, TFloat, TBool
from oitg.units import V, MHz, kHz, ms, us

# dB is not in oitg.units
dB = 1.0


class ZmqWorker(EnvExperiment):
    """
    Standalone ZMQ Worker Experiment.
    
    This is NOT an ExpFragment - it's a standalone EnvExperiment that
    runs continuously, processing ZMQ commands until terminated.
    
    To use:
        1. Submit this experiment from ARTIQ dashboard
        2. It will run indefinitely, processing ZMQ commands
        3. Terminate via dashboard to stop
    """
    
    def build(self):
        """
        Build the experiment.
        
        Note: This is build(), not build_fragment() - we're an EnvExperiment!
        """
        self.setattr_device("core")
        
        # Configuration (can be overridden via arguments)
        self.setattr_argument("master_ip", StringValue(default="192.168.56.101"),
                             tooltip="Manager PC IP address")
        self.setattr_argument("cmd_port", NumberValue(default=5555, ndecimals=0, step=1),
                             tooltip="ZMQ command port (PUB/SUB)")
        self.setattr_argument("data_port", NumberValue(default=5556, ndecimals=0, step=1),
                             tooltip="ZMQ data port (PUSH/PULL)")
        self.setattr_argument("watchdog_timeout", NumberValue(default=30.0, unit="s"),
                             tooltip="Watchdog timeout in seconds")
        
        # State variables
        self.zmq_ctx = None
        self.sub = None
        self.push = None
        self.running = True
        self.camera_inf_active = False
        self.last_comm_time = 0.0
        self.watchdog_last_alert = 0.0
        
        # Placeholders for fragments (initialized in prepare())
        self.ec = None
        self.comp = None
        self.raman = None
        self.sweep = None
        self._fragments_initialized = False
        
        # Sweep result buffers
        self._sweep_freqs = [0.0] * 1000
        self._sweep_counts = [0] * 1000
        self._sweep_num_steps = 0
        
        # Logger
        self.logger = logging.getLogger("ARTIQ.Worker")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(name)s] %(levelname)s: %(message)s'))
            self.logger.addHandler(handler)
    
    def prepare(self):
        """
        Prepare the experiment.
        
        Called after build() but before run().
        Safe for heavy initialization.
        """
        self.logger.info("=" * 60)
        self.logger.info("ARTIQ ZMQ Worker: Preparing...")
        self.logger.info("=" * 60)
        self.logger.info(f"Manager IP: {self.master_ip}")
        self.logger.info(f"Command port: {self.cmd_port}")
        self.logger.info(f"Data port: {self.data_port}")
        
        # Lazy load fragments
        self._init_fragments()
        
        # Apply safety defaults
        try:
            self.apply_safety_defaults_host()
        except Exception as e:
            self.logger.error(f"Safety initialization failed: {e}")
            raise
        
        # Initialize ZMQ
        if not self._init_zmq():
            raise RuntimeError("ZMQ initialization failed - aborting startup")
        
        self.last_comm_time = time.time()
        self.logger.info("Worker ready for commands")
    
    def _init_fragments(self):
        """Lazy initialize fragments."""
        if self._fragments_initialized:
            return
        
        self.logger.info("Lazy-loading fragments...")
        try:
            from ec import ec
            from comp import comp
            from raman_control import raman_control
            from sweeping import sweeping
            
            # Instantiate fragments
            self.ec = ec(self, ["ec"])
            self.comp = comp(self, ["comp"])
            self.raman = raman_control(self, ["raman"])
            self.sweep = sweeping(self, ["sweep"])
            
            self._fragments_initialized = True
            self.logger.info("Fragments loaded successfully.")
        except Exception as e:
            self.logger.exception("Failed to load fragments")
            raise RuntimeError(f"Fragment initialization failed: {e}")
    
    def run(self):
        """
        Main worker loop.
        
        Runs indefinitely until terminated via dashboard or error.
        """
        self.logger.info("=" * 60)
        self.logger.info("ARTIQ ZMQ Worker: Starting main loop")
        self.logger.info("=" * 60)
        
        try:
            while self.running:
                # Check if we should pause/terminate
                try:
                    self.scheduler.pause()
                except TerminationRequested:
                    self.logger.info("Termination requested by scheduler")
                    break
                
                # Process commands
                self._process_commands()
                
                # Check watchdog
                self._check_watchdog()
                
                # Small delay to prevent CPU saturation
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            self.logger.info("Worker interrupted by user")
        except Exception as e:
            self.logger.exception(f"Fatal error in worker loop: {e}")
            self._send_data({
                "status": "WORKER_CRASHED",
                "error": str(e),
                "traceback": traceback.format_exc()
            }, category="FATAL_ERROR")
        finally:
            self._cleanup()
        
        self.logger.info("Worker main loop exited")
    
    def analyze(self):
        """Called after run() completes."""
        self.logger.info("Worker analysis phase (cleanup complete)")
    
    # ==================== ZMQ OPERATIONS ====================
    
    def _init_zmq(self):
        """Initialize ZMQ sockets."""
        try:
            import zmq
            self.zmq_ctx = zmq.Context()
            
            # Command subscriber (SUB)
            self.sub = self.zmq_ctx.socket(zmq.SUB)
            cmd_addr = f"tcp://{self.master_ip}:{int(self.cmd_port)}"
            self.sub.connect(cmd_addr)
            self.sub.setsockopt_string(zmq.SUBSCRIBE, "ARTIQ")
            self.sub.setsockopt_string(zmq.SUBSCRIBE, "ALL")
            self.sub.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout
            
            # Data pusher (PUSH)
            self.push = self.zmq_ctx.socket(zmq.PUSH)
            data_addr = f"tcp://{self.master_ip}:{int(self.data_port)}"
            self.push.connect(data_addr)
            self.push.setsockopt(zmq.LINGER, 0)
            
            self.logger.info(f"ZMQ connected: commands={cmd_addr}, data={data_addr}")
            return True
            
        except Exception as e:
            self.logger.error(f"ZMQ initialization failed: {e}")
            self._safe_zmq_cleanup()
            return False
    
    def _process_commands(self):
        """Process incoming ZMQ commands."""
        try:
            import zmq
            
            # Try to receive (non-blocking due to RCVTIMEO)
            try:
                topic = self.sub.recv_string(flags=zmq.NOBLOCK)
                msg = self.sub.recv_json(flags=zmq.NOBLOCK)
            except zmq.Again:
                return  # No message available
            
            self.last_comm_time = time.time()
            
            cmd_type = msg.get("type", "UNKNOWN")
            payload = msg.get("values", {})
            exp_id = msg.get("exp_id", "UNKNOWN")
            
            self.logger.debug(f"Received: {cmd_type} (exp: {exp_id})")
            
            # Dispatch to handlers
            handlers = {
                "SET_DC": lambda: self._handle_set_dc(payload, exp_id),
                "SET_COOLING": lambda: self._handle_set_cooling(payload, exp_id),
                "RUN_SWEEP": lambda: self._handle_run_sweep(payload, exp_id),
                "CAMERA_TRIGGER": lambda: self._handle_camera_trigger(exp_id),
                "START_CAMERA_INF": lambda: self._handle_start_camera_inf(exp_id),
                "STOP_CAMERA": lambda: self._handle_stop_camera(exp_id),
                "PMT_MEASURE": lambda: self._handle_pmt_measure(msg, exp_id),
                "CAM_SWEEP": lambda: self._handle_cam_sweep(msg, exp_id),
                "SECULAR_SWEEP": lambda: self._handle_secular_sweep(msg, exp_id),
                "EMERGENCY_ZERO": lambda: self._handle_emergency_zero(exp_id),
                "PING": lambda: self._handle_ping(exp_id),
                "STOP_WORKER": lambda: self._handle_stop_worker(exp_id),
            }
            
            handler = handlers.get(cmd_type)
            if handler:
                handler()
            else:
                self.logger.warning(f"Unknown command: {cmd_type}")
                self._send_status("UNKNOWN_COMMAND", {
                    "command": cmd_type, "exp_id": exp_id
                })
                
        except Exception as e:
            self.logger.exception(f"Command processing error: {e}")
            self._send_data({
                "status": "COMMAND_ERROR",
                "error": str(e)
            }, category="ERROR")
    
    def _check_watchdog(self):
        """Check communication watchdog."""
        elapsed = time.time() - self.last_comm_time
        if elapsed > self.watchdog_timeout.get():
            now = time.time()
            if now - self.watchdog_last_alert > 60.0:
                self.logger.error(f"Watchdog triggered! No communication for {elapsed:.1f}s")
                self.apply_safety_defaults_host()
                self._send_status("WATCHDOG_TRIGGERED", {
                    "elapsed_seconds": elapsed
                })
                self.watchdog_last_alert = now
    
    def _send_data(self, payload, category="DATA"):
        """Send data to manager."""
        try:
            import zmq
            packet = {
                "timestamp": time.time(),
                "source": "ARTIQ",
                "category": category,
                "payload": payload
            }
            self.push.send_json(packet, flags=zmq.NOBLOCK)
        except Exception as e:
            self.logger.error(f"Failed to send data: {e}")
    
    def _send_status(self, status, data):
        """Send status update."""
        self._send_data({"status": status, **data}, category="STATUS")
    
    def _safe_zmq_cleanup(self):
        """Cleanup ZMQ resources."""
        try:
            if self.sub:
                self.sub.close()
                self.sub = None
            if self.push:
                self.push.close()
                self.push = None
            if self.zmq_ctx:
                self.zmq_ctx.term()
                self.zmq_ctx = None
        except Exception as e:
            self.logger.warning(f"Error during ZMQ cleanup: {e}")
    
    def _cleanup(self):
        """Final cleanup."""
        self.logger.info("Worker cleanup initiated...")
        try:
            self.apply_safety_defaults_host()
        except Exception as e:
            self.logger.error(f"Safety cleanup failed: {e}")
        
        self._safe_zmq_cleanup()
        self.logger.info("Worker shutdown complete")
    
    # ==================== COMMAND HANDLERS ====================
    
    def _handle_set_dc(self, payload, exp_id):
        """Handle SET_DC command."""
        ec1 = float(payload.get("ec1", 0.0))
        ec2 = float(payload.get("ec2", 0.0))
        comp_h = float(payload.get("comp_h", 0.0))
        comp_v = float(payload.get("comp_v", 0.0))
        
        self.logger.info(f"SET_DC: ec1={ec1:.3f}V, ec2={ec2:.3f}V, comp_h={comp_h:.3f}V, comp_v={comp_v:.3f}V")
        
        try:
            self.set_dc_hardware(ec1, ec2, comp_h, comp_v)
            self._send_status("DC_UPDATED", {
                "ec1": ec1, "ec2": ec2,
                "comp_h": comp_h, "comp_v": comp_v,
                "exp_id": exp_id
            })
        except Exception as e:
            self.logger.exception("SET_DC failed")
            self._send_data({
                "status": "DC_UPDATE_FAILED",
                "error": str(e),
                "exp_id": exp_id
            }, category="ERROR")
    
    def _handle_set_cooling(self, payload, exp_id):
        """Handle SET_COOLING command."""
        amp0 = float(payload.get("amp0", 0.05))
        amp1 = float(payload.get("amp1", 0.05))
        sw0 = int(payload.get("sw0", 0))
        sw1 = int(payload.get("sw1", 0))
        
        self.logger.info(f"SET_COOLING: amp0={amp0}, amp1={amp1}, sw0={sw0}, sw1={sw1}")
        
        try:
            self.set_cooling_hardware(amp0, amp1, sw0, sw1)
            self._send_status("COOLING_UPDATED", {
                "amp0": amp0, "amp1": amp1, "sw0": sw0, "sw1": sw1,
                "exp_id": exp_id
            })
        except Exception as e:
            self.logger.exception("SET_COOLING failed")
            self._send_data({
                "status": "COOLING_UPDATE_FAILED",
                "error": str(e),
                "exp_id": exp_id
            }, category="ERROR")
    
    def _handle_run_sweep(self, payload, exp_id):
        """Handle RUN_SWEEP command."""
        try:
            target = float(payload.get("target_frequency_khz", 400.0))
            span = float(payload.get("span_khz", 40.0))
            steps = int(payload.get("steps", 41))
            att = float(payload.get("attenuation_db", 25.0))
            on_t = float(payload.get("on_time_ms", 100.0))
            off_t = float(payload.get("off_time_ms", 100.0))
            
            self.logger.info(f"RUN_SWEEP: {target}kHz ±{span/2}kHz, {steps} steps")
            
            self._run_sweep_kernel(target, span, steps, att, on_t, off_t)
            
            freqs = self._get_sweep_frequencies()
            counts = self._get_sweep_counts()
            
            self._send_data({
                "status": "SWEEP_COMPLETE",
                "exp_id": exp_id,
                "frequencies_khz": freqs,
                "pmt_counts": counts
            }, category="SWEEP_COMPLETE")
            
        except Exception as e:
            self.logger.exception("RUN_SWEEP failed")
            self._send_data({
                "status": "SWEEP_FAILED",
                "exp_id": exp_id,
                "error": str(e)
            }, category="ERROR")
    
    def _handle_camera_trigger(self, exp_id):
        """Handle CAMERA_TRIGGER command."""
        self.logger.info(f"CAMERA_TRIGGER (exp: {exp_id})")
        try:
            self.camera_trigger_kernel()
            self._send_status("CAMERA_TRIGGERED", {"exp_id": exp_id})
        except Exception as e:
            self.logger.exception("CAMERA_TRIGGER failed")
            self._send_data({
                "status": "CAMERA_TRIGGER_FAILED",
                "error": str(e),
                "exp_id": exp_id
            }, category="ERROR")
    
    def _handle_start_camera_inf(self, exp_id):
        """Handle START_CAMERA_INF command."""
        self.logger.info(f"START_CAMERA_INF (exp: {exp_id})")
        self.camera_inf_active = True
        self._send_status("CAMERA_INF_STARTED", {"exp_id": exp_id})
    
    def _handle_stop_camera(self, exp_id):
        """Handle STOP_CAMERA command."""
        self.logger.info(f"STOP_CAMERA (exp: {exp_id})")
        self.camera_inf_active = False
        self._send_status("CAMERA_STOPPED", {"exp_id": exp_id})
    
    def _handle_pmt_measure(self, msg, exp_id):
        """Handle PMT_MEASURE command."""
        duration_ms = float(msg.get("duration_ms", 100.0))
        self.logger.info(f"PMT_MEASURE: duration={duration_ms}ms (exp: {exp_id})")
        
        try:
            counts = self.pmt_measure_kernel(duration_ms)
            self._send_data({
                "status": "PMT_MEASURE_COMPLETE",
                "exp_id": exp_id,
                "counts": counts,
                "duration_ms": duration_ms
            }, category="PMT_MEASURE")
        except Exception as e:
            self.logger.exception("PMT_MEASURE failed")
            self._send_data({
                "status": "PMT_MEASURE_FAILED",
                "error": str(e),
                "exp_id": exp_id
            }, category="ERROR")
    
    def _handle_cam_sweep(self, msg, exp_id):
        """Handle CAM_SWEEP command."""
        self.logger.info(f"CAM_SWEEP (exp: {exp_id})")
        self._send_status("CAM_SWEEP_NOT_IMPLEMENTED", {"exp_id": exp_id})
    
    def _handle_secular_sweep(self, msg, exp_id):
        """Handle SECULAR_SWEEP command."""
        self.logger.info(f"SECULAR_SWEEP (exp: {exp_id})")
        self._send_status("SECULAR_SWEEP_NOT_IMPLEMENTED", {"exp_id": exp_id})
    
    def _handle_emergency_zero(self, exp_id):
        """Handle emergency shutdown."""
        self.logger.critical(f"EMERGENCY_ZERO triggered! (exp: {exp_id})")
        try:
            self.apply_safety_defaults_host()
            self._send_status("EMERGENCY_ACK", {"exp_id": exp_id})
        except Exception as e:
            self.logger.exception("Emergency shutdown partially failed")
            self._send_status("EMERGENCY_PARTIAL", {
                "exp_id": exp_id,
                "error": str(e)
            })
    
    def _handle_ping(self, exp_id):
        """Handle PING command (health check)."""
        self._send_status("PONG", {
            "exp_id": exp_id,
            "timestamp": time.time()
        })
    
    def _handle_stop_worker(self, exp_id):
        """Handle STOP_WORKER command (graceful shutdown)."""
        self.logger.info(f"STOP_WORKER received (exp: {exp_id})")
        self.running = False
        self._send_status("WORKER_STOPPING", {"exp_id": exp_id})
    
    # ==================== KERNEL METHODS ====================
    
    @rpc
    def apply_safety_defaults_host(self):
        """Host-side wrapper for safety defaults."""
        self.core.break_realtime()
        self.apply_safety_defaults_kernel()
    
    @kernel
    def apply_safety_defaults_kernel(self):
        """Apply safety defaults on kernel."""
        if self.ec:
            self.ec.set_ec(0.0 * V, 0.0 * V)
        if self.comp:
            self.comp.set_hor_ver(0.0 * V, 0.0 * V)
        if self.raman:
            self.raman.set_beams(0.05, 0.05, 0, 0)
        # Turn off all DDS
        if self.sweep:
            self.sweep.dds_axial.cfg_sw(False)
            self.sweep.dds_radial.cfg_sw(False)
    
    @kernel
    def set_dc_hardware(self, ec1: TFloat, ec2: TFloat, comp_h: TFloat, comp_v: TFloat):
        """Apply DC voltages."""
        self.core.break_realtime()
        if self.ec:
            self.ec.set_ec(ec1 * V, ec2 * V)
        if self.comp:
            self.comp.set_hor_ver(comp_h * V, comp_v * V)
    
    @kernel
    def set_cooling_hardware(self, amp0: TFloat, amp1: TFloat, sw0: TInt32, sw1: TInt32):
        """Set cooling beam parameters."""
        self.core.break_realtime()
        if self.raman:
            self.raman.set_beams(amp0, amp1, sw0, sw1)
    
    @kernel
    def camera_trigger_kernel(self):
        """Trigger camera."""
        self.core.break_realtime()
        if self.sweep:
            self.sweep.cam.trigger_us(10.0)
    
    @kernel
    def pmt_measure_kernel(self, duration_ms: TFloat) -> TInt32:
        """Measure PMT counts."""
        self.core.break_realtime()
        if self.sweep:
            return self.sweep.pmt.count(duration_ms)
        return 0
    
    @kernel
    def _run_sweep_kernel(self, target_khz: TFloat, span_khz: TFloat, steps: TInt32,
                         att_db: TFloat, on_ms: TFloat, off_ms: TFloat):
        """Execute frequency sweep."""
        from artiq.experiment import parallel
        
        self.core.break_realtime()
        
        if steps > 1000:
            raise ValueError("Sweep steps exceed buffer size (max 1000)")
        
        start_f = (target_khz - span_khz / 2.0) * kHz
        step_size = (span_khz * kHz) / (steps - 1) if steps > 1 else 0.0 * kHz
        
        if self.sweep:
            # Initialize selected DDS
            self.sweep.selected_dds.device_setup()
            self.sweep.selected_dds.set_att(att_db * dB)
            
            self._sweep_num_steps = steps
            
            for i in range(steps):
                freq = start_f + (i * step_size)
                self._sweep_freqs[i] = freq / kHz
                
                # Set frequency and execute
                self.sweep.selected_dds.set_frequency(freq)
                with parallel:
                    self.sweep.selected_dds.cfg_sw(True)
                    self.sweep.pmt.count(on_ms)
                
                self.sweep.selected_dds.cfg_sw(False)
                self._sweep_counts[i] = self.sweep.pmt.pmt.fetch_count()
                delay(off_ms * ms)
    
    @rpc
    def _get_sweep_frequencies(self):
        """Get sweep frequencies."""
        return self._sweep_freqs[:self._sweep_num_steps]
    
    @rpc
    def _get_sweep_counts(self):
        """Get sweep counts."""
        return self._sweep_counts[:self._sweep_num_steps]


# No make_fragment_scan_exp needed - this is a standalone EnvExperiment!
# To run: artiq_run Artiq_Worker.py
# Or submit via ARTIQ dashboard as a regular experiment
