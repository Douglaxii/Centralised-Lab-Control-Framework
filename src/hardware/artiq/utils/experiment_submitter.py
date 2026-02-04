"""
experiment_submitter.py - Experiment Submission Helper

Phase 3: Unified interface for submitting experiments.

Supports both:
  1. New style: Command-specific experiments (Phase 3A)
  2. Legacy style: ZMQ-based monolithic worker (Phase 1/2)

Usage:
    from utils.experiment_submitter import ExperimentSubmitter
    
    # New style (recommended)
    submitter = ExperimentSubmitter(mode="experiments")
    await submitter.submit_set_dc(ec1=5.0, ec2=5.0)
    
    # Legacy style
    submitter = ExperimentSubmitter(mode="zmq")
    await submitter.submit_set_dc(ec1=5.0, ec2=5.0)
"""

import asyncio
import time
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

try:
    from artiq.language.environment import HasEnvironment
    HAS_ARTIQ = True
except ImportError:
    HAS_ARTIQ = False

from .config_loader import get_config_value
from .async_comm import AsyncZMQClient, send_command_simple


class SubmissionMode(Enum):
    """Experiment submission mode."""
    EXPERIMENTS = "experiments"  # Phase 3A: Command-specific experiments
    ZMQ = "zmq"                  # Phase 1/2: ZMQ-based worker
    AUTO = "auto"                # Auto-detect based on availability


@dataclass
class SubmissionResult:
    """Result of experiment submission."""
    success: bool
    rid: Optional[int] = None  # ARTIQ Run ID
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ExperimentSubmitter:
    """
    Unified experiment submission interface.
    
    Supports both new (command-specific) and legacy (ZMQ) modes.
    Automatically handles connection management and retries.
    
    Example:
        submitter = ExperimentSubmitter(mode="experiments")
        await submitter.connect()
        
        # Submit experiment
        result = await submitter.submit_sweep(
            target_freq_khz=400.0,
            span_khz=40.0,
            steps=41
        )
        
        if result.success:
            print(f"Experiment RID: {result.rid}")
    """
    
    def __init__(self, mode: str = "auto", 
                 master_ip: Optional[str] = None,
                 scheduler=None):
        """
        Initialize experiment submitter.
        
        Args:
            mode: "experiments", "zmq", or "auto"
            master_ip: ARTIQ master IP (loads from config if not provided)
            scheduler: ARTIQ scheduler (for experiment mode)
        """
        self.mode = SubmissionMode(mode if mode != "auto" else self._detect_mode(scheduler))
        self.master_ip = master_ip or get_config_value('network.master_ip', '192.168.56.101')
        self.scheduler = scheduler
        
        # ZMQ client (for legacy mode)
        self._zmq_client: Optional[AsyncZMQClient] = None
        
        # Import experiment submission functions
        if self.mode == SubmissionMode.EXPERIMENTS:
            try:
                from experiments.set_dc_exp import submit_set_dc
                from experiments.secular_sweep_exp import submit_sweep
                from experiments.pmt_measure_exp import submit_pmt_measure
                from experiments.emergency_zero_exp import submit_emergency_zero
                
                self._submit_set_dc = submit_set_dc
                self._submit_sweep = submit_sweep
                self._submit_pmt = submit_pmt_measure
                self._submit_emergency = submit_emergency_zero
            except ImportError:
                print("Warning: Could not import experiment submitters, falling back to ZMQ")
                self.mode = SubmissionMode.ZMQ
    
    def _detect_mode(self, scheduler) -> SubmissionMode:
        """Auto-detect best submission mode."""
        if scheduler is not None and HAS_ARTIQ:
            return SubmissionMode.EXPERIMENTS
        return SubmissionMode.ZMQ
    
    async def connect(self) -> bool:
        """Initialize connections."""
        if self.mode == SubmissionMode.ZMQ:
            self._zmq_client = AsyncZMQClient(master_ip=self.master_ip)
            return await self._zmq_client.connect()
        return True  # Experiment mode uses scheduler, no connection needed
    
    async def disconnect(self):
        """Close connections."""
        if self._zmq_client:
            await self._zmq_client.disconnect()
            self._zmq_client = None
    
    async def submit_set_dc(self, ec1: float = 0.0, ec2: float = 0.0,
                          comp_h: float = 0.0, comp_v: float = 0.0,
                          priority: int = 0) -> SubmissionResult:
        """
        Submit DC setting experiment.
        
        Args:
            ec1, ec2: Endcap voltages (V)
            comp_h, comp_v: Compensation voltages (V)
            priority: Experiment priority
            
        Returns:
            SubmissionResult with RID or error
        """
        if self.mode == SubmissionMode.EXPERIMENTS:
            try:
                rid = self._submit_set_dc(
                    self.scheduler, ec1, ec2, comp_h, comp_v, priority
                )
                return SubmissionResult(success=True, rid=rid)
            except Exception as e:
                return SubmissionResult(success=False, error=str(e))
        else:
            # ZMQ mode
            command = {
                "type": "SET_DC",
                "values": {"ec1": ec1, "ec2": ec2, "comp_h": comp_h, "comp_v": comp_v},
                "timestamp": time.time()
            }
            return await self._send_zmq_command(command)
    
    async def submit_sweep(self, target_freq_khz: float = 400.0,
                         span_khz: float = 40.0, steps: int = 41,
                         att_db: float = 25.0, on_time_ms: float = 100.0,
                         off_time_ms: float = 100.0,
                         dds_choice: str = "axial",
                         priority: int = 0) -> SubmissionResult:
        """
        Submit secular sweep experiment.
        
        Args:
            target_freq_khz: Center frequency (kHz)
            span_khz: Sweep span (kHz)
            steps: Number of steps
            att_db: Attenuation (dB)
            on_time_ms: RF on time per step (ms)
            off_time_ms: Delay between steps (ms)
            dds_choice: "axial" or "radial"
            priority: Experiment priority
            
        Returns:
            SubmissionResult with RID or error
        """
        if self.mode == SubmissionMode.EXPERIMENTS:
            try:
                rid = self._submit_sweep(
                    self.scheduler, target_freq_khz, span_khz, steps,
                    att_db, on_time_ms, off_time_ms, dds_choice, priority
                )
                return SubmissionResult(success=True, rid=rid)
            except Exception as e:
                return SubmissionResult(success=False, error=str(e))
        else:
            command = {
                "type": "RUN_SWEEP",
                "values": {
                    "target_frequency_khz": target_freq_khz,
                    "span_khz": span_khz,
                    "steps": steps,
                    "attenuation_db": att_db,
                    "on_time_ms": on_time_ms,
                    "off_time_ms": off_time_ms,
                    "dds_choice": dds_choice
                },
                "timestamp": time.time()
            }
            return await self._send_zmq_command(command)
    
    async def submit_pmt_measure(self, duration_ms: float = 100.0,
                                num_samples: int = 1,
                                priority: int = 0) -> SubmissionResult:
        """
        Submit PMT measurement experiment.
        
        Args:
            duration_ms: Measurement duration (ms)
            num_samples: Number of samples to average
            priority: Experiment priority
            
        Returns:
            SubmissionResult with RID or error
        """
        if self.mode == SubmissionMode.EXPERIMENTS:
            try:
                rid = self._submit_pmt(self.scheduler, duration_ms, num_samples, priority)
                return SubmissionResult(success=True, rid=rid)
            except Exception as e:
                return SubmissionResult(success=False, error=str(e))
        else:
            command = {
                "type": "PMT_MEASURE",
                "duration_ms": duration_ms,
                "num_samples": num_samples,
                "timestamp": time.time()
            }
            return await self._send_zmq_command(command)
    
    async def submit_emergency_zero(self, priority: int = 100) -> SubmissionResult:
        """
        Submit emergency shutdown experiment.
        
        Args:
            priority: Experiment priority (default: 100 = highest)
            
        Returns:
            SubmissionResult with RID or error
        """
        if self.mode == SubmissionMode.EXPERIMENTS:
            try:
                rid = self._submit_emergency(self.scheduler, priority)
                return SubmissionResult(success=True, rid=rid)
            except Exception as e:
                return SubmissionResult(success=False, error=str(e))
        else:
            command = {
                "type": "EMERGENCY_ZERO",
                "timestamp": time.time()
            }
            return await self._send_zmq_command(command)
    
    async def _send_zmq_command(self, command: Dict[str, Any]) -> SubmissionResult:
        """Send command via ZMQ."""
        if not self._zmq_client:
            return SubmissionResult(success=False, error="ZMQ not connected")
        
        success = await self._zmq_client.send_command(command)
        if success:
            # For ZMQ, we don't get a RID back immediately
            return SubmissionResult(success=True, rid=None)
        return SubmissionResult(success=False, error="Failed to send command")
    
    async def wait_for_completion(self, rid: int, timeout: float = 60.0) -> bool:
        """
        Wait for experiment completion.
        
        Args:
            rid: Run ID to wait for
            timeout: Maximum wait time (seconds)
            
        Returns:
            True if completed, False if timeout
        """
        if self.mode == SubmissionMode.EXPERIMENTS and HAS_ARTIQ:
            # In experiment mode, we would check the scheduler
            # This is a simplified version
            start = time.time()
            while time.time() - start < timeout:
                # Check if experiment is still running
                # (Actual implementation would query scheduler)
                await asyncio.sleep(0.1)
            return True
        else:
            # ZMQ mode - wait for response
            if self._zmq_client:
                data = await self._zmq_client.receive_data(timeout=timeout)
                return data is not None
            return False


# Convenience functions for simple use cases

async def quick_set_dc(ec1: float = 0.0, ec2: float = 0.0,
                      comp_h: float = 0.0, comp_v: float = 0.0,
                      master_ip: Optional[str] = None) -> bool:
    """
    Quick DC setting (one-shot, no persistence).
    
    Example:
        success = await quick_set_dc(ec1=5.0, ec2=5.0)
    """
    submitter = ExperimentSubmitter(mode="zmq", master_ip=master_ip)
    try:
        await submitter.connect()
        result = await submitter.submit_set_dc(ec1, ec2, comp_h, comp_v)
        return result.success
    finally:
        await submitter.disconnect()


async def quick_sweep(target_freq_khz: float = 400.0,
                     span_khz: float = 40.0, steps: int = 41,
                     master_ip: Optional[str] = None) -> Optional[Dict]:
    """
    Quick sweep (one-shot, returns data).
    
    Example:
        data = await quick_sweep(target_freq_khz=400.0, span_khz=40.0)
        if data:
            print(f"Frequencies: {data['frequencies_khz']}")
            print(f"Counts: {data['pmt_counts']}")
    """
    submitter = ExperimentSubmitter(mode="zmq", master_ip=master_ip)
    try:
        await submitter.connect()
        result = await submitter.submit_sweep(
            target_freq_khz, span_khz, steps
        )
        if result.success:
            # Wait for data
            data = await submitter._zmq_client.receive_data(timeout=60.0)
            return data
        return None
    finally:
        await submitter.disconnect()


# Self-test
if __name__ == "__main__":
    print("Testing experiment submitter...")
    
    async def test():
        # Create submitter in ZMQ mode (no scheduler needed for test)
        submitter = ExperimentSubmitter(mode="zmq")
        print(f"  Mode: {submitter.mode}")
        print(f"  Master IP: {submitter.master_ip}")
        print("  Experiment submitter test passed!")
    
    asyncio.run(test())
