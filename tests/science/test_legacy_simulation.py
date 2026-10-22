"""Recovery of injected legacy-spreadsheet defects and density-estimator failure on synthetic data."""

from __future__ import annotations

import numpy as np
import pytest

from gravanom.analysis.compare import term_decomposition
from gravanom.config import DensityConfig, ReductionConfig
from gravanom.density import density_diagnostics
from gravanom.reduction import compute_anomalies, curvature_bb
from gravanom.synthetic import LEGACY_DEFECTS, make_synthetic_survey, simulate_legacy_subsets

from .test_science import _usable

pytestmark = pytest.mark.science


@pytest.fixture(scope="module")
def legacy() -> dict:
    return simulate_legacy_subsets(make_synthetic_survey())


def test_legacy_mode_reproduces_simulated_spreadsheets(legacy: dict) -> None:
    for df in legacy.values():
        leg = compute_anomalies(df, ReductionConfig(legacy_mode=True))
        np.testing.assert_allclose(leg["cba_mgal"], df["abt"], atol=1e-9)


def test_supplied_curvature_defect_is_detected(legacy: dict) -> None:
    ratios = {}
    for lab, df in legacy.items():
        h = df["height_m"].to_numpy()
        pos = h > 1.0
        ratios[lab] = float(np.median(df["bb_supplied_mgal"].to_numpy()[pos] / curvature_bb(h[pos], 2670.0)))
    assert ratios["A"] == pytest.approx(-1.0, abs=0.01)
    assert ratios["B"] == pytest.approx(LEGACY_DEFECTS["bb_scale_b"], abs=0.01)


def test_term_decomposition_attributes_the_defects(legacy: dict) -> None:
    for lab, df in legacy.items():
        td = term_decomposition(compute_anomalies(df), compute_anomalies(df, ReductionConfig(legacy_mode=True)))
        assert td["closure_max_abs_mgal"] < 1e-8
        assert td["ranking_by_rms"][0] == "bouguer_slab_density"
        curv = td["curvature_bb"]["rms_mgal"]
        assert (curv < 0.01) if lab == "A" else (curv > 0.1)


def test_density_estimators_fail_when_anomaly_follows_topography() -> None:
    cat, an = _usable(make_synthetic_survey(variant="low_relief_correlated"))
    d = density_diagnostics(
        an.faa_mgal, cat.height_m, cat.tc_mgal, cat.x_9377, cat.y_9377, DensityConfig(bootstrap_replicates=200)
    )
    lo, hi = d["parasnis"]["ci95_kg_m3"]
    assert not (lo <= 2670 <= hi) or not d["h5"]["reliable"]
