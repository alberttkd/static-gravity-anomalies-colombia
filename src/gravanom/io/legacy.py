"""Readers for the legacy workbooks, with explicit column maps (MASTER_GUIDE App. B.1).

The two legacy subsets are called **A** and **B**. Their file locations, sheet names and
column maps are *not* stored in the repository: they are read from a local YAML file
(``config/private_sources.yaml`` by default, or ``GRAVANOM_LEGACY_SOURCES``), see
``config/private_sources.example.yaml``. The workbooks are opened read-only; cached
formula values (``data_only``) are returned as the legacy anomaly table.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import xlrd
import yaml

from gravanom.io.schema import coerce_records

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCES_FILE = REPO_ROOT / "config" / "private_sources.yaml"

FACT_KEYS = ("source_id", "lon", "lat", "height_m", "g_obs_mgal", "bb_supplied_mgal", "tc_mgal")
LEGACY_KEYS = ("aaa", "abs", "abt")


@dataclass(frozen=True)
class SourceSpec:
    """Location and 0-based column map of one legacy workbook (relative to the private data dir)."""

    label: str
    path: str
    sheet: str
    first_row: int
    last_row: int
    facts: dict[str, int]
    legacy: dict[str, int]
    duplicate_xls: str | None = None
    """Optional ``.xls`` copy that must hold identical values (checked on read)."""


@dataclass(frozen=True)
class LegacyTables:
    """Principal facts (record schema) plus the cached legacy anomalies."""

    records: pd.DataFrame
    legacy: pd.DataFrame  # columns: source, source_id, aaa, abs, abt


class LegacySourcesError(FileNotFoundError):
    """The local legacy-source description is missing or invalid."""


def sources_file() -> Path:
    """Path of the local legacy-source description."""
    env = os.environ.get("GRAVANOM_LEGACY_SOURCES")
    return Path(env) if env else DEFAULT_SOURCES_FILE


def load_source_specs(path: str | Path | None = None) -> list[SourceSpec]:
    """Read the legacy-source specifications (YAML list under ``sources:``)."""
    p = Path(path) if path else sources_file()
    if not p.exists():
        raise LegacySourcesError(f"legacy source description not found ({p.name}); see config/private_sources.example.yaml")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    specs = []
    for s in data.get("sources", []):
        missing = [k for k in FACT_KEYS if k not in s.get("facts", {})] + [
            k for k in LEGACY_KEYS if k not in s.get("legacy", {})
        ]
        if missing:
            raise LegacySourcesError(f"source {s.get('label')}: missing column map keys {missing}")
        specs.append(
            SourceSpec(
                label=str(s["label"]),
                path=str(s["path"]),
                sheet=str(s["sheet"]),
                first_row=int(s["first_row"]),
                last_row=int(s["last_row"]),
                facts={k: int(v) for k, v in s["facts"].items()},
                legacy={k: int(v) for k, v in s["legacy"].items()},
                duplicate_xls=s.get("duplicate_xls"),
            )
        )
    if not specs:
        raise LegacySourcesError("no sources defined")
    return specs


def _id_to_str(value: object) -> str:
    f = float(value)  # type: ignore[arg-type]
    return str(int(f)) if f.is_integer() else repr(f)


def _rows_xlsx(path: Path, spec: SourceSpec) -> list[tuple[object, ...]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[spec.sheet]
        return [tuple(r) for r in ws.iter_rows(min_row=spec.first_row, max_row=spec.last_row, values_only=True)]
    finally:
        wb.close()


def _rows_xls(path: Path, spec: SourceSpec) -> list[tuple[object, ...]]:
    sh = xlrd.open_workbook(str(path)).sheet_by_name(spec.sheet)
    return [tuple(sh.row_values(i)) for i in range(spec.first_row - 1, spec.last_row)]


def _build(rows: list[tuple[object, ...]], spec: SourceSpec) -> LegacyTables:
    ncol = max([*spec.facts.values(), *spec.legacy.values()]) + 1
    rows = [tuple(r[:ncol]) + (None,) * max(0, ncol - len(r)) for r in rows]
    rec = pd.DataFrame({k: [r[i] for r in rows] for k, i in spec.facts.items()})
    rec["source_id"] = [_id_to_str(v) for v in rec["source_id"]]
    rec["source"] = spec.label
    rec["prov_file"] = f"subset {spec.label}"
    rec["prov_sheet"] = "data"
    rec["prov_row"] = np.arange(spec.first_row, spec.first_row + len(rows))
    leg = pd.DataFrame({k: pd.to_numeric([r[i] for r in rows], errors="coerce") for k, i in spec.legacy.items()})
    leg.insert(0, "source_id", rec["source_id"].to_numpy())
    leg.insert(0, "source", spec.label)
    return LegacyTables(coerce_records(rec), leg)


def read_source(root: Path, spec: SourceSpec, check_duplicate: bool = True) -> LegacyTables:
    """Read one legacy workbook; verify its ``.xls`` duplicate when one is declared.

    Raises
    ------
    ValueError
        If the duplicate workbook differs in principal facts or anomalies.
    """
    path = root / spec.path
    rows = _rows_xls(path, spec) if path.suffix.lower() == ".xls" else _rows_xlsx(path, spec)
    tables = _build(rows, spec)
    if check_duplicate and spec.duplicate_xls and (root / spec.duplicate_xls).exists():
        other = _build(_rows_xls(root / spec.duplicate_xls, spec), spec)
        num = ["lon", "lat", "height_m", "g_obs_mgal", "bb_supplied_mgal", "tc_mgal"]
        same = np.allclose(tables.records[num], other.records[num], atol=1e-9, rtol=0, equal_nan=True)
        same &= np.allclose(tables.legacy[list(LEGACY_KEYS)], other.legacy[list(LEGACY_KEYS)], atol=1e-9, rtol=0)
        same &= bool((tables.records["source_id"] == other.records["source_id"]).all())
        if not same:
            raise ValueError(f"subset {spec.label}: duplicate workbooks differ")
    return tables


def read_sources(root: Path, specs: list[SourceSpec] | None = None) -> dict[str, LegacyTables]:
    """Read every legacy subset, keyed by its label (``A``, ``B``)."""
    return {s.label: read_source(root, s) for s in (specs or load_source_specs())}
