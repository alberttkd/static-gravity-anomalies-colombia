"""Harmonization of one or more source record tables into one station catalogue (OP-02).

1. Records sharing an id across sources are compared within the QC-03 tolerances.
   Consistent pairs collapse into one record; inconsistent ones are kept apart and
   flagged ``CONFLICT_SHARED_ID``.
2. Records at (near-)identical positions (< 1 m, QC-04) are merged: mean g, H and
   TC, member ids kept, and the g spread recorded as precision evidence.

Nothing is deleted; every original row stays traceable through ``prov_*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from gravanom.crs import to_analysis
from gravanom.flags import QCFlag
from gravanom.io.schema import STATION_COLUMNS, coerce_records


@dataclass(frozen=True)
class Tolerances:
    """Shared-id agreement tolerances (QC-03) and duplicate radii (QC-04)."""

    lonlat_deg: float = 1e-6
    height_m: float = 0.01
    g_mgal: float = 0.01
    tc_mgal: float = 1e-4
    merge_radius_m: float = 1.0
    near_radius_m: float = 25.0


def _union_find(n: int, pairs: np.ndarray) -> np.ndarray:
    parent = np.arange(n)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return int(i)

    for a, b in pairs:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return np.array([find(i) for i in range(n)])


def _resolve_shared_ids(rec: pd.DataFrame, tol: Tolerances) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Collapse consistent shared-id records; flag conflicting ones."""
    rec = rec.copy()
    rec["uid"] = rec["source"] + ":" + rec["source_id"]
    rec["member_uids"] = [[u] for u in rec["uid"]]
    rec["member_sources"] = [[s] for s in rec["source"]]
    rec["flags"] = [[] for _ in range(len(rec))]
    for col in ("prov_file", "prov_sheet", "prov_row"):
        rec[col] = pd.Series([[v] for v in rec[col].tolist()], index=rec.index, dtype=object)
    counts = rec.groupby("source_id")["source"].nunique()
    shared = sorted(counts.index[counts > 1])
    drop: list[int] = []
    conflicts: list[str] = []
    maxdiff = {"lon_lat_deg": 0.0, "height_m": 0.0, "g_mgal": 0.0, "tc_mgal": 0.0}
    for sid in shared:
        idx = rec.index[rec["source_id"] == sid].tolist()
        first = rec.loc[idx[0]]
        ok = True
        for j in idx[1:]:
            other = rec.loc[j]
            d = {
                "lon_lat_deg": max(abs(first.lon - other.lon), abs(first.lat - other.lat)),
                "height_m": abs(first.height_m - other.height_m),
                "g_mgal": abs(first.g_obs_mgal - other.g_obs_mgal),
                "tc_mgal": abs(first.tc_mgal - other.tc_mgal),
            }
            for k, v in d.items():
                if np.isfinite(v):
                    maxdiff[k] = max(maxdiff[k], float(v))
            ok &= (
                d["lon_lat_deg"] <= tol.lonlat_deg
                and d["height_m"] <= tol.height_m
                and d["g_mgal"] <= tol.g_mgal
                and (not np.isfinite(d["tc_mgal"]) or d["tc_mgal"] <= tol.tc_mgal)
            )
        if ok:
            rec.at[idx[0], "member_uids"] = cast(Any, [rec.at[i, "uid"] for i in idx])
            rec.at[idx[0], "member_sources"] = cast(Any, [rec.at[i, "source"] for i in idx])
            for col in ("prov_file", "prov_sheet", "prov_row"):
                rec.at[idx[0], col] = cast(Any, [v for i in idx for v in cast(list[Any], rec.at[i, col])])
            drop.extend(idx[1:])
        else:
            conflicts.append(sid)
            for i in idx:
                rec.at[i, "flags"] = cast(Any, [QCFlag.CONFLICT_SHARED_ID.value])
    out = rec.drop(index=drop).reset_index(drop=True)
    log = {
        "n_shared_ids": len(shared),
        "n_shared_consistent": len(shared) - len(conflicts),
        "shared_id_conflicts": conflicts,
        "shared_id_max_abs_diff": maxdiff,
        "n_records_after_id_union": len(out),
    }
    return out, log


def harmonize(
    record_tables: list[pd.DataFrame], tolerances: Tolerances | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Merge per-source record tables into one catalogue (one row per position).

    Parameters
    ----------
    record_tables : list of DataFrame
        Tables in the record schema (:data:`gravanom.io.schema.RECORD_COLUMNS`). The
        first table wins when shared ids are collapsed.
    tolerances : Tolerances, optional
        QC-03/QC-04 tolerances.

    Returns
    -------
    catalogue : DataFrame
        Columns :data:`gravanom.io.schema.STATION_COLUMNS`.
    log : dict
        Harmonization log (counts, conflicts, merged groups, near duplicates).
    """
    tol = tolerances or Tolerances()
    rec = pd.concat([coerce_records(t) for t in record_tables], ignore_index=True)
    log: dict[str, Any] = {
        "n_records_in": len(rec),
        "records_per_source": {str(k): int(v) for k, v in rec["source"].value_counts().sort_index().items()},
    }
    rec, id_log = _resolve_shared_ids(rec, tol)
    log.update(id_log)

    finite = np.isfinite(rec["lon"].to_numpy()) & np.isfinite(rec["lat"].to_numpy())
    x = np.full(len(rec), np.nan)
    y = np.full(len(rec), np.nan)
    x[finite], y[finite] = to_analysis(rec.loc[finite, "lon"], rec.loc[finite, "lat"])
    rec["x_9377"], rec["y_9377"] = x, y

    conflict = np.array([QCFlag.CONFLICT_SHARED_ID.value in f for f in rec["flags"]])
    mergeable = np.flatnonzero(finite & ~conflict)
    tree = cKDTree(np.column_stack([x[mergeable], y[mergeable]]))
    pairs = tree.query_pairs(tol.merge_radius_m, output_type="ndarray")
    near = tree.query_pairs(tol.near_radius_m, output_type="ndarray")
    roots = np.arange(len(rec))
    if len(pairs):
        roots[mergeable] = mergeable[_union_find(len(mergeable), pairs)]

    rows: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for root in pd.unique(roots):
        members = np.flatnonzero(roots == root)
        sub = rec.iloc[members]
        first = sub.iloc[0]
        flags = sorted({f for fl in sub["flags"] for f in fl})
        uids = [u for mu in sub["member_uids"] for u in mu]
        row: dict[str, Any] = {
            "station_uid": first["uid"],
            "source_ids": uids,
            "sources": sorted({s for ms in sub["member_sources"] for s in ms}),
            "lon": float(first["lon"]),
            "lat": float(first["lat"]),
            "x_9377": float(first["x_9377"]),
            "y_9377": float(first["y_9377"]),
            "height_m": float(sub["height_m"].mean()),
            "g_obs_mgal": float(sub["g_obs_mgal"].mean()),
            "tc_supplied_mgal": float(sub["tc_mgal"].mean()) if sub["tc_mgal"].notna().any() else np.nan,
            "bb_supplied_mgal": float(sub["bb_supplied_mgal"].mean()) if sub["bb_supplied_mgal"].notna().any() else np.nan,
            "n_merged": len(members),
            "g_obs_spread_mgal": float(sub["g_obs_mgal"].max() - sub["g_obs_mgal"].min()),
            "prov_file": [v for pv in sub["prov_file"] for v in pv],
            "prov_sheet": [v for pv in sub["prov_sheet"] for v in pv],
            "prov_row": [int(v) for pv in sub["prov_row"] for v in pv],
        }
        if len(members) > 1:
            row["station_uid"] = "merged:" + "+".join(sub["uid"])
            flags = sorted({*flags, QCFlag.DUPLICATE_POSITION.value})
            groups.append(
                {
                    "station_uid": row["station_uid"],
                    "members": uids,
                    "g_spread_mgal": row["g_obs_spread_mgal"],
                    "height_spread_m": float(sub["height_m"].max() - sub["height_m"].min()),
                }
            )
        row["qc_flags"] = flags
        rows.append(row)
    cat = pd.DataFrame(rows)
    cat["tc_mgal"] = cat["tc_supplied_mgal"]
    cat = cat.loc[:, list(STATION_COLUMNS)]

    spreads = np.array([g["g_spread_mgal"] for g in groups]) if groups else np.array([])
    log.update(
        {
            "n_positions": len(cat),
            "n_merged_groups": len(groups),
            "n_groups_g_spread_gt_0p1": int((spreads > 0.1).sum()),
            "merged_groups": groups,
            "n_near_duplicate_pairs_lt_25m": int(len(near) - len(pairs)),
            "repeat_precision_sigma_g_mgal": float(np.sqrt(np.mean(spreads**2 / 2))) if spreads.size else None,
        }
    )
    return cat, log
