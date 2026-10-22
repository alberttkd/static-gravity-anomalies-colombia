"""Property tests of the reduction chain (P3 d) and configuration switches."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gravanom.config import ReductionConfig
from gravanom.reduction import TERM_COLUMNS, bouguer_slab, compute_anomalies, compute_legacy, honkasalo


def _stations(lat: float, h: float, g: float = 978_100.0, tc: float = 0.3, bb: float = -0.1) -> pd.DataFrame:
    return pd.DataFrame({"lat": [lat], "height_m": [h], "g_obs_mgal": [g], "tc_mgal": [tc], "bb_supplied_mgal": [bb]})


@settings(max_examples=200, deadline=None)
@given(
    lat=st.floats(-60, 60),
    h=st.floats(-400, 4000),
    rho=st.floats(1000, 3500),
    tc=st.floats(0, 20),
)
def test_cba_identity(lat: float, h: float, rho: float, tc: float) -> None:
    an = compute_anomalies(_stations(lat, h, tc=tc), ReductionConfig(density_kg_m3=rho))
    r = an.iloc[0]
    assert r.cba_mgal == pytest.approx(r.sba_mgal - r.bb_mgal + r.tc_rho_mgal, abs=1e-9)
    assert r.sba_mgal == pytest.approx(r.faa_mgal - r.bc_slab_mgal, abs=1e-9)


@settings(max_examples=100, deadline=None)
@given(h=st.floats(0.1, 5000), rho1=st.floats(1000, 3400), d=st.floats(1, 100))
def test_slab_monotone(h: float, rho1: float, d: float) -> None:
    assert bouguer_slab(h, rho1 + d) > bouguer_slab(h, rho1)
    assert bouguer_slab(h + d, rho1) > bouguer_slab(h, rho1)


def test_sba_decreases_with_density() -> None:
    s = _stations(9.5, 150.0)
    a = compute_anomalies(s, ReductionConfig(density_kg_m3=2300)).sba_mgal.iloc[0]
    b = compute_anomalies(s, ReductionConfig(density_kg_m3=2670)).sba_mgal.iloc[0]
    assert b < a


def test_honkasalo_zero_crossing() -> None:
    lat0 = np.degrees(np.arcsin(np.sqrt(1 / 3)))
    assert honkasalo(lat0) == pytest.approx(0.0, abs=1e-12)


def test_switches_change_only_their_term() -> None:
    s = _stations(9.5, 200.0)
    base = compute_anomalies(s)
    no_h = compute_anomalies(s, ReductionConfig(honkasalo=False))
    no_a = compute_anomalies(s, ReductionConfig(atmospheric=False))
    no_c = compute_anomalies(s, ReductionConfig(curvature="none"))
    assert (base.faa_mgal - no_h.faa_mgal).iloc[0] == pytest.approx(base.honkasalo_mgal.iloc[0])
    assert (base.faa_mgal - no_a.faa_mgal).iloc[0] == pytest.approx(base.atm_mgal.iloc[0])
    assert no_c.bb_mgal.iloc[0] == 0.0
    assert (no_c.cba_mgal - base.cba_mgal).iloc[0] == pytest.approx(base.bb_mgal.iloc[0])


def test_supplied_bb_mode_uses_value_to_add_convention() -> None:
    s = _stations(9.5, 92.0, bb=-0.13158)
    an = compute_anomalies(s, ReductionConfig(curvature="supplied_bb_legacy"))
    assert an.bb_mgal.iloc[0] == pytest.approx(0.13158)


def test_null_tc_gives_null_cba() -> None:
    an = compute_anomalies(_stations(9.5, 100.0, tc=np.nan))
    assert np.isnan(an.cba_mgal.iloc[0]) and np.isfinite(an.sba_mgal.iloc[0])


def test_legacy_mode_matches_appendix_b_formulas() -> None:
    s = _stations(9.3, 90.0, g=978_140.0, tc=0.2, bb=-0.13)  # fictitious values
    leg = compute_anomalies(s, ReductionConfig(legacy_mode=True))
    raw = compute_legacy(s)
    assert list(leg.columns) == list(TERM_COLUMNS)
    assert leg.faa_mgal.iloc[0] == raw.aaa.iloc[0]
    assert leg.cba_mgal.iloc[0] == pytest.approx(raw["abs"].iloc[0] + 0.2, abs=1e-9)
    # Legacy ABS = SBA_legacy - BB (BB supplied as value to add).
    assert leg.sba_mgal.iloc[0] == pytest.approx(raw.aaa.iloc[0] + raw.ccb.iloc[0] - 0.13, abs=1e-9)
