"""Gridders, masks, CV harness and selection rule."""

from __future__ import annotations

import numpy as np
import pytest

from gravanom.config import GriddingConfig
from gravanom.gridding import (
    EqSGridder,
    IDWGridder,
    Points,
    RegressionKriging,
    SplineGridder,
    block_folds,
    confidence_mask,
    cross_validate,
    fit_final_model,
    grid_axes,
    make_grid,
    mask_statistics,
    select_method,
    support_mask,
)
from gravanom.gridding.cv import calibration_stats, metrics
from gravanom.gridding.products import GridTooLargeError, TooFewPointsError


def _pts(n: int = 400, seed: int = 0) -> Points:
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(0, 80_000, n), rng.uniform(0, 80_000, n)
    z = -30 + 1e-4 * x - 2e-4 * y + 5 * np.sin(x / 9000) * np.cos(y / 11000) + rng.normal(0, 0.2, n)
    return Points(x, y, z, rng.uniform(0, 200, n))


def test_masks() -> None:
    sx, sy = np.array([0.0, 10_000, 0, 10_000]), np.array([0.0, 0, 10_000, 10_000])
    px, py = np.array([5000.0, 30_000, 1000]), np.array([5000.0, 30_000, 9000])
    assert support_mask(px, py, sx, sy, 8000).tolist() == [True, False, True]
    assert support_mask(np.array([-500.0]), np.array([5000.0]), sx, sy, 8000).tolist() == [False]
    assert support_mask(np.array([-500.0]), np.array([5000.0]), sx, sy, 8000, use_convex_hull=False).tolist() == [True]
    assert confidence_mask(np.array([1.0, 6.0, np.nan]), 5.0).tolist() == [True, False, False]


def test_block_folds_partition() -> None:
    p = _pts()
    folds = block_folds(p.x, p.y, 15_000, 5, 1)
    test_idx = np.sort(np.concatenate([te for _, te in folds]))
    assert np.array_equal(test_idx, np.arange(len(p)))
    for tr, te in folds:
        assert not set(tr) & set(te)


@pytest.mark.parametrize("gridder", [IDWGridder(), SplineGridder(), EqSGridder(10_000, 1.0), RegressionKriging(1, 1.5)])
def test_gridders_reproduce_smooth_field(gridder) -> None:  # type: ignore[no-untyped-def]
    p = _pts()
    g = gridder.fit(p.x, p.y, p.z, p.h)
    pred, sig = g.predict(p.x[:50] + 10, p.y[:50] + 10, p.h[:50])
    assert np.sqrt(np.mean((pred - p.z[:50]) ** 2)) < 2.5
    assert g.params()["method"] == g.name


def test_kriging_variance_behaviour() -> None:
    p = _pts()
    rk = RegressionKriging(1, 1.5).fit(p.x, p.y, p.z)
    _, s_near = rk.predict(p.x[:5], p.y[:5], include_nugget=False)
    _, s_far = rk.predict(np.array([300_000.0]), np.array([300_000.0]), include_nugget=False)
    assert np.all(s_near < s_far)
    assert s_far[0] == pytest.approx(np.sqrt(rk.variogram.psill), rel=1e-6)
    _, s_obs = rk.predict(p.x[:5], p.y[:5], include_nugget=True)
    assert np.all(s_obs >= s_near)
    m, s = rk.predict(p.x[:5], p.y[:5], return_std=False)
    assert np.all(np.isnan(s)) and np.all(np.isfinite(m))


def test_anisotropic_rk_runs() -> None:
    p = _pts()
    rk = RegressionKriging(1, 1.5, anisotropy=(45.0, 0.5)).fit(p.x, p.y, p.z)
    assert rk.params()["anisotropy"] == [45.0, 0.5]


def test_cross_validate_and_metrics() -> None:
    p = _pts()
    res = cross_validate(lambda: RegressionKriging(1, 1.5), p, block_folds(p.x, p.y, 15_000, 5, 1))
    assert res["rmse"] < 3 and "z" in res and len(res["per_fold"]) == 5
    m = metrics(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
    assert m["rmse"] == 0 and m["r2"] == 1
    c = calibration_stats(np.random.default_rng(0).standard_normal(5000))
    assert abs(c["sd_z"] - 1) < 0.05 and abs(c["coverage95"] - 0.95) < 0.01


def test_selection_rule() -> None:
    base = {"idw": {"outer": {"rmse": 6.0}}, "rk_matern": {"outer": {"rmse": 4.0}, "calibrated": {}}}
    assert select_method({**base, "eqs": {"outer": {"rmse": 3.0}}})["selected"] == "rk_matern"  # no EqS uncertainty
    assert select_method({**base, "eqs": {"outer": {"rmse": 3.0}, "calibrated": {}}})["selected"] == "eqs"
    assert select_method({**base, "eqs": {"outer": {"rmse": 3.9}, "calibrated": {}}})["selected"] == "rk_matern"
    assert select_method(base)["ratio_to_idw"] == pytest.approx(4 / 6)


def test_final_grid_product() -> None:
    p = _pts()
    cfg = GriddingConfig(trend_degree=1, matern_nu=1.5, cell_size_m=2000)
    fm = fit_final_model("rk_matern", p, cfg)
    ds = make_grid(fm, p, cfg)
    sup = ds.support_mask.values == 1
    assert np.isfinite(ds.value.values[sup]).all() and np.isnan(ds.value.values[~sup]).all()
    assert np.allclose(ds.sigma_cal.values[sup], fm.calibration_c * ds.sigma_raw.values[sup])
    assert ds.attrs["crs"] == "EPSG:9377"
    assert np.allclose(ds.x.values % 2000, 0)
    st = mask_statistics(ds)
    assert 0 < st["supported_share"] <= 1


def test_grid_guards() -> None:
    p = _pts(20)
    with pytest.raises(TooFewPointsError):
        fit_final_model("idw", p, GriddingConfig())
    big = _pts()
    gx, gy = grid_axes(np.array([0.0, 3e6]), np.array([0.0, 3e6]), 1000.0)
    fm = fit_final_model("idw", big, GriddingConfig())
    with pytest.raises(GridTooLargeError):
        make_grid(fm, big, GriddingConfig(), axes=(gx, gy))
