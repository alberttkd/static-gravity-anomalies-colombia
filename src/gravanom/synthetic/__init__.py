"""Deterministic synthetic dataset with known truth (labelled SYNTHETIC)."""

from gravanom.synthetic.files import write_synthetic
from gravanom.synthetic.generator import (
    HIGH_RELIEF,
    LOW_RELIEF_CORRELATED,
    SYNTHETIC_LABEL,
    SyntheticSpec,
    SyntheticSurvey,
    make_synthetic_survey,
)
from gravanom.synthetic.legacy_sim import LEGACY_DEFECTS, simulate_legacy_subsets

__all__ = [
    "HIGH_RELIEF",
    "LEGACY_DEFECTS",
    "LOW_RELIEF_CORRELATED",
    "SYNTHETIC_LABEL",
    "SyntheticSpec",
    "SyntheticSurvey",
    "make_synthetic_survey",
    "simulate_legacy_subsets",
    "write_synthetic",
]
