"""Spherical-cap Bouguer correction and the curvature (Bullard B) term."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from gravanom.constants import CAP_EARTH_RADIUS_M, CAP_RADIUS_M, SI_TO_MGAL, G
from gravanom.reduction.corrections import bouguer_slab

F64 = NDArray[np.float64]


def spherical_cap(
    height_m: ArrayLike,
    density_kg_m3: float | ArrayLike,
    earth_radius_m: float = CAP_EARTH_RADIUS_M,
    cap_radius_m: float = CAP_RADIUS_M,
) -> F64:
    r"""Attraction of a spherical cap of thickness h and arc radius S (Bullard A+B).

    Closed form of LaFehr (1991a), with the figure-scale erratum (1992):

    .. math::
        BC_{cap} = 2\pi G\rho\,[(1+\mu)h - \lambda R],\qquad R = R_0 + h,

    where :math:`\mu = \eta^2/3 - \eta`, :math:`\eta = h/R`, and :math:`\lambda` is
    the closed-form function of :math:`\alpha = S/R_0` and :math:`\delta = R_0/R`
    given in MASTER_GUIDE App. A.3.

    Parameters
    ----------
    height_m : array_like
        Station height [m]; must exceed -500 m.
    density_kg_m3 : float or array_like
        Reduction density [kg m^-3].
    earth_radius_m : float
        Mean Earth radius R0 [m].
    cap_radius_m : float
        Arc radius S of the cap [m] (166.735 km).

    Returns
    -------
    ndarray
        Cap attraction [mGal]; *subtracted* from the free-air anomaly.

    References
    ----------
    LaFehr (1991a); Hinze et al. (2005), Eq. 7.
    """
    h = np.asarray(height_m, dtype=np.float64)
    if np.any(h <= -500.0):
        raise ValueError("spherical_cap requires heights > -500 m")
    alpha = cap_radius_m / earth_radius_m
    r = earth_radius_m + h
    delta = earth_radius_m / r
    eta = h / r
    mu = eta**2 / 3.0 - eta
    cos_a, sin_a, sin_h = np.cos(alpha), np.sin(alpha), np.sin(alpha / 2.0)
    d = 3.0 * cos_a**2 - 2.0
    f = cos_a
    k = sin_a**2
    p = -6.0 * cos_a**2 * sin_h + 4.0 * sin_h**3
    m = -3.0 * sin_a**2 * cos_a
    n = 2.0 * (sin_h - sin_h**2)
    root = np.sqrt((f - delta) ** 2 + k)
    lam = ((d + f * delta + delta**2) * root + p + m * np.log(n / (f - delta + root))) / 3.0
    rho = np.asarray(density_kg_m3, dtype=np.float64)
    return np.asarray(2.0 * np.pi * G * rho * ((1.0 + mu) * h - lam * r) * SI_TO_MGAL, dtype=np.float64)


def curvature_bb(height_m: ArrayLike, density_kg_m3: float | ArrayLike) -> F64:
    r"""Curvature (Bullard B) term :math:`BB = BC_{cap} - BC_{slab}`.

    Positive for heights below about 4.15 km, so it *reduces* the Bouguer anomaly.

    Returns
    -------
    ndarray
        BB [mGal].
    """
    return spherical_cap(height_m, density_kg_m3) - bouguer_slab(height_m, density_kg_m3)


def bb_cubic_approximation(height_m: ArrayLike) -> F64:
    r"""Cubic approximation of BB for 2670 kg m^-3 (Whitman, 1991 style).

    .. math:: BB \approx 1.464\times10^{-3}h - 3.533\times10^{-7}h^2 + 4.5\times10^{-14}h^3
    """
    h = np.asarray(height_m, dtype=np.float64)
    return 1.464e-3 * h - 3.533e-7 * h**2 + 4.5e-14 * h**3
