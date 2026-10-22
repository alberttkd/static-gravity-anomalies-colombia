"""Free-air, simple Bouguer and complete Bouguer anomalies (MASTER_GUIDE §5.5.2).

.. math::
    FAA &= g + g_H - \\gamma_0 + \\delta g_h + \\delta g_{atm}\\\\
    SBA &= FAA - BC_{slab}\\\\
    CBA &= FAA - BC_{cap} + TC_\\rho = SBA - BB + TC_\\rho
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gravanom.config import ReductionConfig
from gravanom.reduction.corrections import (
    atmospheric,
    bouguer_slab,
    height_correction,
    height_correction_legacy,
    honkasalo,
)
from gravanom.reduction.curvature import spherical_cap
from gravanom.reduction.legacy import compute_legacy
from gravanom.reduction.normal_gravity import normal_gravity_grs80

#: Output columns of :func:`compute_anomalies`, all in mGal.
TERM_COLUMNS = (
    "gamma0_mgal",
    "honkasalo_mgal",
    "atm_mgal",
    "height_corr_mgal",
    "bc_slab_mgal",
    "bc_cap_mgal",
    "bb_mgal",
    "tc_rho_mgal",
    "faa_mgal",
    "sba_mgal",
    "cba_mgal",
)


def compute_anomalies(stations: pd.DataFrame, config: ReductionConfig | None = None) -> pd.DataFrame:
    """Compute every reduction term and the three anomalies at the stations.

    Parameters
    ----------
    stations : DataFrame
        Canonical station table: ``lat`` [deg], ``height_m`` [m], ``g_obs_mgal``,
        ``tc_mgal`` (nullable; a null terrain correction gives a null CBA) and,
        for ``curvature="supplied_bb_legacy"`` or legacy mode, ``bb_supplied_mgal``.
    config : ReductionConfig, optional
        Reduction parameters; defaults to the standard configuration.

    Returns
    -------
    DataFrame
        The columns of :data:`TERM_COLUMNS` [mGal], same index as ``stations``.
        In legacy mode ``sba_mgal`` and ``cba_mgal`` hold the legacy ABS and ABT
        (both include the supplied BB) and the term columns hold the legacy terms.
    """
    cfg = config or ReductionConfig()
    if cfg.legacy_mode:
        return _legacy_terms(stations)

    lat = stations["lat"].to_numpy(dtype=np.float64)
    h = stations["height_m"].to_numpy(dtype=np.float64)
    g = stations["g_obs_mgal"].to_numpy(dtype=np.float64)
    tc = stations["tc_mgal"].to_numpy(dtype=np.float64, na_value=np.nan)
    rho = cfg.density_kg_m3

    gamma0 = normal_gravity_grs80(lat)
    g_h = honkasalo(lat) if cfg.honkasalo else np.zeros_like(lat)
    atm = atmospheric(h) if cfg.atmospheric else np.zeros_like(lat)
    if cfg.height_correction == "hinze2005_second_order":
        dgh = height_correction(lat, h)
    else:
        dgh = height_correction_legacy(h)
    slab = bouguer_slab(h, rho)
    if cfg.curvature == "lafehr1991_closed_form":
        cap = spherical_cap(h, rho)
    elif cfg.curvature == "supplied_bb_legacy":
        # The supplied values are "values to add" (BB_supplied = -BB), F-05.
        cap = slab - stations["bb_supplied_mgal"].to_numpy(dtype=np.float64)
    else:
        cap = slab.copy()
    tc_rho = tc * rho / cfg.terrain_reference_density_kg_m3

    faa = g + g_h - gamma0 + dgh + atm
    sba = faa - slab
    cba = faa - cap + tc_rho
    return pd.DataFrame(
        {
            "gamma0_mgal": gamma0,
            "honkasalo_mgal": g_h,
            "atm_mgal": atm,
            "height_corr_mgal": dgh,
            "bc_slab_mgal": slab,
            "bc_cap_mgal": cap,
            "bb_mgal": cap - slab,
            "tc_rho_mgal": tc_rho,
            "faa_mgal": faa,
            "sba_mgal": sba,
            "cba_mgal": cba,
        },
        index=stations.index,
    )


def _legacy_terms(stations: pd.DataFrame) -> pd.DataFrame:
    leg = compute_legacy(stations)
    return pd.DataFrame(
        {
            "gamma0_mgal": leg["gtn"],
            "honkasalo_mgal": leg["clat"],
            "atm_mgal": leg["catm"],
            "height_corr_mgal": leg["cal"],
            "bc_slab_mgal": -leg["ccb"],
            "bc_cap_mgal": -leg["ccb"] - stations["bb_supplied_mgal"].astype(float),
            "bb_mgal": -stations["bb_supplied_mgal"].astype(float),
            "tc_rho_mgal": stations["tc_mgal"].astype(float),
            "faa_mgal": leg["aaa"],
            "sba_mgal": leg["abs"],
            "cba_mgal": leg["abt"],
        },
        index=stations.index,
    )


def anomaly_column(target: str) -> str:
    """Map a target name (FAA, SBA, CBA) to its anomaly column."""
    mapping = {"FAA": "faa_mgal", "SBA": "sba_mgal", "CBA": "cba_mgal"}
    if target not in mapping:
        raise ValueError(f"unknown anomaly target {target!r}")
    return mapping[target]
