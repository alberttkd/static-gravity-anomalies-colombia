"""Legacy mode: the legacy spreadsheet formulas reproduced exactly (MASTER_GUIDE App. B.2).

Only for audit and reproduction. The legacy "ABS" includes the supplied BB, i.e.
it equals SBA - BB in the standard definitions; "ABT" adds the supplied CT.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gravanom.reduction.normal_gravity import normal_gravity_legacy

#: Gravitational constant typed into the legacy spreadsheets (cell K2 / R5).
G_LEGACY = 6.6743 * 10**-11
#: Slab density hard-coded in the legacy formulas (F-02).
RHO_LEGACY_KG_M3 = 2300.0


def compute_legacy(stations: pd.DataFrame) -> pd.DataFrame:
    """Recompute AAA, ABS and ABT with the legacy formulas.

    Parameters
    ----------
    stations : DataFrame
        Needs ``lat``, ``height_m``, ``g_obs_mgal``, ``bb_supplied_mgal`` and ``tc_mgal``.

    Returns
    -------
    DataFrame
        Columns ``gtn``, ``clat``, ``catm``, ``ccb``, ``cal``, ``aaa``, ``abs``, ``abt``
        [mGal], same index as ``stations``.
    """
    lat = stations["lat"].to_numpy(dtype=np.float64)
    h = stations["height_m"].to_numpy(dtype=np.float64)
    g = stations["g_obs_mgal"].to_numpy(dtype=np.float64)
    bb = stations["bb_supplied_mgal"].to_numpy(dtype=np.float64)
    tc = stations["tc_mgal"].to_numpy(dtype=np.float64)
    s = np.sin(np.radians(lat))
    gtn = normal_gravity_legacy(lat)
    clat = 0.0371 * (1 - 3 * s**2)
    catm = 0.874 - (9.9 * 10**-5) * h + (3.56 * 10**-9) * h**2
    ccb = -2 * np.pi * G_LEGACY * RHO_LEGACY_KG_M3 * h * 100000
    cal = 0.3086 * h - 0.073 * (h / 1000) ** 2
    aaa = g + clat + catm + cal - gtn
    abs_ = g + clat + catm + cal + ccb + bb - gtn
    abt = g + clat + catm + cal + ccb + bb + tc - gtn
    return pd.DataFrame(
        {"gtn": gtn, "clat": clat, "catm": catm, "ccb": ccb, "cal": cal, "aaa": aaa, "abs": abs_, "abt": abt},
        index=stations.index,
    )
