"""Station-level uncertainty: first-order propagation and Monte Carlo (MASTER_GUIDE §5.5.3).

Independent error sources: observed gravity (sigma_g), height (sigma_H), terrain
correction (relative sigma_TC) and north position (sigma_pos, through gamma_0).
The density is a *scenario* (model choice), not a random error, and is excluded.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from gravanom.config import ReductionConfig, UncertaintyConfig
from gravanom.reduction.anomalies import compute_anomalies

ANOMALIES = ("faa_mgal", "sba_mgal", "cba_mgal")
#: Station columns the reduction needs.
NUMERIC_INPUTS = ("lat", "height_m", "g_obs_mgal", "tc_mgal", "bb_supplied_mgal")
#: Metres per degree of latitude (local approximation, sufficient for derivatives).
M_PER_DEG_LAT = 110_574.0


def _perturbed(stations: pd.DataFrame, dg: Any = 0.0, dh: Any = 0.0, dtc_rel: Any = 0.0, dn_m: Any = 0.0) -> pd.DataFrame:
    s = stations.copy()
    s["g_obs_mgal"] = s["g_obs_mgal"].to_numpy(dtype=float) + dg
    s["height_m"] = s["height_m"].to_numpy(dtype=float) + dh
    s["tc_mgal"] = s["tc_mgal"].to_numpy(dtype=float, na_value=np.nan) * (1.0 + dtc_rel)
    s["lat"] = s["lat"].to_numpy(dtype=float) + np.asarray(dn_m) / M_PER_DEG_LAT
    return s


def sensitivities(stations: pd.DataFrame, reduction: ReductionConfig | None = None) -> dict[str, pd.DataFrame]:
    """Partial derivatives of FAA/SBA/CBA by central differences.

    Returns a dict keyed by error source (``g`` [mGal/mGal], ``h`` [mGal/m],
    ``tc_rel`` [mGal per unit relative TC change], ``north`` [mGal/m]) of
    DataFrames with the anomaly columns.
    """
    cfg = reduction or ReductionConfig()
    steps = {"g": ("dg", 0.01), "h": ("dh", 0.1), "tc_rel": ("dtc_rel", 0.01), "north": ("dn_m", 10.0)}
    out: dict[str, pd.DataFrame] = {}
    for name, (kw, step) in steps.items():
        up = compute_anomalies(_perturbed(stations, **{kw: step}), cfg)
        dn = compute_anomalies(_perturbed(stations, **{kw: -step}), cfg)
        out[name] = (up[list(ANOMALIES)] - dn[list(ANOMALIES)]) / (2 * step)
    return out


def propagate(
    stations: pd.DataFrame,
    reduction: ReductionConfig | None = None,
    uncertainty: UncertaintyConfig | None = None,
) -> pd.DataFrame:
    """First-order σ of FAA, SBA and CBA per station [mGal].

    .. math:: \\sigma^2 = \\sum_k (\\partial A/\\partial x_k)^2\\,\\sigma_k^2

    Returns columns ``sigma_faa_mgal``, ``sigma_sba_mgal``, ``sigma_cba_mgal``.
    """
    u = uncertainty or UncertaintyConfig()
    sens = sensitivities(stations, reduction)
    sig = {"g": u.sigma_g_mgal, "h": u.sigma_h_m, "tc_rel": u.sigma_tc_rel, "north": u.sigma_pos_m}
    var = sum((sens[k].fillna(0.0) ** 2) * sig[k] ** 2 for k in sig)
    assert isinstance(var, pd.DataFrame)
    res = var.pow(0.5)
    res.loc[stations["tc_mgal"].isna().to_numpy(), "cba_mgal"] = np.nan
    return res.rename(columns={a: f"sigma_{a}" for a in ANOMALIES})


def _whitened_normals(rng: np.random.Generator, n_draws: int, k: int) -> np.ndarray:
    """Standard-normal draws with *exact* zero mean and identity sample covariance.

    Moment matching (a variance-reduction technique): the sample means and
    covariance of the ``k`` input error vectors are corrected exactly, so that the
    Monte Carlo spread differs from the linear σ only through non-linearity.
    """
    z = rng.standard_normal((n_draws, k))
    z -= z.mean(axis=0)
    cov = np.cov(z, rowvar=False, ddof=1)
    chol = np.linalg.cholesky(np.atleast_2d(cov))
    return np.asarray(np.linalg.solve(chol, z.T).T)


def monte_carlo(
    stations: pd.DataFrame,
    reduction: ReductionConfig | None = None,
    uncertainty: UncertaintyConfig | None = None,
) -> pd.DataFrame:
    """Monte Carlo σ of FAA/SBA/CBA (fixed seed, common random numbers across stations).

    Each draw perturbs g, H, TC and the north position of *all* stations and re-runs
    the full (non-linear) reduction. Returns the same columns as :func:`propagate`.
    """
    cfg = reduction or ReductionConfig()
    u = uncertainty or UncertaintyConfig()
    rng = np.random.default_rng(u.random_state)
    z = _whitened_normals(rng, u.mc_draws, 4)
    n = len(stations)
    cols = [c for c in NUMERIC_INPUTS if c in stations.columns]
    small = stations[cols].reset_index(drop=True)
    ref = compute_anomalies(small, cfg)
    total = {a: np.zeros(n) for a in ANOMALIES}
    total_sq = {a: np.zeros(n) for a in ANOMALIES}
    chunk = max(1, 500_000 // max(n, 1))
    for start in range(0, u.mc_draws, chunk):
        zc = z[start : start + chunk]
        m = len(zc)
        base = pd.concat([small] * m, ignore_index=True)

        def rep(col: int, zc: np.ndarray = zc) -> np.ndarray:
            return np.repeat(zc[:, col], n)

        pert = _perturbed(
            base,
            dg=rep(0) * u.sigma_g_mgal,
            dh=rep(1) * u.sigma_h_m,
            dtc_rel=rep(2) * u.sigma_tc_rel,
            dn_m=rep(3) * u.sigma_pos_m,
        )
        an = compute_anomalies(pert, cfg)
        for a in ANOMALIES:
            # Centre on the noise-free value to avoid cancellation in the sum of squares.
            vals = an[a].to_numpy().reshape(m, n) - ref[a].to_numpy()
            total[a] += vals.sum(axis=0)
            total_sq[a] += (vals**2).sum(axis=0)
    out = {}
    nd = u.mc_draws
    for a in ANOMALIES:
        mean = total[a] / nd
        var = (total_sq[a] - nd * mean**2) / (nd - 1)
        out[f"sigma_{a}"] = np.sqrt(np.maximum(var, 0.0))
    return pd.DataFrame(out, index=stations.index)


def uncertainty_report(linear: pd.DataFrame, mc: pd.DataFrame, uncertainty: UncertaintyConfig) -> dict[str, Any]:
    """Summary statistics and the Monte Carlo vs linear agreement (criterion: < 5 %)."""
    rep: dict[str, Any] = {"config": uncertainty.model_dump(mode="json"), "per_anomaly": {}}
    for col in linear.columns:
        lin, m = linear[col].to_numpy(), mc[col].to_numpy()
        ok = np.isfinite(lin) & np.isfinite(m) & (lin > 0)
        rel = np.abs(m[ok] - lin[ok]) / lin[ok]
        rep["per_anomaly"][col] = {
            "linear_median_mgal": float(np.median(lin[ok])),
            "linear_max_mgal": float(np.max(lin[ok])),
            "mc_median_mgal": float(np.median(m[ok])),
            "max_rel_diff": float(rel.max()),
            "pass_lt_5pct": bool(rel.max() < 0.05),
        }
    return rep
