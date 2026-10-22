"""Quality control: rules (§5.8) and report."""

from gravanom.qc.report import (
    QCReport,
    add_flag,
    add_post_reduction_flags,
    bb_comparison,
    exclusion_mask,
    has_flag,
    legacy_comparison,
    run_qc,
)
from gravanom.qc.rules import QCThresholds, robust_z

__all__ = [
    "QCReport",
    "QCThresholds",
    "add_flag",
    "add_post_reduction_flags",
    "bb_comparison",
    "exclusion_mask",
    "has_flag",
    "legacy_comparison",
    "robust_z",
    "run_qc",
]
