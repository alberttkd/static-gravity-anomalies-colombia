"""Variography: admissible models only (Gaussian excluded, P5 d), WLS fit, fallbacks."""

from __future__ import annotations

import numpy as np
import pytest

from gravanom.gridding.gridders import RegressionKriging
from gravanom.gridding.variography import (
    VariogramFitError,
    VariogramModel,
    directional_lengths,
    experimental_variogram,
    fit_variogram,
    matern_correlation,
)


@pytest.mark.parametrize("nu", ["gaussian", np.inf, 1.0, 3.5, 100.0])
def test_gaussian_and_other_nu_rejected(nu: object) -> None:
    with pytest.raises(ValueError):
        matern_correlation(np.array([1.0]), 1000.0, nu)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        VariogramModel(nu, 0.0, 1.0, 1000.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RegressionKriging(nu=nu).fit(np.arange(40.0), np.arange(40.0), np.arange(40.0))  # type: ignore[arg-type]


def test_matern_closed_forms() -> None:
    r = np.array([0.0, 1000.0, 5000.0])
    assert np.allclose(matern_correlation(r, 1000.0, 0.5), np.exp(-r / 1000.0))
    for nu in (0.5, 1.5, 2.5):
        c = matern_correlation(r, 1000.0, nu)
        assert c[0] == pytest.approx(1.0) and np.all(np.diff(c) < 0)


def _field(n: int = 600, seed: int = 0, length: float = 8000.0, nugget: float = 0.05) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(0, 60_000, n), rng.uniform(0, 60_000, n)
    d = np.hypot(x[:, None] - x[None], y[:, None] - y[None])
    c = 4.0 * matern_correlation(d, length, 1.5) + np.eye(n) * nugget
    z = np.linalg.cholesky(c) @ rng.standard_normal(n)
    return x, y, z


def test_experimental_variogram_basic() -> None:
    x, y, z = _field()
    ev = experimental_variogram(x, y, z, 1500.0, 30_000.0)
    assert np.all(ev.n_pairs > 0) and np.all(np.diff(ev.lag_m) > 0)
    assert ev.gamma[0] < ev.gamma[-1]


def test_wls_fit_recovers_parameters() -> None:
    x, y, z = _field(800, seed=3)
    m, info = fit_variogram(x, y, z, 1.5, 1500.0, 30_000.0)
    assert info["fallback_step"] in {"configured", "max_lag_20km"}
    assert 4000 < m.length_m < 16000
    assert 1.5 < m.sill < 8


def test_fit_failure_raises() -> None:
    x = np.array([0.0, 1.0, 2.0])
    with pytest.raises(VariogramFitError):
        fit_variogram(x, x, x, 1.5, 1500.0, 30_000.0)


def test_directional_lengths_detect_anisotropy() -> None:
    rng = np.random.default_rng(5)
    n = 700
    x, y = rng.uniform(0, 60_000, n), rng.uniform(0, 60_000, n)
    # Stretch along north: correlation length 3x longer in y.
    d = np.hypot(x[:, None] - x[None], (y[:, None] - y[None]) / 3.0)
    z = np.linalg.cholesky(4 * matern_correlation(d, 5000.0, 1.5) + np.eye(n) * 0.05) @ rng.standard_normal(n)
    m, _ = fit_variogram(x, y, z, 1.5)
    res = directional_lengths(x, y, z, m)
    assert res["ratio"] < 0.7 and res["major_azimuth_deg"] in (0.0, 135.0, 45.0)
    assert res["lengths_m"]["0"] > res["lengths_m"]["90"]
