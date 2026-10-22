"""End-to-end pipeline on synthetic data: artifacts, manifests, determinism, injected defects, demo export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import rasterio

from gravanom.config import GriddingConfig, PipelineConfig
from gravanom.demo import NotSyntheticError, export_demo
from gravanom.pipeline import run_pipeline
from gravanom.provenance import sha256_file
from gravanom.synthetic import make_synthetic_survey, write_synthetic

FAST = PipelineConfig(gridding=GriddingConfig(trend_degree=2, matern_nu=1.5, cell_size_m=1000))


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("art")
    a = run_pipeline("synthetic", FAST, root / "a", "none", run_id="fixed")
    b = run_pipeline("synthetic", FAST, root / "b", "none", run_id="fixed")
    return a, b


def test_artifacts_exist(runs: tuple[Path, Path]) -> None:
    a, _ = runs
    for name in (
        "stations.parquet",
        "anomalies.parquet",
        "qc_report.json",
        "reduction_report.json",
        "uncertainty_report.json",
        "density_report.json",
        "variogram.json",
        "sensitivity.json",
        "metadata.json",
        "manifest.json",
    ):
        assert (a / name).exists(), name
    gdir = a / "grids" / "cba_rk_matern"
    for layer in ("value", "sigma_raw", "sigma_cal", "trend", "residual", "support_mask", "confidence_mask"):
        assert (gdir / f"{layer}.tif").exists()
    with rasterio.open(gdir / "value.tif") as src:
        assert src.crs.to_epsg() == 9377
        assert src.nodata != src.nodata  # NaN
        assert src.tags()["label"] == "SYNTHETIC"


def test_manifest(runs: tuple[Path, Path]) -> None:
    m = json.loads((runs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert m["dataset_kind"] == "synthetic" and m["label"] == "SYNTHETIC"
    assert "synthetic_survey.csv" in m["inputs"] and m["versions"]["harmonica"]
    assert m["seeds"]["cv"] == 20261022 and m["outputs"]
    for rel, h in m["outputs"].items():
        assert sha256_file(runs[0] / rel) == h


def test_determinism(runs: tuple[Path, Path]) -> None:
    ma = json.loads((runs[0] / "manifest.json").read_text(encoding="utf-8"))["outputs"]
    mb = json.loads((runs[1] / "manifest.json").read_text(encoding="utf-8"))["outputs"]
    assert ma == mb


def test_injected_defects_flagged(runs: tuple[Path, Path], synthetic_metadata: dict) -> None:
    qc = json.loads((runs[0] / "qc_report.json").read_text(encoding="utf-8"))
    exp = synthetic_metadata["expected_flags"]
    for flag in ("ERROR_RANGE", "TC_SUSPECT", "H_NONPOSITIVE"):
        assert sorted(qc["flagged_station_uids"].get(flag, [])) == sorted(exp[flag])
    assert qc["flag_counts"]["DUPLICATE_POSITION"] == len(exp["DUPLICATE_POSITION"])
    assert qc["harmonization"]["n_groups_g_spread_gt_0p1"] == 2


def test_uncertainty_mc_vs_linear(runs: tuple[Path, Path]) -> None:
    rep = json.loads((runs[0] / "uncertainty_report.json").read_text(encoding="utf-8"))
    assert all(v["pass_lt_5pct"] for v in rep["per_anomaly"].values())


def test_demo_export(runs: tuple[Path, Path], tmp_path: Path) -> None:
    out = export_demo(runs[0], tmp_path / "demo")
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert idx["label"] == "SYNTHETIC" and idx["grids"][0]["images"]["value"]["file"]
    assert (out / idx["grids"][0]["images"]["value"]["file"]).read_bytes()[:4] == b"\x89PNG"
    st = json.loads((out / "stations.geojson").read_text(encoding="utf-8"))
    assert st["properties"]["label"] == "SYNTHETIC" and "cba_2300_mgal" in st["features"][0]["properties"]


def test_demo_refuses_private(runs: tuple[Path, Path], tmp_path: Path) -> None:
    fake = tmp_path / "run"
    fake.mkdir()
    (fake / "manifest.json").write_text(json.dumps({"dataset_kind": "private"}), encoding="utf-8")
    with pytest.raises(NotSyntheticError):
        export_demo(fake, tmp_path / "demo")


def test_synthetic_generator_deterministic(tmp_path: Path) -> None:
    a = write_synthetic(make_synthetic_survey(), tmp_path / "a")
    b = write_synthetic(make_synthetic_survey(), tmp_path / "b")
    for k in a:
        assert sha256_file(a[k]) == sha256_file(b[k])
    committed = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "synthetic_survey.csv"
    assert sha256_file(a["survey"]) == sha256_file(committed)
