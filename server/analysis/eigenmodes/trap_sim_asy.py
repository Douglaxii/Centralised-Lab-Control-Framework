# -*- coding: utf-8 -*-
"""
Created on Tue Aug  5 09:50:36 2025

@author: Dougl
"""

# ── Python stdlib ────────────────────────────────────────────────────
import math
import os
from itertools import combinations
from typing import Iterable, Sequence, Tuple

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

# ── Trap parameters (globals; may be patched by importer) ────────────
u_RF = 100        # RF voltage amplitude [V]
#v_end = 8.78         # DC end-cap voltage [V]
r_0 = 0.8e-3        # half distance between RF rods [m]
z_0 = 2.5e-3        # half distance between end-caps [m]
RF_MHZ = 35.8515       # drive frequency [MHz]
OMEGA = RF_MHZ * 1e6 * 2 * math.pi  # RF angular frequency [rad/s]

EC1 = 10      #V
EC2 = 10    #V



kappa = [0.077094,0.122618,0.109548]  # (k_x, k_y, k_z)
chi   = [1.015475,1.014046]


# kappa = [0.109548,0.109548,0.109548]  # (k_x, k_y, k_z)
# chi   = [1,1]

def mass_from_A(A: int, *, u_amu: float = U_AMU) -> float:
    """Convert an integer mass number *A* to kilograms (no binding-energy corr.)."""
    if A <= 0:
        raise ValueError("Mass number must be positive.")
    return A * u_amu

#potential calculation

def alpha_coeffs(m_kg, *, q=E_CH, u_rf=None, omega=None, r0=None):
    """
    Return array [αx, αy, αz] such that the RF pseudopotential energy is
        U_alpha = αx x^2 + αy y^2 + αz z^2.
    """
    if u_rf is None:
        u_rf = u_RF
    if omega is None:
        omega = OMEGA
    if r0 is None:
        r0 = r_0
    chi_x, chi_y = chi
    pref = q**2 * u_rf**2 / (4 * m_kg * omega**2 * r0**4)  # J/m^2 per χ
    return np.array([pref * chi_x, pref * chi_y, 0.0], dtype=float)

def beta_coeffs(*, q=E_CH, ec1=None, ec2=None, z0=None):
    """
    Return arrays for static/DC potential energy:
        U_beta = βx x^2 + βy y^2 + βz z^2 + γz z
        
    Where:
    - [βx, βy, βz] are quadratic coefficients from symmetric endcap voltage
    - γz is the linear coefficient from asymmetric endcap voltage
    
    The full DC potential is derived from:
        φ(z) = (EC2-EC1)/(2z₀) z + (EC1+EC2)/2
    which gives both quadratic trapping terms and a linear term.
    """
    if ec1 is None:
        ec1 = globals().get("EC1")
    if ec2 is None:
        ec2 = globals().get("EC2")
    if z0 is None:
        z0 = globals().get("z_0")
    if ec1 is None or ec2 is None or z0 is None:
        raise ValueError("beta_coeffs needs EC1, EC2 and z0 (either explicit or global).")
    
    # Symmetric component for quadratic terms
    v_sym = (ec1 + ec2) / 2.0
    # Asymmetric component for linear term
    v_asym = (ec2 - ec1) / 2.0
    
    kx, ky, kz = kappa
    # Quadratic coefficients (same as before, but using v_sym)
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
    # alpha_fn(m_kg) -> [αx,αy,αz]; beta_fn() -> ([βx,βy,βz], γz)  (both in J/m^2 and J/m)
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

    # ---- Coulomb energy (unchanged) ----
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


#find positions of ions old

def _pack(R):  # (N,3) -> (3N,)
    return np.asarray(R, dtype=float).ravel()

def _unpack(x):  # (3N,) -> (N,3)
    x = np.asarray(x, dtype=float)
    return x.reshape(-1, 3)

# ... (previous code remains the same until pos_find function)

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
    masses = np.asarray(masses, dtype=float)
    N = masses.size
    if N == 0:
        raise ValueError("masses cannot be empty")

    # --- choose a length scale for initialization ---
    if scale is None:
        # Physics-based axial spacing for two ions: d ≈ (k_e e^2 / (2 βz))^(1/3)
        beta_quad, gamma_z = beta_fn()                     # Get both quadratic and linear
        bx, by, bz = beta_quad                             # J/m^2
        # Check if bz is positive to avoid division by zero or negative values
        if bz <= 0:
            scale = 1e-5  # Default small scale
        else:
            d3 = (K_E * E_CH**2) / (2.0 * abs(bz))         # m^3 (use abs to handle negative values)
            scale = d3 ** (1.0/3.0)                        # meters

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

    # --- coefficients α_i and β (constants for energy/grad) ---
    beta_quad, gamma_z = beta_fn()                         # Get both components
    beta_quad = np.asarray(beta_quad, dtype=float)         # (3,)
    gamma_z = float(gamma_z)                               # scalar
    alpha_all  = np.vstack([np.asarray(alpha_fn(m_kg=m), float) for m in masses])  # (N,3)

    def energy_and_grad(x):
        R = _unpack(x)                                     # (N,3)

        # Trap: quadratic terms
        coeff  = alpha_all + beta_quad[np.newaxis, :]      # (N,3) + (3,) -> broadcasting works
        trap_E_quad = float(np.sum(coeff * (R**2)))
        trap_g_quad = 2.0 * coeff * R

        # Trap: linear term in z
        trap_E_lin = gamma_z * np.sum(R[:, 2])             # γz * sum(z_i)
        trap_g_lin = np.zeros_like(R)
        trap_g_lin[:, 2] = gamma_z                         # gradient is γz in z-direction

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
                    # if ions overlap, push energy large and gradient finite
                    # (avoid NaN to keep optimizer alive)
                    tiny = 1e-18
                    r2 = tiny
                if softening > 0.0:
                    s2 = r2 + softening**2
                    r  = math.sqrt(s2)
                    r3 = s2 * r                             # (r^2 + eps^2)^(3/2)
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

    # --- bounds (optional) ---
    bounds = None
    if box is not None:
        Lx, Ly, Lz = box
        bounds = [(-Lx, Lx), (-Ly, Ly), (-Lz, Lz)] * N

    # --- optimizer options (single definition) ---
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

    # --- optional polish with exact Coulomb ---
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


def _eigenmodes_from_list(
    A_list: Sequence[int],
    *,
    chi_vec: Tuple[float, float] = tuple(chi),              # (χx, χy)
    kappa_vec: Tuple[float, float, float] = tuple(kappa),   # (κx, κy, κz)
    theta_deg: float = 0.0,  # Rotation angle in degrees around x-axis
    z_offset: float = 0.0,   # Z-axis offset in meters
    tol: float = 1e-12,
    # Optional knobs for the equilibrium search via pos_find:
    softening: float = 1e-9,
    box: Tuple[float, float, float] | None = (1e-3, 1e-3, 2e-3),
    n_restarts: int = 8,
    random_state: int | None = 0,
    verbose: bool = False,
):
    """
    Compute normal modes for ions with integer mass numbers in A_list.

    Equilibrium positions are obtained with `pos_find` using the same trap
    parameters (via local α/β coefficient builders consistent with chi_vec/kappa_vec).
    The Hessian is then computed by finite differences around that equilibrium.
    """
    if not A_list:
        raise RuntimeError("Need at least one ion.")

    # ---- local α/β coefficient builders using the provided chi/kappa ----
    χx, χy = chi_vec
    κx, κy, κz = kappa_vec

    def _alpha_coeffs_local(m_kg: float) -> np.ndarray:
        pref = (E_CH**2) * (u_RF**2) / (4.0 * m_kg * OMEGA**2 * r_0**4)
        return np.array([pref * χx, pref * χy, 0.0], dtype=float)

    def _beta_coeffs_local():
        # Use global EC1 and EC2 values
        ec1_val = globals().get("EC1", 0.0)
        ec2_val = globals().get("EC2", 0.0)
        
        # Symmetric component for quadratic terms
        v_sym = (ec1_val + ec2_val) / 2.0
        # Asymmetric component for linear term
        v_asym = (ec2_val - ec1_val) / 2.0
        
        pref_quad = E_CH * v_sym / (z_0**2)
        beta_quad = np.array([-0.5 * pref_quad * κx, -0.5 * pref_quad * κy, +pref_quad * κz], dtype=float)
        
        # Linear coefficient in z-direction
        gamma_z = E_CH * v_asym / z_0  # J/m
        
        return beta_quad, gamma_z

    # ---- masses and Coulomb const ----
    masses = np.asarray([mass_from_A(A) for A in A_list], dtype=float)  # kg
    N = masses.size
    C_COUL = K_E * (E_CH**2)  # J·m

    # ---- radial stability sanity check (α+β must be > 0 in x,y) ----
    α_all = np.vstack([_alpha_coeffs_local(m_i) for m_i in masses])      # (N,3)
    β_quad, γ_z = _beta_coeffs_local()
    βx, βy, βz = β_quad
    if np.any((α_all[:, 0] + βx) <= 0.0) or np.any((α_all[:, 1] + βy) <= 0.0):
        raise ValueError("Chosen χ and κ give radial instability (α+β ≤ 0).")

    # ----------------------------------------------------------------
    # 1) Get 3D equilibrium via your pos_find (NO z-only search here)
    # ----------------------------------------------------------------
    positions_opt, res = pos_find(
        masses,
        alpha_fn=_alpha_coeffs_local,
        beta_fn=_beta_coeffs_local,
        softening=softening,
        box=box,
        n_restarts=n_restarts,
        random_state=random_state,
        verbose=verbose,
        # Keep SciPy defaults/method from your pos_find
    )
    if verbose:
        print("pos_find success:", getattr(res, "success", None), "E[J]:", getattr(res, "fun", None))

    # ----------------------------------------------------------------
    # 2) Apply z_offset first, then rotate around the x-axis
    #    When theta=0: crystal along z-axis
    #    When theta=90: crystal along y-axis
    # ----------------------------------------------------------------
    # First apply the z_offset to the original equilibrium positions
    coords_with_offset = positions_opt.copy()
    coords_with_offset[:, 2] += z_offset  # Add z_offset to all z-coordinates
    
    # Then rotate the offset positions by theta_deg around the x-axis
    theta_rad = math.radians(theta_deg)
    cos_theta = math.cos(theta_rad)
    sin_theta = math.sin(theta_rad)
    
    # Rotation matrix around the x-axis
    R_matrix = np.array([
        [1,          0,           0],
        [0, cos_theta, -sin_theta],
        [0, sin_theta,  cos_theta]
    ], dtype=float)
    
    # Apply rotation to the offset coordinates
    coords_rotated = coords_with_offset @ R_matrix.T  # (N,3) @ (3,3) -> (N,3)
    
    z_eq_with_offset = coords_with_offset[:, 2].copy()   # axial projection after offset but before rotation
    coords = coords_rotated  # Use the rotated coordinates for Hessian calculation

    # ----------------------------------------------------------------
    # 3) Define total potential U(vec) consistent with α/β and Coulomb
    #    (This is for the original positions before rotation, but we'll use rotated coords for Hessian)
    # ----------------------------------------------------------------
    def U(vec: np.ndarray) -> float:
        total = 0.0
        # trap terms (coefficients are mass-dependent in x,y via α)
        for i in range(N):
            xi, yi, zi = vec[3*i:3*i+3]
            total += ((α_all[i, 0] + βx) * xi**2 +
                      (α_all[i, 1] + βy) * yi**2 +
                      (0.0 + βz) * zi**2 +
                      γ_z * zi)  # Add linear term
        # Coulomb terms
        for i, j in combinations(range(N), 2):
            ri = vec[3*i:3*i+3]
            rj = vec[3*j:3*j+3]
            total += C_COUL / np.linalg.norm(ri - rj)
        return float(total)

    # ----------------------------------------------------------------
    # 4) Analytic Hessian at rotated equilibrium (trap + Coulomb)
    #     H is 3N x 3N in coordinate space (not mass-weighted)
    # ----------------------------------------------------------------
    H = np.zeros((3*N, 3*N), dtype=float)

    # (a) Trap contributions: diagonal per ion
    #     U_trap,i = (αx_i+βx) x_i^2 + (αy_i+βy) y_i^2 + (βz) z_i^2 + γ_z z_i
    #     ⇒ ∂²U/∂x_i² = 2(αx_i+βx), ∂²U/∂y_i² = 2(αy_i+βy), ∂²U/∂z_i² = 2(βz)
    #     Note: linear term γ_z z_i has zero second derivative
    for i in range(N):
        H[3*i + 0, 3*i + 0] += 2.0 * (α_all[i, 0] + βx)
        H[3*i + 1, 3*i + 1] += 2.0 * (α_all[i, 1] + βy)
        H[3*i + 2, 3*i + 2] += 2.0 * (0.0           + βz)

    # (b) Coulomb contributions: for each pair (i,j)
    #     For U = k/r with r = |r_i - r_j| and d = r_i - r_j:
    #       G = k * ( I/r^3 - 3 * (d d^T)/r^5 )
    #     Then blocks:  H_ii += G,  H_jj += G,  H_ij -= G,  H_ji -= G
    C = K_E * (E_CH**2)  # J·m
    for i in range(N - 1):
        ri = coords[i]
        for j in range(i + 1, N):
            rj = coords[j]
            d  = ri - rj                       # vector (3,)
            r2 = float(np.dot(d, d))
            if r2 == 0.0:
                raise RuntimeError("Two ions have zero separation at equilibrium.")
            r  = math.sqrt(r2)
            r5 = r2 * r2 * r                   # = r^5 (stable)
            I3 = np.eye(3)
    
            # Coulomb Hessian block (correct sign):
            # G = k * (3 d d^T - r^2 I) / r^5
            G = C * (3.0 * np.outer(d, d) - r2 * I3) / r5     # 3x3
    
            i_slice = slice(3*i, 3*i+3)
            j_slice = slice(3*j, 3*j+3)
            H[i_slice, i_slice] += G
            H[j_slice, j_slice] += G
            H[i_slice, j_slice] -= G
            H[j_slice, i_slice] -= G


    # ----------------------------------------------------------------
    # 5) Mass-weight, diagonalize
    #     K = M^{-1/2} H M^{-1/2}; eigenvalues are ω²
    # ----------------------------------------------------------------
    M_inv_sqrt = np.repeat(1.0 / np.sqrt(masses), 3)  # (3N,)
    K = (M_inv_sqrt[:, None] * H) * M_inv_sqrt[None, :]
    lam, V = np.linalg.eigh(K)                        # V are mass-weighted eigenvectors (e')
    # normalize columns for neat output
    V = V / np.linalg.norm(V, axis=0, keepdims=True)
    freqs_Hz = np.sqrt(np.clip(lam, 0.0, None)) / (2.0 * math.pi)
    # Return with rotated coordinates and z-positions
    return freqs_Hz, V, z_eq_with_offset, coords


def eigenmodes_from_masses(
    A_seq: Iterable[int],
    *,
    chi_vec: Tuple[float, float] = tuple(chi),
    kappa_vec: Tuple[float, float, float] = tuple(kappa),
    theta_deg: float = 0.0,
    z_offset: float = 0.0,  # Z-axis offset in meters
    **kwargs,
):
    """Compute normal modes for a sequence of integer mass numbers.

    Extra keyword arguments are forwarded to `_eigenmodes_from_list`
    (e.g., softening, box, n_restarts, random_state, verbose).
    """
    return _eigenmodes_from_list(list(A_seq), chi_vec=chi_vec, kappa_vec=kappa_vec, 
                                 theta_deg=theta_deg, z_offset=z_offset, **kwargs)


# -------------------------------------------------------------------
# Convenience helpers (unchanged)
# -------------------------------------------------------------------

def _label_two(vec: np.ndarray) -> str:
    ex = vec[0] ** 2 + vec[3] ** 2
    ey = vec[1] ** 2 + vec[4] ** 2
    ez = vec[2] ** 2 + vec[5] ** 2
    axis = int(np.argmax([ex, ey, ez]))
    if axis == 2:
        return "Axial in-phase" if np.sign(vec[2]) == np.sign(vec[5]) else "Axial out-of-phase"
    return f"Radial ({'x' if axis == 0 else 'y'})"


def modes_dataframe(freqs_Hz, V):
    freqs = np.asarray(freqs_Hz); V = np.asarray(V)
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


# -------------------------------------------------------------------
# CLI that saves the table as PNG
# -------------------------------------------------------------------

def _format_df(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    df2["freq [kHz]"] = df2["freq [kHz]"].map(lambda x: f"{x:,.3f}")
    for col in df2.columns[2:]:
        df2[col] = df2[col].map(lambda x: f"{x: .4f}")
    return df2


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

    # You can set the rotation angle here or modify the input to accept theta
    theta_input = input("Enter rotation angle in degrees (default 0): ").strip()
    theta_deg = float(theta_input) if theta_input else 0.0
    
    z_offset_input = input("Enter z_offset in micrometers (default 0): ").strip()
    z_offset_um = float(z_offset_input) if z_offset_input else 0.0
    z_offset = z_offset_um * 1e-6  # Convert micrometers to meters
    
    freqs, V, z_eq, coords = eigenmodes_from_masses(masses, theta_deg=theta_deg, z_offset=z_offset)

    df = modes_dataframe(freqs, V)
    

    #find angle between two ion crystal and z axis
    if len(masses) >= 2:
        DX = coords[0][0] - coords[1][0]
        DY = coords[0][1] - coords[1][1]
        DZ = coords[0][2] - coords[1][2]
        angle = math.atan(math.sqrt(DX ** 2 + DY ** 2) / abs(DZ)) * 360 / (2*math.pi)
        print(f'angle between crystal and z axis is {angle}')

    print("\nz-equilibrium positions [µm]:", z_eq * 1e6)
    print("\nCartesian coordinates [µm] (one ion per row):\n", coords * 1e6)
    print("\n", df.to_string(index=False))

    # format DataFrame for PNG export
    df_fmt = _format_df(df)
    rows, cols = df_fmt.shape
    fig_w, fig_h = max(6.0, cols * 1.2), max(2.5, rows * 0.45)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    ax.set_title(
        "Normal modes for ions: "
        f"{' '.join(map(str, masses))}\n"
        f"U_RF={u_RF} V,  EC1 = {EC1}, EC2 = {EC2}, V,  Ω={RF_MHZ} MHz,  θ={theta_deg}°"
    )

    tbl = ax.table(cellText=df_fmt.values, colLabels=df_fmt.columns, loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1.2, 1.2)
    fig.tight_layout()

    slug = "-".join(map(str, masses))
    filename = f"normal_modes_{slug}_{int(u_RF)}V_{float(EC1)}V_{float(EC2)}V_{RF_MHZ:.1f}MHz_theta{theta_deg}deg.png"
    save_dir = "eigenmode_tables"
    os.makedirs(save_dir, exist_ok=True)
    #fig.savefig(os.path.join(save_dir, filename), dpi=300)
    plt.show(fig)

    #print(f"Saved → {os.path.join(save_dir, filename)}")