"""Gridders with a common interface: ``fit(x, y, z, h)`` and ``predict(x, y, h)``.

* :class:`RegressionKriging` (primary, §5.5.5): OLS polynomial trend + simple kriging
  of the residuals with a WLS-fitted Matérn covariance; returns the kriging σ.
* :class:`EqSGridder`: Harmonica equivalent sources at constant relative depth.
* :class:`IDWGridder` and :class:`SplineGridder`: baselines (no uncertainty).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import harmonica as hm
import numpy as np
import verde as vd
from numpy.typing import NDArray
from scipy.linalg import cho_factor, cho_solve, solve_triangular
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist

from gravanom.analysis.trend import PolynomialTrend
from gravanom.gridding.variography import VariogramModel, fit_variogram

F64 = NDArray[np.float64]


class Gridder(Protocol):
    """Interface shared by all gridders."""

    name: str

    def fit(self, x: F64, y: F64, z: F64, h: F64) -> Gridder: ...

    def predict(self, x: F64, y: F64, h: F64) -> tuple[F64, F64 | None]: ...

    def params(self) -> dict[str, Any]: ...


def _anisotropic_coords(x: F64, y: F64, aniso: tuple[float, float] | None) -> tuple[F64, F64]:
    """Map coordinates so that geometric anisotropy becomes isotropy.

    ``aniso = (azimuth_deg, ratio)``: azimuth of the major axis clockwise from north,
    and the minor/major ratio of length scales.
    """
    if aniso is None:
        return np.asarray(x, float), np.asarray(y, float)
    az, ratio = np.radians(aniso[0]), aniso[1]
    a = x * np.sin(az) + y * np.cos(az)
    b = (x * np.cos(az) - y * np.sin(az)) / ratio
    return np.asarray(a), np.asarray(b)


@dataclass
class RegressionKriging:
    """Trend (OLS, degree 0-2) plus simple kriging of residuals (Matérn covariance).

    With the trend estimated by GLS this would be universal kriging; OLS is the
    accepted MVP simplification (§5.5.5). The kriging variance ignores trend
    uncertainty and is therefore calibrated by block CV.
    """

    trend_degree: int = 2
    nu: float = 1.5
    bin_m: float = 1500.0
    max_lag_m: float = 30_000.0
    anisotropy: tuple[float, float] | None = None
    model: VariogramModel | None = None
    """Fixed variogram model; when None it is fitted to the training residuals."""
    name: str = "rk_matern"
    fit_info: dict[str, Any] = field(default_factory=dict)
    _trend: PolynomialTrend | None = None
    _xy: F64 | None = None
    _chol: Any = None
    _alpha: F64 | None = None
    _fitted_model: VariogramModel | None = None

    def fit(self, x: F64, y: F64, z: F64, h: F64 | None = None) -> RegressionKriging:
        self._trend = PolynomialTrend(self.trend_degree).fit(x, y, z)
        r = np.asarray(z, float) - self._trend.predict(x, y)
        ax, ay = _anisotropic_coords(x, y, self.anisotropy)
        if self.model is None:
            model, info = fit_variogram(ax, ay, r, self.nu, self.bin_m, self.max_lag_m)
            self.fit_info = {k: v for k, v in info.items() if k != "experimental"}
            self.fit_info["experimental"] = info["experimental"]
        else:
            model = self.model
        self._fitted_model = model
        self._xy = np.column_stack([ax, ay])
        k = model.covariance(cdist(self._xy, self._xy)) + np.eye(len(r)) * max(model.nugget, 1e-6 * model.psill)
        self._chol = cho_factor(k, lower=True)
        self._alpha = cho_solve(self._chol, r)
        return self

    @property
    def variogram(self) -> VariogramModel:
        if self._fitted_model is None:
            raise RuntimeError("not fitted")
        return self._fitted_model

    def predict(
        self,
        x: F64,
        y: F64,
        h: F64 | None = None,
        include_nugget: bool = True,
        chunk: int = 4000,
        return_std: bool = True,
    ) -> tuple[F64, F64]:
        """Prediction and kriging σ [mGal].

        ``include_nugget=True`` gives the σ of a new *observation* (used in CV);
        ``False`` gives the σ of the continuous field. With ``return_std=False`` the
        σ array is NaN and the O(n^2) variance solve is skipped.
        """
        if self._trend is None or self._xy is None or self._alpha is None:
            raise RuntimeError("not fitted")
        m = self.variogram
        ax, ay = _anisotropic_coords(np.asarray(x, float), np.asarray(y, float), self.anisotropy)
        pts = np.column_stack([ax, ay])
        mean = np.empty(len(pts))
        var = np.empty(len(pts))
        lower = self._chol[0]
        for s in range(0, len(pts), chunk):
            kk = m.covariance(cdist(self._xy, pts[s : s + chunk]))
            mean[s : s + chunk] = kk.T @ self._alpha
            if not return_std:
                var[s : s + chunk] = np.nan
                continue
            v = solve_triangular(lower, kk, lower=True, check_finite=False)
            var[s : s + chunk] = m.psill - np.einsum("ij,ij->j", v, v)
        mean += self._trend.predict(x, y)
        var = np.maximum(var, 0.0) + (m.nugget if include_nugget else 0.0)
        return mean, np.sqrt(var)

    def trend_at(self, x: F64, y: F64) -> F64:
        if self._trend is None:
            raise RuntimeError("not fitted")
        return self._trend.predict(x, y)

    def params(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "method": self.name,
            "trend_degree": self.trend_degree,
            "nu": self.nu,
            "anisotropy": list(self.anisotropy) if self.anisotropy else None,
        }
        if self._fitted_model is not None:
            out["variogram"] = self._fitted_model.to_dict()
        if self.fit_info:
            out["fallback_step"] = self.fit_info.get("fallback_step")
        return out


@dataclass
class EqSGridder:
    """Equivalent sources (Harmonica) at constant relative depth below the data."""

    depth_m: float = 14_000.0
    damping: float = 0.01
    name: str = "eqs"
    _eqs: Any = None

    def fit(self, x: F64, y: F64, z: F64, h: F64) -> EqSGridder:
        self._eqs = hm.EquivalentSources(damping=self.damping, depth=self.depth_m)
        self._eqs.fit((np.asarray(x), np.asarray(y), np.asarray(h)), np.asarray(z))
        return self

    def predict(self, x: F64, y: F64, h: F64) -> tuple[F64, None]:
        return np.asarray(self._eqs.predict((np.asarray(x), np.asarray(y), np.asarray(h)))), None

    def params(self) -> dict[str, Any]:
        return {"method": self.name, "depth_m": self.depth_m, "damping": self.damping}


@dataclass
class IDWGridder:
    """Inverse-distance weighting (legacy configuration: p = 2, 12 neighbours)."""

    power: float = 2.0
    k: int = 12
    name: str = "idw"
    _tree: Any = None
    _z: F64 | None = None

    def fit(self, x: F64, y: F64, z: F64, h: F64 | None = None) -> IDWGridder:
        self._tree = cKDTree(np.column_stack([x, y]))
        self._z = np.asarray(z, float)
        return self

    def predict(self, x: F64, y: F64, h: F64 | None = None) -> tuple[F64, None]:
        if self._z is None:
            raise RuntimeError("not fitted")
        k = min(self.k, len(self._z))
        d, i = self._tree.query(np.column_stack([x, y]), k=k)
        d, i = np.atleast_2d(d), np.atleast_2d(i)
        w = 1.0 / np.maximum(d, 1e-9) ** self.power
        return np.asarray((w * self._z[i]).sum(axis=1) / w.sum(axis=1)), None

    def params(self) -> dict[str, Any]:
        return {"method": self.name, "power": self.power, "k": self.k}


@dataclass
class SplineGridder:
    """Linear trend plus Verde biharmonic spline (benchmark)."""

    damping: float | None = 1e-8
    name: str = "spline"
    _chain: Any = None

    def fit(self, x: F64, y: F64, z: F64, h: F64 | None = None) -> SplineGridder:
        self._chain = vd.Chain([("trend", vd.Trend(degree=1)), ("spline", vd.Spline(damping=self.damping))])
        self._chain.fit((np.asarray(x), np.asarray(y)), np.asarray(z))
        return self

    def predict(self, x: F64, y: F64, h: F64 | None = None) -> tuple[F64, None]:
        return np.asarray(self._chain.predict((np.asarray(x), np.asarray(y)))), None

    def params(self) -> dict[str, Any]:
        return {"method": self.name, "trend_degree": 1, "damping": self.damping}
