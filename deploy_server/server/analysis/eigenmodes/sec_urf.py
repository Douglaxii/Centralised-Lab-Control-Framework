#!/usr/bin/env python3

from __future__ import annotations

# ── stdlib ──────────────────────────────────────────────────────────
import sys, importlib, math, os
from typing import List
from datetime import datetime

# ── 3rd-party ───────────────────────────────────────────────────────
import pandas as pd
import numpy as np

from itertools import product
from typing import Sequence, Iterable

# ── import the physics engine ───────────────────────────────────────
try:
    trap = importlib.import_module("trap_sim")
    print("✓ using physics module: trap_sim")
except ModuleNotFoundError:
    sys.exit("❌  trap_sim.py not found on PYTHONPATH")

# ── helper: evaluate one grid point ─────────────────────────────────
def sec_freq(layout_u: List[int], u_rf: float, v_end: float) -> np.ndarray:
    """Return *all* 3 N secular freqs in kHz; NaNs if unstable."""
    saved_u, saved_v = trap.u_RF, trap.v_end
    try:
        trap.u_RF, trap.v_end = u_rf, v_end
        freqs_Hz, V, z_eq , coord= trap.eigenmodes_from_masses(layout_u)
        return freqs_Hz / 1e3,  z_eq # → kHz, 
    except Exception:
        return np.full(3 * len(layout_u), math.nan)
    finally:
        trap.u_RF, trap.v_end = saved_u, saved_v

# ── finds estimation of v_end according to sec ─────────────────────────────────
def nearest_index(values, target):
    """
    Return the index of the element in *values* whose value is
    closest to *target*.  In case of a tie, the first index wins.
    """

    idx, _ = min(
        enumerate(values),
        key=lambda pair: abs(pair[1] - target)
    )
    return idx

try:
    sec_z = float(input("measured axial secular frequency for single Be+ [kHz]: "))
except ValueError:
    sys.exit("v_end must be a number – exiting.")

v_vals = np.linspace(0.001, 100.001, 1000)
freqs  = np.empty((1000, 3)) 
for i, v in enumerate(v_vals):
    freqs[i, :] , z_eq = sec_freq([9], 250.0, v)

freqs_z = freqs[:, 0]
v_index = nearest_index(freqs_z, sec_z)
v_setting = v_vals[v_index]


print('V_end is approximately: ' + str(v_setting) + 'V')


# ── iterate different number of ions and u_rf ──────────────────────────────────────────────────────
u_vals = np.linspace(50.0, 250.0, 200)
max_ions = 2  # max number of cotrapped ions




def ion_mass_permutations(
    n_ions: int,
    *,
    candidates: Sequence[int] = (1, 2, 3, 14, 16, 18, 26, 27, 28),
    must_contain: tuple[int, ...] = (),
    as_numpy: bool = False,
) -> Iterable[tuple[int, ...] | np.ndarray]:

    # --- validation ---------------------------------------------------------
    illegal = set(must_contain) - set(candidates)
    if illegal:
        raise ValueError(f"masses {sorted(illegal)} not in *candidates*")

    # quick helper
    meets_must = (
        (lambda t: all(m in t for m in must_contain))
        if must_contain
        else (lambda t: True)
    )

    # ------------------------------------------------------------------------
    for combo in product(candidates, repeat=n_ions):
        # enforce required masses
        if not meets_must(combo):
            continue

        # ignore the “twin” created by 180° rotation
        if combo > combo[::-1]:
            continue

        yield np.asarray(combo) if as_numpy else combo







# ── parameters ──────────────────────────
u_rf       = 230.0                     
max_ions   = 4                         
candidates = (1, 2, 3, 9)

dfs = []

for n in range(2, max_ions + 1):
    rows = []
    for masses in ion_mass_permutations(n, candidates=candidates):
        if masses.count(9) >= 1:
            axial_kHz, z_eq = sec_freq(list(masses), u_rf, v_setting)
            if np.any(np.isnan(axial_kHz)) or np.any(np.isclose(axial_kHz, 0.0)):
                continue

            axial_kHz = np.sort(axial_kHz)

            row = {f"{n}": masses}
            for i in range(1):  # ← iterate up to n - 1 inclusive
                row[f"axial_{n}_{i}"] = axial_kHz[i]
            #row["z_eq[µm]"] = ", ".join(f"{z:.3f}" for z in z_eq * 1e6)

            rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        df = df.sort_values(by=f"axial_{n}_0").reset_index(drop=True)
        dfs.append(df)


wide = pd.concat(dfs, axis=1)
# ── timestamped file-name ───────────────────────────────────────────
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
outfile   = f"iondatasheet_{v_setting:.3f}V_{timestamp}.csv"
#wide.to_csv(outfile, index=False)

print(
    f"✓ wrote {len(wide)} rows × {wide.shape[1]} columns to {outfile}\n"
    "  (each ion-count block is now sorted in ascending axial frequency)"
)

# ── show the table in the console ──────────────────────────────────
print("\nPreview of the results table:\n")


try:
    from tabulate import tabulate

    preview = wide.head(50)
    print(tabulate(preview, headers='keys', tablefmt='github', showindex=False))


except ImportError:
    with pd.option_context('display.max_columns', None,
                           'display.width',       None):
        print(wide.head(50))





































