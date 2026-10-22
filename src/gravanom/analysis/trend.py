"""Polynomial trend (regional field) and regional/residual decomposition (OP-11, §5.5.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

F64 = NDArray[np.float64]

#: Coordinate scale of the design matrix [m] (keeps the normal equations well conditioned).
COORD_SCALE_M = 1e5


@dataclass
class PolynomialTrend:
    """OLS polynomial surface ``m(s) = sum beta_a s^a``, ``|a| <= degree``, in projected metres."""

    degree: int
    x0: float = 0.0
    y0: float = 0.0
    coef: F64 = field(default_factory=lambda: np.zeros(0))

    def design(self, x: F64, y: F64) -> F64:
        """Design matrix in centred coordinates scaled to units of 100 km."""
        xs = (np.asarray(x, float) - self.x0) / COORD_SCALE_M
        ys = (np.asarray(y, float) - self.y0) / COORD_SCALE_M
        cols = [np.ones_like(xs)]
        for d in range(1, self.degree + 1):
            for i in range(d + 1):
                cols.append(xs ** (d - i) * ys**i)
        return np.column_stack(cols)

    def fit(self, x: F64, y: F64, z: F64) -> PolynomialTrend:
        """Fit by ordinary least squares; returns ``self``."""
        self.x0, self.y0 = float(np.mean(x)), float(np.mean(y))
        self.coef, *_ = np.linalg.lstsq(self.design(x, y), np.asarray(z, float), rcond=None)
        return self

    def predict(self, x: F64, y: F64) -> F64:
        """Evaluate the trend surface [same units as z]."""
        return np.asarray(self.design(x, y) @ self.coef)


def decompose(x: F64, y: F64, z: F64, degree: int) -> dict[str, Any]:
    """Regional (polynomial trend) and residual components at the points.

    Returns
    -------
    dict
        ``regional`` and ``residual`` arrays, the fitted ``trend`` and the share of
        variance explained by the regional component.
    """
    z = np.asarray(z, float)
    tr = PolynomialTrend(degree).fit(x, y, z)
    reg = tr.predict(x, y)
    res = z - reg
    explained = 1.0 - float(np.var(res) / np.var(z)) if np.var(z) > 0 else 0.0
    return {"regional": reg, "residual": res, "trend": tr, "variance_explained": explained, "degree": degree}


def station_residual(x: F64, y: F64, z: F64, usable: NDArray[np.bool_], degree: int = 2) -> F64:
    """Residual ``z - regional`` at every station; the polynomial is fitted on ``usable`` finite points.

    Stations that are not usable (or have non-finite z) get NaN.
    """
    z = np.asarray(z, dtype=np.float64)
    ok = np.asarray(usable, dtype=bool) & np.isfinite(z)
    out = np.full(z.shape, np.nan)
    if ok.sum() > (degree + 1) * (degree + 2) // 2:
        tr = PolynomialTrend(degree).fit(np.asarray(x)[ok], np.asarray(y)[ok], z[ok])
        out[ok] = z[ok] - tr.predict(np.asarray(x)[ok], np.asarray(y)[ok])
    return out
