"""Quality-control rules (MASTER_GUIDE §5.8). Each rule returns a boolean mask of hits."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import numpy as np
import pandas as pd
import shapely
from numpy.typing import NDArray
from scipy.spatial import cKDTree
from scipy.stats import theilslopes

BoolArray = NDArray[np.bool_]
F64 = NDArray[np.float64]

#: Robust-scale factor making the MAD consistent with the normal standard deviation.
MAD_TO_SD = 1.4826


@dataclass(frozen=True)
class QCThresholds:
    """Thresholds of the QC rules (defaults from §5.8)."""

    lat_range: tuple[float, float] = (-5.0, 15.0)
    lon_range: tuple[float, float] = (-82.0, -66.0)
    height_range_m: tuple[float, float] = (-50.0, 6000.0)
    g_range_mgal: tuple[float, float] = (977_000.0, 984_000.0)
    tc_range_mgal: tuple[float, float] = (0.0, 50.0)
    tc_zero_min_height_m: float = 20.0
    tc_neighbours: int = 10
    tc_z_mad: float = 3.5
    tc_mad_floor_mgal: float = 0.02
    spatial_z_mad: float = 4.0
    faa_h_z_mad: float = 4.0


def robust_z(values: F64, mad_floor: float = 0.0) -> F64:
    """Robust z-scores ``(v - median) / (1.4826 MAD)``; the scale is floored at ``mad_floor``."""
    v = np.asarray(values, dtype=np.float64)
    med = np.nanmedian(v)
    scale = max(MAD_TO_SD * float(np.nanmedian(np.abs(v - med))), mad_floor, 1e-12)
    return np.asarray((v - med) / scale, dtype=np.float64)


def rule_schema(cat: pd.DataFrame) -> BoolArray:
    """QC-01: required principal facts missing or non-finite."""
    cols = ["lon", "lat", "height_m", "g_obs_mgal"]
    vals = cat[cols].to_numpy(dtype=np.float64, na_value=np.nan)
    return np.asarray(~np.isfinite(vals).all(axis=1))


def rule_range(cat: pd.DataFrame, t: QCThresholds = QCThresholds()) -> BoolArray:
    """QC-02: values outside the plausible ranges (non-finite values are QC-01, not QC-02)."""

    def outside(col: str, lo: float, hi: float) -> BoolArray:
        v = cat[col].to_numpy(dtype=np.float64, na_value=np.nan)
        with np.errstate(invalid="ignore"):
            return np.asarray(np.isfinite(v) & ((v < lo) | (v > hi)))

    return (
        outside("lat", *t.lat_range)
        | outside("lon", *t.lon_range)
        | outside("height_m", *t.height_range_m)
        | outside("g_obs_mgal", *t.g_range_mgal)
        | outside("tc_supplied_mgal", *t.tc_range_mgal)
    )


def rule_h_nonpositive(cat: pd.DataFrame) -> BoolArray:
    """QC-06: onshore station with H <= 0 m (warning)."""
    h = cat["height_m"].to_numpy(dtype=np.float64, na_value=np.nan)
    with np.errstate(invalid="ignore"):
        return np.asarray(h <= 0.0)


def rule_tc_suspect(cat: pd.DataFrame, t: QCThresholds = QCThresholds()) -> BoolArray:
    """QC-05: TC = 0 at H > 20 m, or TC a robust outlier relative to its 10 neighbours.

    The neighbour test uses ``z = (TC - median_nbr) / max(1.4826 MAD_nbr, floor)``
    with ``|z| > 3.5``.
    """
    tc = cat["tc_supplied_mgal"].to_numpy(dtype=np.float64, na_value=np.nan)
    h = cat["height_m"].to_numpy(dtype=np.float64, na_value=np.nan)
    with np.errstate(invalid="ignore"):
        hit = (tc == 0.0) & (h > t.tc_zero_min_height_m)
    xy = cat[["x_9377", "y_9377"]].to_numpy(dtype=np.float64)
    ok = np.isfinite(xy).all(axis=1) & np.isfinite(tc)
    idx = np.flatnonzero(ok)
    k = min(t.tc_neighbours + 1, len(idx))
    if k > 3:
        tree = cKDTree(xy[idx])
        _, nb = tree.query(xy[idx], k=k)
        nbr_tc = tc[idx][nb[:, 1:]]
        med = np.median(nbr_tc, axis=1)
        mad = MAD_TO_SD * np.median(np.abs(nbr_tc - med[:, None]), axis=1)
        z = (tc[idx] - med) / np.maximum(mad, t.tc_mad_floor_mgal)
        hit[idx] |= np.abs(z) > t.tc_z_mad
    return np.asarray(hit)


@lru_cache(maxsize=1)
def colombia_land_polygon() -> shapely.Geometry:
    """Natural Earth 1:10m admin-0 polygon of Colombia (public domain), bundled with the package."""
    import json

    text = resources.files("gravanom.data").joinpath("ne_admin0_colombia.geojson").read_text(encoding="utf-8")
    geoms = [shapely.geometry.shape(f["geometry"]) for f in json.loads(text)["features"]]
    poly = shapely.union_all(geoms)
    shapely.prepare(poly)
    return poly


def rule_offshore(cat: pd.DataFrame, polygon: shapely.Geometry | None = None) -> BoolArray:
    """QC-12: coordinates outside the Colombia land polygon (warning)."""
    poly = polygon if polygon is not None else colombia_land_polygon()
    lon = cat["lon"].to_numpy(dtype=np.float64, na_value=np.nan)
    lat = cat["lat"].to_numpy(dtype=np.float64, na_value=np.nan)
    ok = np.isfinite(lon) & np.isfinite(lat)
    hit = np.zeros(len(cat), dtype=bool)
    hit[ok] = ~shapely.contains_xy(poly, lon[ok], lat[ok])
    return hit


def rule_faa_h_outlier(faa_mgal: F64, height_m: F64, t: QCThresholds = QCThresholds()) -> BoolArray:
    """QC-08: outlier of the FAA-H relationship (Theil-Sen line, robust |z| > 4; warning)."""
    faa = np.asarray(faa_mgal, dtype=np.float64)
    h = np.asarray(height_m, dtype=np.float64)
    ok = np.isfinite(faa) & np.isfinite(h)
    hit = np.zeros(faa.shape, dtype=bool)
    if ok.sum() < 10:
        return hit
    slope, intercept, _, _ = theilslopes(faa[ok], h[ok])
    resid = faa[ok] - (intercept + slope * h[ok])
    hit[ok] = np.abs(robust_z(resid)) > t.faa_h_z_mad
    return hit


def rule_spatial_outlier(cv_residual_mgal: F64, t: QCThresholds = QCThresholds()) -> BoolArray:
    """QC-07: block-CV residual of the selected gridder with robust |z| > 4 (warning)."""
    r = np.asarray(cv_residual_mgal, dtype=np.float64)
    hit = np.zeros(r.shape, dtype=bool)
    ok = np.isfinite(r)
    if ok.sum() >= 10:
        hit[ok] = np.abs(robust_z(r[ok])) > t.spatial_z_mad
    return hit
