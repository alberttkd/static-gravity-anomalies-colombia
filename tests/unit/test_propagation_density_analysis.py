"""Uncertainty propagation, density diagnostics, trend, profiles, contours, comparisons, render."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from gravanom.analysis import (
    compare_grids,
    compare_station_runs,
    contours,
    decompose,
    profile,
    term_decomposition,
)
from gravanom.analysis.profiles import ProfileOutsideSupportError
from gravanom.config import DensityConfig, ReductionConfig, UncertaintyConfig
from gravanom.crs import to_analysis
from gravanom.density import InsufficientDataError, density_diagnostics, density_scenarios
from gravanom.reduction import compute_anomalies
from gravanom.render import colorize, render_layer, robust_symmetric_limits
from gravanom.uncertainty import monte_carlo, propagate, sensitivities, uncertainty_report
from tests.conftest import make_stations


def test_sensitivities_match_guide() -> None:
    s = make_stations(20)
    sens = sensitivities(s)
    assert np.allclose(sens["g"]["cba_mgal"], 1.0)
    assert np.all(np.abs(sens["h"]["cba_mgal"] - 0.195) < 0.003)  # §5.5.3, rho = 2670
    s23 = sensitivities(s, ReductionConfig(density_kg_m3=2300))
    assert np.all(np.abs(s23["h"]["cba_mgal"] - 0.212) < 0.003)
    assert np.all(np.abs(sens["north"]["faa_mgal"] * 1000 + 0.27) < 0.03)  # ~0.27 mGal/km at ~9 N


def test_mc_matches_linear_and_config_overrides() -> None:
    s = make_stations(30)
    u = UncertaintyConfig(sigma_g_mgal=0.3, sigma_h_m=3.0, sigma_tc_rel=0.2, sigma_pos_m=100, mc_draws=500)
    lin, mc = propagate(s, uncertainty=u), monte_carlo(s, uncertainty=u)
    rep = uncertainty_report(lin, mc, u)
    assert all(v["pass_lt_5pct"] for v in rep["per_anomaly"].values())
    assert np.all(lin["sigma_cba_mgal"] > propagate(s)["sigma_cba_mgal"])


def _density_case(rho_true: float, n: int = 600) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(2)
    x, y = rng.uniform(0, 150_000, n), rng.uniform(0, 150_000, n)
    h = 750 + 700 * np.sin(x / 13_000) * np.cos(y / 17_000)
    tc = rng.uniform(0.2, 1.0, n)
    from gravanom.density import unit_density_term

    faa = rho_true * unit_density_term(h, tc) + 1e-4 * x + rng.normal(0, 1.0, n)
    return faa, h, tc, x, y


def test_density_recovers_truth() -> None:
    d = density_diagnostics(*_density_case(2400.0), config=DensityConfig(bootstrap_replicates=100))
    for k in ("nettleton", "parasnis"):
        assert abs(d[k]["estimate_kg_m3"] - 2400) < 30
        lo, hi = d[k]["ci95_kg_m3"]
        assert lo <= 2400 <= hi
    assert d["h5"]["supported"] is False


def test_density_insufficient() -> None:
    faa, h, tc, x, y = _density_case(2400.0, 50)
    with pytest.raises(InsufficientDataError):
        density_diagnostics(faa, h, tc, x, y)


def test_density_scenarios() -> None:
    out = density_scenarios({2300.0: np.array([1.0, 2.0]), 2670.0: np.array([0.0, 0.0])})
    assert out["differences"]["2670-2300"]["mean_mgal"] == pytest.approx(-1.5)


def test_decompose() -> None:
    rng = np.random.default_rng(0)
    x, y = rng.uniform(0, 1e5, 300), rng.uniform(0, 1e5, 300)
    z = 3 + 2e-4 * x + rng.normal(0, 0.1, 300)
    d = decompose(x, y, z, 1)
    assert d["variance_explained"] > 0.99 and abs(d["residual"].mean()) < 1e-9


def _grid() -> xr.Dataset:
    x0, y0 = to_analysis(-75.0, 9.0)
    gx = np.round(x0 / 500) * 500 + np.arange(-40, 41) * 500.0
    gy = np.round(y0 / 500) * 500 + np.arange(-40, 41) * 500.0
    xx, yy = np.meshgrid(gx, gy)
    val = (xx - gx.mean()) / 1000.0
    sup = (np.abs(xx - gx.mean()) < 15_000).astype(np.uint8)
    return xr.Dataset(
        {
            "value": (("y", "x"), np.where(sup, val, np.nan), {"units": "mGal"}),
            "sigma_cal": (("y", "x"), np.where(sup, 1.0, np.nan), {"units": "mGal"}),
            "support_mask": (("y", "x"), sup),
            "confidence_mask": (("y", "x"), sup),
        },
        coords={"x": gx, "y": gy},
        attrs={"cell_size_m": 500.0},
    )


def test_profile_and_contours() -> None:
    ds = _grid()
    pr = profile(ds, [(-75.1, 9.0), (-74.9, 9.0)], buffer_m=2000)
    v = np.array(pr["value"], dtype=float)
    assert np.nanmax(v) - np.nanmin(v) > 20 and all(pr["supported"])
    pr2 = profile(ds, [(-75.19, 9.0), (-74.81, 9.0)])
    assert any(pr2["supported"]) and not all(pr2["supported"])
    with pytest.raises(ProfileOutsideSupportError):
        profile(ds, [(-75.19, 8.82), (-75.18, 8.83)])
    with pytest.raises(ValueError):
        profile(ds, [(-75.0, 9.0)])
    fc = contours(ds, 5.0)
    levels = {f["properties"]["level"] for f in fc["features"]}
    assert {-10.0, 0.0, 10.0} <= levels
    lon, lat = fc["features"][0]["geometry"]["coordinates"][0]
    assert -76 < lon < -74 and 8 < lat < 10


def test_profile_stations() -> None:
    ds = _grid()
    x, y = to_analysis(np.array([-75.0, -75.0]), np.array([9.005, 9.2]))
    st = pd.DataFrame(
        {
            "station_uid": ["a", "b"],
            "x_9377": x,
            "y_9377": y,
            "height_m": [10.0, 20.0],
            "cba_mgal": [1.0, 2.0],
        }
    )
    pr = profile(ds, [(-75.1, 9.0), (-74.9, 9.0)], stations=st, value_column="cba_mgal")
    assert [s["station_uid"] for s in pr["stations"]] == ["a"]


def test_compare_functions() -> None:
    s = make_stations(10)
    a = compute_anomalies(s).assign(station_uid=s.station_uid)
    b = compute_anomalies(s, ReductionConfig(density_kg_m3=2300)).assign(station_uid=s.station_uid)
    d = compare_station_runs(a, b)
    assert d["cba_mgal"]["mean_mgal"] < 0 and d["faa_mgal"]["rms_mgal"] == 0
    with pytest.raises(ValueError):
        compare_station_runs(a, b.iloc[:5])
    ds = _grid()
    assert compare_grids(ds, ds)["rms_mgal"] == 0
    s["bb_supplied_mgal"] = -0.1
    td = term_decomposition(compute_anomalies(s), compute_anomalies(s, ReductionConfig(legacy_mode=True)))
    assert td["closure_max_abs_mgal"] < 1e-9 and td["ranking_by_rms"][0] == "bouguer_slab_density"


def test_render() -> None:
    lo, hi = robust_symmetric_limits(np.array([-3.0, 1.0, 2.0, np.nan]))
    assert lo == -hi
    rgba = colorize(np.array([[np.nan, 0.0]]), "RdBu_r", -1, 1)
    assert rgba[0, 0, 3] == 0 and rgba[0, 1, 3] == 255
    with pytest.raises(ValueError):
        colorize(np.zeros((1, 1)), "jet", 0, 1)
    png, meta = render_layer(_grid(), "value")
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and meta["vmin"] == -meta["vmax"]
    w, s, e, n = meta["bounds"]
    assert w < e and s < n
    png2, _ = render_layer(_grid(), "lowconf_hatch")
    assert png2[:4] == b"\x89PNG"
