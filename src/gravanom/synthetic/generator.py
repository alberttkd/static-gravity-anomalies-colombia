"""Deterministic synthetic gravity survey with known truth (MASTER_GUIDE §8.2).

**All values are fictitious.** Every output is labelled SYNTHETIC.

The forward model inverts the standard reduction chain exactly:

.. math::
    g = CBA_{true} + \\gamma_0 - g_H - \\delta g_h - \\delta g_{atm} + BC_{cap}(\\rho_{true}) - TC\\,\\rho_{true}/\\rho_{TC}

so that reducing the noise-free observations with ``rho = rho_true`` returns the true
CBA. Gravity noise N(0, 0.3 mGal) is added, then height noise N(0, 1 m) is added to
the *reported* heights so that height errors propagate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import gstools as gs
import harmonica as hm
import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

from gravanom.crs import to_analysis, to_geographic
from gravanom.reduction import atmospheric, height_correction, honkasalo, normal_gravity_grs80, spherical_cap

SYNTHETIC_LABEL = "SYNTHETIC"
RHO_TC = 2670.0


@dataclass(frozen=True)
class SyntheticSpec:
    """Parameters of the synthetic survey (defaults from §8.2)."""

    seed: int = 20261022
    center_lon: float = -75.0
    center_lat: float = 9.0
    half_width_m: float = 80_000.0
    cell_m: float = 500.0
    n_traverses: int = 20
    stations_per_traverse: int = 100
    spacing_m: tuple[float, float] = (1000.0, 1600.0)
    heading_sd_deg: float = 8.0
    topo_len_scale_m: float = 15_000.0
    height_range_m: tuple[float, float] = (0.0, 300.0)
    rho_true_kg_m3: float = 2670.0
    regional_range_mgal: tuple[float, float] = (-60.0, -10.0)
    prism_contrasts_kg_m3: tuple[float, ...] = (-300.0, -200.0, 150.0, 250.0)
    tc_range_mgal: tuple[float, float] = (0.1, 1.0)
    sigma_g_mgal: float = 0.3
    sigma_h_m: float = 1.0
    n_duplicate_pairs: int = 5
    n_duplicate_pairs_offset: int = 2
    duplicate_offset_mgal: float = 0.5
    n_tc_zeros: int = 3
    tc_zero_min_height_m: float = 50.0
    n_g_out_of_range: int = 1
    topo_correlated_mgal_per_m: float = 0.0
    """Anomaly term proportional to the topography (lowlands over thick, light fill); 0 disables it."""


HIGH_RELIEF = SyntheticSpec(height_range_m=(0.0, 1500.0), rho_true_kg_m3=2400.0, seed=20261023)
#: Low relief whose true anomaly is correlated with the topography: density estimators must fail here.
LOW_RELIEF_CORRELATED = SyntheticSpec(topo_correlated_mgal_per_m=0.08, seed=20261024)


@dataclass
class SyntheticSurvey:
    """Output of :func:`make_synthetic_survey`."""

    stations: pd.DataFrame
    """Columns: id, lon, lat, height_m, g_obs_mgal, tc_mgal, cba_true_mgal, height_true_m."""
    grid_x: np.ndarray
    grid_y: np.ndarray
    truth_cba: np.ndarray
    """True CBA on the grid (rows = ascending y) at the topographic surface [mGal]."""
    topography: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


def _scale(a: np.ndarray, lo: float, hi: float) -> tuple[float, float]:
    """Affine coefficients mapping min(a)..max(a) onto lo..hi."""
    s = (hi - lo) / float(a.max() - a.min())
    return s, lo - s * float(a.min())


def _traverses(
    spec: SyntheticSpec, rng: np.random.Generator, x0: float, y0: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs, ys, line = [], [], []
    lim = spec.half_width_m - 2000.0
    for t in range(spec.n_traverses):
        x, y = rng.uniform(-lim, lim, size=2)
        heading = rng.uniform(0, 2 * np.pi)
        for _ in range(spec.stations_per_traverse):
            xs.append(x0 + x)
            ys.append(y0 + y)
            line.append(t)
            step = rng.uniform(*spec.spacing_m)
            heading += np.radians(rng.normal(0.0, spec.heading_sd_deg))
            nx, ny = x + step * np.cos(heading), y + step * np.sin(heading)
            if abs(nx) > lim or abs(ny) > lim:  # turn back towards the centre
                heading = np.arctan2(-y, -x) + np.radians(rng.normal(0.0, 20.0))
                nx, ny = x + step * np.cos(heading), y + step * np.sin(heading)
            x, y = nx, ny
    return np.array(xs), np.array(ys), np.array(line)


def make_synthetic_survey(
    spec: SyntheticSpec | None = None,
    variant: Literal["default", "high_relief", "low_relief_correlated"] = "default",
) -> SyntheticSurvey:
    """Generate the synthetic survey. Deterministic for a given ``spec``.

    Parameters
    ----------
    spec : SyntheticSpec, optional
        Survey parameters; defaults to ``SyntheticSpec()``, :data:`HIGH_RELIEF` or
        :data:`LOW_RELIEF_CORRELATED`.
    variant : {"default", "high_relief", "low_relief_correlated"}
        Selects the default specification when ``spec`` is None.
    """
    presets = {"high_relief": HIGH_RELIEF, "low_relief_correlated": LOW_RELIEF_CORRELATED}
    spec = spec or presets.get(variant, SyntheticSpec())
    rng = np.random.default_rng(spec.seed)
    cx, cy = to_analysis(spec.center_lon, spec.center_lat)
    x0, y0 = float(np.round(cx / spec.cell_m) * spec.cell_m), float(np.round(cy / spec.cell_m) * spec.cell_m)
    gx = x0 + np.arange(-spec.half_width_m, spec.half_width_m + spec.cell_m / 2, spec.cell_m)
    gy = y0 + np.arange(-spec.half_width_m, spec.half_width_m + spec.cell_m / 2, spec.cell_m)

    # Topography and terrain-correction fields (Matérn nu = 1.5 random fields).
    topo_model = gs.Matern(dim=2, var=1.0, len_scale=spec.topo_len_scale_m, nu=1.5)
    topo_raw = gs.SRF(topo_model, seed=spec.seed + 1).structured([gx, gy]).T
    s, c = _scale(topo_raw, *spec.height_range_m)
    topo = s * topo_raw + c
    tc_model = gs.Matern(dim=2, var=1.0, len_scale=2 * spec.topo_len_scale_m, nu=2.5)
    tc_raw = gs.SRF(tc_model, seed=spec.seed + 2).structured([gx, gy]).T
    s, c = _scale(tc_raw, *spec.tc_range_mgal)
    tc_grid = s * tc_raw + c

    # Station traverses.
    sx, sy, line = _traverses(spec, rng, x0, y0)
    interp_topo = RegularGridInterpolator((gy, gx), topo)
    interp_tc = RegularGridInterpolator((gy, gx), tc_grid)
    h_true = interp_topo(np.column_stack([sy, sx]))
    tc = interp_tc(np.column_stack([sy, sx]))

    # True CBA: quadratic regional + four buried prisms.
    u = (np.meshgrid(gx, gy)[0] - x0) / spec.half_width_m
    v = (np.meshgrid(gx, gy)[1] - y0) / spec.half_width_m
    coef = rng.normal(0.0, 1.0, size=5)

    def quad(uu: np.ndarray, vv: np.ndarray) -> np.ndarray:
        return np.asarray(coef[0] * uu + coef[1] * vv + coef[2] * uu**2 + coef[3] * uu * vv + coef[4] * vv**2)

    rs, rc = _scale(quad(u, v), *spec.regional_range_mgal)
    prisms, prism_meta = [], []
    for contrast in spec.prism_contrasts_kg_m3:
        pcx, pcy = rng.uniform(-0.6, 0.6, size=2) * spec.half_width_m
        wx, wy = rng.uniform(10_000.0, 30_000.0, size=2)
        top = rng.uniform(2000.0, 8000.0)
        thick = rng.uniform(3000.0, 8000.0)
        prisms.append([x0 + pcx - wx / 2, x0 + pcx + wx / 2, y0 + pcy - wy / 2, y0 + pcy + wy / 2, -top - thick, -top])
        prism_meta.append(
            {
                "contrast_kg_m3": contrast,
                "top_depth_m": top,
                "thickness_m": thick,
                "width_x_m": wx,
                "width_y_m": wy,
            }
        )
    prisms_arr = np.array(prisms)
    dens = np.array(spec.prism_contrasts_kg_m3)
    topo_mean = float(topo.mean())

    def truth(xx: np.ndarray, yy: np.ndarray, hh: np.ndarray) -> np.ndarray:
        uu, vv = (xx - x0) / spec.half_width_m, (yy - y0) / spec.half_width_m
        reg = rs * quad(uu, vv) + rc
        gz = hm.prism_gravity((xx, yy, hh), prisms_arr, dens, field="g_z", parallel=False)
        topo_term = spec.topo_correlated_mgal_per_m * (hh - topo_mean) if spec.topo_correlated_mgal_per_m else 0.0
        return np.asarray(reg + gz + topo_term)

    gxx, gyy = np.meshgrid(gx, gy)
    truth_grid = truth(gxx.ravel(), gyy.ravel(), topo.ravel()).reshape(topo.shape)
    cba_true = truth(sx, sy, h_true)

    # Forward reduction to "observed" gravity.
    lon, lat = to_geographic(sx, sy)
    rho = spec.rho_true_kg_m3
    g = (
        cba_true
        + normal_gravity_grs80(lat)
        - honkasalo(lat)
        - height_correction(lat, h_true)
        - atmospheric(h_true)
        + spherical_cap(h_true, rho)
        - tc * rho / RHO_TC
    )
    g = g + rng.normal(0.0, spec.sigma_g_mgal, size=g.size)
    h_obs = h_true + rng.normal(0.0, spec.sigma_h_m, size=g.size)

    ids = [f"S{i:05d}" for i in range(g.size)]
    df = pd.DataFrame(
        {
            "id": ids,
            "lon": lon,
            "lat": lat,
            "height_m": h_obs,
            "g_obs_mgal": g,
            "tc_mgal": tc,
            "cba_true_mgal": cba_true,
            "height_true_m": h_true,
            "traverse": line,
        }
    )

    # Injected defects.
    expected: dict[str, list[str]] = {"DUPLICATE_POSITION": [], "TC_SUSPECT": [], "ERROR_RANGE": []}
    pick = rng.choice(g.size, size=spec.n_duplicate_pairs + spec.n_tc_zeros + spec.n_g_out_of_range, replace=False)
    dup_idx = pick[: spec.n_duplicate_pairs]
    rest = [i for i in rng.permutation(g.size) if i not in set(pick) and h_obs[i] > spec.tc_zero_min_height_m]
    tc0_idx = np.array(rest[: spec.n_tc_zeros])
    bad_idx = pick[spec.n_duplicate_pairs : spec.n_duplicate_pairs + spec.n_g_out_of_range]
    dups = df.iloc[dup_idx].copy()
    dups["id"] = [f"D{i:05d}" for i in range(len(dups))]
    offsets = np.zeros(len(dups))
    offsets[: spec.n_duplicate_pairs_offset] = spec.duplicate_offset_mgal
    dups["g_obs_mgal"] = dups["g_obs_mgal"].to_numpy() + offsets
    for orig, new in zip(df.iloc[dup_idx]["id"], dups["id"], strict=True):
        expected["DUPLICATE_POSITION"].append(f"merged:SYN:{orig}+SYN:{new}")
    df.loc[tc0_idx, "tc_mgal"] = 0.0
    expected["TC_SUSPECT"] = [f"SYN:{ids[i]}" for i in tc0_idx]
    df.loc[bad_idx, "g_obs_mgal"] = 990_000.0
    expected["ERROR_RANGE"] = [f"SYN:{ids[i]}" for i in bad_idx]
    df = pd.concat([df, dups], ignore_index=True)
    expected["H_NONPOSITIVE"] = [f"SYN:{i}" for i in df.loc[df["height_m"] <= 0, "id"] if not i.startswith("D")]

    metadata: dict[str, Any] = {
        "label": SYNTHETIC_LABEL,
        "description": "Fictitious gravity survey generated by gravanom.synthetic (MASTER_GUIDE §8.2). Not real data.",
        "licence": "CC BY 4.0",
        "variant": variant,
        "spec": {k: (list(v) if isinstance(v, tuple) else v) for k, v in spec.__dict__.items()},
        "crs_analysis": "EPSG:9377",
        "grid_origin_m": [float(gx[0]), float(gy[0])],
        "n_stations": len(df),
        "regional_coefficients": coef.tolist(),
        "prisms": prism_meta,
        "expected_flags": expected,
    }
    return SyntheticSurvey(df, gx, gy, truth_grid, topo, metadata)
