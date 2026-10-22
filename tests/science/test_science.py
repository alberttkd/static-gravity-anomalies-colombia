"""Scientific validation on synthetic data (§5.10): density recovery, CV skill/calibration, truth recovery."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gravanom.config import DensityConfig, GriddingConfig
from gravanom.density import density_diagnostics
from gravanom.flags import ERROR_FLAGS, QCFlag
from gravanom.gridding import Points, fit_final_model, make_grid, nested_cv, select_method
from gravanom.harmonize import harmonize
from gravanom.io.schema import coerce_records
from gravanom.qc import exclusion_mask, run_qc
from gravanom.reduction import compute_anomalies
from gravanom.synthetic import make_synthetic_survey

pytestmark = pytest.mark.science


def _records(df: pd.DataFrame) -> pd.DataFrame:
    return coerce_records(
        pd.DataFrame(
            {
                "source": "SYN",
                "source_id": df["id"],
                "lon": df["lon"],
                "lat": df["lat"],
                "height_m": df["height_m"],
                "g_obs_mgal": df["g_obs_mgal"],
                "tc_mgal": df["tc_mgal"],
                "bb_supplied_mgal": np.nan,
                "prov_file": "mem",
                "prov_sheet": "",
                "prov_row": np.arange(len(df)),
            }
        )
    )


def _usable(survey) -> tuple[pd.DataFrame, pd.DataFrame]:  # type: ignore[no-untyped-def]
    cat, log = harmonize([_records(survey.stations)])
    cat, _ = run_qc(cat, log)
    cat = cat[~exclusion_mask(cat, [*ERROR_FLAGS, QCFlag.TC_SUSPECT])].reset_index(drop=True)
    return cat, compute_anomalies(cat)


def test_density_recovery_high_relief() -> None:
    cat, an = _usable(make_synthetic_survey(variant="high_relief"))
    d = density_diagnostics(
        an.faa_mgal,
        cat.height_m,
        cat.tc_mgal,
        cat.x_9377,
        cat.y_9377,
        DensityConfig(bootstrap_replicates=300),
    )
    for k in ("nettleton", "parasnis"):
        assert abs(d[k]["estimate_kg_m3"] - 2400) <= 60, k
        lo, hi = d[k]["ci95_kg_m3"]
        assert lo <= 2400 <= hi, k


@pytest.fixture(scope="module")
def synthetic_cv() -> dict:
    survey = make_synthetic_survey()
    cat, an = _usable(survey)
    pts = Points(cat.x_9377.to_numpy(), cat.y_9377.to_numpy(), an.cba_mgal.to_numpy(), cat.height_m.to_numpy())
    cfg = GriddingConfig()
    reps = {m: nested_cv(m, pts, cfg) for m in ("idw", "rk_matern")}
    return {"survey": survey, "pts": pts, "cfg": cfg, "reports": reps}


def test_skill_vs_idw(synthetic_cv: dict) -> None:
    sel = select_method(synthetic_cv["reports"])
    assert sel["selected"] == "rk_matern" and sel["ratio_to_idw"] <= 0.70


def test_calibration_outer_folds(synthetic_cv: dict) -> None:
    cal = synthetic_cv["reports"]["rk_matern"]["calibrated"]
    assert 0.85 <= cal["sd_z"] <= 1.15
    assert 0.92 <= cal["coverage95"] <= 0.98


def test_truth_recovery(synthetic_cv: dict) -> None:
    s, pts, cfg = synthetic_cv["survey"], synthetic_cv["pts"], synthetic_cv["cfg"]
    fm = fit_final_model("rk_matern", pts, cfg)
    ds = make_grid(fm, pts, cfg, axes=(s.grid_x, s.grid_y))
    sup = ds.support_mask.values == 1
    err = ds.value.values[sup] - s.truth_cba[sup]
    rmse = float(np.sqrt(np.mean(err**2)))
    assert rmse <= 1.25 * synthetic_cv["reports"]["rk_matern"]["outer"]["rmse"]
    cov = float(np.mean(np.abs(err) < 1.96 * ds.sigma_cal.values[sup]))
    assert 0.90 <= cov <= 0.98
