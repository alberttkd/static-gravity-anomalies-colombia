"""Configuration models (P1 f) and the Gaussian-exclusion rule (P5 d)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gravanom.config import (
    CVConfig,
    GriddingConfig,
    MaskConfig,
    PipelineConfig,
    ReductionConfig,
    UncertaintyConfig,
    config_hash,
    load_gridding_config,
    load_reduction_config,
)

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (ReductionConfig, {"density_kg_m3": 999}),
        (ReductionConfig, {"density_kg_m3": 3501}),
        (ReductionConfig, {"normal_gravity": "WGS84"}),
        (ReductionConfig, {"curvature": "bullard_approx"}),
        (GriddingConfig, {"cell_size_m": 50}),
        (GriddingConfig, {"cell_size_m": 6000}),
        (GriddingConfig, {"matern_nu": "gaussian"}),
        (GriddingConfig, {"matern_nu": 1.0}),
        (GriddingConfig, {"method": "kriging_gaussian"}),
        (GriddingConfig, {"max_lag_m": 1000}),
        (MaskConfig, {"max_distance_m": 500}),
        (CVConfig, {"n_splits": 2}),
        (CVConfig, {"block_size_m": 100_000}),
        (UncertaintyConfig, {"sigma_g_mgal": -0.1}),
        (UncertaintyConfig, {"mc_draws": 10}),
        (ReductionConfig, {"unknown_key": 1}),
    ],
)
def test_out_of_range_rejected(model: type, kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_defaults_match_guide() -> None:
    r, g = ReductionConfig(), GriddingConfig()
    assert r.density_kg_m3 == 2670 and r.honkasalo and r.atmospheric and r.curvature == "lafehr1991_closed_form"
    assert g.cell_size_m == 500 and g.cv.block_size_m == 15000 and g.cv.n_splits == 5 and g.cv.random_state == 20261022
    assert g.mask.max_distance_m == 5000 and g.mask.max_sigma_mgal == 5.0


def test_config_hash_is_stable_and_sensitive() -> None:
    assert config_hash(PipelineConfig()) == config_hash(PipelineConfig())
    assert config_hash(ReductionConfig()) != config_hash(ReductionConfig(density_kg_m3=2300))


def test_uncertainty_overridable() -> None:
    u = UncertaintyConfig(sigma_g_mgal=0.3, sigma_h_m=5, sigma_tc_rel=0.2, sigma_pos_m=10)
    assert (u.sigma_g_mgal, u.sigma_h_m, u.sigma_tc_rel, u.sigma_pos_m) == (0.3, 5, 0.2, 10)


@pytest.mark.parametrize("name", ["reduction.default.yaml", "reduction.legacy.yaml"])
def test_reduction_yaml_files_load(name: str) -> None:
    load_reduction_config(REPO / "config" / name)


def test_gridding_yaml_loads() -> None:
    assert load_gridding_config(REPO / "config" / "gridding.default.yaml") == GriddingConfig()
