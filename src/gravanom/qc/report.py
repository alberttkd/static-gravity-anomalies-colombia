"""Run the QC rules on a catalogue and build the QC report (OP-03)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
import shapely
from pydantic import BaseModel, Field

from gravanom.flags import QCFlag
from gravanom.qc.rules import (
    QCThresholds,
    rule_faa_h_outlier,
    rule_h_nonpositive,
    rule_offshore,
    rule_range,
    rule_schema,
    rule_tc_suspect,
)
from gravanom.reduction.curvature import curvature_bb


class QCReport(BaseModel):
    """Aggregate QC report. Contains no raw station records except flagged ids."""

    n_stations: int
    flag_counts: dict[str, int]
    flagged_station_uids: dict[str, list[str]]
    harmonization: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    bb_comparison: dict[str, Any] | None = None
    legacy_comparison: dict[str, Any] | None = None


def add_flag(cat: pd.DataFrame, mask: np.ndarray, flag: QCFlag) -> pd.DataFrame:
    """Return a copy of ``cat`` with ``flag`` added to ``qc_flags`` where ``mask`` is True."""
    out = cat.copy()
    out["qc_flags"] = [
        sorted({*flags, flag.value}) if hit else list(flags) for flags, hit in zip(out["qc_flags"], mask, strict=True)
    ]
    return out


def has_flag(cat: pd.DataFrame, flag: QCFlag) -> np.ndarray:
    """Boolean mask of stations carrying ``flag``."""
    return np.array([flag.value in f for f in cat["qc_flags"]], dtype=bool)


def exclusion_mask(cat: pd.DataFrame, flags: tuple[QCFlag, ...] | list[QCFlag]) -> np.ndarray:
    """Boolean mask of stations carrying any of ``flags``."""
    wanted = {f.value for f in flags}
    return np.array([bool(wanted & set(f)) for f in cat["qc_flags"]], dtype=bool)


def run_qc(
    cat: pd.DataFrame,
    harmonization_log: dict[str, Any] | None = None,
    thresholds: QCThresholds | None = None,
    land_polygon: shapely.Geometry | None = None,
) -> tuple[pd.DataFrame, QCReport]:
    """Apply the pre-reduction QC rules QC-01, -02, -05, -06 and -12.

    QC-03 (shared-id conflicts) and QC-04 (duplicates) are set by
    :func:`gravanom.harmonize.harmonize`; QC-07/08 need anomalies or CV residuals
    and are added later (:func:`add_post_reduction_flags`).

    ``TC_SUSPECT`` stations get ``tc_mgal = NaN`` (treated as missing, never imputed);
    ``tc_supplied_mgal`` keeps the original value.
    """
    t = thresholds or QCThresholds()
    out = cat.copy()
    out = add_flag(out, rule_schema(out), QCFlag.ERROR_SCHEMA)
    out = add_flag(out, rule_range(out, t), QCFlag.ERROR_RANGE)
    tc_hit = rule_tc_suspect(out, t)
    out = add_flag(out, tc_hit, QCFlag.TC_SUSPECT)
    out.loc[tc_hit, "tc_mgal"] = np.nan
    out = add_flag(out, rule_h_nonpositive(out), QCFlag.H_NONPOSITIVE)
    out = add_flag(out, rule_offshore(out, land_polygon), QCFlag.OFFSHORE_OR_OUTSIDE)
    return out, build_report(out, harmonization_log, t)


def add_post_reduction_flags(
    cat: pd.DataFrame, anomalies: pd.DataFrame, thresholds: QCThresholds | None = None
) -> pd.DataFrame:
    """Add QC-08 (FAA-H outlier) once the free-air anomaly is known."""
    t = thresholds or QCThresholds()
    hit = rule_faa_h_outlier(anomalies["faa_mgal"].to_numpy(), cat["height_m"].to_numpy(), t)
    return add_flag(cat, hit, QCFlag.FAA_H_OUTLIER)


def build_report(cat: pd.DataFrame, harmonization_log: dict[str, Any] | None, t: QCThresholds) -> QCReport:
    """Count flags and assemble the :class:`QCReport`."""
    counts = {f.value: int(has_flag(cat, f).sum()) for f in QCFlag}
    flagged = {
        f.value: cat.loc[has_flag(cat, f), "station_uid"].astype(str).tolist()
        for f in QCFlag
        if counts[f.value] and f is not QCFlag.DUPLICATE_POSITION
    }
    return QCReport(
        n_stations=len(cat),
        flag_counts=counts,
        flagged_station_uids=flagged,
        harmonization=harmonization_log or {},
        thresholds=asdict(t),
    )


def bb_comparison(cat: pd.DataFrame, reference_density_kg_m3: float = 2670.0) -> dict[str, Any]:
    """QC-09 (audit only): supplied BB versus the recomputed LaFehr BB, per source.

    Supplied BB values are "values to add", so the ratio of a correct value to the
    recomputed BB is close to -1.
    """
    bb = curvature_bb(cat["height_m"].to_numpy(), reference_density_kg_m3)
    sup = cat["bb_supplied_mgal"].to_numpy(dtype=np.float64, na_value=np.nan)
    out: dict[str, Any] = {"reference_density_kg_m3": reference_density_kg_m3, "per_source": {}}
    first_src = [s[0] if len(s) else "" for s in cat["sources"]]
    for src in sorted(set(first_src)):
        m = (np.array(first_src) == src) & np.isfinite(sup) & (cat["height_m"].to_numpy() > 0)
        if not m.any():
            continue
        ratio = sup[m] / bb[m]
        q = np.quantile(ratio, [0.05, 0.5, 0.95])
        out["per_source"][src] = {
            "n": int(m.sum()),
            "ratio_median": float(q[1]),
            "ratio_q05": float(q[0]),
            "ratio_q95": float(q[2]),
            "max_abs_diff_mgal": float(np.max(np.abs(sup[m] + bb[m]))),
        }
    return out


def legacy_comparison(recomputed: pd.DataFrame, cached: pd.DataFrame) -> dict[str, Any]:
    """QC-10: legacy-mode anomalies recomputed versus cached spreadsheet values, per column."""
    res: dict[str, Any] = {}
    for col in ("aaa", "abs", "abt"):
        d = recomputed[col].to_numpy() - cached[col].to_numpy()
        res[col] = {
            "max_abs_mgal": float(np.nanmax(np.abs(d))),
            "mean_mgal": float(np.nanmean(d)),
            "n": int(np.isfinite(d).sum()),
        }
    return res
