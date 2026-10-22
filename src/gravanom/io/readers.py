"""Readers for generic station CSV files (e.g. the synthetic dataset) and grid products."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import xarray as xr

from gravanom.io.schema import coerce_records

#: Column names expected in a generic station CSV.
CSV_COLUMNS = ("id", "lon", "lat", "height_m", "g_obs_mgal", "tc_mgal")


def read_station_csv(path: str | Path, source: str = "SYN") -> pd.DataFrame:
    """Read a station CSV with columns :data:`CSV_COLUMNS` into the record schema.

    Lines starting with ``#`` are comments. ``bb_supplied_mgal`` is optional.
    """
    p = Path(path)
    df = pd.read_csv(p, comment="#", dtype={"id": str})
    missing = [c for c in CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{p.name}: missing columns {missing}")
    rec = pd.DataFrame(
        {
            "source": source,
            "source_id": df["id"].astype(str),
            "lon": df["lon"],
            "lat": df["lat"],
            "height_m": df["height_m"],
            "g_obs_mgal": df["g_obs_mgal"],
            "tc_mgal": df["tc_mgal"],
            "bb_supplied_mgal": df["bb_supplied_mgal"] if "bb_supplied_mgal" in df else np.nan,
            "prov_file": p.name,
            "prov_sheet": "",
            "prov_row": np.arange(2, len(df) + 2),
        }
    )
    return coerce_records(rec)


def read_grid_dir(path: str | Path) -> xr.Dataset:
    """Read a grid product directory (one COG per layer, ``grid.json``) into an xarray Dataset.

    Rows are returned in ascending y (south to north), as produced by the pipeline.
    """
    p = Path(path)
    meta = json.loads((p / "grid.json").read_text(encoding="utf-8")) if (p / "grid.json").exists() else {}
    data_vars = {}
    x = y = None
    for tif in sorted(p.glob("*.tif")):
        with rasterio.open(tif) as src:
            arr = src.read(1)[::-1]
            t = src.transform
            units = src.tags().get("units", "")
            if x is None:
                x = t.c + t.a * (np.arange(src.width) + 0.5)
                y = (t.f + t.e * (np.arange(src.height) + 0.5))[::-1]
        data_vars[tif.stem] = (("y", "x"), arr, {"units": units})
    if x is None or y is None:
        raise FileNotFoundError(f"no grid layers in {p}")
    return xr.Dataset(
        data_vars,
        coords={"x": x, "y": y},
        attrs={**{k: v for k, v in meta.items() if isinstance(v, (str, int, float))}},
    )
