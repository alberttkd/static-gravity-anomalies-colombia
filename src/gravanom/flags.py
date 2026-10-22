"""Controlled vocabulary of quality-control flags (MASTER_GUIDE §5.8)."""

from __future__ import annotations

from enum import StrEnum


class QCFlag(StrEnum):
    """QC flags. Quality control never deletes records; it assigns these flags."""

    ERROR_SCHEMA = "ERROR_SCHEMA"
    ERROR_RANGE = "ERROR_RANGE"
    CONFLICT_SHARED_ID = "CONFLICT_SHARED_ID"
    DUPLICATE_POSITION = "DUPLICATE_POSITION"
    TC_SUSPECT = "TC_SUSPECT"
    H_NONPOSITIVE = "H_NONPOSITIVE"
    SPATIAL_OUTLIER = "SPATIAL_OUTLIER"
    FAA_H_OUTLIER = "FAA_H_OUTLIER"
    GGM_INCONSISTENT = "GGM_INCONSISTENT"
    OFFSHORE_OR_OUTSIDE = "OFFSHORE_OR_OUTSIDE"


#: Flags that make a record unusable for any product.
ERROR_FLAGS: frozenset[QCFlag] = frozenset({QCFlag.ERROR_SCHEMA, QCFlag.ERROR_RANGE, QCFlag.CONFLICT_SHARED_ID})

#: Flags that are warnings only (records are kept).
WARNING_FLAGS: frozenset[QCFlag] = frozenset(
    {
        QCFlag.H_NONPOSITIVE,
        QCFlag.SPATIAL_OUTLIER,
        QCFlag.FAA_H_OUTLIER,
        QCFlag.GGM_INCONSISTENT,
        QCFlag.OFFSHORE_OR_OUTSIDE,
    }
)
