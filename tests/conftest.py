"""Shared fixtures. Real data are only touched by tests marked ``private``."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gravanom.harmonize import harmonize
from gravanom.io.readers import read_station_csv
from gravanom.qc import run_qc

REPO = Path(__file__).resolve().parents[1]
SYNTHETIC_CSV = REPO / "data" / "synthetic" / "synthetic_survey.csv"
SYNTHETIC_META = REPO / "data" / "synthetic" / "synthetic_metadata.json"


@pytest.fixture(scope="session")
def golden() -> dict:
    return json.loads((REPO / "tests" / "fixtures" / "golden_vectors.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def synthetic_records() -> pd.DataFrame:
    return read_station_csv(SYNTHETIC_CSV)


@pytest.fixture(scope="session")
def synthetic_catalogue(synthetic_records: pd.DataFrame) -> tuple[pd.DataFrame, object, dict]:
    cat, log = harmonize([synthetic_records])
    cat, report = run_qc(cat, log)
    return cat, report, log


@pytest.fixture(scope="session")
def synthetic_metadata() -> dict:
    return json.loads(SYNTHETIC_META.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def private_root() -> Path:
    env = os.environ.get("GRAVANOM_PRIVATE_DATA_DIR")
    from gravanom.io.legacy import sources_file

    if not env or not Path(env).is_dir() or not sources_file().exists():
        pytest.skip("GRAVANOM_PRIVATE_DATA_DIR not set or invalid")
    return Path(env)


def make_stations(n: int = 50, seed: int = 1, **overrides: object) -> pd.DataFrame:
    """Small artificial station table in the canonical catalogue schema."""
    rng = np.random.default_rng(seed)
    lon = -75.0 + rng.uniform(-0.3, 0.3, n)
    lat = 9.0 + rng.uniform(-0.3, 0.3, n)
    from gravanom.crs import to_analysis

    x, y = to_analysis(lon, lat)
    df = pd.DataFrame(
        {
            "station_uid": [f"T:{i}" for i in range(n)],
            "source_ids": [[f"T:{i}"] for i in range(n)],
            "sources": [["T"] for _ in range(n)],
            "lon": lon,
            "lat": lat,
            "x_9377": x,
            "y_9377": y,
            "height_m": rng.uniform(20, 250, n),
            "g_obs_mgal": 978_150 + rng.normal(0, 10, n),
            "tc_mgal": rng.uniform(0.2, 0.5, n),
            "tc_supplied_mgal": np.nan,
            "bb_supplied_mgal": np.nan,
            "n_merged": 1,
            "g_obs_spread_mgal": 0.0,
            "qc_flags": [[] for _ in range(n)],
            "prov_file": [["t.csv"] for _ in range(n)],
            "prov_sheet": [[""] for _ in range(n)],
            "prov_row": [[i] for i in range(n)],
        }
    )
    df["tc_supplied_mgal"] = df["tc_mgal"]
    for k, v in overrides.items():
        df[k] = v
    return df
