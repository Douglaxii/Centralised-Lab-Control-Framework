"""
ZmqWorker.py - ARTIQ worker with ZMQ integration.

Receives commands from manager via ZMQ and executes on ARTIQ hardware.
Sends data/results back to manager via ZMQ.

Command types handled:
    - SET_DC: Set endcap and compensation voltages
    - SET_COOLING: Set Raman cooling beam parameters
    - RUN_SWEEP: Run secular frequency sweep
    - CAMERA_TRIGGER: Send TTL trigger to camera
    - START_CAMERA_INF: Acknowledge camera infinite mode
    - STOP_CAMERA: Acknowledge camera stop
    - PMT_MEASURE: Simple PMT measurement
    - CAM_SWEEP: Sweep with camera triggers
    - SECULAR_SWEEP: Sweep without camera (axial/radial)
    - EMERGENCY_ZERO: Safety shutdown

Usage:
    artiq_run repository/ZmqWorker.py
"""

import sys
import time
import json
import zmq
import logging

# Add repository to path for imports
sys.path.insert(0, "D:/artiq/artiq-master/repository")

from ndscan.experiment import ExpFragment, FloatParam, IntParam, BoolParam, make_fragment_scan_exp
from artiq.experiment import *
from artiq.language import rpc
from oitg.units import V, MHz, kHz, ms, us, dB

# Import fragments (lowercase)
from fragments.ec import ec
from fragments.comp import comp
from fragments.raman_control import raman_control
from fragments.sweeping import sweeping


class ZmqWorker(ExpFragment):
    """
    ARTIQ Worker with ZMQ integration.
    
    Receives commands from manager and executes on hardware.
    """
    
    def build_fragment(self):
        """Build the experiment fragment."""
        self.setattr_device("core")
        
        # Hardware fragments (lowercase class names)
        self.setattr_fragment("ec", ec)
        self.setattr_fragment("comp", comp)
        self.setattr_fragment("raman", raman_control)
        self.setattr_fragment("sweep", sweeping)
        
        # Initialize logger
        self.logger = logging.getLogger("ARTIQ.Worker")
        
        # ZMQ context (initialized in host_setup)
        self.zmq_ctx = None
        self.sub = None  # Subscriber for commands
        self.push = None  # Push for data
        
        # Worker state
        self.running = True
        self.camera_inf_active = False
        self.last_comm_time = time.time()
        
        # Configuration (match manager config)
        self.master_ip = "127.0.0.1"
        self.cmd_port = 5555
        self.data_port = 5556
        self.watchdog_timeout = 30.0
    
    def prepare(self):
        """Prepare before run - called once before kernel execution."""
        self.logger.info("ZmqWorker: Initializing ZMQ...")
        self._init_zmq()
    
    def run(self):
        """Main worker loop - runs on host."""
        self.logger.info("=" * 50)
        self.logger.info("ARTIQ ZMQ Worker: Starting...")
        
        # Initialize hardware via kernel
        self.init_hardware()
        
        self.logger.info("ARTIQ Worker: Online. Waiting for commands...")
        
        # Command loop
        while self.running:
            try:
                self._process_commands()
                self._check_watchdog()
                time.sleep(0.001)  # Small delay to prevent busy-waiting
            except KeyboardInterrupt:
                self.logger.info("Worker stopped manually.")
                break
            except Exception as e:
                self.logger.error(f"Error in Worker Loop: {e}")
        
        self._cleanup()
    
    def _init_zmq(self):
        """Initialize ZMQ sockets."""
        try:
            self.zmq_ctx = zmq.Context()
            
            # Command subscriber (SUB) - receives from manager's PUB
            self.sub = self.zmq_ctx.socket(zmq.SUB)
            cmd_addr = f"tcp://{self.master_ip}:{self.cmd_port}"
            self.sub.connect(cmd_addr)
            # Subscribe to "ARTIQ" and "ALL" topics
            self.sub.setsockopt_string(zmq.SUBSCRIBE, "ARTIQ")
            self.sub.setsockopt_string(zmq.SUBSCRIBE, "ALL")
            # Set receive timeout
            self.sub.setsockopt(zmq.RCVTIMEO, 100)
            
            # Data pusher (PUSH) - sends to manager's PULL
            self.push = self.zmq_ctx.socket(zmq.PUSH)
            data_addr = f"tcp://{self.master_ip}:{self.data_port}"
            self.push.connect(data_addr)
            self.push.setsockopt(zmq.LINGER, 0)
            
            self.logger.info(f"ZMQ connected to {self.master_ip}")
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
            
            # Execute command
            if cmd_type == "SET_DC":
                self._handle_set_dc(payload, exp_id)
            elif cmd_type == "SET_COOLING":
                self._handle_set_cooling(payload, exp_id)
            elif cmd_type == "RUN_SWEEP":
                self._handle_run_sweep(payload, exp_id)
            elif cmd_type == "CAMERA_TRIGGER":
                self._handle_camera_trigger(exp_id)
            elif cmd_type == "START_CAMERA_INF":
                self._handle_start_camera_inf(exp_id)
            elif cmd_type == "STOP_CAMERA":
                self._handle_stop_camera(exp_id)
            elif cmd_type == "PMT_MEASURE":
                self._handle_pmt_measure(msg, exp_id)
            elif cmd_type == "CAM_SWEEP":
                self._handle_cam_sweep(msg, exp_id)
            elif cmd_type == "SECULAR_SWEEP":
                self._handle_secular_sweep(msg, exp_id)
            elif cmd_type == "EMERGENCY_ZERO":
                self._handle_emergency_zero(exp_id)
            else:
                self.logger.warning(f"Unknown command type: {cmd_type}")
                
        except zmq.Again:
            # No message available
            pass
        except Exception as e:
            self.logger.error(f"Error processing command: {e}")
    
    def _handle_set_dc(self, payload, exp_id):
        """Handle SET_DC command."""
        ec1 = payload.get("ec1", 0.0)
        ec2 = payload.get("ec2", 0.0)
        comp_h = payload.get("comp_h", 0.0)
        comp_v = payload.get("comp_v", 0.0)
        
        self.logger.info(f"SET_DC: ec1={ec1}, ec2={ec2}, comp_h={comp_h}, comp_v={comp_v}")
        
        # Apply via kernel
        self.set_dc_hardware(ec1, ec2, comp_h, comp_v)
        
        # Send acknowledgment
        self._send_status("DC_UPDATED", {
            "ec1": ec1, "ec2": ec2,
            "comp_h": comp_h, "comp_v": comp_v,
            "exp_id": exp_id
        })
    
    def _handle_set_cooling(self, payload, exp_id):
        """Handle SET_COOLING command."""
        sw0 = int(payload.get("sw0", 0))
        sw1 = int(payload.get("sw1", 0))
        amp0 = payload.get("amp0", 0.05)
        amp1 = payload.get("amp1", 0.05)
        
        self.logger.info(f"SET_COOLING: amp0={amp0}, amp1={amp1}, sw0={sw0}, sw1={sw1}")
        
        # Apply via kernel
        self.set_cooling_hardware(amp0, amp1, sw0, sw1)
        
        # Send acknowledgment
        self._send_status("COOLING_UPDATED", {
            "amp0": amp0, "amp1": amp1,
            "sw0": sw0, "sw1": sw1,
            "exp_id": exp_id
        })
    
    def _handle_run_sweep(self, payload, exp_id):
        """Handle RUN_SWEEP command."""
        target = payload.get("target_frequency_khz", 400.0)
        span = payload.get("span_khz", 40.0)
        steps = int(payload.get("steps", 41))
        att = payload.get("attenuation_db", 25.0)
        on_t = payload.get("on_time_ms", 100.0)
        off_t = payload.get("off_time_ms", 100.0)
        
        self.logger.info(f"RUN_SWEEP: target={target}kHz, span={span}kHz, steps={steps}")
        
        try:
            # Execute sweep
            freqs, counts = self.run_sweep_kernel(target, span, steps, att, on_t, off_t)
            
            # Send results
            self._send_data({
                "status": "SWEEP_COMPLETE",
                "exp_id": exp_id,
                "frequencies_khz": freqs,
                "pmt_counts": counts
            }, category="SWEEP_COMPLETE")
            
        except Exception as e:
            self.logger.error(f"Sweep failed: {e}")
            self._send_data({
                "status": "SWEEP_FAILED",
                "exp_id": exp_id,
                "error": str(e)
            }, category="ERROR")
    
    def _handle_camera_trigger(self, exp_id):
        """Handle CAMERA_TRIGGER command."""
        self.logger.info(f"CAMERA_TRIGGER (exp: {exp_id})")
        self.trigger_camera_kernel()
        self._send_status("CAMERA_TRIGGERED", {"exp_id": exp_id})
    
    def _handle_start_camera_inf(self, exp_id):
        """Handle START_CAMERA_INF command."""
        self.logger.info(f"START_CAMERA_INF (exp: {exp_id})")
        self.camera_inf_active = True
        self._send_status("CAMERA_INF_ACK", {
            "exp_id": exp_id,
            "status": "ready_for_ttl"
        })
    
    def _handle_stop_camera(self, exp_id):
        """Handle STOP_CAMERA command."""
        self.logger.info(f"STOP_CAMERA (exp: {exp_id})")
        self.camera_inf_active = False
        self._send_status("CAMERA_STOP_ACK", {"exp_id": exp_id})
    
    def _handle_pmt_measure(self, msg, exp_id):
        """Handle PMT_MEASURE command."""
        duration_ms = msg.get("duration_ms", 100.0)
        self.logger.info(f"PMT_MEASURE: duration={duration_ms}ms (exp: {exp_id})")
        
        counts = self.pmt_measure_kernel(duration_ms)
        
        self._send_data({
            "counts": counts,
            "duration_ms": duration_ms,
            "exp_id": exp_id
        }, category="PMT_MEASURE_RESULT")
    
    def _handle_cam_sweep(self, msg, exp_id):
        """Handle CAM_SWEEP command."""
        params = msg.get("params", {})
        
        target = params.get("target_frequency_khz", 400.0)
        span = params.get("span_khz", 40.0)
        steps = int(params.get("steps", 41))
        on_t = params.get("on_time_ms", 100.0)
        off_t = params.get("off_time_ms", 100.0)
        att = params.get("attenuation_db", 25.0)
        
        self.logger.info(f"CAM_SWEEP: {target}kHz span={span}kHz steps={steps}")
        
        try:
            freqs, counts = self.run_cam_sweep_kernel(target, span, steps, on_t, off_t, att)
            
            self._send_data({
                "frequencies_khz": freqs,
                "pmt_counts": counts,
                "exp_id": exp_id
            }, category="CAM_SWEEP_COMPLETE")
        except Exception as e:
            self.logger.error(f"CAM_SWEEP failed: {e}")
            self._send_data({
                "error": str(e),
                "exp_id": exp_id
            }, category="CAM_SWEEP_ERROR")
    
    def _handle_secular_sweep(self, msg, exp_id):
        """Handle SECULAR_SWEEP command."""
        params = msg.get("params", {})
        
        target = params.get("target_frequency_khz", 400.0)
        span = params.get("span_khz", 40.0)
        steps = int(params.get("steps", 41))
        on_t = params.get("on_time_ms", 100.0)
        off_t = params.get("off_time_ms", 100.0)
        att = params.get("attenuation_db", 25.0)
        dds_choice = params.get("dds_choice", "axial")
        
        self.logger.info(f"SECULAR_SWEEP: {target}kHz DDS={dds_choice}")
        
        try:
            freqs, counts = self.run_secular_sweep_kernel(
                target, span, steps, on_t, off_t, att, dds_choice
            )
            
            self._send_data({
                "frequencies_khz": freqs,
                "pmt_counts": counts,
                "exp_id": exp_id
            }, category="SECULAR_SWEEP_COMPLETE")
        except Exception as e:
            self.logger.error(f"SECULAR_SWEEP failed: {e}")
            self._send_data({
                "error": str(e),
                "exp_id": exp_id
            }, category="SECULAR_SWEEP_ERROR")
    
    def _handle_emergency_zero(self, exp_id):
        """Handle EMERGENCY_ZERO command."""
        self.logger.error(f"EMERGENCY_ZERO triggered! (exp: {exp_id})")
        self.apply_safety_defaults()
        self._send_status("EMERGENCY_ACK", {"exp_id": exp_id})
    
    def _check_watchdog(self):
        """Check for connection loss."""
        elapsed = time.time() - self.last_comm_time
        if elapsed > self.watchdog_timeout:
            self.logger.error(f"WATCHDOG: Connection lost for {elapsed:.1f}s")
            self.apply_safety_defaults()
            self.last_comm_time = time.time()  # Reset to prevent spam
    
    def _send_data(self, payload, category="DATA"):
        """Send data to manager."""
        try:
            packet = {
                "timestamp": time.time(),
                "source": "ARTIQ",
                "category": category,
                "payload": payload
            }
            self.push.send_json(packet, flags=zmq.NOBLOCK)
        except zmq.Again:
            pass  # Drop if would block
        except Exception as e:
            self.logger.error(f"Failed to send data: {e}")
    
    def _send_status(self, status, data):
        """Send status update to manager."""
        self._send_data({"status": status, **data}, category="STATUS")
    
    def _cleanup(self):
        """Cleanup resources."""
        self.logger.info("Cleaning up...")
        self.apply_safety_defaults()
        if self.sub:
            self.sub.close()
        if self.push:
            self.push.close()
        if self.zmq_ctx:
            self.zmq_ctx.term()
        self.logger.info("Worker shutdown complete")
    
    # ========================================================================
    # Kernel methods - these run on the ARTIQ core device
    # ========================================================================
    
    @kernel
    def init_hardware(self):
        """Initialize hardware with safe defaults."""
        self.core.reset()
        self.core.break_realtime()
        self.ec.device_setup()
        self.comp.device_setup()
        self.raman.device_setup()
        self.sweep.device_setup()
        
        # Apply safety defaults
        self.ec.set_ec(0.0 * V, 0.0 * V)
        self.comp.set_hor_ver(0.0 * V, 0.0 * V)
        self.raman.set_beams(0.05, 0.05, 0, 0)
    
    @kernel
    def apply_safety_defaults(self):
        """Apply safety defaults (0V, beams off)."""
        self.core.break_realtime()
        self.ec.set_ec(0.0 * V, 0.0 * V)
        self.comp.set_hor_ver(0.0 * V, 0.0 * V)
        self.raman.set_beams(0.05, 0.05, 0, 0)
    
    @kernel
    def set_dc_hardware(self, ec1: TFloat, ec2: TFloat, comp_h: TFloat, comp_v: TFloat):
        """Apply DC voltages on hardware."""
        self.core.break_realtime()
        self.ec.set_ec(ec1 * V, ec2 * V)
        self.comp.set_hor_ver(comp_h * V, comp_v * V)
    
    @kernel
    def set_cooling_hardware(self, amp0: TFloat, amp1: TFloat, sw0: TInt, sw1: TInt):
        """Apply cooling parameters on hardware."""
        self.core.break_realtime()
        self.raman.set_beams(amp0, amp1, sw0, sw1)
    
    @kernel
    def trigger_camera_kernel(self):
        """Send TTL pulse to camera."""
        self.core.break_realtime()
        self.sweep.cam.pulse(10 * us)
    
    @kernel
    def pmt_measure_kernel(self, duration_ms: TFloat) -> TInt:
        """Simple PMT measurement."""
        self.core.break_realtime()
        self.sweep.pmt.gate_rising(duration_ms * ms)
        delay(duration_ms * ms)
        return self.sweep.pmt.fetch_count()
    
    @kernel
    def run_sweep_kernel(self, target_khz: TFloat, span_khz: TFloat, steps: TInt,
                         att_db: TFloat, on_ms: TFloat, off_ms: TFloat) -> TTuple([TList(TFloat), TList(TInt32)]):
        """Run secular sweep on hardware."""
        from artiq.experiment import parallel
        from oitg.units import kHz, ms, dB
        
        self.core.break_realtime()
        
        # Calculate frequency range
        start_f = (target_khz - span_khz / 2.0) * kHz
        step_size = (span_khz * kHz) / (steps - 1)
        
        # Initialize DDS
        self.sweep.dds.init()
        self.sweep.dds.set_att(att_db * dB)
        
        # Arrays for results (will be returned via RPC)
        freqs = [0.0] * steps
        counts = [0] * steps
        
        for i in range(steps):
            freq = start_f + (i * step_size)
            freqs[i] = float(freq / kHz)
            
            # Set frequency and execute
            self.sweep.dds.set(frequency=freq)
            with parallel:
                self.sweep.dds.cfg_sw(True)
                self.sweep.pmt.gate_rising(on_ms * ms)
            
            self.sweep.dds.cfg_sw(False)
            counts[i] = int(self.sweep.pmt.fetch_count())
            
            delay(off_ms * ms)
        
        return freqs, counts
    
    @kernel
    def run_cam_sweep_kernel(self, target_khz: TFloat, span_khz: TFloat, steps: TInt,
                             on_ms: TFloat, off_ms: TFloat, att_db: TFloat) -> TTuple([TList(TFloat), TList(TInt32)]):
        """Run sweep with camera triggers."""
        from artiq.experiment import parallel
        from oitg.units import kHz, ms, dB
        
        self.core.break_realtime()
        
        start_f = (target_khz - span_khz / 2.0) * kHz
        step_size = (span_khz * kHz) / (steps - 1)
        
        self.sweep.dds.init()
        self.sweep.dds.set_att(att_db * dB)
        
        freqs = [0.0] * steps
        counts = [0] * steps
        
        for i in range(steps):
            freq = start_f + (i * step_size)
            freqs[i] = float(freq / kHz)
            
            self.sweep.dds.set(frequency=freq)
            with parallel:
                self.sweep.dds.cfg_sw(True)
                self.sweep.pmt.gate_rising(on_ms * ms)
                self.sweep.cam.pulse(on_ms * ms)
            
            self.sweep.dds.cfg_sw(False)
            counts[i] = int(self.sweep.pmt.fetch_count())
            
            delay(off_ms * ms)
        
        return freqs, counts
    
    @kernel
    def run_secular_sweep_kernel(self, target_khz: TFloat, span_khz: TFloat, steps: TInt,
                                  on_ms: TFloat, off_ms: TFloat, att_db: TFloat,
                                  dds_choice: TStr) -> TTuple([TList(TFloat), TList(TInt32)]):
        """Run secular sweep with DDS selection."""
        from artiq.experiment import parallel
        from oitg.units import kHz, ms, dB
        
        self.core.break_realtime()
        
        # Select DDS based on choice
        if dds_choice == "axial":
            dds = self.sweep.dds_axial
        else:
            dds = self.sweep.dds_radial
        
        start_f = (target_khz - span_khz / 2.0) * kHz
        step_size = (span_khz * kHz) / (steps - 1)
        
        dds.init()
        dds.set_att(att_db * dB)
        
        freqs = [0.0] * steps
        counts = [0] * steps
        
        for i in range(steps):
            freq = start_f + (i * step_size)
            freqs[i] = float(freq / kHz)
            
            dds.set(frequency=freq)
            with parallel:
                dds.cfg_sw(True)
                self.sweep.pmt.gate_rising(on_ms * ms)
            
            dds.cfg_sw(False)
            counts[i] = int(self.sweep.pmt.fetch_count())
            
            delay(off_ms * ms)
        
        return freqs, counts


# Create standalone experiment class (PascalCase)
ZmqWorkerExp = make_fragment_scan_exp(ZmqWorker)
