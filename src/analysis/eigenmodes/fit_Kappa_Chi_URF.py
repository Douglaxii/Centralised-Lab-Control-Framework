# -*- coding: utf-8 -*-

from __future__ import annotations

# ── Python stdlib ────────────────────────────────────────────────────
import math
from dataclasses import dataclass, field
from typing import Sequence, Iterable
import contextlib

# ── Third-party ──────────────────────────────────────────────────────
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.optimize import linear_sum_assignment
import trap_sim as model


# ── Data containers ──────────────────────────────────────────────────
@dataclass
class DataSet:
    masses_A: list[int]
    measured_kHz: list[float]
    which_modes: str = "axial"
    sigma_kHz: float | list[float] | None = None
    u_RF: float = 100.0
    v_end: float = 4.0
    RF_MHZ: float | None = None
    r_0: float | None = None
    z_0: float | None = None
    pos_kwargs: dict = field(default_factory=lambda: dict(softening=1e-9, box=(1e-3,1e-3,2e-3), n_restarts=2, random_state=0, verbose=False))
    name: str = ""

    # Cached weights vector (computed on first access)
    @property
    def weights(self) -> np.ndarray:
        y = np.asarray(self.measured_kHz, dtype=float)
        if self.sigma_kHz is None:
            w = np.ones_like(y)
        elif np.isscalar(self.sigma_kHz):
            w = np.full_like(y, float(self.sigma_kHz))
        else:
            w = np.asarray(self.sigma_kHz, dtype=float)
            if w.shape != y.shape:
                raise ValueError("sigma_kHz must be scalar or same length as measured_kHz")
        return np.clip(w, 1e-9, None)


@dataclass
class FitMultiResult:
    chi: tuple[float, float]
    kappa: tuple[float, float, float]
    chi_err: tuple[float, float] | None
    kappa_err: tuple[float, float, float] | None
    per_dataset: list[pd.DataFrame]  # columns: measured, predicted, residual (kHz)
    success: bool
    message: str


# ── Utilities ────────────────────────────────────────────────────────
@contextlib.contextmanager
def trap_context(*, u_RF: float | None = None, v_end: float | None = None,
                 RF_MHZ: float | None = None, r_0: float | None = None,
                 z_0: float | None = None):
    """Temporarily override trap globals in the imported `model` module."""
    # Snapshot originals
    orig = {
        'u_RF': model.u_RF,
        'v_end': model.v_end,
        'RF_MHZ': model.RF_MHZ,
        'OMEGA': model.OMEGA,
        'r_0': model.r_0,
        'z_0': model.z_0,
    }
    try:
        if u_RF is not None:
            model.u_RF = float(u_RF)
        if v_end is not None:
            model.v_end = float(v_end)
        if r_0 is not None:
            model.r_0 = float(r_0)
        if z_0 is not None:
            model.z_0 = float(z_0)
        if RF_MHZ is not None:
            model.RF_MHZ = float(RF_MHZ)
            model.OMEGA = model.RF_MHZ * 1e6 * 2.0 * math.pi
        yield
    finally:
        # Restore
        model.u_RF = orig['u_RF']
        model.v_end = orig['v_end']
        model.RF_MHZ = orig['RF_MHZ']
        model.OMEGA = orig['OMEGA']
        model.r_0 = orig['r_0']
        model.z_0 = orig['z_0']


def _select_modes(freqs_Hz: np.ndarray, V: np.ndarray, *, which: str = "all",
                  axis_thresh: float = 0.6) -> np.ndarray:
    if which == "all":
        return np.arange(freqs_Hz.size)
    N = V.shape[0] // 3
    X = (V[0::3, :]**2).sum(axis=0)
    Y = (V[1::3, :]**2).sum(axis=0)
    Z = (V[2::3, :]**2).sum(axis=0)
    if which == "axial":
        return np.where(Z >= axis_thresh)[0]
    if which == "radial":
        return np.where((X + Y) >= axis_thresh)[0]
    if which == "radial_x":
        return np.where(X >= axis_thresh)[0]
    if which == "radial_y":
        return np.where(Y >= axis_thresh)[0]
    raise ValueError("which must be one of: 'all','axial','radial','radial_x','radial_y'.")


def _pred_freqs_kHz_for_dataset(params: np.ndarray, ds: DataSet,
                                *, axis_thresh: float = 0.6) -> np.ndarray:
    """Return sorted predicted kHz for the selected modes of one dataset."""
    chi_x, chi_y, kx, ky, kz = params
    with trap_context(u_RF=ds.u_RF, v_end=ds.v_end, RF_MHZ=ds.RF_MHZ, r_0=ds.r_0, z_0=ds.z_0):
        freqs_Hz, V, *_ = model.eigenmodes_from_masses(
            ds.masses_A, chi_vec=(chi_x, chi_y), kappa_vec=(kx, ky, kz), **ds.pos_kwargs
        )
    idx = _select_modes(freqs_Hz, V, which=ds.which_modes, axis_thresh=axis_thresh)
    f_sel = freqs_Hz[idx] / 1e3
    return np.sort(f_sel)


def _stability_ok_for_dataset(params: np.ndarray, ds: DataSet) -> bool:
    """Radial stability check α+β > 0 in x and y for all ions, at ds settings."""
    chi_x, chi_y, kx, ky, kz = params
    # Geometry / drive from ds or model defaults
    RF_MHZ = model.RF_MHZ if ds.RF_MHZ is None else float(ds.RF_MHZ)
    OMEGA = RF_MHZ * 1e6 * 2.0 * math.pi
    r0 = model.r_0 if ds.r_0 is None else float(ds.r_0)
    z0 = model.z_0 if ds.z_0 is None else float(ds.z_0)

    # α prefactor (mass-dependent) and β from v_end
    for A in ds.masses_A:
        m_kg = model.mass_from_A(A)
        pref_a = (model.E_CH**2) * (ds.u_RF**2) / (4.0 * m_kg * OMEGA**2 * r0**4)
        ax = pref_a * chi_x
        ay = pref_a * chi_y
        pref_b = model.E_CH * ds.v_end / (z0**2)
        bx = -0.5 * pref_b * kx
        by = -0.5 * pref_b * ky
        if (ax + bx) <= 0.0 or (ay + by) <= 0.0:
            return False
    return True


# ── Global fit across datasets ───────────────────────────────────────

def fit_chi_kappa_multi(
    datasets: Sequence[DataSet],
    *,
    init: tuple[float, float, float, float, float] | None = None,
    bounds_scale: tuple[float, float] = (0.2, 5.0),
    robust_loss: str = "soft_l1",
    axis_thresh: float = 0.6,
    max_nfev: int = 300,
) -> FitMultiResult:
    if not datasets:
        raise ValueError("datasets must be a non-empty sequence of DataSet")

    # Build concatenated measurement and weights (only for sizing; we match within residuals)
    total_meas = sum(len(ds.measured_kHz) for ds in datasets)

    # Initial guess & bounds
    if init is None:
        init = (float(model.chi[0]), float(model.chi[1]), float(model.kappa[0]), float(model.kappa[1]), float(model.kappa[2]))
    lo, hi = bounds_scale
    lb = np.maximum(np.array(init) * lo, 1e-6)
    ub = np.maximum(np.array(init) * hi, lb * 1.0001)

    # Residuals builder
    meas_concat = np.concatenate([np.asarray(ds.measured_kHz, float) for ds in datasets])
    w_concat = np.concatenate([ds.weights for ds in datasets])

    # Offsets for slicing in final report
    offsets = np.cumsum([0] + [len(ds.measured_kHz) for ds in datasets])

    def residuals(params: np.ndarray) -> np.ndarray:
        r_all = []
        for ds in datasets:
            if not _stability_ok_for_dataset(params, ds):
                # penalize heavily if unstable at these settings
                r_all.append(np.full(len(ds.measured_kHz), 1e6))
                continue
            try:
                pred = _pred_freqs_kHz_for_dataset(params, ds, axis_thresh=axis_thresh)
            except Exception:
                r_all.append(np.full(len(ds.measured_kHz), 1e6))
                continue
            y = np.asarray(ds.measured_kHz, float)
            w = ds.weights
            if pred.size < y.size:
                r_all.append(np.full_like(y, 1e6))
                continue
            # Hungarian assignment per dataset
            cost = (pred[None, :] - y[:, None])**2 / (w[:, None]**2)
            row_ind, col_ind = linear_sum_assignment(cost)
            matched = pred[col_ind]
            r_all.append((matched - y) / w)
        return np.concatenate(r_all)

    res = least_squares(
        residuals,
        x0=np.array(init, float),
        bounds=(lb, ub),
        loss=robust_loss,
        jac="2-point",
        xtol=1e-10, ftol=1e-10, gtol=1e-10,
        max_nfev=max_nfev,
    )

    best = res.x

    # Build per-dataset matched tables for reporting
    per_tables: list[pd.DataFrame] = []
    for ds in datasets:
        try:
            pred = _pred_freqs_kHz_for_dataset(best, ds, axis_thresh=axis_thresh)
        except Exception:
            y = np.asarray(ds.measured_kHz, float)
            per_tables.append(pd.DataFrame({"measured [kHz]": y, "predicted [kHz]": np.nan, "residual [kHz]": np.nan}))
            continue
        y = np.asarray(ds.measured_kHz, float)
        w = ds.weights
        cost = (pred[None, :] - y[:, None])**2 / (w[:, None]**2)
        row_ind, col_ind = linear_sum_assignment(cost)
        matched = pred[col_ind]
        tbl = pd.DataFrame({
            "measured [kHz]": y,
            "predicted [kHz]": matched,
            "residual [kHz]": matched - y,
        })
        per_tables.append(tbl)

    # 1σ errors from Jacobian
    chi_err = kappa_err = None
    try:
        dof = max(1, meas_concat.size - 5)
        s2 = 2.0 * res.cost / dof
        JTJ = res.jac.T @ res.jac
        cov = s2 * np.linalg.pinv(JTJ)
        errs = np.sqrt(np.clip(np.diag(cov), 0.0, None))
        chi_err = (errs[0], errs[1])
        kappa_err = (errs[2], errs[3], errs[4])
    except Exception:
        pass

    return FitMultiResult(
        chi=(best[0], best[1]),
        kappa=(best[2], best[3], best[4]),
        chi_err=chi_err,
        kappa_err=kappa_err,
        per_dataset=per_tables,
        success=res.success,
        message=res.message,
    )


# ── Simple interactive CLI ──────────────────────────────────────────

def _cli_prompt_float(prompt: str, default: float | None = None) -> float:
    while True:
        s = input(prompt + (f" [default {default}]: " if default is not None else ": ")).strip()
        if not s and default is not None:
            return float(default)
        try:
            return float(s)
        except ValueError:
            print("Please enter a number.")


def _cli():
    print("\n=== Joint fit of χ, κ across multiple trap settings ===\n")
    masses_line = input("Enter ion mass numbers (u), space-separated (e.g., '9 9'):\n> ").strip()
    masses = [int(tok) for tok in masses_line.split()]

    # Defaults from current model
    default_r0 = model.r_0
    default_z0 = model.z_0
    default_RF = model.RF_MHZ

    datasets: list[DataSet] = []
    n_sets = int(_cli_prompt_float("How many datasets (different settings) do you want to fit?", 2))

    for k in range(n_sets):
        print(f"\n--- Dataset {k+1}/{n_sets} ---")
        u = _cli_prompt_float("U_RF in volts", model.u_RF)
        v = _cli_prompt_float("V_end in volts", model.v_end)
        rf = _cli_prompt_float("RF_MHZ (blank = keep model default)", default_RF)
        use_default_geom = input("Use default geometry r_0, z_0 from model? [Y/n] ").strip().lower()
        if use_default_geom in ("", "y", "yes"):
            r0 = default_r0; z0 = default_z0
        else:
            r0 = _cli_prompt_float("r_0 (m)", default_r0)
            z0 = _cli_prompt_float("z_0 (m)", default_z0)
        which = input("Which modes? [all | axial | radial | radial_x | radial_y] (default: axial)\n> ").strip() or "axial"
        y_line = input("Measured frequencies in kHz (space-separated):\n> ").strip()
        y = [float(tok) for tok in y_line.split()]
        s_line = input("1σ uncertainties in kHz (single number or leave blank for equal weights):\n> ").strip()
        sigma = float(s_line) if s_line else None
        name = input("Optional label for this dataset (press Enter to skip):\n> ").strip()

        ds = DataSet(masses_A=masses, measured_kHz=y, sigma_kHz=sigma,
                     which_modes=which, u_RF=u, v_end=v, RF_MHZ=rf,
                     r_0=r0, z_0=z0, name=name)
        datasets.append(ds)

    # Initial guess and fit
    init = (float(model.chi[0]), float(model.chi[1]), float(model.kappa[0]), float(model.kappa[1]), float(model.kappa[2]))
    result = fit_chi_kappa_multi(datasets, init=init)

    print("\n--- Fit status:", "SUCCESS" if result.success else "FAILED", "---")
    print(result.message)

    cx, cy = result.chi
    kx, ky, kz = result.kappa
    if result.chi_err and result.kappa_err:
        dcx, dcy = result.chi_err
        dkx, dky, dkz = result.kappa_err
        '''
        print(f"\nχx = {cx:.6f} ± {dcx:.6f}")
        print(f"χy = {cy:.6f} ± {dcy:.6f}")
        print(f"κx = {kx:.6f} ± {dkx:.6f}")
        print(f"κy = {ky:.6f} ± {dky:.6f}")
        print(f"κz = {kz:.6f} ± {dkz:.6f}")
        '''
        print(f"\n χ = [{cx:.6f},{cy:.6f}]")
        print(f"\n κ = [{kx:.6f},{ky:.6f},{kz:.6f}]")
    else:
        print(f"\nχx = {cx:.6f}\nχy = {cy:.6f}\nκx = {kx:.6f}\nκy = {ky:.6f}\nκz = {kz:.6f}")

    # Print per-dataset tables
    for k, (ds, tbl) in enumerate(zip(datasets, result.per_dataset), 1):
        header = ds.name if ds.name else f"Dataset {k}"
        print(f"\n{header}: U_RF={ds.u_RF:.3f} V, V_end={ds.v_end:.3f} V, RF={ds.RF_MHZ if ds.RF_MHZ is not None else model.RF_MHZ:.3f} MHz")
        print(tbl.to_string(index=False))


if __name__ == "__main__":
    _cli()
