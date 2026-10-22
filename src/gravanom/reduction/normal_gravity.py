"""Normal gravity on the reference ellipsoid."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from gravanom.constants import GRS80, Ellipsoid


def normal_gravity_grs80(lat_deg: ArrayLike, ellipsoid: Ellipsoid = GRS80) -> NDArray[np.float64]:
    r"""Normal gravity on the ellipsoid, Somigliana closed form.

    .. math:: \gamma_0(\varphi)=\gamma_e\,\frac{1+k\sin^2\varphi}{\sqrt{1-e^2\sin^2\varphi}}

    Parameters
    ----------
    lat_deg : array_like
        Geodetic latitude [degree].
    ellipsoid : Ellipsoid
        Level ellipsoid (default GRS80).

    Returns
    -------
    ndarray
        Normal gravity on the ellipsoid surface [mGal].

    References
    ----------
    Moritz (2000); Hinze et al. (2005), Eq. 2.
    """
    s2 = np.sin(np.radians(np.asarray(lat_deg, dtype=np.float64))) ** 2
    return np.asarray(
        ellipsoid.gamma_e_mgal * (1.0 + ellipsoid.k * s2) / np.sqrt(1.0 - ellipsoid.e2 * s2),
        dtype=np.float64,
    )


def normal_gravity_legacy(lat_deg: ArrayLike) -> NDArray[np.float64]:
    """Normal gravity with the coefficients of the legacy spreadsheets (App. B.2, column H).

    Numerically GRS80 to within 2e-5 mGal; used only in legacy mode.
    """
    s2 = np.sin(np.radians(np.asarray(lat_deg, dtype=np.float64))) ** 2
    return np.asarray(
        978032.67714 * ((1 + 0.00193185138639 * s2) / np.sqrt(1 - 0.00669437999013 * s2)),
        dtype=np.float64,
    )
