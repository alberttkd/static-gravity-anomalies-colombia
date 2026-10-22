"""Simulated legacy spreadsheets with known defects (all values fictitious).

The clean stations of a synthetic survey are split by traverse into two subsets, A and B,
which are "reduced" with the legacy spreadsheet formulas (:func:`gravanom.reduction.legacy.compute_legacy`:
slab density 2300 kg m^-3, first-order height correction, legacy normal-gravity coefficients) and
a supplied curvature (Bullard B) value:

* subset A supplies the cubic approximation of BB with the correct "value to add" sign;
* subset B supplies it with the opposite sign and scaled by :data:`LEGACY_DEFECTS` ``["bb_scale_b"]``.

The reconciliation of these tables with the standard reduction must recover both defects.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from gravanom.reduction.curvature import bb_cubic_approximation
from gravanom.reduction.legacy import compute_legacy
from gravanom.synthetic.generator import SyntheticSurvey

#: Injected defects, so that tests and the paper can check that they are recovered.
LEGACY_DEFECTS: dict[str, Any] = {
    "density_kg_m3": 2300.0,
    "bb_sign_a": -1.0,
    "bb_sign_b": +1.0,
    "bb_scale_b": 1.08,
}


def simulate_legacy_subsets(survey: SyntheticSurvey) -> dict[str, pd.DataFrame]:
    """Two legacy subsets (even and odd traverses) with their legacy anomalies.

    Returns
    -------
    dict
        ``{"A": df, "B": df}``; each frame has ``id``, ``lon``, ``lat``, ``height_m``,
        ``g_obs_mgal``, ``tc_mgal``, ``bb_supplied_mgal``, ``traverse`` and the legacy
        columns ``aaa``, ``abs``, ``abt`` [mGal].
    """
    st = survey.stations
    clean = st[st["id"].str.startswith("S") & (st["g_obs_mgal"] < 985_000.0) & (st["tc_mgal"] > 0.0)]
    out: dict[str, pd.DataFrame] = {}
    for label, parity in (("A", 0), ("B", 1)):
        df = clean[clean["traverse"] % 2 == parity].copy().reset_index(drop=True)
        bb = bb_cubic_approximation(df["height_m"].to_numpy())
        if label == "A":
            df["bb_supplied_mgal"] = LEGACY_DEFECTS["bb_sign_a"] * bb
        else:
            df["bb_supplied_mgal"] = LEGACY_DEFECTS["bb_sign_b"] * LEGACY_DEFECTS["bb_scale_b"] * bb
        leg = compute_legacy(df)
        out[label] = pd.concat([df, leg[["aaa", "abs", "abt"]]], axis=1)
    return out
