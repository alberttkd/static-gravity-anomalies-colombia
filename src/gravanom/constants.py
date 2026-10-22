"""Physical constants and reference-ellipsoid parameters.

All gravity quantities in this package are expressed in mGal (1 mGal = 1e-5 m s^-2).

References
----------
Moritz, H. (2000). Geodetic Reference System 1980. J. Geodesy 74, 128-133.
Tiesinga, E. et al. (2021). CODATA recommended values of the fundamental physical
    constants: 2018. Rev. Mod. Phys. 93, 025010.
Hinze, W. J. et al. (2005). New standards for reducing gravity data: The North
    American gravity database. Geophysics 70(4), J25-J32.
LaFehr, T. R. (1991). An exact solution for the gravity curvature (Bullard B)
    correction. Geophysics 56(8), 1179-1184.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: Newtonian constant of gravitation, CODATA 2018 [m^3 kg^-1 s^-2].
G: Final[float] = 6.67430e-11

#: 1 mGal expressed in SI units [m s^-2].
MGAL: Final[float] = 1e-5

#: Conversion factor from m s^-2 to mGal.
SI_TO_MGAL: Final[float] = 1e5

#: Standard Bouguer reduction density (Hinze, 2003; Hinze et al., 2005) [kg m^-3].
RHO_STANDARD_KG_M3: Final[float] = 2670.0

#: Mean Earth radius used by the spherical-cap formula (LaFehr, 1991a) [m].
CAP_EARTH_RADIUS_M: Final[float] = 6_371_000.0

#: Outer radius (arc length) of the Bullard B spherical cap, 1.4639 degrees [m].
CAP_RADIUS_M: Final[float] = 166_735.0


@dataclass(frozen=True)
class Ellipsoid:
    """Level-ellipsoid constants needed for normal gravity.

    Attributes
    ----------
    name : str
        Ellipsoid name.
    a_m : float
        Semi-major axis [m].
    f : float
        Flattening [-].
    gamma_e_mgal : float
        Normal gravity at the equator [mGal].
    k : float
        Somigliana constant ``k = (b gamma_p) / (a gamma_e) - 1`` [-].
    e2 : float
        First eccentricity squared [-].
    """

    name: str
    a_m: float
    f: float
    gamma_e_mgal: float
    k: float
    e2: float


#: Geodetic Reference System 1980 (Moritz, 2000).
GRS80: Final[Ellipsoid] = Ellipsoid(
    name="GRS80",
    a_m=6_378_137.0,
    f=0.003_352_810_681,
    gamma_e_mgal=978_032.677_15,
    k=0.001_931_851_353,
    e2=0.006_694_380_022_90,
)

#: EPSG code for storage coordinates (geographic, lon/lat order with always_xy).
CRS_STORAGE: Final[str] = "EPSG:4326"
#: EPSG code for analysis (MAGNA-SIRGAS 2018 / Origen-Nacional; IGAC Res. 471/2020).
CRS_ANALYSIS: Final[str] = "EPSG:9377"
#: EPSG code for web display.
CRS_WEB: Final[str] = "EPSG:3857"

#: Free-text vertical reference used until question Q3 is answered.
VERTICAL_REFERENCE: Final[str] = "height above mean sea level (assumed orthometric; datum unknown)"
