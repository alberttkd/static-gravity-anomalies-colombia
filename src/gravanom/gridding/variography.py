"""Experimental variograms and weighted-least-squares Matérn fits (MASTER_GUIDE §5.5.5).

Only admissible (conditionally negative definite) models are allowed: the Matérn
family with nu in {0.5, 1.5, 2.5}. The Gaussian model is excluded (F-09; Stein, 1999).
The fit minimizes Cressie's (1985) criterion
:math:`\\sum_k N(h_k)\\,[\\hat\\gamma(h_k)/\\gamma(h_k;\\theta) - 1]^2`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

F64 = NDArray[np.float64]

#: Admissible Matérn smoothness values.
ALLOWED_NU: tuple[float, ...] = (0.5, 1.5, 2.5)


class VariogramFitError(RuntimeError):
    """No admissible variogram model could be fitted (API code VARIOGRAM_FIT_FAILED)."""


def matern_correlation(r: F64, length_m: float, nu: float) -> F64:
    r"""Matérn correlation with the :math:`\sqrt{2\nu}\,r/\ell` parameterization.

    Closed forms for nu = 0.5 (exponential), 1.5 and 2.5. Any other value, in
    particular a Gaussian model, raises ``ValueError``.
    """
    if nu not in ALLOWED_NU:
        raise ValueError(f"Matérn nu must be one of {ALLOWED_NU}; got {nu!r} (the Gaussian model is excluded)")
    s = np.sqrt(2.0 * nu) * np.asarray(r, dtype=np.float64) / length_m
    e = np.exp(-s)
    if nu == 0.5:
        return np.asarray(e)
    if nu == 1.5:
        return np.asarray((1.0 + s) * e)
    return np.asarray((1.0 + s + s**2 / 3.0) * e)


@dataclass(frozen=True)
class VariogramModel:
    """Fitted Matérn variogram: nugget tau^2, partial sill sigma^2, length scale l [m]."""

    nu: float
    nugget: float
    psill: float
    length_m: float

    def __post_init__(self) -> None:
        if self.nu not in ALLOWED_NU:
            raise ValueError(f"Matérn nu must be one of {ALLOWED_NU} (Gaussian excluded)")

    @property
    def sill(self) -> float:
        return self.nugget + self.psill

    def covariance(self, r: F64) -> F64:
        """Covariance of the continuous part, C(r) = sigma^2 rho(r) (nugget excluded)."""
        return np.asarray(self.psill * matern_correlation(r, self.length_m, self.nu))

    def gamma(self, r: F64) -> F64:
        """Semivariogram gamma(r) = tau^2 + sigma^2 - C(r) for r > 0; gamma(0) = 0."""
        r = np.asarray(r, dtype=np.float64)
        g = self.nugget + self.psill - self.covariance(r)
        return np.asarray(np.where(r > 0, g, 0.0))

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentalVariogram:
    """Binned Matheron semivariogram."""

    lag_m: F64
    gamma: F64
    n_pairs: F64
    direction_deg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "lag_m": self.lag_m.tolist(),
            "gamma_mgal2": self.gamma.tolist(),
            "n_pairs": self.n_pairs.astype(int).tolist(),
            "direction_deg": self.direction_deg,
        }


def experimental_variogram(
    x: F64,
    y: F64,
    z: F64,
    bin_m: float = 1500.0,
    max_lag_m: float = 30_000.0,
    direction_deg: float | None = None,
    tolerance_deg: float = 22.5,
) -> ExperimentalVariogram:
    """Matheron estimator on all point pairs up to ``max_lag_m``.

    Parameters
    ----------
    x, y : array_like
        Projected coordinates [m].
    z : array_like
        Values (e.g. trend residuals) [mGal].
    bin_m, max_lag_m : float
        Bin width and maximum lag [m].
    direction_deg : float, optional
        Azimuth (degrees clockwise from north, axial, 0-180) for a directional
        variogram, with angular tolerance ``tolerance_deg``.

    Returns
    -------
    ExperimentalVariogram
        Bin centres (mean pair distance per bin), gamma [mGal^2] and pair counts;
        empty bins are dropped.
    """
    x, y, z = (np.asarray(a, dtype=np.float64) for a in (x, y, z))
    i, j = np.triu_indices(len(x), k=1)
    dx, dy = x[j] - x[i], y[j] - y[i]
    d = np.hypot(dx, dy)
    keep = (d > 0) & (d <= max_lag_m)
    if direction_deg is not None:
        az = np.degrees(np.arctan2(dx, dy)) % 180.0
        diff = np.abs((az - direction_deg % 180.0 + 90.0) % 180.0 - 90.0)
        keep &= diff <= tolerance_deg
    d, sq = d[keep], 0.5 * (z[j[keep]] - z[i[keep]]) ** 2
    nb = int(np.ceil(max_lag_m / bin_m))
    k = np.minimum((d / bin_m).astype(np.int64), nb - 1)
    n = np.bincount(k, minlength=nb).astype(np.float64)
    g = np.bincount(k, weights=sq, minlength=nb)
    lag = np.bincount(k, weights=d, minlength=nb)
    ok = n > 0
    return ExperimentalVariogram(lag[ok] / n[ok], g[ok] / n[ok], n[ok], direction_deg)


def _wls_fit(
    ev: ExperimentalVariogram, nu: float, max_lag_m: float, fixed_nugget: float | None
) -> tuple[VariogramModel, float]:
    h, g, n = ev.lag_m, ev.gamma, ev.n_pairs
    gmax = float(g.max())
    lo_len, hi_len = max(float(h.min()) / 2.0, 100.0), 5.0 * max_lag_m

    def model(p: F64) -> VariogramModel:
        nug = fixed_nugget if fixed_nugget is not None else float(p[0])
        return VariogramModel(nu, nug, float(p[-2]), float(p[-1]))

    def resid(p: F64) -> F64:
        gm = model(p).gamma(h)
        return np.asarray(np.sqrt(n) * (g / np.maximum(gm, 1e-12) - 1.0))

    best: tuple[VariogramModel, float] | None = None
    for frac_len in (0.15, 0.4, 1.0):
        nug0 = 0.5 * float(g[0])
        p0 = [max(gmax - nug0, 1e-3), frac_len * max_lag_m]
        lb, ub = [1e-6, lo_len], [10.0 * gmax, hi_len]
        if fixed_nugget is None:
            p0, lb, ub = [nug0, *p0], [0.0, *lb], [2.0 * gmax, *ub]
        start = np.clip(p0, np.array(lb) + 1e-9, np.array(ub) - 1e-9)
        sol = least_squares(resid, start, bounds=(lb, ub), method="trf", x_scale="jac", max_nfev=2000)
        cost = float(np.sum(sol.fun**2))
        if sol.success and (best is None or cost < best[1]):
            best = (model(sol.x), cost)
    if best is None:
        raise VariogramFitError("least-squares variogram fit did not converge")
    m = best[0]
    if m.length_m >= 0.99 * hi_len:
        raise VariogramFitError(f"degenerate fit: length scale at upper bound ({m.length_m:.0f} m >> domain)")
    return best


def fit_variogram(
    x: F64,
    y: F64,
    z: F64,
    nu: float,
    bin_m: float = 1500.0,
    max_lag_m: float = 30_000.0,
) -> tuple[VariogramModel, dict[str, Any]]:
    """Fit a Matérn model with the fallback order of phase P5.

    Order: (1) as configured; (2) ``max_lag = 20 km``; (3) nugget fixed at half the
    first-bin gamma; (4) nu = 0.5. If all fail, :class:`VariogramFitError`.

    Returns
    -------
    model : VariogramModel
    info : dict
        Experimental variogram used, the fallback step reached and the WLS cost.
    """
    if nu not in ALLOWED_NU:
        raise ValueError(f"Matérn nu must be one of {ALLOWED_NU} (Gaussian excluded)")
    attempts: list[tuple[str, float, float, bool]] = [
        ("configured", nu, max_lag_m, False),
        ("max_lag_20km", nu, min(max_lag_m, 20_000.0), False),
        ("fixed_nugget", nu, min(max_lag_m, 20_000.0), True),
        ("nu_0.5", 0.5, min(max_lag_m, 20_000.0), True),
    ]
    errors: list[str] = []
    for step, nu_i, lag_i, fix in attempts:
        ev = experimental_variogram(x, y, z, bin_m, lag_i)
        if len(ev.lag_m) < 4:
            errors.append(f"{step}: fewer than 4 non-empty bins")
            continue
        try:
            model, cost = _wls_fit(ev, nu_i, lag_i, 0.5 * float(ev.gamma[0]) if fix else None)
        except VariogramFitError as exc:
            errors.append(f"{step}: {exc}")
            continue
        return model, {
            "fallback_step": step,
            "wls_cost": cost,
            "experimental": ev.to_dict(),
            "errors": errors,
        }
    raise VariogramFitError("; ".join(errors))


def directional_lengths(
    x: F64,
    y: F64,
    z: F64,
    model: VariogramModel,
    bin_m: float = 1500.0,
    max_lag_m: float = 30_000.0,
    directions_deg: tuple[float, ...] = (0.0, 45.0, 90.0, 135.0),
) -> dict[str, Any]:
    """Anisotropy test: refit the length scale per direction with nu, nugget and sill fixed.

    Returns the per-direction length scales, the minor/major ratio and the major-axis azimuth.
    """
    lengths: dict[float, float] = {}
    for az in directions_deg:
        ev = experimental_variogram(x, y, z, bin_m, max_lag_m, direction_deg=az)
        if len(ev.lag_m) < 4:
            continue

        def resid(p: F64, ev: ExperimentalVariogram = ev) -> F64:
            gm = VariogramModel(model.nu, model.nugget, model.psill, float(p[0])).gamma(ev.lag_m)
            return np.asarray(np.sqrt(ev.n_pairs) * (ev.gamma / np.maximum(gm, 1e-12) - 1.0))

        sol = least_squares(resid, [model.length_m], bounds=([100.0], [10.0 * max_lag_m]))
        lengths[az] = float(sol.x[0])
    if len(lengths) < 2:
        return {"lengths_m": {}, "ratio": None, "major_azimuth_deg": None}
    major = max(lengths, key=lambda a: lengths[a])
    return {
        "lengths_m": {f"{a:g}": v for a, v in lengths.items()},
        "ratio": min(lengths.values()) / max(lengths.values()),
        "major_azimuth_deg": major,
    }
