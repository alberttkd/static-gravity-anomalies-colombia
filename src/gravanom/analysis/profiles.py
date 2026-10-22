"""Profiles across a grid (OP-12)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import shapely
import xarray as xr
from scipy.interpolate import RegularGridInterpolator

from gravanom.crs import to_analysis


class ProfileOutsideSupportError(ValueError):
    """The profile line does not cross any supported cell."""


def _sample(ds: xr.Dataset, var: str, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    f = RegularGridInterpolator((ds["y"].values, ds["x"].values), ds[var].values, bounds_error=False, fill_value=np.nan)
    return np.asarray(f(np.column_stack([y, x])))


def profile(
    ds: xr.Dataset,
    coordinates_lonlat: list[tuple[float, float]] | list[list[float]],
    stations: pd.DataFrame | None = None,
    value_column: str = "value",
    buffer_m: float = 2000.0,
    step_m: float | None = None,
) -> dict[str, Any]:
    """Sample a grid along a polyline given in EPSG:4326.

    Parameters
    ----------
    ds : Dataset
        Grid product (EPSG:9377) with ``value``, ``sigma_cal`` and ``support_mask``.
    coordinates_lonlat : list of (lon, lat)
        Polyline vertices (at least two).
    stations : DataFrame, optional
        Stations with ``x_9377``, ``y_9377``, ``height_m`` and ``value_column``;
        those within ``buffer_m`` are projected onto the line.
    step_m : float, optional
        Sampling step; defaults to the grid cell size.

    Returns
    -------
    dict
        ``distance_km``, ``value``, ``sigma``, ``supported`` along the line, and
        ``stations`` (distance along, offset, value, sigma if present, height).
    """
    coords = np.asarray(coordinates_lonlat, dtype=float)
    if coords.ndim != 2 or len(coords) < 2:
        raise ValueError("a profile needs at least two vertices")
    lx, ly = to_analysis(coords[:, 0], coords[:, 1])
    line = shapely.LineString(np.column_stack([lx, ly]))
    step = step_m or float(ds.attrs.get("cell_size_m", 500.0))
    d = np.arange(0.0, line.length + step / 2, step)
    pts = shapely.line_interpolate_point(line, d)
    px, py = shapely.get_x(pts), shapely.get_y(pts)
    val = _sample(ds, "value", px, py)
    sig = _sample(ds, "sigma_cal", px, py)
    sup = _sample(ds, "support_mask", px, py) >= 0.999
    val[~sup] = np.nan
    sig[~sup] = np.nan
    if not sup.any():
        raise ProfileOutsideSupportError("the profile does not intersect the support mask")
    out: dict[str, Any] = {
        "distance_km": (d / 1000).tolist(),
        "value": val.tolist(),
        "sigma": sig.tolist(),
        "supported": sup.tolist(),
        "length_km": line.length / 1000,
        "buffer_m": buffer_m,
        "stations": [],
    }
    if stations is not None and len(stations):
        sp = shapely.points(stations["x_9377"].to_numpy(), stations["y_9377"].to_numpy())
        off = shapely.distance(line, sp)
        near = np.flatnonzero(off <= buffer_m)
        along = shapely.line_locate_point(line, sp[near])
        for i, a, o in zip(near, along, off[near], strict=True):
            row = stations.iloc[i]
            out["stations"].append(
                {
                    "station_uid": str(row.get("station_uid", i)),
                    "distance_km": float(a / 1000),
                    "offset_m": float(o),
                    "value": float(row[value_column]),
                    "sigma": float(row["sigma"]) if "sigma" in row and np.isfinite(row["sigma"]) else None,
                    "height_m": float(row["height_m"]),
                }
            )
        out["stations"].sort(key=lambda s: s["distance_km"])
    return out
