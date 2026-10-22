"""Render grid layers as PNG images in EPSG:3857 for web maps.

Unsupported cells are fully transparent (alpha = 0), never interpolated colours.
Anomalies use a diverging, colour-blind-safe map (ColorBrewer RdBu) centred at 0 with
symmetric robust limits; σ and other magnitudes use viridis.
"""

from __future__ import annotations

import io
from typing import Any

import matplotlib as mpl
import numpy as np
import xarray as xr
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject

from gravanom.constants import CRS_ANALYSIS, CRS_WEB
from gravanom.crs import to_geographic

DIVERGING = "RdBu_r"
SEQUENTIAL = "viridis"
ALLOWED_CMAPS = ("RdBu_r", "viridis", "cividis", "magma")
SEQUENTIAL_LAYERS = frozenset({"sigma_raw", "sigma_cal", "distance_m"})


def robust_symmetric_limits(values: np.ndarray, lo_pct: float = 2.0, hi_pct: float = 98.0) -> tuple[float, float]:
    """Symmetric limits ``(-a, a)`` with ``a`` the larger magnitude of the 2 and 98 % quantiles."""
    v = values[np.isfinite(values)]
    if v.size == 0:
        return -1.0, 1.0
    a = float(max(abs(np.percentile(v, lo_pct)), abs(np.percentile(v, hi_pct))))
    a = a if a > 0 else 1.0
    return -a, a


def default_style(layer: str, values: np.ndarray) -> tuple[str, float, float]:
    """Colormap and limits for a layer."""
    if layer in SEQUENTIAL_LAYERS:
        v = values[np.isfinite(values)]
        return (
            SEQUENTIAL,
            (float(np.percentile(v, 2)) if v.size else 0.0),
            (float(np.percentile(v, 98)) if v.size else 1.0),
        )
    lo, hi = robust_symmetric_limits(values)
    return DIVERGING, lo, hi


def warp_to_web(grid: xr.Dataset, layer: str) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Reproject a layer to EPSG:3857 (nearest neighbour, so masks stay crisp).

    Returns the array (north-up) and the bounds ``(west, south, east, north)`` in lon/lat.
    """
    x, y = grid["x"].values, grid["y"].values
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    src = grid[layer].values.astype("float64")[::-1]
    if "support_mask" in grid and layer not in ("support_mask", "confidence_mask"):
        src = np.where(grid["support_mask"].values[::-1] == 1, src, np.nan)
    src_t = from_origin(x[0] - dx / 2, y[-1] + dy / 2, dx, dy)
    h, w = src.shape
    left, bottom, right, top = x[0] - dx / 2, y[0] - dy / 2, x[-1] + dx / 2, y[-1] + dy / 2
    dst_t, dw, dh = calculate_default_transform(CRS_ANALYSIS, CRS_WEB, w, h, left, bottom, right, top)
    dst = np.full((dh, dw), np.nan)
    reproject(
        src,
        dst,
        src_transform=src_t,
        src_crs=CRS_ANALYSIS,
        dst_transform=dst_t,
        dst_crs=CRS_WEB,
        resampling=Resampling.nearest,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    west, north = dst_t * (0, 0)
    east, south = dst_t * (dw, dh)
    lon, lat = to_geographic(np.array([west, east]), np.array([south, north]), src=CRS_WEB)
    return dst, (float(lon[0]), float(lat[0]), float(lon[1]), float(lat[1]))


def colorize(values: np.ndarray, cmap: str, vmin: float, vmax: float) -> np.ndarray:
    """RGBA uint8 image; NaN cells transparent."""
    if cmap not in ALLOWED_CMAPS:
        raise ValueError(f"cmap must be one of {ALLOWED_CMAPS}")
    norm = np.clip((values - vmin) / (vmax - vmin if vmax > vmin else 1.0), 0, 1)
    rgba = (mpl.colormaps[cmap](np.nan_to_num(norm)) * 255).astype(np.uint8)
    rgba[~np.isfinite(values), 3] = 0
    return rgba


def hatch(shape: tuple[int, int], where: np.ndarray, spacing: int = 6) -> np.ndarray:
    """Diagonal-line RGBA pattern (dark grey) on cells where ``where`` is True."""
    r, c = np.indices(shape)
    lines = ((r + c) % spacing) == 0
    rgba = np.zeros((*shape, 4), np.uint8)
    on = lines & where
    rgba[on] = (40, 40, 40, 200)
    return rgba


def render_layer(
    grid: xr.Dataset,
    layer: str,
    cmap: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Render a grid layer (or ``lowconf_hatch``) to PNG bytes plus display metadata."""
    if layer == "lowconf_hatch":
        sup, _ = warp_to_web(grid, "support_mask")
        conf, bounds = warp_to_web(grid, "confidence_mask")
        rgba = hatch(sup.shape, (sup == 1) & (conf != 1))
        meta: dict[str, Any] = {"layer": layer, "bounds": bounds}
    else:
        if layer not in grid:
            raise KeyError(layer)
        arr, bounds = warp_to_web(grid, layer)
        dc, dlo, dhi = default_style(
            layer,
            grid[layer].values[grid["support_mask"].values == 1] if "support_mask" in grid else grid[layer].values,
        )
        cm, lo, hi = cmap or dc, dlo if vmin is None else vmin, dhi if vmax is None else vmax
        rgba = colorize(arr, cm, lo, hi)
        meta = {
            "layer": layer,
            "bounds": bounds,
            "cmap": cm,
            "vmin": lo,
            "vmax": hi,
            "units": grid[layer].attrs.get("units", ""),
        }
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=False)
    return buf.getvalue(), meta
