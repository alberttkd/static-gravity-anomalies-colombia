"""Run and grid comparisons (OP-14)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import xarray as xr


def _stats(d: np.ndarray) -> dict[str, float]:
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {"n": 0}
    return {
        "n": int(d.size),
        "mean_mgal": float(d.mean()),
        "sd_mgal": float(d.std()),
        "min_mgal": float(d.min()),
        "max_mgal": float(d.max()),
        "rms_mgal": float(np.sqrt(np.mean(d**2))),
    }


def compare_station_runs(
    a: pd.DataFrame, b: pd.DataFrame, columns: tuple[str, ...] = ("faa_mgal", "sba_mgal", "cba_mgal")
) -> dict[str, Any]:
    """Statistics of ``a - b`` per anomaly column. Both tables need the same ``station_uid`` set."""
    if set(a["station_uid"]) != set(b["station_uid"]):
        raise ValueError("runs have different station sets")
    b2 = b.set_index("station_uid").loc[a["station_uid"]]
    return {c: _stats(a[c].to_numpy() - b2[c].to_numpy()) for c in columns if c in a and c in b2}


def compare_grids(a: xr.Dataset, b: xr.Dataset, variable: str = "value") -> dict[str, Any]:
    """Statistics of ``a - b`` over cells supported in both grids (same axes required)."""
    if a.sizes != b.sizes or not np.allclose(a["x"], b["x"]) or not np.allclose(a["y"], b["y"]):
        raise ValueError("grids have different axes")
    both = (a["support_mask"].values == 1) & (b["support_mask"].values == 1)
    return _stats((a[variable].values - b[variable].values)[both])


def term_decomposition(standard: pd.DataFrame, legacy: pd.DataFrame) -> dict[str, Any]:
    """Term-by-term difference standard minus legacy (RQ1).

    Both tables are outputs of :func:`gravanom.reduction.compute_anomalies`
    (legacy mode for ``legacy``). Each term's effect on the CBA is given with its
    sign convention (+ added to the anomaly, - subtracted).
    """
    effects = {
        "normal_gravity": -(standard["gamma0_mgal"] - legacy["gamma0_mgal"]),
        "honkasalo": standard["honkasalo_mgal"] - legacy["honkasalo_mgal"],
        "atmospheric": standard["atm_mgal"] - legacy["atm_mgal"],
        "height_correction": standard["height_corr_mgal"] - legacy["height_corr_mgal"],
        "bouguer_slab_density": -(standard["bc_slab_mgal"] - legacy["bc_slab_mgal"]),
        "curvature_bb": -(standard["bb_mgal"] - legacy["bb_mgal"]),
        "terrain_scaling": standard["tc_rho_mgal"] - legacy["tc_rho_mgal"],
    }
    out: dict[str, Any] = {k: _stats(v.to_numpy(dtype=float)) for k, v in effects.items()}
    total = standard["cba_mgal"] - legacy["cba_mgal"]
    out["total_cba"] = _stats(total.to_numpy(dtype=float))
    resid = total - sum(effects.values())
    out["closure_max_abs_mgal"] = float(np.nanmax(np.abs(resid.to_numpy(dtype=float))))
    ranked = sorted(effects, key=lambda k: -out[k].get("rms_mgal", 0.0))
    out["ranking_by_rms"] = ranked
    return out
