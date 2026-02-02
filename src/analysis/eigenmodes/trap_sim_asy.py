# -*- coding: utf-8 -*-
"""
Asymmetric trap simulation for eigenmode calculation.

This module provides functions to calculate normal modes of trapped ions
with asymmetric endcap voltages (EC1 != EC2).

Main API:
    calculate_eigenmode(u_rf, ec1, ec2, masses, **kwargs)
        Calculate eigenmodes for given trap parameters and ion masses.

Example:
    >>> from trap_sim_asy import calculate_eigenmode
    >>> freqs, modes, z_eq, coords = calculate_eigenmode(350.0, 10.0, 10.0, [9, 3])
    >>> print(f"Axial mode: {freqs[0]/1e3:.1f} kHz")
"""

# ── Python stdlib ────────────────────────────────────────────────────
import math
import os
from itertools import combinations
from typing import Iterable, Sequence, Tuple, Dict, Any, Optional

# ── Third-party ──────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from functools import partial
from scipy.optimize import minimize
import warnings

# ── Physical constants ───────────────────────────────────────────────
EPS0 = 8.854_187_812_8e-12  # vacuum permittivity [F/m]
E_CH = 1.602_176_634e-19    # elementary charge [C]
U_AMU = 1.660_539_066_60e-27  # atomic-mass unit [kg]
K_E  = 8.9875517923e9     

# ── Default trap parameters (can be overridden via kwargs) ───────────
DEFAULT_TRAP_PARAMS = {
    'r_0': 0.8e-3,        # half distance between RF rods [m]
    'z_0': 2.5e-3,        # half distance between end-caps [m]
    'rf_mhz': 35.8515,    # drive frequency [MHz]
    'kappa': [0.077094, 0.122618, 0.109548],  # (k_x, k_y, k_z)
    'chi': [1.015475, 1.014046],  # (chi_x, chi_y)
}

# ── Backward compatibility globals (may be patched by importer) ──────
u_RF = 100        # RF voltage amplitude [V]
r_0 = DEFAULT_TRAP_PARAMS['r_0']
z_0 = DEFAULT_TRAP_PARAMS['z_0']
RF_MHZ = DEFAULT_TRAP_PARAMS['rf_mhz']
OMEGA = RF_MHZ * 1e6 * 2 * math.pi  # RF angular frequency [rad/s]

EC1 = 10      #V
EC2 = 10      #V

kappa = DEFAULT_TRAP_PARAMS['kappa']
chi = DEFAULT_TRAP_PARAMS['chi']


def mass_from_A(A: int, *, u_amu: float = U_AMU) -> float:
    """Convert an integer mass number *A* to kilograms (no binding-energy corr.)."""
    if A <= 0:
        raise ValueError("Mass number must be positive.")
    return A * u_amu


def _get_omega(rf_mhz: float) -> float:
    """Calculate angular frequency from MHz."""
    return rf_mhz * 1e6 * 2 * math.pi


def alpha_coeffs(m_kg: float, *, q=E_CH, u_rf: float, omega: float, r0: float, 
                 chi_vec: Sequence[float]) -> np.ndarray:
    """
    Return array [αx, αy, αz] such that the RF pseudopotential energy is
        U_alpha = αx x^2 + αy y^2 + αz z^2.
    """
    chi_x, chi_y = chi_vec[0], chi_vec[1]
    pref = q**2 * u_rf**2 / (4 * m_kg * omega**2 * r0**4)  # J/m^2 per χ
    return np.array([pref * chi_x, pref * chi_y, 0.0], dtype=float)


def beta_coeffs(*, q=E_CH, ec1: float, ec2: float, z0: float,
                kappa_vec: Sequence[float]) -> Tuple[np.ndarray, float]:
    """
    Return arrays for static/DC potential energy:
        U_beta = βx x^2 + βy y^2 + βz z^2 + γz z
        
    Where:
    - [βx, βy, βz] are quadratic coefficients from symmetric endcap voltage
    - γz is the linear coefficient from asymmetric endcap voltage
    """
    # Symmetric component for quadratic terms
    v_sym = (ec1 + ec2) / 2.0
    # Asymmetric component for linear term
    v_asym = (ec2 - ec1) / 2.0
    
    kx, ky, kz = kappa_vec[0], kappa_vec[1], kappa_vec[2]
    # Quadratic coefficients
    pref_quad = q * v_sym / z0**2  # J/m^2 per κ
    beta_quad = np.array([-0.5 * pref_quad * kx, -0.5 * pref_quad * ky, +pref_quad * kz], dtype=float)
    
    # Linear coefficient in z-direction
    gamma_z = q * v_asym / z0  # J/m
    
    return beta_quad, gamma_z


def total_potential(positions,
                    masses,
                    alpha_fn,
                    beta_fn,
                    *,
                    charges=None,
                    softening=0.0,
                    return_breakdown=False):
    """
    Total potential energy:
        V_total = sum_i [ alpha_i(pos_i, m_i) + beta_i(pos_i) + gamma_i(pos_i) ]  +  sum_{i<j} k_e q_i q_j / |r_i - r_j|

    Parameters
    ----------
    positions : (N,3) array_like
        Ion coordinates (meters).
    masses : (N,) array_like
        Ion masses (kg), in the same order as positions.
    alpha_fn : callable
        Called as alpha_fn(pos, m_kg=m) -> scalar potential contribution for that ion.
    beta_fn : callable
        Called as beta_fn() -> (beta_quad, gamma_z) where beta_quad is [βx,βy,βz] and gamma_z is linear coefficient.
    charges : (N,) array_like or None
        Charges (Coulombs). If None, all are +e.
    softening : float
        Optional softening length (m) to avoid 1/0 at r=0. Uses r = sqrt(r^2 + softening^2) if >0.
    return_breakdown : bool
        If True, return a dict with totals and per-ion components.

    Returns
    -------
    float or dict
        Total potential energy [J], or a breakdown dict if return_breakdown=True.
    """
    R = np.asarray(positions, dtype=float)
    M = np.asarray(masses,    dtype=float)
    if R.ndim != 2 or R.shape[1] != 3:
        raise ValueError("positions must have shape (N,3)")
    if M.shape != (R.shape[0],):
        raise ValueError("masses must have shape (N,)")

    N = R.shape[0]
    if charges is None:
        q = np.full(N, E_CH, dtype=float)
    else:
        q = np.asarray(charges, dtype=float)
        if q.shape != (N,):
            raise ValueError("charges must have shape (N,)")

    # ---- trap contributions (per ion) ----
    beta_quad, gamma_z = beta_fn()
    beta_quad = np.asarray(beta_quad, dtype=float)  # (3,)
    gamma_z = float(gamma_z)  # scalar
    
    V_alpha_i = np.empty(N, dtype=float)
    V_beta_i  = np.empty(N, dtype=float)
    V_gamma_i = np.empty(N, dtype=float)
    V_trap_per_ion = np.empty(N, dtype=float)

    for i in range(N):
        a = np.asarray(alpha_fn(m_kg=M[i]), dtype=float)  # (3,)
        r2 = R[i]**2
        V_alpha_i[i] = float(np.dot(a, r2))               # α⋅r^2
        V_beta_i[i]  = float(np.dot(beta_quad, r2))       # β⋅r^2
        V_gamma_i[i] = gamma_z * R[i, 2]                  # γz * z
        V_trap_per_ion[i] = V_alpha_i[i] + V_beta_i[i] + V_gamma_i[i]

    V_trap_total = float(V_trap_per_ion.sum())

    # ---- Coulomb energy ----
    dR  = R[:, None, :] - R[None, :, :]
    r2  = np.einsum('ijk,ijk->ij', dR, dR)
    if softening > 0.0:
        r = np.sqrt(r2 + softening**2)
    else:
        r = np.sqrt(r2)
        np.fill_diagonal(r, np.inf)

    inv_r = 1.0 / r
    qiqj  = q[:, None] * q[None, :]
    V_coul_matrix = K_E * qiqj * inv_r
    V_coul_per_ion = V_coul_matrix.sum(axis=1)
    V_coul_total   = 0.5 * float(V_coul_per_ion.sum())

    V_total = V_trap_total + V_coul_total

    # ---- breakdown return ----
    if return_breakdown:
        return dict(
            total=V_total,
            trap_total=V_trap_total,
            coulomb_total=V_coul_total,
            per_ion=dict(
                alpha=V_alpha_i,
                beta=V_beta_i,
                gamma=V_gamma_i,
                trap=V_trap_per_ion,
                coulomb=V_coul_per_ion,
            ),
        )
    return V_total    


def _pack(R):  # (N,3) -> (3N,)
    return np.asarray(R, dtype=float).ravel()


def _unpack(x):  # (3N,) -> (N,3)
    x = np.asarray(x, dtype=float)
    return x.reshape(-1, 3)


def pos_find(
    masses,
    *,
    alpha_fn,
    beta_fn,
    charges=None,
    softening=0.1,
    init="linear",
    scale=None,
    box=None,
    n_restarts=600,
    method="L-BFGS-B",
    options=None,
    random_state=None,
    verbose=False,
):
    """
    Find equilibrium positions for ions in the trap.
    
    Parameters
    ----------
    masses : array_like
        Ion masses in kg.
    alpha_fn : callable
        Function returning alpha coefficients for a given mass.
    beta_fn : callable
        Function returning (beta_quad, gamma_z) coefficients.
    charges : array_like, optional
        Ion charges in C. Defaults to +e for all.
    softening : float
        Softening length for Coulomb potential.
    init : str
        Initialization method: "linear" or "random".
    scale : float, optional
        Length scale for initialization.
    box : tuple, optional
        Bounds for optimization (Lx, Ly, Lz).
    n_restarts : int
        Number of optimization restarts.
    method : str
        Optimization method.
    options : dict
        Optimizer options.
    random_state : int or RandomState
        Random seed.
    verbose : bool
        Print progress.
    
    Returns
    -------
    positions : ndarray
        Equilibrium positions (N, 3) in meters.
    result : OptimizeResult
        Optimization result object.
    """
    masses = np.asarray(masses, dtype=float)
    N = masses.size
    if N == 0:
        raise ValueError("masses cannot be empty")

    # --- choose a length scale for initialization ---
    if scale is None:
        beta_quad, gamma_z = beta_fn()
        bx, by, bz = beta_quad
        if bz <= 0:
            scale = 1e-5
        else:
            d3 = (K_E * E_CH**2) / (2.0 * abs(bz))
            scale = d3 ** (1.0/3.0)

    # --- RNG for inits/jitters ---
    if isinstance(random_state, (np.random.Generator, np.random.RandomState)):
        rng = random_state
    else:
        rng = np.random.default_rng(random_state)

    def make_init(kind):
        if kind == "linear":
            dz = 1.0 * scale
            z = (np.arange(N) - 0.5*(N-1)) * dz
            R0 = np.column_stack([np.zeros(N), np.zeros(N), z])
        elif kind == "random":
            R0 = rng.normal(scale=0.2*scale, size=(N, 3))
        else:
            raise ValueError("init must be 'linear' or 'random'")
        return R0

    # --- charges ---
    if charges is None:
        q = np.full(N, E_CH, dtype=float)
    else:
        q = np.asarray(charges, dtype=float)
        if q.shape != (N,):
            raise ValueError("charges must have shape (N,)")

    # --- coefficients ---
    beta_quad, gamma_z = beta_fn()
    beta_quad = np.asarray(beta_quad, dtype=float)
    gamma_z = float(gamma_z)
    alpha_all = np.vstack([np.asarray(alpha_fn(m_kg=m), float) for m in masses])

    def energy_and_grad(x):
        R = _unpack(x)

        # Trap: quadratic terms
        coeff = alpha_all + beta_quad[np.newaxis, :]
        trap_E_quad = float(np.sum(coeff * (R**2)))
        trap_g_quad = 2.0 * coeff * R

        # Trap: linear term in z
        trap_E_lin = gamma_z * np.sum(R[:, 2])
        trap_g_lin = np.zeros_like(R)
        trap_g_lin[:, 2] = gamma_z

        trap_E = trap_E_quad + trap_E_lin
        trap_g = trap_g_quad + trap_g_lin

        # Coulomb
        coul_E = 0.0
        coul_g = np.zeros_like(R)
        for i in range(N-1):
            ri = R[i]; qi = q[i]
            for j in range(i+1, N):
                d  = ri - R[j]
                r2 = float(np.dot(d, d))
                if r2 == 0.0:
                    tiny = 1e-18
                    r2 = tiny
                if softening > 0.0:
                    s2 = r2 + softening**2
                    r  = math.sqrt(s2)
                    r3 = s2 * r
                else:
                    r  = math.sqrt(r2)
                    r3 = r2 * r
                keqq = K_E * qi * q[j]
                coul_E += keqq / r
                gpair = (keqq / r3) * d
                coul_g[i] += gpair
                coul_g[j] -= gpair

        E = trap_E + coul_E
        g = trap_g + coul_g
        return E, _pack(g)

    # --- bounds ---
    bounds = None
    if box is not None:
        Lx, Ly, Lz = box
        bounds = [(-Lx, Lx), (-Ly, Ly), (-Lz, Lz)] * N

    # --- optimizer options ---
    opt_options = {"maxiter": 5000, "ftol": 1e-15, "gtol": 1e-12}
    if options:
        opt_options.update(options)

    # --- multistart ---
    best = None
    best_res = None
    starts = [make_init("linear")] + [
        make_init("linear") + rng.normal(scale=0.05*scale, size=(N,3))
        for _ in range(max(0, n_restarts-1))
    ]
    for k, R0 in enumerate(starts, 1):
        x0 = _pack(R0)
        res = minimize(energy_and_grad, x0, method=method,
                       jac=True, bounds=bounds, options=opt_options)
        if verbose:
            print(f"start {k}/{len(starts)} -> success={res.success}, "
                  f"E={res.fun:.12e}, |grad|={np.linalg.norm(res.jac):.3e}")
        if (best is None) or (res.fun < best_res.fun):
            best = _unpack(res.x)
            best_res = res

    # --- polish with exact Coulomb ---
    if softening > 0.0 and best_res.success:
        s = softening
        softening = 0.0
        res2 = minimize(energy_and_grad, _pack(best), method=method,
                        jac=True, bounds=bounds,
                        options={"maxiter": 3000, "ftol": 1e-15, "gtol": 1e-12})
        softening = s
        if res2.success and res2.fun <= best_res.fun:
            best, best_res = _unpack(res2.x), res2

    return best, best_res


def calculate_eigenmode(
    u_rf: float,
    ec1: float,
    ec2: float,
    masses: Sequence[int],
    *,
    r_0: float = None,
    z_0: float = None,
    rf_mhz: float = None,
    kappa: Sequence[float] = None,
    chi: Sequence[float] = None,
    softening: float = 1e-9,
    n_restarts: int = 8,
    box: Tuple[float, float, float] = (1e-3, 1e-3, 2e-3),
    random_state: int = 0,
    verbose: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Calculate eigenmodes for ions in an asymmetric trap.

    This is the main API function for eigenmode calculation.

    Parameters
    ----------
    u_rf : float
        RF voltage amplitude [V].
    ec1 : float
        Endcap 1 voltage [V].
    ec2 : float
        Endcap 2 voltage [V].
    masses : Sequence[int]
        List of ion mass numbers (e.g., [9, 3] for Be-9 and He-3).
    r_0 : float, optional
        Half distance between RF rods [m]. Default: 0.8e-3.
    z_0 : float, optional
        Half distance between end-caps [m]. Default: 2.5e-3.
    rf_mhz : float, optional
        RF drive frequency [MHz]. Default: 35.8515.
    kappa : Sequence[float], optional
        Geometric factors [kx, ky, kz]. Default: [0.077094, 0.122618, 0.109548].
    chi : Sequence[float], optional
        Efficiency factors [chi_x, chi_y]. Default: [1.015475, 1.014046].
    softening : float, optional
        Coulomb softening length [m]. Default: 1e-9.
    n_restarts : int, optional
        Number of optimization restarts. Default: 8.
    box : Tuple[float, float, float], optional
        Search bounds (Lx, Ly, Lz) [m]. Default: (1e-3, 1e-3, 2e-3).
    random_state : int, optional
        Random seed. Default: 0.
    verbose : bool, optional
        Print debug info. Default: False.

    Returns
    -------
    freqs_hz : ndarray
        Eigenfrequencies in Hz (sorted), shape (3*N,).
    eigenvectors : ndarray
        Mass-weighted eigenvectors, shape (3*N, 3*N).
    z_eq : ndarray
        Z-equilibrium positions [m], shape (N,).
    coords : ndarray
        3D equilibrium positions [m], shape (N, 3).

    Examples
    --------
    >>> freqs, modes, z_eq, coords = calculate_eigenmode(350.0, 10.0, 10.0, [9, 3])
    >>> print(f"Axial mode: {freqs[0]/1e3:.1f} kHz")
    Axial mode: 1234.5 kHz
    """
    # Use defaults for unspecified parameters
    if r_0 is None:
        r_0 = DEFAULT_TRAP_PARAMS['r_0']
    if z_0 is None:
        z_0 = DEFAULT_TRAP_PARAMS['z_0']
    if rf_mhz is None:
        rf_mhz = DEFAULT_TRAP_PARAMS['rf_mhz']
    if kappa is None:
        kappa = DEFAULT_TRAP_PARAMS['kappa']
    if chi is None:
        chi = DEFAULT_TRAP_PARAMS['chi']

    # Validate inputs
    if len(masses) == 0:
        raise ValueError("masses cannot be empty")
    if u_rf < 0:
        raise ValueError("u_rf must be non-negative")
    if rf_mhz <= 0:
        raise ValueError("rf_mhz must be positive")

    # Convert masses to kg
    masses_kg = np.asarray([mass_from_A(A) for A in masses], dtype=float)
    N = masses_kg.size
    omega = _get_omega(rf_mhz)

    # Local coefficient functions with bound parameters
    def _alpha_fn(m_kg: float) -> np.ndarray:
        return alpha_coeffs(
            m_kg, u_rf=u_rf, omega=omega, r0=r_0, chi_vec=chi
        )

    def _beta_fn() -> Tuple[np.ndarray, float]:
        return beta_coeffs(
            ec1=ec1, ec2=ec2, z0=z_0, kappa_vec=kappa
        )

    # Radial stability check
    α_all = np.vstack([_alpha_fn(m_i) for m_i in masses_kg])
    β_quad, γ_z = _beta_fn()
    βx, βy, βz = β_quad
    if np.any((α_all[:, 0] + βx) <= 0.0) or np.any((α_all[:, 1] + βy) <= 0.0):
        raise ValueError("Chosen parameters give radial instability (α+β ≤ 0).")

    # Find equilibrium positions
    positions_opt, res = pos_find(
        masses_kg,
        alpha_fn=_alpha_fn,
        beta_fn=_beta_fn,
        softening=softening,
        box=box,
        n_restarts=n_restarts,
        random_state=random_state,
        verbose=verbose,
    )
    if verbose:
        print("pos_find success:", getattr(res, "success", None), 
              "E[J]:", getattr(res, "fun", None))

    # Use equilibrium positions directly (no rotation or offset)
    coords = positions_opt
    z_eq = coords[:, 2].copy()

    # Build and diagonalize Hessian
    H = _build_hessian(coords, masses_kg, α_all, β_quad, γ_z)
    freqs_hz, eigenvectors = _diagonalize_hessian(H, masses_kg)

    return freqs_hz, eigenvectors, z_eq, coords


def _build_hessian(
    coords: np.ndarray,
    masses: np.ndarray,
    alpha_all: np.ndarray,
    beta_quad: np.ndarray,
    gamma_z: float,
) -> np.ndarray:
    """Build the Hessian matrix at equilibrium positions."""
    N = masses.size
    βx, βy, βz = beta_quad
    H = np.zeros((3*N, 3*N), dtype=float)

    # Trap contributions (diagonal per ion)
    for i in range(N):
        H[3*i + 0, 3*i + 0] += 2.0 * (alpha_all[i, 0] + βx)
        H[3*i + 1, 3*i + 1] += 2.0 * (alpha_all[i, 1] + βy)
        H[3*i + 2, 3*i + 2] += 2.0 * (0.0 + βz)

    # Coulomb contributions
    C = K_E * (E_CH**2)
    for i in range(N - 1):
        ri = coords[i]
        for j in range(i + 1, N):
            rj = coords[j]
            d = ri - rj
            r2 = float(np.dot(d, d))
            if r2 == 0.0:
                raise RuntimeError("Two ions have zero separation at equilibrium.")
            r = math.sqrt(r2)
            r5 = r2 * r2 * r
            I3 = np.eye(3)
            G = C * (3.0 * np.outer(d, d) - r2 * I3) / r5

            i_slice = slice(3*i, 3*i+3)
            j_slice = slice(3*j, 3*j+3)
            H[i_slice, i_slice] += G
            H[j_slice, j_slice] += G
            H[i_slice, j_slice] -= G
            H[j_slice, i_slice] -= G

    return H


def _diagonalize_hessian(
    H: np.ndarray,
    masses: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Diagonalize mass-weighted Hessian to get eigenfrequencies and eigenvectors."""
    M_inv_sqrt = np.repeat(1.0 / np.sqrt(masses), 3)
    K = (M_inv_sqrt[:, None] * H) * M_inv_sqrt[None, :]
    lam, V = np.linalg.eigh(K)
    V = V / np.linalg.norm(V, axis=0, keepdims=True)
    freqs_hz = np.sqrt(np.clip(lam, 0.0, None)) / (2.0 * math.pi)
    return freqs_hz, V


# -------------------------------------------------------------------
# Backward compatibility wrappers
# -------------------------------------------------------------------

def _eigenmodes_from_list(
    A_list: Sequence[int],
    *,
    chi_vec: Tuple[float, float] = tuple(chi),
    kappa_vec: Tuple[float, float, float] = tuple(kappa),
    tol: float = 1e-12,
    softening: float = 1e-9,
    box: Tuple[float, float, float] | None = (1e-3, 1e-3, 2e-3),
    n_restarts: int = 8,
    random_state: int | None = 0,
    verbose: bool = False,
):
    """
    Backward compatibility wrapper. Use calculate_eigenmode() instead.
    
    Computes eigenmodes using global u_RF, EC1, EC2 values.
    """
    import warnings
    warnings.warn("_eigenmodes_from_list is deprecated, use calculate_eigenmode() instead",
                  DeprecationWarning)
    
    # Use global values for backward compatibility
    global u_RF, EC1, EC2
    return calculate_eigenmode(
        u_rf=u_RF,
        ec1=EC1,
        ec2=EC2,
        masses=A_list,
        r_0=r_0,
        z_0=z_0,
        rf_mhz=RF_MHZ,
        kappa=kappa_vec,
        chi=chi_vec,
        softening=softening,
        n_restarts=n_restarts,
        box=box,
        random_state=random_state,
        verbose=verbose,
    )


def eigenmodes_from_masses(
    A_seq: Iterable[int],
    *,
    chi_vec: Tuple[float, float] = tuple(chi),
    kappa_vec: Tuple[float, float, float] = tuple(kappa),
    **kwargs,
):
    """
    Backward compatibility wrapper. Use calculate_eigenmode() instead.
    
    Compute normal modes for a sequence of integer mass numbers.
    """
    import warnings
    warnings.warn("eigenmodes_from_masses is deprecated, use calculate_eigenmode() instead",
                  DeprecationWarning)
    return _eigenmodes_from_list(
        list(A_seq), 
        chi_vec=chi_vec, 
        kappa_vec=kappa_vec,
        **kwargs
    )


# -------------------------------------------------------------------
# Convenience helpers
# -------------------------------------------------------------------

def _label_two(vec: np.ndarray) -> str:
    ex = vec[0] ** 2 + vec[3] ** 2
    ey = vec[1] ** 2 + vec[4] ** 2
    ez = vec[2] ** 2 + vec[5] ** 2
    axis = int(np.argmax([ex, ey, ez]))
    if axis == 2:
        return "Axial in-phase" if np.sign(vec[2]) == np.sign(vec[5]) else "Axial out-of-phase"
    return f"Radial ({'x' if axis == 0 else 'y'})"


def modes_dataframe(freqs_hz, V):
    """Create a pandas DataFrame with mode information."""
    freqs = np.asarray(freqs_hz); V = np.asarray(V)
    N = V.shape[0] // 3
    cols = ["Mode", "freq [kHz]"] + [f"{axis}{i + 1}" for i in range(N) for axis in "xyz"]
    rows = []
    for k in range(3 * N):
        label = _label_two(V[:, k]) if N == 2 else f"Mode {k}"
        rows.append([label, freqs[k] / 1e3, *V[:, k]])
    df = pd.DataFrame(rows, columns=cols)
    if N == 2:
        order = [
            "Axial in-phase", "Axial out-of-phase",
            "Radial (y)", "Radial (x)", "Radial (y)", "Radial (x)"
        ]
        df["_ord"] = df["Mode"].apply(order.index)
        df = df.sort_values("_ord").drop(columns="_ord").reset_index(drop=True)
    return df


def _format_df(df: pd.DataFrame) -> pd.DataFrame:
    """Format DataFrame for display."""
    df2 = df.copy()
    df2["freq [kHz]"] = df2["freq [kHz]"].map(lambda x: f"{x:,.3f}")
    for col in df2.columns[2:]:
        df2[col] = df2[col].map(lambda x: f"{x: .4f}")
    return df2


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

if __name__ == "__main__":
    line = input(
        "Enter ion mass numbers (u) separated by spaces "
        "(blank line to quit):\n> "
    ).strip()

    if not line:
        print("No masses entered – exiting.")
        raise SystemExit

    try:
        masses = [int(tok) for tok in line.split()]
    except ValueError:
        print("Non-integer detected – exiting.")
        raise SystemExit
    
    # Get trap parameters from user or use defaults
    u_rf_input = input(f"Enter RF voltage [V] (default {u_RF}): ").strip()
    u_rf = float(u_rf_input) if u_rf_input else u_RF
    
    ec1_input = input(f"Enter EC1 [V] (default {EC1}): ").strip()
    ec1 = float(ec1_input) if ec1_input else EC1
    
    ec2_input = input(f"Enter EC2 [V] (default {EC2}): ").strip()
    ec2 = float(ec2_input) if ec2_input else EC2
    
    freqs, V, z_eq, coords = calculate_eigenmode(
        u_rf=u_rf, ec1=ec1, ec2=ec2, masses=masses
    )

    df = modes_dataframe(freqs, V)
    
    if len(masses) >= 2:
        DX = coords[0][0] - coords[1][0]
        DY = coords[0][1] - coords[1][1]
        DZ = coords[0][2] - coords[1][2]
        angle = math.atan(math.sqrt(DX ** 2 + DY ** 2) / abs(DZ)) * 360 / (2*math.pi)
        print(f'angle between crystal and z axis is {angle}')

    print("\nz-equilibrium positions [µm]:", z_eq * 1e6)
    print("\nCartesian coordinates [µm] (one ion per row):\n", coords * 1e6)
    print("\n", df.to_string(index=False))

    df_fmt = _format_df(df)
    rows, cols = df_fmt.shape
    fig_w, fig_h = max(6.0, cols * 1.2), max(2.5, rows * 0.45)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    ax.set_title(
        "Normal modes for ions: "
        f"{' '.join(map(str, masses))}\n"
        f"U_RF={u_rf} V,  EC1={ec1} V, EC2={ec2} V,  Ω={RF_MHZ} MHz"
    )

    tbl = ax.table(cellText=df_fmt.values, colLabels=df_fmt.columns, loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1.2, 1.2)
    fig.tight_layout()

    slug = "-".join(map(str, masses))
    filename = f"normal_modes_{slug}_{int(u_rf)}V_{float(ec1)}V_{float(ec2)}V_{RF_MHZ:.1f}MHz.png"
    save_dir = "eigenmode_tables"
    os.makedirs(save_dir, exist_ok=True)
    plt.show(fig)
