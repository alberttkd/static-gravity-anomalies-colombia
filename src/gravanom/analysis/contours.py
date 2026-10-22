"""Contour lines of a grid as GeoJSON in EPSG:4326 (OP-13)."""

from __future__ import annotations

from typing import Any

import contourpy
import numpy as np
import xarray as xr

from gravanom.crs import to_geographic


def contours(ds: xr.Dataset, interval_mgal: float = 5.0, variable: str = "value") -> dict[str, Any]:
    """Contour the supported part of a grid at multiples of ``interval_mgal``.

    Masked (NaN) cells are excluded. Returns a GeoJSON FeatureCollection of
    LineStrings with a ``level`` property [mGal].
    """
    if interval_mgal <= 0:
        raise ValueError("interval must be positive")
    z = ds[variable].values.astype(float)
    if "support_mask" in ds:
        z = np.where(ds["support_mask"].values.astype(bool), z, np.nan)
    feats: list[dict[str, Any]] = []
    if np.isfinite(z).any():
        lo = np.ceil(np.nanmin(z) / interval_mgal) * interval_mgal
        hi = np.floor(np.nanmax(z) / interval_mgal) * interval_mgal
        gen = contourpy.contour_generator(ds["x"].values, ds["y"].values, np.ma.masked_invalid(z), name="serial")
        for level in np.arange(lo, hi + interval_mgal / 2, interval_mgal):
            for line in gen.lines(float(level)):
                seg = np.asarray(line)
                if len(seg) < 2:
                    continue
                lon, lat = to_geographic(seg[:, 0], seg[:, 1])
                feats.append(
                    {
                        "type": "Feature",
                        "properties": {"level": round(float(level), 6), "units": "mGal"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": np.round(np.column_stack([lon, lat]), 6).tolist(),
                        },
                    }
                )
    return {"type": "FeatureCollection", "features": feats, "properties": {"interval_mgal": interval_mgal}}
