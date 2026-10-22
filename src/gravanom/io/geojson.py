"""GeoJSON serialization of stations (EPSG:4326)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FACT_COLUMNS = (
    "lon",
    "lat",
    "height_m",
    "g_obs_mgal",
    "tc_mgal",
    "tc_supplied_mgal",
    "n_merged",
    "g_obs_spread_mgal",
)


def _clean(v: Any) -> Any:
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return round(f, 6) if np.isfinite(f) else None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_clean(x) for x in v]
    return v


def stations_feature_collection(
    cat: pd.DataFrame,
    anomalies: pd.DataFrame | None = None,
    label: str = "",
    extra: dict[str, np.ndarray] | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """FeatureCollection of stations with principal facts, QC flags and reduction terms.

    ``fields`` restricts the property set (``station_uid`` and ``qc_flags`` are always kept).
    """
    an = anomalies.set_index("station_uid") if anomalies is not None else None
    feats = []
    for i, row in enumerate(cat.to_dict("records")):
        props: dict[str, Any] = {
            "station_uid": row["station_uid"],
            "qc_flags": list(row["qc_flags"]),
            "sources": list(row["sources"]),
        }
        for c in FACT_COLUMNS:
            props[c] = _clean(row[c])
        if an is not None and row["station_uid"] in an.index:
            for c, v in an.loc[row["station_uid"]].items():
                if c != "config_hash":
                    props[str(c)] = _clean(v)
        if extra:
            for k, arr in extra.items():
                props[k] = _clean(arr[i])
        if fields:
            props = {k: v for k, v in props.items() if k in fields or k in ("station_uid", "qc_flags")}
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(float(row["lon"]), 7), round(float(row["lat"]), 7)],
                },
                "properties": props,
            }
        )
    return {
        "type": "FeatureCollection",
        "features": feats,
        "properties": {"label": label, "crs": "EPSG:4326", "units": "mGal"},
    }
