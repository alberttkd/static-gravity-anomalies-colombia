"""Data-driven reduction-density diagnostics (MASTER_GUIDE §5.5.4).

Both estimators work on residuals after removing a polynomial trend (degree 2 by
default) and get 95 % confidence intervals from a spatial block bootstrap.

Nettleton (1939): the density minimizing |corr(CBA(rho), H)|.
Parasnis (1952): OLS slope of FAA on the unit-density Bouguer-plus-terrain term
:math:`X = BC_{cap}(H; \\rho = 1) - TC/\\rho_{TC}`, since
:math:`FAA = \\rho X + c + \\varepsilon` when CBA is uncorrelated with topography.

Both assume topography and subsurface density are uncorrelated; with low relief the
estimates are weakly constrained (hypothesis H5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from gravanom.config import DensityConfig
from gravanom.reduction.curvature import spherical_cap

F64 = NDArray[np.float64]

#: Minimum number of stations for the diagnostics (OP-06).
MIN_STATIONS = 100
#: Physically plausible range of crustal reduction densities [kg m^-3].
PLAUSIBLE_RHO_KG_M3 = (1800.0, 3000.0)


class InsufficientDataError(ValueError):
    """Too few usable points for an estimator (API code INSUFFICIENT_DATA)."""


def design_matrix(x: F64, y: F64, degree: int) -> F64:
    """Polynomial design matrix in centred, scaled coordinates (units of 100 km)."""
    xs = (x - x.mean()) / 1e5
    ys = (y - y.mean()) / 1e5
    cols = [np.ones_like(xs)]
    for d in range(1, degree + 1):
        for i in range(d + 1):
            cols.append(xs ** (d - i) * ys**i)
    return np.column_stack(cols)


def detrend(values: F64, x: F64, y: F64, degree: int) -> F64:
    """Residuals of an OLS polynomial trend of the given degree (columns of ``values`` independently)."""
    a = design_matrix(x, y, degree)
    coef, *_ = np.linalg.lstsq(a, values, rcond=None)
    return np.asarray(values - a @ coef)


def unit_density_term(height_m: F64, tc_mgal: F64, rho_tc_kg_m3: float = 2670.0) -> F64:
    """Parasnis regressor X = BC_cap(H; rho = 1 kg m^-3) - TC / rho_TC [mGal per kg m^-3]."""
    return np.asarray(spherical_cap(height_m, 1.0) - tc_mgal / rho_tc_kg_m3)


@dataclass(frozen=True)
class _Inputs:
    faa: F64
    xterm: F64
    h: F64
    x: F64
    y: F64


def _nettleton_point(inp: _Inputs, rhos: F64, degree: int) -> tuple[float, F64]:
    r = detrend(np.column_stack([inp.faa, inp.xterm, inp.h]), inp.x, inp.y, degree)
    faa_r, x_r, h_r = r[:, 0], r[:, 1], r[:, 2]
    cba = faa_r[:, None] - x_r[:, None] * rhos[None, :]
    cba -= cba.mean(axis=0)
    hc = h_r - h_r.mean()
    corr = (cba * hc[:, None]).sum(axis=0) / np.sqrt((cba**2).sum(axis=0) * (hc**2).sum())
    return float(rhos[np.argmin(np.abs(corr))]), np.asarray(corr)


def _parasnis_point(inp: _Inputs, degree: int) -> tuple[float, float]:
    r = detrend(np.column_stack([inp.faa, inp.xterm]), inp.x, inp.y, degree)
    faa_r, x_r = r[:, 0], r[:, 1]
    a = np.column_stack([x_r, np.ones_like(x_r)])
    (rho, c), *_ = np.linalg.lstsq(a, faa_r, rcond=None)
    return float(rho), float(c)


def _blocks(x: F64, y: F64, block_m: float) -> list[NDArray[np.int64]]:
    keys = np.floor(x / block_m).astype(np.int64) * 1_000_003 + np.floor(y / block_m).astype(np.int64)
    _, inv = np.unique(keys, return_inverse=True)
    return [np.flatnonzero(inv == k) for k in range(inv.max() + 1)]


def density_diagnostics(
    faa_mgal: F64,
    height_m: F64,
    tc_mgal: F64,
    x_m: F64,
    y_m: F64,
    config: DensityConfig | None = None,
    rho_tc_kg_m3: float = 2670.0,
) -> dict[str, Any]:
    """Nettleton and Parasnis density estimates with block-bootstrap 95 % CIs.

    Parameters
    ----------
    faa_mgal, height_m, tc_mgal : array_like
        Free-air anomaly [mGal], height [m] and supplied terrain correction [mGal]
        at the stations; stations with non-finite values are dropped.
    x_m, y_m : array_like
        Projected coordinates [m] (EPSG:9377).
    config : DensityConfig, optional
        Grid of densities, trend degree and bootstrap settings.

    Returns
    -------
    dict
        ``nettleton`` and ``parasnis`` blocks (estimate, CI, bootstrap spread),
        the Nettleton correlation curve and the H5 evaluation.

    Raises
    ------
    InsufficientDataError
        Fewer than 100 usable stations.
    """
    cfg = config or DensityConfig()
    arrs = [np.asarray(a, dtype=np.float64) for a in (faa_mgal, height_m, tc_mgal, x_m, y_m)]
    ok = np.logical_and.reduce([np.isfinite(a) for a in arrs])
    if ok.sum() < MIN_STATIONS:
        raise InsufficientDataError(f"density diagnostics need >= {MIN_STATIONS} stations, got {int(ok.sum())}")
    faa, h, tc, x, y = (a[ok] for a in arrs)
    inp = _Inputs(faa, unit_density_term(h, tc, rho_tc_kg_m3), h, x, y)
    rhos = np.arange(cfg.rho_min_kg_m3, cfg.rho_max_kg_m3 + cfg.rho_step_kg_m3 / 2, cfg.rho_step_kg_m3)

    rho_n, curve = _nettleton_point(inp, rhos, cfg.trend_degree)
    rho_p, intercept = _parasnis_point(inp, cfg.trend_degree)

    rng = np.random.default_rng(cfg.random_state)
    blocks = _blocks(x, y, cfg.bootstrap_block_m)
    boot_n = np.empty(cfg.bootstrap_replicates)
    boot_p = np.empty(cfg.bootstrap_replicates)
    for b in range(cfg.bootstrap_replicates):
        idx = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), size=len(blocks))])
        sub = _Inputs(*(getattr(inp, f)[idx] for f in ("faa", "xterm", "h", "x", "y")))
        boot_n[b], _ = _nettleton_point(sub, rhos, cfg.trend_degree)
        boot_p[b], _ = _parasnis_point(sub, cfg.trend_degree)

    def summary(est: float, boot: F64, bounded: bool) -> dict[str, Any]:
        lo, hi = np.quantile(boot, [0.025, 0.975])
        res: dict[str, Any] = {
            "estimate_kg_m3": est,
            "ci95_kg_m3": [float(lo), float(hi)],
            "ci95_half_width_kg_m3": float((hi - lo) / 2),
            "bootstrap_sd_kg_m3": float(boot.std(ddof=1)),
        }
        if bounded:
            at_edge = (boot <= rhos[0]) | (boot >= rhos[-1])
            res["at_grid_boundary"] = bool(est <= rhos[0] or est >= rhos[-1])
            res["bootstrap_share_at_boundary"] = float(at_edge.mean())
        return res

    nett = summary(rho_n, boot_n, True)
    pars = summary(rho_p, boot_p, False)
    pars["intercept_mgal"] = intercept
    widths = [nett["ci95_half_width_kg_m3"], pars["ci95_half_width_kg_m3"]]
    plausible = (PLAUSIBLE_RHO_KG_M3[0] <= rho_p <= PLAUSIBLE_RHO_KG_M3[1]) and not nett["at_grid_boundary"]
    overlap = max(nett["ci95_kg_m3"][0], pars["ci95_kg_m3"][0]) <= min(nett["ci95_kg_m3"][1], pars["ci95_kg_m3"][1])
    reliable = max(widths) <= 300.0 and plausible and overlap
    return {
        "n_stations": int(ok.sum()),
        "trend_degree": cfg.trend_degree,
        "bootstrap": {
            "block_m": cfg.bootstrap_block_m,
            "replicates": cfg.bootstrap_replicates,
            "n_blocks": len(blocks),
        },
        "relief": {"height_sd_m": float(h.std()), "height_range_m": [float(h.min()), float(h.max())]},
        "nettleton": nett,
        "parasnis": pars,
        "nettleton_curve": {"rho_kg_m3": rhos.tolist(), "corr": curve.tolist()},
        "h5": {
            "statement": (
                "The reduction density cannot be constrained reliably. A reliable estimate needs both CI "
                "half-widths <= 300 kg m^-3, a physically plausible value (Parasnis within 1800-3000, "
                "Nettleton not at the grid boundary) and overlapping CIs of the two methods."
            ),
            "supported": not reliable,
            "ci95_half_widths_kg_m3": widths,
            "plausible": plausible,
            "methods_agree": overlap,
        },
    }


def density_scenarios(cba_by_density: dict[float, F64]) -> dict[str, Any]:
    """Statistics of the CBA differences between density scenarios (pairwise to the largest)."""
    keys = sorted(cba_by_density)
    ref = keys[-1]
    out: dict[str, Any] = {"reference_kg_m3": ref, "differences": {}}
    for k in keys[:-1]:
        d = cba_by_density[ref] - cba_by_density[k]
        d = d[np.isfinite(d)]
        out["differences"][f"{ref:g}-{k:g}"] = {
            "mean_mgal": float(d.mean()),
            "min_mgal": float(d.min()),
            "max_mgal": float(d.max()),
            "sd_mgal": float(d.std()),
        }
    return out
