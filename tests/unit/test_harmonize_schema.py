"""Harmonization (QC-03/04) and schema validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gravanom.flags import QCFlag
from gravanom.harmonize import harmonize
from gravanom.io.schema import SchemaError, coerce_records, validate_records, validate_stations


def _rec(source: str, ids: list[str], lon: list[float], g: list[float] | None = None) -> pd.DataFrame:
    n = len(ids)
    return pd.DataFrame(
        {
            "source": source,
            "source_id": ids,
            "lon": lon,
            "lat": [9.0 + 0.01 * i for i in range(n)],
            "height_m": [100.0] * n,
            "g_obs_mgal": g or [978_100.0] * n,
            "tc_mgal": [0.3] * n,
            "bb_supplied_mgal": [np.nan] * n,
            "prov_file": f"{source}.xlsx",
            "prov_sheet": "s",
            "prov_row": list(range(2, n + 2)),
        }
    )


def test_shared_ids_collapse_when_consistent() -> None:
    a = _rec("A", ["1", "2"], [-75.0, -75.1])
    b = _rec("B", ["2", "3"], [-75.1, -75.2])
    b.loc[0, "lat"] = a.loc[1, "lat"]
    cat, log = harmonize([a, b])
    assert log["n_shared_ids"] == 1 and log["n_shared_consistent"] == 1
    assert len(cat) == 3
    row = cat[cat.station_uid == "A:2"].iloc[0]
    assert row.sources == ["A", "B"] and row.source_ids == ["A:2", "B:2"]
    assert row.prov_file == ["A.xlsx", "B.xlsx"]


def test_shared_ids_conflict_flagged() -> None:
    a = _rec("A", ["1"], [-75.0])
    b = _rec("B", ["1"], [-75.0], g=[978_101.0])
    cat, log = harmonize([a, b])
    assert log["shared_id_conflicts"] == ["1"]
    assert len(cat) == 2
    assert all(QCFlag.CONFLICT_SHARED_ID.value in f for f in cat.qc_flags)


def test_duplicate_positions_merged() -> None:
    a = _rec("A", ["1", "2", "3"], [-75.0, -75.0, -75.3], g=[978_100.0, 978_100.9, 978_050.0])
    a.loc[1, "lat"] = a.loc[0, "lat"]
    cat, log = harmonize([a])
    assert log["n_merged_groups"] == 1 and log["n_groups_g_spread_gt_0p1"] == 1
    m = cat[cat.n_merged == 2].iloc[0]
    assert m.station_uid == "merged:A:1+A:2"
    assert m.g_obs_mgal == pytest.approx(978_100.45) and m.g_obs_spread_mgal == pytest.approx(0.9)
    assert QCFlag.DUPLICATE_POSITION.value in m.qc_flags


def test_record_schema_issues() -> None:
    r = _rec("A", ["1", "1"], [-75.0, np.nan])
    msgs = {i.message for i in validate_records(r)}
    assert "null or non-numeric value" in msgs and "id not unique within source" in msgs
    with pytest.raises(SchemaError):
        coerce_records(r.drop(columns=["lon"]))


def test_station_schema(synthetic_catalogue) -> None:  # type: ignore[no-untyped-def]
    cat = synthetic_catalogue[0]
    assert validate_stations(cat) == []
    bad = cat.copy()
    bad.at[bad.index[0], "qc_flags"] = ["NOT_A_FLAG"]
    assert validate_stations(bad)[0].message == "unknown flag"
