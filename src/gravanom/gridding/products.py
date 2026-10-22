"""Grid products: final model fitting, grid definition, prediction, σ and masks (OP-08)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import xarray as xr
from numpy.typing import NDArray

from gravanom.config import GriddingConfig
from gravanom.constants import CRS_ANALYSIS
from gravanom.gridding.cv import Points, block_folds, calibration_stats, candidates_for, select_candidate
from gravanom.gridding.gridders import Gridder, RegressionKriging
from gravanom.gridding.masks import confidence_mask, distance_to_nearest, inside_hull

F64 = NDArray[np.float64]

#: Upper bound on the number of grid cells (API code GRID_TOO_LARGE).
MAX_CELLS = 2_000_000
#: Minimum number of points for gridding (API code INSUFFICIENT_DATA).
MIN_POINTS = 30


class GridTooLargeError(ValueError):
    """The requested grid exceeds :data:`MAX_CELLS`."""


class TooFewPointsError(ValueError):
    """Fewer than :data:`MIN_POINTS` usable points."""


@dataclass
class FinalModel:
    """A gridder fitted on all points plus its calibration factor."""

    gridder: Gridder
    calibration_c: float | None
    selection: dict[str, Any]


def grid_axes(x: F64, y: F64, cell_m: float, pad_m: float = 0.0) -> tuple[F64, F64]:
    """Cell-centre axes aligned to multiples of the cell size, covering the points' bounding box."""
    x0 = np.floor((np.min(x) - pad_m) / cell_m) * cell_m
    x1 = np.ceil((np.max(x) + pad_m) / cell_m) * cell_m
    y0 = np.floor((np.min(y) - pad_m) / cell_m) * cell_m
    y1 = np.ceil((np.max(y) + pad_m) / cell_m) * cell_m
    return np.arange(x0, x1 + cell_m / 2, cell_m), np.arange(y0, y1 + cell_m / 2, cell_m)


def fit_final_model(
    method: str, pts: Points, cfg: GriddingConfig, anisotropy: tuple[float, float] | None = None
) -> FinalModel:
    """Select hyper-parameters by block CV on all points, then refit on all points.

    The calibration factor is ``c = sd(z)`` of the selected candidate's block CV.
    """
    if len(pts) < MIN_POINTS:
        raise TooFewPointsError(f"gridding needs >= {MIN_POINTS} points, got {len(pts)}")
    cands = candidates_for(method, cfg, anisotropy)
    folds = block_folds(pts.x, pts.y, cfg.cv.block_size_m, cfg.cv.n_splits, cfg.cv.random_state)
    best, res, scores = select_candidate(cands, pts, folds)
    c = calibration_stats(res["z"])["sd_z"] if "z" in res else None
    g = best.factory().fit(pts.x, pts.y, pts.z, pts.h)
    return FinalModel(g, c, {"chosen": best.label, "cv_rmse": res["rmse"], "scores": scores})


def make_grid(model: FinalModel, pts: Points, cfg: GriddingConfig, axes: tuple[F64, F64] | None = None) -> xr.Dataset:
    """Predict on the grid; unsupported cells are NaN in every value layer.

    Layers: ``value``, ``sigma_raw``, ``sigma_cal`` (field σ, nugget excluded),
    ``trend`` [mGal], ``support_mask``, ``confidence_mask`` (uint8), ``distance_m``.
    EqS predictions are made at the median station height.
    """
    gx, gy = axes or grid_axes(pts.x, pts.y, cfg.cell_size_m)
    if gx.size * gy.size > MAX_CELLS:
        raise GridTooLargeError(f"grid of {gx.size * gy.size} cells exceeds {MAX_CELLS}")
    xx, yy = np.meshgrid(gx, gy)
    dist = distance_to_nearest(xx, yy, pts.x, pts.y)
    support = dist <= cfg.mask.max_distance_m
    if cfg.mask.use_convex_hull:
        support &= inside_hull(xx, yy, pts.x, pts.y)
    value = np.full(xx.shape, np.nan)
    sig_raw = np.full(xx.shape, np.nan)
    trend = np.full(xx.shape, np.nan)
    px, py = xx[support], yy[support]
    hh = np.full(px.shape, float(np.median(pts.h)))
    g = model.gridder
    s: F64 | None
    if isinstance(g, RegressionKriging):
        p, s = g.predict(px, py, hh, include_nugget=False)
        trend[support] = g.trend_at(px, py)
    else:
        p, s = g.predict(px, py, hh)
    value[support] = p
    if s is not None:
        sig_raw[support] = s
    sig_cal = sig_raw * model.calibration_c if model.calibration_c is not None else np.full(xx.shape, np.nan)
    conf = confidence_mask(sig_cal, cfg.mask.max_sigma_mgal) & support
    ds = xr.Dataset(
        {
            "value": (("y", "x"), value, {"units": "mGal", "long_name": "gridded anomaly"}),
            "sigma_raw": (
                ("y", "x"),
                sig_raw,
                {"units": "mGal", "long_name": "kriging standard deviation (raw)"},
            ),
            "sigma_cal": (
                ("y", "x"),
                sig_cal,
                {"units": "mGal", "long_name": "calibrated standard deviation"},
            ),
            "trend": (("y", "x"), trend, {"units": "mGal", "long_name": "regional polynomial trend"}),
            "support_mask": (("y", "x"), support.astype(np.uint8), {"long_name": "1 = supported by data"}),
            "confidence_mask": (
                ("y", "x"),
                conf.astype(np.uint8),
                {"long_name": "1 = calibrated sigma <= threshold"},
            ),
            "distance_m": (("y", "x"), dist, {"units": "m", "long_name": "distance to nearest station"}),
        },
        coords={"x": ("x", gx, {"units": "m", "axis": "X"}), "y": ("y", gy, {"units": "m", "axis": "Y"})},
        attrs={
            "crs": CRS_ANALYSIS,
            "cell_size_m": cfg.cell_size_m,
            "method": g.name,
            "calibration_c": model.calibration_c if model.calibration_c is not None else float("nan"),
            "Conventions": "CF-1.8",
        },
    )
    return ds


def mask_statistics(ds: xr.Dataset) -> dict[str, Any]:
    """Share of supported and confident cells (answers RQ3 / H3)."""
    n = int(ds["support_mask"].size)
    sup = int(ds["support_mask"].sum())
    conf = int(ds["confidence_mask"].sum())
    return {
        "n_cells": n,
        "supported_share": sup / n,
        "confident_share_of_bbox": conf / n,
        "confident_share_of_supported": conf / sup if sup else 0.0,
        "h3_supported": bool(conf / n < 0.5),
    }
