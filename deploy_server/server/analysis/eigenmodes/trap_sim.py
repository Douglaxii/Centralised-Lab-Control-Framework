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

# ── Physical constants ───────────────────────────────────────────────
EPS0 = 8.854_187_812_8e-12  # vacuum permittivity [F/m]
E_CH = 1.602_176_634e-19    # elementary charge [C]
U_AMU = 1.660_539_066_60e-27  # atomic-mass unit [kg]
K_E  = 8.9875517923e9     

# ── Trap parameters (globals; may be patched by importer) ────────────
u_RF = 300        # RF voltage amplitude [V]
v_end = 30         # DC end-cap voltage [V]
r_0 = 0.8e-3        # half distance between RF rods [m]
z_0 = 2.5e-3        # half distance between end-caps [m]
RF_MHZ = 35.8515       # drive frequency [MHz]
OMEGA = RF_MHZ * 1e6 * 2 * math.pi  # RF angular frequency [rad/s]

kappa = [0.261519,0.256080,0.108838]  # (k_x, k_y, k_z)
chi   = [0.939947,0.935415]

'''
kappa = [0.109,0.109,0.1019] # (k_x, k_y, k_z)
chi   = [1.0,1.0]
#potential calculation
'''
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

def beta_coeffs(*, q=E_CH, v_end=None, z0=None):
    """
    Return array [βx, βy, βz] such that the static/DC energy is
        U_beta = βx x^2 + βy y^2 + βz z^2.
    Sign conventions follow your definition.
    """
    if v_end is None:
        v_end = globals().get("v_end")
    if z0 is None:
        z0 = globals().get("z_0")
    if v_end is None or z0 is None:
        raise ValueError("beta_coeffs needs v_end and z0 (either explicit or global).")
    kx, ky, kz = kappa
    pref = q * v_end / z0**2  # J/m^2 per κ
    return np.array([-0.5 * pref * kx, -0.5 * pref * ky, +pref * kz], dtype=float)


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
        V_total = sum_i [ alpha_i(pos_i, m_i) + beta_i(pos_i) ]  +  sum_{i<j} k_e q_i q_j / |r_i - r_j|

    Parameters
    ----------
    positions : (N,3) array_like
        Ion coordinates (meters).
    masses : (N,) array_like
        Ion masses (kg), in the same order as positions.
    alpha_fn : callable
        Called as alpha_fn(pos, m_kg=m) -> scalar potential contribution for that ion.
    beta_fn : callable
        Called as beta_fn(pos) -> scalar potential contribution for that ion.
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
    # alpha_fn(m_kg) -> [αx,αy,αz]; beta_fn() -> [βx,βy,βz]  (both in J/m^2)
    beta_coeff = np.asarray(beta_fn(), dtype=float)     # (3,)
    V_alpha_i = np.empty(N, dtype=float)
    V_beta_i  = np.empty(N, dtype=float)
    V_trap_per_ion = np.empty(N, dtype=float)

    for i in range(N):
        a = np.asarray(alpha_fn(m_kg=M[i]), dtype=float)  # (3,)
        r2 = R[i]**2
        V_alpha_i[i] = float(np.dot(a, r2))               # α⋅r^2
        V_beta_i[i]  = float(np.dot(beta_coeff, r2))      # β⋅r^2
        V_trap_per_ion[i] = V_alpha_i[i] + V_beta_i[i]

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
                trap=V_trap_per_ion,
                coulomb=V_coul_per_ion,
            ),
        )
    return V_total

    
#find positions of ions

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
    softening=0.0,
    init="linear",
    scale=None,
    box=None,
    n_restarts=6,
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
        bx, by, bz = beta_coeffs()                     # J/m^2
        d3 = (K_E * E_CH**2) / (2.0 * bz)              # m^3
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
    beta_coeff = np.asarray(beta_fn(), dtype=float)        # (3,)
    alpha_all  = np.vstack([np.asarray(alpha_fn(m_kg=m), float) for m in masses])  # (N,3)

    def energy_and_grad(x):
        R = _unpack(x)                                     # (N,3)

        # Trap
        coeff  = alpha_all + beta_coeff                    # (N,3)
        trap_E = float(np.sum(coeff * (R**2)))
        trap_g = 2.0 * coeff * R

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




'''
masses = np.array([9, 3, 2, 2,2]) * U_AMU

positions_opt, res = pos_find(
    masses,
    alpha_fn=alpha_coeffs,   # depends on mass, returns [αx,αy,αz]
    beta_fn=beta_coeffs,     # mass-independent, returns [βx,βy,βz]
    softening=1e-9,
    box=(1e-3, 1e-3, 2e-3),
    n_restarts=8,
    random_state=0,
    verbose=True
)



print("Optimal positions (m):\n", positions_opt)
'''


#eigenmode calculater
def mass_from_A(A: int, *, u_amu: float = U_AMU) -> float:
    """Convert an integer mass number *A* to kilograms (no binding-energy corr.)."""
    if A <= 0:
        raise ValueError("Mass number must be positive.")
    return A * u_amu

def _eigenmodes_from_list(
    A_list: Sequence[int],
    *,
    chi_vec: Tuple[float, float] = tuple(chi),              # (χx, χy)
    kappa_vec: Tuple[float, float, float] = tuple(kappa),   # (κx, κy, κz)
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

    def _beta_coeffs_local() -> np.ndarray:
        pref = E_CH * v_end / (z_0**2)
        return np.array([-0.5 * pref * κx, -0.5 * pref * κy, +pref * κz], dtype=float)

    # ---- masses and Coulomb const ----
    masses = np.asarray([mass_from_A(A) for A in A_list], dtype=float)  # kg
    N = masses.size
    C_COUL = K_E * (E_CH**2)  # J·m

    # ---- radial stability sanity check (α+β must be > 0 in x,y) ----
    α_all = np.vstack([_alpha_coeffs_local(m_i) for m_i in masses])      # (N,3)
    βx, βy, βz = _beta_coeffs_local()
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

    r_eq_flat = positions_opt.reshape(-1).astype(float)  # (3N,)
    coords = positions_opt.copy()                        # (N,3)
    z_eq = coords[:, 2].copy()                           # axial projection (for printing)

    # ----------------------------------------------------------------
    # 2) Define total potential U(vec) consistent with α/β and Coulomb
    # ----------------------------------------------------------------
    def U(vec: np.ndarray) -> float:
        total = 0.0
        # trap terms (coefficients are mass-dependent in x,y via α)
        for i in range(N):
            xi, yi, zi = vec[3*i:3*i+3]
            total += ((α_all[i, 0] + βx) * xi**2 +
                      (α_all[i, 1] + βy) * yi**2 +
                      (0.0 + βz) * zi**2)
        # Coulomb terms
        for i, j in combinations(range(N), 2):
            ri = vec[3*i:3*i+3]
            rj = vec[3*j:3*j+3]
            total += C_COUL / np.linalg.norm(ri - rj)
        return float(total)

    # ----------------------------------------------------------------
    # 3) Analytic Hessian at equilibrium (trap + Coulomb)
    #     H is 3N x 3N in coordinate space (not mass-weighted)
    # ----------------------------------------------------------------
    H = np.zeros((3*N, 3*N), dtype=float)

    # (a) Trap contributions: diagonal per ion
    #     U_trap,i = (αx_i+βx) x_i^2 + (αy_i+βy) y_i^2 + (βz) z_i^2
    #     ⇒ ∂²U/∂x_i² = 2(αx_i+βx), etc.
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
    # 4) Mass-weight, diagonalize
    #     K = M^{-1/2} H M^{-1/2}; eigenvalues are ω²
    # ----------------------------------------------------------------
    M_inv_sqrt = np.repeat(1.0 / np.sqrt(masses), 3)  # (3N,)
    K = (M_inv_sqrt[:, None] * H) * M_inv_sqrt[None, :]
    lam, V = np.linalg.eigh(K)                        # V are mass-weighted eigenvectors (e')
    # normalize columns for neat output
    V = V / np.linalg.norm(V, axis=0, keepdims=True)
    freqs_Hz = np.sqrt(np.clip(lam, 0.0, None)) / (2.0 * math.pi)

    return freqs_Hz, V, z_eq, coords





def eigenmodes_from_masses(
    A_seq: Iterable[int],
    *,
    chi_vec: Tuple[float, float] = tuple(chi),
    kappa_vec: Tuple[float, float, float] = tuple(kappa),
    **kwargs,
):
    """Compute normal modes for a sequence of integer mass numbers.

    Extra keyword arguments are forwarded to `_eigenmodes_from_list`
    (e.g., softening, box, n_restarts, random_state, verbose).
    """
    return _eigenmodes_from_list(list(A_seq), chi_vec=chi_vec, kappa_vec=kappa_vec, **kwargs)



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
# Simple CLI that saves the table as PNG
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

    freqs, V, z_eq, coords = eigenmodes_from_masses(masses)

    df = modes_dataframe(freqs, V)

    print("\nz-equilibrium positions [µm]:", z_eq * 1e6)
    print("\nCartesian coordinates (one ion per row):\n", coords)
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
        f"U_RF={u_RF} V,  V_end={v_end} V,  Ω={RF_MHZ} MHz"
    )

    tbl = ax.table(cellText=df_fmt.values, colLabels=df_fmt.columns, loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1.2, 1.2)
    fig.tight_layout()

    slug = "-".join(map(str, masses))
    filename = f"normal_modes_{slug}_{int(u_RF)}V_{float(v_end)}V_{RF_MHZ:.1f}MHz.png"
    save_dir = "eigenmode_tables"
    os.makedirs(save_dir, exist_ok=True)
    #fig.savefig(os.path.join(save_dir, filename), dpi=300)
    plt.close(fig)

    print(f"Saved → {os.path.join(save_dir, filename)}")

