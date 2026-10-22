"""Coordinate transformations (always lon/lat order, ``always_xy=True``)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pyproj import Transformer

from gravanom.constants import CRS_ANALYSIS, CRS_STORAGE

F64 = NDArray[np.float64]


@lru_cache(maxsize=16)
def transformer(src: str, dst: str) -> Transformer:
    """Cached :class:`pyproj.Transformer` with ``always_xy=True``."""
    return Transformer.from_crs(src, dst, always_xy=True)


def to_analysis(lon: ArrayLike, lat: ArrayLike) -> tuple[F64, F64]:
    """EPSG:4326 lon/lat [deg] to EPSG:9377 easting/northing [m]."""
    x, y = transformer(CRS_STORAGE, CRS_ANALYSIS).transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)


def to_geographic(x: ArrayLike, y: ArrayLike, src: str = CRS_ANALYSIS) -> tuple[F64, F64]:
    """Projected coordinates [m] (default EPSG:9377) to EPSG:4326 lon/lat [deg]."""
    lon, lat = transformer(src, CRS_STORAGE).transform(np.asarray(x, float), np.asarray(y, float))
    return np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
