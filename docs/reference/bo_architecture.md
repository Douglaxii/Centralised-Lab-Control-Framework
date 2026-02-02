# Two-Phase Bayesian Optimization Architecture

**Version:** 2.0  
**Scope:** Optimization of Be+/HD+ Loading and Ejection Cycles

---

## 1. Executive Summary

This architecture implements a "Divide and Conquer" strategy for experimental control. Instead of optimizing the entire experimental sequence as a single high-dimensional problem (which is computationally intractable and prone to failure), the process is split into two distinct phases:

1. **Phase I (TuRBO - Component Optimization):** Uses Trust Region Bayesian Optimization to rapidly locate high-performing regions for individual experimental stages. This handles the high dimensionality of local parameters.
2. **Phase II (MOBO - Global Optimization):** Uses Constrained Multi-Objective Bayesian Optimization to fine-tune the interactions between stages. This focuses on balancing conflicting objectives (speed vs. fidelity) while strictly enforcing safety and purity constraints.

---

## 2. Phase I: Component-Level Optimization (The TuRBO Layer)

The primary challenge in tuning individual stages (Loading/Ejection) is the high number of control parameters (Voltages, Laser Detunings, Pulse Timings). Standard Global BO is too slow here. We utilize **TuRBO**, which creates local "Trust Regions" (hyperspheres) to focus the search, allowing for rapid convergence even with >20 parameters.

### 2.1 Module A: Be+ Loading Optimizer

- **Goal:** find optimal parameters for each ion_count [1,8]
- **Algorithm:** TuRBO-1 (Single Trust Region)
- **Input Vectors:** 
  - RF voltage (u_rf_volts)
  - DC electrodes (ec1, ec2, comp_h, comp_v)
  - Laser parameters (amp0, amp1, cooling detuning)
  - Timing parameters (oven_start, oven_duration, pi_start, pi_duration)
- **Metric:** ion_counts
- **Stopping Criterion:** prefered ion number has been reached

### 2.2 Module B: Be+ Ejection Optimizer

- **Goal:** Maximize ejection efficiency (minimize residual Be+)
- **Algorithm:** TuRBO-1
- **Input Vectors:** 
  - Tickle amplitude and frequency
  - RF voltage (u_rf_volts)
  - DC electrodes (ec1, ec2, comp_h, comp_v)
  - Laser parameters (amp0, amp1, cooling detuning)
  - Ejection timing parameters
- **Metric:** ion_counts
- **Stopping Criterion:** ion_count = 1 (can only measure after the process)

### 2.3 Module C: HD+ Loading Optimizer

- **Goal:** Maximize Sympathetic Cooling efficiency / HD+ yield /minimise crystalisation time
- **Algorithm:** TuRBO-1
- **Input Vectors:** 
  - piezo
  - RF voltage (u_rf_volts)
  - DC electrodes (ec1, ec2, comp_h, comp_v)
  - Laser parameters (amp0, amp1, cooling detuning)
  - HD loading timing parameters
  - Reaction delays
- **Metric:** ion_counts, ion pos, PMT
- **Stopping Criterion:** 

---

## 3. Phase II: System-Level Optimization (The MOBO Layer)

Once the individual stages are roughly optimized, the system enters the Global Cycle Optimization. Here, parameters are allowed to float within a tighter bound determined by Phase I. The focus shifts from "maximizing one number" to "balancing trade-offs."

**Algorithm:** qNEHVI (Noisy Expected Hypervolume Improvement) with Outcome Constraints

### 3.1 The Multi-Objective Architecture

The system no longer seeks a single "best" point. It seeks a **Pareto Front**—a set of optimal configurations representing different trade-offs.

- **Objective 1 (Yield):** load prefered number of Be+. exact number determined by optimizing the entire experiment
- **Objective 2 (Yield):** load exactly one MHI
- **Objective 3 (Yield):** after ejection, only one visible ion remains
- **Objective 4 (Speed):** Minimize Cycle Time (Total experiment duration)
- **Objective 5 (success):** final secular frequency matches prediction

### 3.2 The Constraint Layer

Unlike Phase I, Phase II imposes strict "Pass/Fail" criteria on the experimental outcomes. The optimizer learns the boundary between "Valid" and "Invalid" experiments.

- **Constraint 1 (Purity):** `Be_Residual <= Threshold`. If an experiment yields high HD+ but fails to eject all Be+, it is marked as a violation.
- **Constraint 2 (Stability):** pressure exceeds a threshold
- **Constraint 3 (Stability):** laser high power output time must < a threshold

---

## 4. The "Warm Start" Data Handover

A critical architectural feature is the **Transfer Learning** step between Phase I and Phase II.

1. **State Capture:** The top k best parameter configurations from the TuRBO runs (Phase I) are extracted.
2. **Space Pruning:** The search space for Phase II is automatically cropped. Instead of searching the full voltage range (e.g., 0V–100V), the bounds are tightened to the successful regions identified in Phase I (e.g., 45V–55V).
3. **Initialization:** The Phase II Gaussian Process is "pre-trained" with the data points from Phase I. This prevents the Global Optimizer from wasting time exploring known bad regions (like 0V).

---

## 5. ASK-TELL Interface

The optimization loop functions as a client-server architecture between the **Experiment Controller** (Hardware) and the **Optimizer** (Software).

### 5.1 Basic Workflow

```python
from server.optimizer import TwoPhaseController, Phase

# Initialize controller
controller = TwoPhaseController(config)

# Start Phase I
controller.start_phase(Phase.BE_LOADING_TURBO)

# Optimization loop
while not controller.is_complete():
    # 1. ASK: Get parameters
    params, metadata = controller.ask()
    
    # 2. EVALUATE: Run experiment
    # ... set hardware parameters ...
    # ... trigger experiment ...
    # ... wait for completion ...
    
    # 3. MEASURE: Collect results
    measurements = {
        "total_fluorescence": read_pmt(),
        "cycle_time_ms": get_elapsed_time()
    }
    
    # 4. TELL: Register results
    controller.tell(measurements)
```

### 5.2 Phase Transition

```python
# After Be+ loading succeeds
controller.start_phase(Phase.BE_EJECTION_TURBO)

# After ejection completes
controller.start_phase(Phase.HD_LOADING_TURBO)

# Finally, start global optimization
controller.start_phase(Phase.GLOBAL_MOBO)
```

---

## 6. Implementation

### 6.1 Core Classes

| Class | File | Purpose |
|-------|------|---------|
| `TwoPhaseController` | `two_phase_controller.py` | Main coordinator with ASK-TELL interface |
| `TuRBOOptimizer` | `turbo.py` | Phase I component optimization |
| `MOBOOptimizer` | `mobo.py` | Phase II multi-objective optimization |
| `TrustRegionState` | `turbo.py` | Trust region management |
| `ParetoFront` | `mobo.py` | Pareto front maintenance |

### 6.2 Configuration

```python
from server.optimizer import OptimizationConfig

config = OptimizationConfig(
    target_be_count=1,
    target_hd_present=True,
    
    # Phase I settings
    turbo_max_iterations=50,
    turbo_n_init=10,
    
    # Phase II settings
    mobo_max_iterations=30,
    mobo_n_init=5,
    
    # Warm start
    warm_start_top_k=5,
    
    # Constraints
    be_residual_threshold=0.1,
    max_cycle_time_ms=30000.0
)
```

### 6.3 ControlManager Integration

```python
# ControlManager handles optimizer commands
{
    "action": "OPTIMIZE_START",
    "target_be_count": 1,
    "target_hd_present": True
}

{
    "action": "OPTIMIZE_SUGGESTION"  # ASK
}

{
    "action": "OPTIMIZE_RESULT",      # TELL
    "measurements": {
        "total_fluorescence": 100.0,
        "cycle_time_ms": 5000
    }
}
```

---

## 7. Visual Data Flow Summary

```
[ Phase I: TuRBO Agents ]
       |
       | (Outputs: Best Parameter Subsets)
       V
[ Data Handover / Bounds Tightening ]
       |
       | (Inputs: Pruned Search Space + Priors)
       V
[ Phase II: Constrained MOBO ]
       |
    (Ask) -------------------------> (Tell)
    |                                    |
    V                                    |
[ Hardware Controller ] -----------------|
    | Action: Run Cycle
    | Output: N_HD, Time, Be_Residue
```

---

## 8. Key Advantages

1. **Scalability:** Handles 20+ dimensional parameter spaces
2. **Efficiency:** TuRBO converges faster than global BO for component tuning
3. **Flexibility:** MOBO provides Pareto front for trade-off analysis
4. **Safety:** Constraints ensure experimental validity
5. **Warm Start:** Phase I data accelerates Phase II convergence

---

## 9. Migration from Legacy SAASBO

| Legacy (SAASBO) | New (Two-Phase) | Notes |
|-----------------|-----------------|-------|
| `OptimisationManager` | `TwoPhaseController` | New ASK-TELL interface |
| `OptimisationConfig` | `OptimizationConfig` | New field names |
| `OptimisationPhase` | `Phase` | Simplified enum |
| `get_suggestion()` | `ask()` | Returns (params, metadata) |
| `register_result()` | `tell(measurements)` | Direct measurement input |
| `is_running()` | `current_phase != Phase.IDLE` | Phase-based state |

---

## 10. References

1. Eriksson et al. "Scalable Global Optimization via Local Bayesian Optimization" (TuRBO)
2. Daulton et al. "Parallel Bayesian Optimization of Multiple Noisy Objectives" (qNEHVI)
3. Gardner et al. "Bayesian Optimization with Inequality Constraints"
