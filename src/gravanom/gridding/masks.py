"""Reliability masks (MASTER_GUIDE §5.5.8)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import Delaunay, cKDTree

F64 = NDArray[np.float64]


def distance_to_nearest(px: F64, py: F64, sx: F64, sy: F64) -> F64:
    """Distance [m] from each query point to the nearest station."""
    d, _ = cKDTree(np.column_stack([sx, sy])).query(np.column_stack([np.ravel(px), np.ravel(py)]))
    return np.asarray(d).reshape(np.shape(px))


def inside_hull(px: F64, py: F64, sx: F64, sy: F64) -> NDArray[np.bool_]:
    """True where a query point lies inside the convex hull of the stations."""
    tri = Delaunay(np.column_stack([sx, sy]))
    inside = tri.find_simplex(np.column_stack([np.ravel(px), np.ravel(py)])) >= 0
    return np.asarray(inside).reshape(np.shape(px))


def support_mask(
    px: F64, py: F64, sx: F64, sy: F64, max_distance_m: float = 5000.0, use_convex_hull: bool = True
) -> NDArray[np.bool_]:
    """Supported cells: within ``max_distance_m`` of a station and (optionally) inside the hull."""
    ok = distance_to_nearest(px, py, sx, sy) <= max_distance_m
    if use_convex_hull:
        ok &= inside_hull(px, py, sx, sy)
    return np.asarray(ok)


def confidence_mask(sigma_cal_mgal: F64, max_sigma_mgal: float = 5.0) -> NDArray[np.bool_]:
    """Confident cells: calibrated σ at or below ``max_sigma_mgal`` (NaN is not confident)."""
    s = np.asarray(sigma_cal_mgal, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        return np.asarray(np.isfinite(s) & (s <= max_sigma_mgal))
