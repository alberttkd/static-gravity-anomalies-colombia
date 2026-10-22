"""Station corrections, expressed as values *added* to the observed-gravity side.

Every anomaly then has the form ``g + sum(corrections) - gamma_0`` (§5.5.1).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from gravanom.constants import SI_TO_MGAL, G

F64 = NDArray[np.float64]


def _f64(x: ArrayLike) -> F64:
    return np.asarray(x, dtype=np.float64)


def honkasalo(lat_deg: ArrayLike) -> F64:
    r"""Honkasalo (permanent-tide) term for IGSN71 data.

    .. math:: g_H = 0.0371\,(1-3\sin^2\varphi)

    Added to IGSN71 observed gravity to undo the permanent-tide correction. It is
    *not* a latitude correction (legacy label "corrección por latitud", F-03).

    Parameters
    ----------
    lat_deg : array_like
        Geodetic latitude [degree].

    Returns
    -------
    ndarray
        Term to add to observed gravity [mGal]; zero at ``sin^2(phi) = 1/3``.

    References
    ----------
    Hinze et al. (2005).
    """
    return 0.0371 * (1.0 - 3.0 * np.sin(np.radians(_f64(lat_deg))) ** 2)


def atmospheric(height_m: ArrayLike) -> F64:
    r"""Atmospheric correction.

    .. math:: \delta g_{atm} = 0.874 - 9.9\times10^{-5}h + 3.56\times10^{-9}h^2

    Parameters
    ----------
    height_m : array_like
        Station height [m]; valid up to 10 km.

    Returns
    -------
    ndarray
        Correction added to the anomaly (subtracted from normal gravity) [mGal].

    References
    ----------
    Hinze et al. (2005), Eq. 3.
    """
    h = _f64(height_m)
    return 0.874 - 9.9e-5 * h + 3.56e-9 * h**2


def height_correction(lat_deg: ArrayLike, height_m: ArrayLike) -> F64:
    r"""Second-order (free-air) height correction for GRS80.

    .. math:: \delta g_h = (0.3087691-0.0004398\sin^2\varphi)\,h-7.2125\times10^{-8}h^2

    Positive upward heights give a positive value: normal gravity decreases with
    height, so the correction is added to the observed side.

    Parameters
    ----------
    lat_deg : array_like
        Geodetic latitude [degree].
    height_m : array_like
        Station height [m].

    Returns
    -------
    ndarray
        Height correction [mGal].

    References
    ----------
    Hinze et al. (2005), Eq. 5.
    """
    s2 = np.sin(np.radians(_f64(lat_deg))) ** 2
    h = _f64(height_m)
    return (0.3087691 - 0.0004398 * s2) * h - 7.2125e-8 * h**2


def height_correction_legacy(height_m: ArrayLike) -> F64:
    r"""Legacy free-air correction of the legacy spreadsheets (App. B.2, column M).

    .. math:: \delta g_h = 0.3086\,h - 0.073\,(h/1000)^2
    """
    h = _f64(height_m)
    return 0.3086 * h - 0.073 * (h / 1000.0) ** 2


def bouguer_slab(height_m: ArrayLike, density_kg_m3: float | ArrayLike) -> F64:
    r"""Attraction of an infinite horizontal slab (Bullard A).

    .. math:: BC_{slab} = 2\pi G\rho h

    Parameters
    ----------
    height_m : array_like
        Slab thickness = station height [m].
    density_kg_m3 : float or array_like
        Reduction density [kg m^-3].

    Returns
    -------
    ndarray
        Slab attraction [mGal]; *subtracted* from the free-air anomaly.
        0.11197 mGal/m for 2670 kg m^-3.

    References
    ----------
    Hinze et al. (2005), Eq. 6.
    """
    return 2.0 * np.pi * G * _f64(density_kg_m3) * _f64(height_m) * SI_TO_MGAL
