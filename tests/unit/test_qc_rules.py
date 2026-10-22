"""Positive and negative tests for every QC rule (P2 f)."""

from __future__ import annotations

import numpy as np
import shapely

from gravanom.flags import QCFlag
from gravanom.qc import QCThresholds, has_flag, robust_z, run_qc
from gravanom.qc.rules import (
    rule_faa_h_outlier,
    rule_h_nonpositive,
    rule_offshore,
    rule_range,
    rule_schema,
    rule_spatial_outlier,
    rule_tc_suspect,
)
from tests.conftest import make_stations


def test_schema_rule() -> None:
    s = make_stations(5)
    assert not rule_schema(s).any()
    s.loc[2, "g_obs_mgal"] = np.nan
    assert rule_schema(s).tolist() == [False, False, True, False, False]


def test_range_rule() -> None:
    s = make_stations(6)
    assert not rule_range(s).any()
    s.loc[0, "g_obs_mgal"] = 990_000
    s.loc[1, "lat"] = 20
    s.loc[2, "height_m"] = 7000
    s.loc[3, "tc_supplied_mgal"] = -1
    assert rule_range(s).tolist() == [True, True, True, True, False, False]


def test_range_rule_ignores_nan() -> None:
    s = make_stations(3)
    s.loc[0, "height_m"] = np.nan
    assert not rule_range(s).any()


def test_h_nonpositive_rule() -> None:
    s = make_stations(3)
    assert not rule_h_nonpositive(s).any()
    s.loc[1, "height_m"] = -1.0
    assert rule_h_nonpositive(s).tolist() == [False, True, False]


def test_tc_suspect_zero_rule() -> None:
    s = make_stations(40)
    assert not rule_tc_suspect(s).any()
    s.loc[3, "tc_supplied_mgal"] = 0.0
    s.loc[3, "height_m"] = 60.0
    s.loc[4, "tc_supplied_mgal"] = 0.0
    s.loc[4, "height_m"] = 10.0  # low station: zero is plausible
    hit = rule_tc_suspect(s, QCThresholds(tc_z_mad=1e9))
    assert hit[3] and not hit[4]


def test_tc_suspect_neighbour_outlier() -> None:
    s = make_stations(40)
    s["tc_supplied_mgal"] = 0.3
    s.loc[7, "tc_supplied_mgal"] = 5.0
    hit = rule_tc_suspect(s)
    assert hit[7] and hit.sum() == 1


def test_offshore_rule() -> None:
    s = make_stations(3)
    poly = shapely.box(-76, 8, -74, 10)
    assert not rule_offshore(s, poly).any()
    s.loc[0, "lon"] = -80.0
    assert rule_offshore(s, poly).tolist() == [True, False, False]


def test_offshore_default_polygon_colombia() -> None:
    s = make_stations(2)
    s["lon"], s["lat"] = [-74.8, -77.5], [9.0, 12.0]  # inland vs Caribbean Sea
    assert rule_offshore(s).tolist() == [False, True]


def test_faa_h_outlier_rule() -> None:
    rng = np.random.default_rng(0)
    h = rng.uniform(0, 300, 200)
    faa = 0.2 * h + rng.normal(0, 1, 200)
    assert not rule_faa_h_outlier(faa, h).any()
    faa[10] += 50
    hit = rule_faa_h_outlier(faa, h)
    assert hit[10] and hit.sum() == 1


def test_spatial_outlier_rule() -> None:
    r = np.random.default_rng(1).normal(0, 1, 300)
    assert not rule_spatial_outlier(r).any()
    r[5] = 30
    assert rule_spatial_outlier(r)[5]


def test_robust_z() -> None:
    z = robust_z(np.array([1.0, 2.0, 3.0, 4.0, 100.0]))
    assert abs(z[2]) < 1e-12 and z[-1] > 10


def test_run_qc_sets_tc_missing() -> None:
    s = make_stations(30)
    s.loc[5, "tc_supplied_mgal"] = 0.0
    s.loc[5, "tc_mgal"] = 0.0
    out, rep = run_qc(s, land_polygon=shapely.box(-80, 5, -70, 13))
    assert has_flag(out, QCFlag.TC_SUSPECT)[5]
    assert np.isnan(out.loc[5, "tc_mgal"]) and out.loc[5, "tc_supplied_mgal"] == 0.0
    assert rep.flag_counts["TC_SUSPECT"] >= 1 and rep.n_stations == 30
