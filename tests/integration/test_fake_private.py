"""The private-data code paths, exercised with *fictitious* workbooks in the legacy layout.

No real data are involved: the workbooks are generated here with random values, in the
column layout of MASTER_GUIDE App. B.1.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import pytest
from typer.testing import CliRunner

from gravanom.cli import app
from gravanom.config import GriddingConfig, PipelineConfig
from gravanom.io.legacy import read_sources
from gravanom.pipeline import PrivateDataUnavailableError, load_dataset, private_data_dir, run_pipeline
from gravanom.reduction import bb_cubic_approximation, compute_legacy

FAKE_SOURCES = """
sources:
  - {label: A, path: a/subset_a.xlsx, sheet: data, first_row: 2, last_row: 975,
     facts: {source_id: 0, lon: 1, lat: 2, height_m: 3, g_obs_mgal: 4, bb_supplied_mgal: 5, tc_mgal: 6},
     legacy: {aaa: 13, abs: 14, abt: 15}}
  - {label: B, path: b/subset_b.xlsx, sheet: data, first_row: 2, last_row: 1066,
     facts: {source_id: 0, lon: 1, lat: 2, height_m: 3, g_obs_mgal: 4, bb_supplied_mgal: 5, tc_mgal: 6},
     legacy: {aaa: 12, abs: 13, abt: 14}}
"""


def _facts(rng: np.random.Generator, ids: list[int], lon0: float) -> pd.DataFrame:
    n = len(ids)
    lon = lon0 + rng.uniform(0, 0.9, n)
    lat = 9.0 + rng.uniform(0, 0.9, n)
    h = rng.uniform(10, 200, n)
    g = 978_160 + 0.2 * h - 20 * (lon - lon0) + rng.normal(0, 3, n)
    return pd.DataFrame(
        {"id": ids, "lon": lon, "lat": lat, "height_m": h, "g_obs_mgal": g, "tc_mgal": rng.uniform(0.2, 0.6, n)}
    )


def _write(path: Path, sheet: str, df: pd.DataFrame, bb: np.ndarray, legacy_cols: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    leg = compute_legacy(df.assign(bb_supplied_mgal=bb))
    ncol = max(legacy_cols) + 1
    ws.append([f"c{i}" for i in range(ncol)])
    for i, r in enumerate(df.itertuples(index=False)):
        row: list[object] = [None] * ncol
        row[:7] = [r.id, r.lon, r.lat, r.height_m, r.g_obs_mgal, float(bb[i]), r.tc_mgal]
        for col, name in zip(legacy_cols, ("aaa", "abs", "abt"), strict=True):
            row[col] = float(leg[name].iloc[i])
        ws.append(row)
    wb.save(path)


@pytest.fixture(scope="module")
def fake_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Fictitious subset A (300 rows) and B (320 rows) workbooks sharing 25 ids."""
    rng = np.random.default_rng(7)
    root = tmp_path_factory.mktemp("fake_private")
    (root / "sources.yaml").write_text(FAKE_SOURCES, encoding="utf-8")
    a = _facts(rng, list(range(1, 301)), -75.2)
    b = _facts(rng, [*range(1, 26), *range(2000, 2295)], -74.3)
    b.iloc[:25, 1:] = a.iloc[:25, 1:].to_numpy()  # shared ids: identical principal facts
    _write(root / "a" / "subset_a.xlsx", "data", a, -0.999 * bb_cubic_approximation(a.height_m), (13, 14, 15))
    _write(root / "b" / "subset_b.xlsx", "data", b, 1.1 * bb_cubic_approximation(b.height_m), (12, 13, 14))
    return root


def test_private_dir_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAVANOM_PRIVATE_DATA_DIR", raising=False)
    monkeypatch.setenv("GRAVANOM_LEGACY_SOURCES", str(tmp_path / "missing.yaml"))
    with pytest.raises(PrivateDataUnavailableError):
        private_data_dir()
    with pytest.raises(PrivateDataUnavailableError):
        private_data_dir(tmp_path)
    with pytest.raises(ValueError):
        load_dataset("nope")


def test_fake_readers(fake_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAVANOM_LEGACY_SOURCES", str(fake_root / "sources.yaml"))
    tables = read_sources(fake_root)
    a, b = tables["A"], tables["B"]
    assert len(a.records) == 300 and len(b.records) == 320
    assert list(a.legacy.columns) == ["source", "source_id", "aaa", "abs", "abt"]


def test_fake_private_pipeline(fake_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAVANOM_PRIVATE_DATA_DIR", str(fake_root))
    monkeypatch.setenv("GRAVANOM_LEGACY_SOURCES", str(fake_root / "sources.yaml"))
    cfg = PipelineConfig(
        gridding=GriddingConfig(
            trend_degree=1, matern_nu=1.5, cell_size_m=1000, eqs_depths_m=(10_000.0,), eqs_dampings=(1.0,)
        )
    )
    run_dir = run_pipeline("private", cfg, tmp_path, "full", run_id="fake")
    red = json.loads((run_dir / "reduction_report.json").read_text(encoding="utf-8"))
    for src in ("A", "B"):
        assert red["legacy"][src]["legacy_mode_vs_cached"]["abt"]["max_abs_mgal"] < 1e-6
    assert red["legacy"]["B"]["term_decomposition_standard2670_vs_legacy"]["curvature_bb"]["mean_mgal"] < 0
    qc = json.loads((run_dir / "qc_report.json").read_text(encoding="utf-8"))
    assert qc["harmonization"]["n_shared_ids"] == 25 and qc["bb_comparison"]["per_source"]["A"]["ratio_median"] < 0
    sens = json.loads((run_dir / "sensitivity.json").read_text(encoding="utf-8"))
    assert {"block_size", "seeds", "seed_mean_ratio_to_idw"} <= set(sens["sensitivity"])
    sel = json.loads((run_dir / "selection.json").read_text(encoding="utf-8"))
    assert set(sel["rmse"]) == {"idw", "spline", "rk_matern", "eqs"}
    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["dataset_kind"] == "private" and sorted(m["inputs"]) == ["subset A", "subset B"]  # labels only


def test_cli_commands(fake_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAVANOM_PRIVATE_DATA_DIR", str(fake_root))
    monkeypatch.setenv("GRAVANOM_LEGACY_SOURCES", str(fake_root / "sources.yaml"))
    runner = CliRunner()
    r = runner.invoke(app, ["ingest", "--dataset", "private", "--out", str(tmp_path / "s.parquet")])
    assert r.exit_code == 0, r.output and (tmp_path / "s.parquet").exists()
    r = runner.invoke(app, ["qc", "--dataset", "synthetic", "--out", str(tmp_path / "qc.json")])
    assert r.exit_code == 0 and "TC_SUSPECT" in r.output
    cfg = tmp_path / "c.yaml"
    cfg.write_text("reduction:\n  density_kg_m3: 2300\ngridding:\n  method: idw\n  cell_size_m: 2000\n", encoding="utf-8")
    r = runner.invoke(app, ["reduce", "--dataset", "synthetic", "--config", str(cfg), "--out", str(tmp_path / "a.parquet")])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["grid", "--dataset", "synthetic", "--config", str(cfg), "--artifacts", str(tmp_path / "art")])
    assert r.exit_code == 0, r.output
    run_dir = Path(r.output.strip().splitlines()[-1])
    r = runner.invoke(app, ["report", str(run_dir)])
    assert r.exit_code == 0 and "cell_size" in r.output
    r = runner.invoke(app, ["export-static-demo", "--run-dir", str(run_dir), "--out", str(tmp_path / "demo")])
    assert r.exit_code == 0 and (tmp_path / "demo" / "index.json").exists()
    r = runner.invoke(app, ["run", "--validation", "bogus"])
    assert r.exit_code != 0
