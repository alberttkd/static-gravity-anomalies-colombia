"""Canonical station schemas (MASTER_GUIDE §6.5) and their validation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gravanom.flags import QCFlag

#: Columns of a per-source record table (output of the readers, input to harmonization).
RECORD_COLUMNS: dict[str, str] = {
    "source": "str",
    "source_id": "str",
    "lon": "float64",
    "lat": "float64",
    "height_m": "float64",
    "g_obs_mgal": "float64",
    "tc_mgal": "float64",
    "bb_supplied_mgal": "float64",
    "prov_file": "str",
    "prov_sheet": "str",
    "prov_row": "int64",
}

#: Required (non-null) principal facts.
REQUIRED_FACTS = ("lon", "lat", "height_m", "g_obs_mgal")

#: Columns of the canonical station catalogue (one row per position).
STATION_COLUMNS: tuple[str, ...] = (
    "station_uid",
    "source_ids",
    "sources",
    "lon",
    "lat",
    "x_9377",
    "y_9377",
    "height_m",
    "g_obs_mgal",
    "tc_mgal",
    "tc_supplied_mgal",
    "bb_supplied_mgal",
    "n_merged",
    "g_obs_spread_mgal",
    "qc_flags",
    "prov_file",
    "prov_sheet",
    "prov_row",
)


class SchemaError(ValueError):
    """Raised when a table does not conform to its schema."""


@dataclass(frozen=True)
class SchemaIssue:
    """One schema problem: a missing column or a row with an invalid value."""

    column: str
    message: str
    rows: tuple[int, ...] = ()


def validate_records(df: pd.DataFrame) -> list[SchemaIssue]:
    """Check a per-source record table against :data:`RECORD_COLUMNS`.

    Returns a list of issues; an empty list means valid. Missing columns are
    reported once; null or non-finite principal facts are reported per row.
    """
    issues: list[SchemaIssue] = []
    missing = [c for c in RECORD_COLUMNS if c not in df.columns]
    for col in missing:
        issues.append(SchemaIssue(col, "missing column"))
    if missing:
        return issues
    for col in REQUIRED_FACTS:
        vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
        bad = np.flatnonzero(~np.isfinite(vals))
        if bad.size:
            issues.append(SchemaIssue(col, "null or non-numeric value", tuple(int(i) for i in bad)))
    if df["source_id"].isna().any():
        issues.append(SchemaIssue("source_id", "null id", tuple(np.flatnonzero(df["source_id"].isna()))))
    dup = df.duplicated(subset=["source", "source_id"], keep=False)
    if dup.any():
        issues.append(SchemaIssue("source_id", "id not unique within source", tuple(np.flatnonzero(dup))))
    return issues


def coerce_records(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with the dtypes of :data:`RECORD_COLUMNS` (numeric coercion to NaN)."""
    issues = [i for i in validate_records(df) if i.message == "missing column"]
    if issues:
        raise SchemaError("; ".join(f"{i.column}: {i.message}" for i in issues))
    out = df.loc[:, list(RECORD_COLUMNS)].copy()
    for col, dtype in RECORD_COLUMNS.items():
        if dtype == "float64":
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
        elif dtype == "int64":
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(-1).astype("int64")
        else:
            out[col] = out[col].astype(str)
    return out.reset_index(drop=True)


def validate_stations(df: pd.DataFrame) -> list[SchemaIssue]:
    """Check a station catalogue against :data:`STATION_COLUMNS` and the flag vocabulary."""
    issues = [SchemaIssue(c, "missing column") for c in STATION_COLUMNS if c not in df.columns]
    if issues:
        return issues
    if df["station_uid"].duplicated().any():
        issues.append(SchemaIssue("station_uid", "not unique"))
    allowed = {f.value for f in QCFlag}
    bad_rows = [i for i, flags in enumerate(df["qc_flags"]) if not set(flags) <= allowed]
    if bad_rows:
        issues.append(SchemaIssue("qc_flags", "unknown flag", tuple(bad_rows)))
    return issues
