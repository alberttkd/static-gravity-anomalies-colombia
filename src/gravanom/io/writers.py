"""Writers for station tables, grids, contours and reports, always with CRS metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.transform import from_origin

from gravanom.constants import CRS_ANALYSIS, CRS_STORAGE

LIST_COLUMNS = ("source_ids", "sources", "qc_flags", "prov_file", "prov_sheet", "prov_row")


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if np.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, Path):
        return obj.as_posix()
    if hasattr(obj, "model_dump"):
        return _jsonable(obj.model_dump(mode="json"))
    return obj


def to_jsonable(obj: Any) -> Any:
    """Convert numpy scalars/arrays, paths, NaN and Pydantic models into JSON-compatible values."""
    return _jsonable(obj)


def write_json(obj: Any, path: str | Path) -> Path:
    """Write deterministic JSON (sorted keys, NaN as null, UTF-8, trailing newline)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_jsonable(obj), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
    p.write_text(text + "\n", encoding="utf-8", newline="\n")
    return p


def stations_geodataframe(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Build a GeoDataFrame in EPSG:4326 from ``lon``/``lat`` columns."""
    return gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=CRS_STORAGE)


def write_geoparquet(df: pd.DataFrame, path: str | Path) -> Path:
    """Write a station table as GeoParquet (EPSG:4326 point geometry)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    stations_geodataframe(df).to_parquet(p, index=False, compression="zstd", write_covering_bbox=False)
    return p


def _flatten_lists(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in LIST_COLUMNS or (len(out) and isinstance(out[col].iloc[0], (list, tuple, np.ndarray))):
            out[col] = [";".join(str(v) for v in x) for x in out[col]]
    return out


def write_gpkg(df: pd.DataFrame, path: str | Path, layer: str = "stations") -> Path:
    """Write a station table as GeoPackage (list columns joined with ``;``)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    stations_geodataframe(_flatten_lists(df)).to_file(p, layer=layer, driver="GPKG")
    return p


def write_csv(df: pd.DataFrame, path: str | Path, header_comment: str | None = None) -> Path:
    """Write a CSV with fixed float formatting (deterministic), optional ``#`` header line."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = _flatten_lists(df).to_csv(index=False, float_format="%.10g", lineterminator="\n")
    text = (f"# {header_comment}\n" if header_comment else "") + body
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def write_cog(
    values: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    path: str | Path,
    crs: str = CRS_ANALYSIS,
    tags: dict[str, str] | None = None,
    dtype: str = "float32",
) -> Path:
    """Write a 2-D array (rows = ascending y) as a Cloud-Optimized GeoTIFF.

    The raster has an embedded CRS and NaN nodata (fixes F-17). Coordinates are
    cell centres; the first row written is the northernmost.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    dx = float(x_coords[1] - x_coords[0])
    dy = float(y_coords[1] - y_coords[0])
    arr = np.asarray(values)[::-1].astype(dtype)
    transform = from_origin(float(x_coords[0]) - dx / 2, float(y_coords[-1]) + dy / 2, dx, dy)
    profile = {
        "driver": "COG",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": crs,
        "transform": transform,
        "nodata": np.nan if dtype.startswith("float") else 255,
        "compress": "deflate",
        "overview_resampling": "average",
    }
    with rasterio.open(p, "w", **profile) as dst:
        dst.write(arr, 1)
        if tags:
            dst.update_tags(**tags)
    return p


def write_netcdf(ds: xr.Dataset, path: str | Path) -> Path:
    """Write a grid dataset as NetCDF (CF-1.8 attributes expected on ``ds``)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(p)
    return p


def write_geojson(feature_collection: dict[str, Any], path: str | Path) -> Path:
    """Write a GeoJSON FeatureCollection (coordinates in EPSG:4326)."""
    return write_json(feature_collection, path)
