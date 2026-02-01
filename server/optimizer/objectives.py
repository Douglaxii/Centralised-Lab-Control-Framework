"""
Objective functions for each optimization phase.

Each phase has a specific goal and corresponding cost function that
balances multiple objectives (accuracy, speed, efficiency).
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger("optimizer.objectives")


class ObjectiveFunction(ABC):
    """Base class for objective functions."""
    
    @abstractmethod
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute scalarized cost from measurements.
        
        Args:
            params: Parameter values used
            measurements: Experimental measurements
            
        Returns:
            Tuple of (total_cost, cost_components)
        """
        pass
    
    @abstractmethod
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Check if optimization goal has been achieved."""
        pass


class BeLoadingObjective(ObjectiveFunction):
    """
    Phase I: Be+ Loading Optimization Objective
    
    Goal: Isolate exactly N_Be_target ions while minimizing:
    - Total cycle time
    - Cooling power
    - PI laser duration (KEY: reduces patch potentials)
    
    Cost Function:
        C = C_accuracy + C_stability + C_time + C_cooling + C_pi_duration
    """
    
    def __init__(
        self,
        target_ion_count: int = 1,
        target_secular_freq: float = 307.0,  # kHz
        w_accuracy: float = 100.0,    # Weight for count accuracy
        w_stability: float = 10.0,    # Weight for secular frequency stability
        w_time: float = 0.1,          # Weight for total time
        w_cooling: float = 5.0,       # Weight for cooling power
        w_pi: float = 20.0,           # Weight for PI duration (HIGH - key metric)
    ):
        """
        Initialize Be+ loading objective.
        
        Args:
            target_ion_count: Target number of Be+ ions
            target_secular_freq: Target secular frequency (kHz)
            w_accuracy: Weight for count accuracy penalty
            w_stability: Weight for stability metric
            w_time: Weight for process speed
            w_cooling: Weight for cooling power
            w_pi: Weight for PI laser duration (key metric)
        """
        self.target_ion_count = target_ion_count
        self.target_secular_freq = target_secular_freq
        self.w_accuracy = w_accuracy
        self.w_stability = w_stability
        self.w_time = w_time
        self.w_cooling = w_cooling
        self.w_pi = w_pi
        
        logger.info(
            f"BeLoadingObjective: target={target_ion_count} ions, "
            f"freq={target_secular_freq} kHz"
        )
    
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute scalarized cost for Be+ loading.
        
        Measurements expected:
        - ion_count: Number of ions detected
        - secular_freq: Measured secular frequency (kHz)
        - total_time_ms: Total experiment cycle time (ms)
        - cooling_power_mw: 397nm cooling power used (mW)
        """
        components = {}
        
        # === C_accuracy: Target Accuracy ===
        ion_count = measurements.get("ion_count", 0)
        
        if ion_count == self.target_ion_count:
            # Perfect match - no penalty
            c_accuracy = 0.0
        elif ion_count == 0:
            # Empty trap - HIGHEST PENALTY
            c_accuracy = 1000.0
        elif ion_count < self.target_ion_count:
            # Underloaded - high penalty
            c_accuracy = 500.0 * (self.target_ion_count - ion_count)
        else:
            # Overloaded - penalty proportional to excess
            c_accuracy = 200.0 * (ion_count - self.target_ion_count)
        
        components["accuracy"] = c_accuracy
        
        # === C_stability: Stability Metric ===
        secular_freq = measurements.get("secular_freq", self.target_secular_freq)
        freq_error = abs(secular_freq - self.target_secular_freq)
        # Normalize: 1% error = penalty of 1
        c_stability = freq_error / (self.target_secular_freq * 0.01)
        components["stability"] = self.w_stability * c_stability
        
        # === C_time: Process Speed ===
        total_time_ms = measurements.get("total_time_ms", 5000.0)
        # Normalize to ~5 second baseline
        c_time = total_time_ms / 1000.0
        components["time"] = self.w_time * c_time
        
        # === C_cooling: 397nm Power ===
        cooling_power = params.get("cooling_power_mw", 0.8)
        # Reward using minimum cooling power
        c_cooling = cooling_power
        components["cooling"] = self.w_cooling * c_cooling
        
        # === C_pi: PI Duration (KEY METRIC) ===
        pi_duration = params.get("be_pi_laser_duration_ms", 500.0)
        # Strong penalty for long PI exposure (patch potentials)
        # Normalize: 500ms baseline
        c_pi = pi_duration / 100.0  # 100ms units
        components["pi_duration"] = self.w_pi * c_pi
        
        # Total cost
        total_cost = sum(components.values())
        
        # Add base accuracy penalty
        total_cost += self.w_accuracy * c_accuracy
        
        logger.debug(
            f"Be+ Loading cost={total_cost:.2f}: "
            f"accuracy={c_accuracy:.2f}, stability={c_stability:.2f}, "
            f"time={c_time:.2f}, cooling={c_cooling:.2f}, pi={c_pi:.2f}"
        )
        
        return total_cost, components
    
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Check if we have the target number of stable Be+ ions."""
        ion_count = measurements.get("ion_count", 0)
        secular_freq = measurements.get("secular_freq", 0)
        
        # Must have exact target count
        if ion_count != self.target_ion_count:
            return False
        
        # Must have stable secular frequency (within 5%)
        freq_error = abs(secular_freq - self.target_secular_freq)
        if freq_error > self.target_secular_freq * 0.05:
            return False
        
        return True


class BeEjectionObjective(ObjectiveFunction):
    """
    Phase II: Be+ Ejection Optimization Objective
    
    Goal: Surgically reduce ion numbers from overload (N > N_target)
    to exactly N_target without emptying the trap.
    
    Strategy: Tune tickle pulse (amplitude and duration).
    
    Reward Logic:
    - Success (N == N_target): Max reward
    - Partial Progress: Scaled reward based on progress
    - Overshoot (N == 0): High penalty
    - Stagnant (N unchanged): Slight penalty
    """
    
    def __init__(
        self,
        target_ion_count: int = 1,
        w_success: float = -1000.0,   # Negative = reward
        w_progress: float = -100.0,   # Negative = reward
        w_overshoot: float = 500.0,   # Penalty for emptying
        w_stagnant: float = 50.0,     # Penalty for no change
        w_time: float = 0.5,          # Weight for pulse duration
    ):
        """
        Initialize Be+ ejection objective.
        
        Args:
            target_ion_count: Target ion count after ejection
            w_success: Reward for hitting target (negative = reward)
            w_progress: Reward for partial progress (negative = reward)
            w_overshoot: Penalty for emptying trap
            w_stagnant: Penalty for no change
            w_time: Weight for pulse duration (efficiency)
        """
        self.target_ion_count = target_ion_count
        self.w_success = w_success
        self.w_progress = w_progress
        self.w_overshoot = w_overshoot
        self.w_stagnant = w_stagnant
        self.w_time = w_time
        
        # Track previous state for progress calculation
        self.prev_ion_count: Optional[int] = None
        
        logger.info(f"BeEjectionObjective: target={target_ion_count} ions")
    
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute cost for Be+ ejection.
        
        Measurements expected:
        - ion_count: Number of ions after ejection attempt
        - initial_count: Number of ions before ejection
        """
        components = {}
        
        ion_count = measurements.get("ion_count", 0)
        initial_count = measurements.get("initial_count", ion_count)
        
        # === Success: N == N_target ===
        if ion_count == self.target_ion_count:
            components["success"] = self.w_success  # Large negative = reward
            components["progress"] = 0.0
            components["overshoot"] = 0.0
            components["stagnant"] = 0.0
            
        # === Overshoot: N == 0 (trap emptied) ===
        elif ion_count == 0:
            components["success"] = 0.0
            components["progress"] = 0.0
            components["overshoot"] = self.w_overshoot
            components["stagnant"] = 0.0
            
        # === Partial Progress: Moving toward target ===
        elif ion_count > self.target_ion_count:
            # Distance from target before and after
            dist_before = abs(initial_count - self.target_ion_count)
            dist_after = abs(ion_count - self.target_ion_count)
            
            if dist_after < dist_before:
                # Making progress - scaled reward
                progress_ratio = (dist_before - dist_after) / dist_before
                components["progress"] = self.w_progress * progress_ratio
                components["stagnant"] = 0.0
            else:
                # No progress or wrong direction
                components["progress"] = 0.0
                components["stagnant"] = self.w_stagnant
            
            components["success"] = 0.0
            components["overshoot"] = 0.0
            
        # === Under target (shouldn't happen with tickle) ===
        else:
            components["success"] = 0.0
            components["progress"] = 0.0
            components["overshoot"] = self.w_overshoot * 0.5
            components["stagnant"] = 0.0
        
        # === Time efficiency ===
        tickle_duration = params.get("tickle_duration_ms", 100.0)
        components["time"] = self.w_time * tickle_duration / 100.0
        
        total_cost = sum(components.values())
        
        logger.debug(
            f"Be+ Ejection cost={total_cost:.2f}: "
            f"N={ion_count} (from {initial_count}), "
            f"components={components}"
        )
        
        return total_cost, components
    
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """Check if ejection succeeded."""
        ion_count = measurements.get("ion_count", 0)
        return ion_count == self.target_ion_count


class HdLoadingObjective(ObjectiveFunction):
    """
    Phase III: HD+ Loading Optimization Objective
    
    Goal: Load a "Dark" HD+ ion into the Be+ crystal while minimizing:
    - Gas load (HD valve duration)
    - Thermal load (E-gun duration)
    
    Verification: Secular frequency sweep (HD+ is invisible)
    
    Cost Function:
        C = C_sweep + C_be_count + C_piezo + C_egun
    """
    
    def __init__(
        self,
        target_be_count: int = 1,
        be_secular_freq: float = 307.0,      # kHz
        hd_secular_freq: float = 277.0,      # kHz (coupled Be-HD radial)
        freq_tolerance_khz: float = 5.0,     # Tolerance for peak matching
        w_sweep_success: float = -1000.0,    # Reward for HD+ detection
        w_sweep_fail: float = 200.0,         # Penalty for no HD+
        w_be_count_match: float = -500.0,   # Reward for correct Be+ count
        w_be_count_wrong: float = 50.0,      # Penalty for wrong Be+ count
        w_piezo: float = 10.0,               # Weight for piezo efficiency
        w_egun: float = 5.0,                 # Weight for e-gun efficiency
    ):
        """
        Initialize HD+ loading objective.
        
        Args:
            target_be_count: Target Be+ count (should be 1)
            be_secular_freq: Expected Be+ secular frequency (kHz)
            hd_secular_freq: Expected coupled Be-HD frequency (kHz)
            freq_tolerance_khz: Tolerance for frequency matching
            w_sweep_success: Reward for detecting HD+
            w_sweep_fail: Penalty for not detecting HD+
            w_be_count_match: Reward for correct Be+ count
            w_be_count_wrong: Penalty for wrong Be+ count
            w_piezo: Weight for piezo voltage (efficiency)
            w_egun: Weight for e-gun duration (efficiency)
        """
        self.target_be_count = target_be_count
        self.be_secular_freq = be_secular_freq
        self.hd_secular_freq = hd_secular_freq
        self.freq_tolerance = freq_tolerance_khz
        self.w_sweep_success = w_sweep_success
        self.w_sweep_fail = w_sweep_fail
        self.w_be_count_match = w_be_count_match
        self.w_be_count_wrong = w_be_count_wrong
        self.w_piezo = w_piezo
        self.w_egun = w_egun
        
        logger.info(
            f"HdLoadingObjective: target Be+={target_be_count}, "
            f"Be freq={be_secular_freq} kHz, HD freq={hd_secular_freq} kHz"
        )
    
    def compute_cost(
        self,
        params: Dict[str, float],
        measurements: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute cost for HD+ loading.
        
        Measurements expected:
        - sweep_peak_freq: Detected peak frequency (kHz)
        - sweep_peak_found: Whether a peak was detected
        - ion_count: Be+ ion count after loading
        """
        components = {}
        
        # === C_sweep: Primary verification via secular sweep ===
        peak_freq = measurements.get("sweep_peak_freq", 0.0)
        peak_found = measurements.get("sweep_peak_found", False)
        
        if peak_found:
            # Check if peak matches HD+ target frequency
            hd_error = abs(peak_freq - self.hd_secular_freq)
            be_error = abs(peak_freq - self.be_secular_freq)
            
            if hd_error < self.freq_tolerance:
                # Success! Peak at coupled Be-HD frequency
                components["sweep"] = self.w_sweep_success
                logger.info(f"HD+ detected! Peak at {peak_freq:.1f} kHz")
            elif be_error < self.freq_tolerance:
                # Peak at Be+ only frequency - no HD+ loaded
                components["sweep"] = self.w_sweep_fail
                logger.debug(f"No HD+ detected. Peak at Be+ freq {peak_freq:.1f} kHz")
            else:
                # Peak at unexpected frequency
                components["sweep"] = self.w_sweep_fail * 1.5
                logger.warning(f"Unexpected peak at {peak_freq:.1f} kHz")
        else:
            # No peak found - ion loss or other issue
            components["sweep"] = self.w_sweep_fail * 2.0
            logger.warning("No peak found in secular sweep")
        
        # === C_be_count: Validate Be+ count ===
        ion_count = measurements.get("ion_count", 0)
        
        if ion_count == self.target_be_count:
            # Correct Be+ count maintained
            components["be_count"] = self.w_be_count_match
        else:
            # Wrong Be+ count (lost or gained ions)
            components["be_count"] = self.w_be_count_wrong * abs(
                ion_count - self.target_be_count
            )
        
        # === C_piezo: Piezo efficiency (minimize voltage) ===
        piezo_voltage = params.get("piezo", 0.0)
        # Cost proportional to voltage used
        components["piezo"] = self.w_piezo * (piezo_voltage / self.PIEZO_MAX)
        
        # === C_egun: E-gun efficiency (minimize duration) ===
        egun_duration = params.get("hd_egun_duration_ms", 1200.0)
        # Cost proportional to duration
        components["egun"] = self.w_egun * (egun_duration / 1000.0)
        
        total_cost = sum(components.values())
        
        logger.debug(
            f"HD+ Loading cost={total_cost:.2f}: "
            f"sweep={components['sweep']:.2f}, be_count={components['be_count']:.2f}, "
            f"piezo={components['piezo']:.2f}, egun={components['egun']:.2f}"
        )
        
        return total_cost, components
    
    def is_success(self, measurements: Dict[str, Any]) -> bool:
        """
        Check if HD+ loading succeeded.
        
        Success criteria:
        1. Sweep peak matches HD+ frequency
        2. Be+ count is correct
        """
        # Check Be+ count
        ion_count = measurements.get("ion_count", 0)
        if ion_count != self.target_be_count:
            return False
        
        # Check sweep
        peak_freq = measurements.get("sweep_peak_freq", 0.0)
        peak_found = measurements.get("sweep_peak_found", False)
        
        if not peak_found:
            return False
        
        hd_error = abs(peak_freq - self.hd_secular_freq)
        return hd_error < self.freq_tolerance
    
    # Class constant
    PIEZO_MAX = 4.0  # Maximum piezo voltage


# Factory function for creating objectives
def create_objective(phase: str, **kwargs) -> ObjectiveFunction:
    """
    Create an objective function for a given phase.
    
    Args:
        phase: One of "be_loading", "be_ejection", "hd_loading"
        **kwargs: Phase-specific parameters
        
    Returns:
        ObjectiveFunction instance
    """
    if phase == "be_loading":
        return BeLoadingObjective(
            target_ion_count=kwargs.get("target_ion_count", 1),
            target_secular_freq=kwargs.get("target_secular_freq", 307.0),
        )
    elif phase == "be_ejection":
        return BeEjectionObjective(
            target_ion_count=kwargs.get("target_ion_count", 1),
        )
    elif phase == "hd_loading":
        return HdLoadingObjective(
            target_be_count=kwargs.get("target_be_count", 1),
            be_secular_freq=kwargs.get("be_secular_freq", 307.0),
            hd_secular_freq=kwargs.get("hd_secular_freq", 277.0),
        )
    else:
        raise ValueError(f"Unknown phase: {phase}")
