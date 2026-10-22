"""API contract tests (P7): every endpoint, success and error paths, public mode, PNG alpha, performance."""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
from app.main import create_app
from app.settings import Settings
from fastapi.testclient import TestClient
from PIL import Image

API = "/api/v1"


def _client(tmp: Path, **kw: object) -> TestClient:
    return TestClient(create_app(Settings(gravanom_artifacts_dir=tmp, gravanom_private_data_dir=None, **kw)))  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    return _client(tmp_path_factory.mktemp("api"))


def _wait(client: TestClient, job_id: str, timeout: float = 300) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"{API}/gridding-jobs/{job_id}").json()
        if st["status"] in ("done", "failed"):
            return st
        time.sleep(0.5)
    raise TimeoutError(job_id)


@pytest.fixture(scope="module")
def run_id(client: TestClient) -> str:
    return client.post(f"{API}/reductions", json={"dataset": "synthetic"}).json()["run_id"]


@pytest.fixture(scope="module")
def idw_grid(client: TestClient, run_id: str) -> str:
    r = client.post(f"{API}/gridding-jobs", json={"run_id": run_id, "config": {"method": "idw", "cell_size_m": 1000}})
    assert r.status_code == 202
    st = _wait(client, r.json()["job_id"])
    assert st["status"] == "done", st
    return st["grid_id"]


def _problem(r, status: int, code: str) -> None:  # type: ignore[no-untyped-def]
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == code


def test_health_and_headers(client: TestClient) -> None:
    r = client.get(f"{API}/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff" and "content-security-policy" in r.headers


def test_datasets(client: TestClient) -> None:
    ds = client.get(f"{API}/datasets").json()
    assert [d["id"] for d in ds] == ["synthetic"]
    assert ds[0]["label"] == "SYNTHETIC" and ds[0]["n_stations"] == 2000 and len(ds[0]["extent"]) == 4


def test_dataset_stations_and_qc(client: TestClient) -> None:
    fc = client.get(f"{API}/datasets/synthetic/stations").json()
    p = fc["features"][0]["properties"]
    assert fc["properties"]["label"] == "SYNTHETIC"
    for k in ("faa_mgal", "cba_mgal", "gamma0_mgal", "bc_cap_mgal", "sigma_cba_mgal", "qc_flags"):
        assert k in p
    js = client.get(f"{API}/datasets/synthetic/stations", params={"format": "json", "fields": "cba_mgal"}).json()
    assert set(js["stations"][0]) == {"station_uid", "qc_flags", "cba_mgal"}
    qc = client.get(f"{API}/datasets/synthetic/qc").json()
    assert qc["flag_counts"]["ERROR_RANGE"] == 1 and qc["flag_counts"]["TC_SUSPECT"] == 3
    _problem(client.get(f"{API}/datasets/private/qc"), 503, "PRIVATE_DATA_UNAVAILABLE")
    _problem(client.get(f"{API}/datasets/other/qc"), 422, "VALIDATION_ERROR")


def test_reduction_and_errors(client: TestClient, run_id: str) -> None:
    r = client.post(f"{API}/reductions", json={"dataset": "synthetic", "config": {"density_kg_m3": 2300}})
    assert r.status_code == 200 and r.json()["run_id"] != run_id
    s = r.json()["summary"]
    assert s["n_excluded_error_flags"] == 1 and s["cba_mgal"]["max"] < 100
    _problem(client.post(f"{API}/reductions", json={"config": {"density_kg_m3": 100}}), 422, "VALIDATION_ERROR")
    _problem(client.post(f"{API}/reductions", json={"config": {"normal_gravity": "WGS84"}}), 422, "VALIDATION_ERROR")
    _problem(client.post(f"{API}/reductions", json={"bogus": 1}), 422, "VALIDATION_ERROR")
    st = client.get(f"{API}/reductions/{run_id}/stations", params={"quantity": "cba_mgal"}).json()
    assert set(st["features"][0]["properties"]) <= {"station_uid", "qc_flags", "cba_mgal", "lon", "lat"}
    _problem(client.get(f"{API}/reductions/{run_id}/stations", params={"quantity": "x"}), 422, "VALIDATION_ERROR")
    _problem(client.get(f"{API}/reductions/nope/stations"), 404, "NOT_FOUND")


def test_legacy_mode_reduction(client: TestClient) -> None:
    r = client.post(f"{API}/reductions", json={"config": {"legacy_mode": True}})
    assert r.status_code == 200  # synthetic has no supplied BB: legacy SBA/CBA are null
    assert r.json()["summary"]["faa_mgal"]["n"] > 0


def test_density_sensitivity(client: TestClient) -> None:
    r = client.post(f"{API}/sensitivity/density", json={"dataset": "synthetic", "densities": [2670, 2300]})
    body = r.json()
    assert r.status_code == 200 and body["stats"]["mean"] < 0
    assert body["diagnostics"]["nettleton"]["estimate_kg_m3"] > 0
    d = body["stations"]["features"][0]["properties"]["delta_cba_mgal"]
    a = client.post(f"{API}/reductions", json={"config": {"density_kg_m3": 2670}}).json()["run_id"]
    b = client.post(f"{API}/reductions", json={"config": {"density_kg_m3": 2300}}).json()["run_id"]
    fa = client.get(f"{API}/reductions/{a}/stations", params={"quantity": "cba_mgal"}).json()["features"][0]["properties"]
    fb = client.get(f"{API}/reductions/{b}/stations", params={"quantity": "cba_mgal"}).json()["features"][0]["properties"]
    assert d == pytest.approx(fa["cba_mgal"] - fb["cba_mgal"], abs=1e-5)
    _problem(client.post(f"{API}/sensitivity/density", json={"densities": [2670]}), 422, "VALIDATION_ERROR")


def test_manifest(client: TestClient, run_id: str) -> None:
    m = client.get(f"{API}/runs/{run_id}/manifest").json()
    assert m["inputs"] and m["versions"]["gravanom"] and m["seeds"] and m["config_hash"]
    _problem(client.get(f"{API}/runs/nope/manifest"), 404, "NOT_FOUND")


def test_grid_endpoints(client: TestClient, idw_grid: str) -> None:
    meta = client.get(f"{API}/grids/{idw_grid}").json()
    assert meta["crs"] == "EPSG:9377" and meta["units"] == "mGal" and meta["method"] == "idw"
    img = client.get(f"{API}/grids/{idw_grid}/image", params={"layer": "value"})
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    bounds = [float(v) for v in img.headers["x-bounds"].split(",")]
    assert bounds[0] < bounds[2] and bounds[1] < bounds[3]
    assert client.get(f"{API}/grids/{idw_grid}/image-meta").json()["cmap"] == "RdBu_r"
    _problem(client.get(f"{API}/grids/{idw_grid}/image", params={"layer": "bad"}), 422, "VALIDATION_ERROR")
    _problem(client.get(f"{API}/grids/{idw_grid}/image", params={"cmap": "jet"}), 422, "VALIDATION_ERROR")
    c = client.get(f"{API}/grids/{idw_grid}/contours", params={"interval": 10}).json()
    assert c["features"] and c["features"][0]["properties"]["units"] == "mGal"
    smp = client.get(f"{API}/grids/{idw_grid}/sample", params={"lon": -75.0, "lat": 9.0}).json()
    assert smp["supported"] in (True, False) and smp["units"] == "mGal"
    far = client.get(f"{API}/grids/{idw_grid}/sample", params={"lon": -70.0, "lat": 2.0}).json()
    assert far["supported"] is False and far["value"] is None
    val = client.get(f"{API}/grids/{idw_grid}/validation").json()
    assert val["cv"]["idw"]["outer"]["rmse"] > 0
    _problem(client.get(f"{API}/grids/nope"), 404, "NOT_FOUND")
    _problem(client.get(f"{API}/gridding-jobs/nope"), 404, "NOT_FOUND")


def test_unsupported_cells_transparent(client: TestClient, idw_grid: str) -> None:
    png = client.get(f"{API}/grids/{idw_grid}/image", params={"layer": "value"}).content
    rgba = np.asarray(Image.open(io.BytesIO(png)))
    entry = client.app.state.services.grids.get(idw_grid)  # type: ignore[attr-defined]
    share_supported = float(entry.ds["support_mask"].mean())
    opaque = float((rgba[..., 3] > 0).mean())
    assert 0 < opaque < 1
    assert abs(opaque - share_supported) < 0.1  # area-preserving to within the Mercator distortion
    corner = rgba[0, 0]
    assert corner[3] == 0


def test_profile(client: TestClient, idw_grid: str) -> None:
    r = client.post(f"{API}/grids/{idw_grid}/profile", json={"coordinates": [[-75.3, 9.0], [-74.7, 9.0]], "buffer_m": 2000})
    assert r.status_code == 200, r.text
    p = r.json()
    assert len(p["distance_km"]) == len(p["value"]) and p["units"] == "mGal"
    assert all(s["offset_m"] <= 2000 for s in p["stations"])
    _problem(client.post(f"{API}/grids/{idw_grid}/profile", json={"coordinates": [[-75.3, 9.0]]}), 422, "VALIDATION_ERROR")
    _problem(
        client.post(f"{API}/grids/{idw_grid}/profile", json={"coordinates": [[-70.0, 2.0], [-70.1, 2.1]]}),
        409,
        "INSUFFICIENT_DATA",
    )


def test_download_cog(client: TestClient, idw_grid: str, tmp_path: Path) -> None:
    r = client.get(f"{API}/grids/{idw_grid}/download", params={"format": "cog", "layer": "value"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "metadata.json" in names and "manifest.json" in names
    tif = next(n for n in names if n.endswith(".tif"))
    zf.extract(tif, tmp_path)
    with rasterio.open(tmp_path / tif) as src:
        assert src.crs.to_epsg() == 9377 and np.isnan(src.nodata)
    assert json.loads(zf.read("metadata.json"))["label"] == "SYNTHETIC"
    nc = client.get(f"{API}/grids/{idw_grid}/download", params={"format": "netcdf", "layer": "value"})
    assert nc.status_code == 200


def test_rk_job_performance_and_calibration(client: TestClient, run_id: str) -> None:
    t0 = time.time()
    r = client.post(
        f"{API}/gridding-jobs",
        json={"run_id": run_id, "config": {"method": "rk_matern", "trend_degree": 2, "matern_nu": 1.5}},
    )
    st = _wait(client, r.json()["job_id"])
    elapsed = time.time() - t0
    assert st["status"] == "done", st
    print(f"gridding job (2k stations, 500 m, nested CV): {elapsed:.1f} s")
    assert elapsed < 120
    meta = client.get(f"{API}/grids/{st['grid_id']}").json()
    assert 0.85 <= meta["cv"]["sd_z"] <= 1.15
    t1 = time.time()
    assert client.get(f"{API}/grids/{st['grid_id']}/image", params={"layer": "sigma_cal"}).status_code == 200
    assert time.time() - t1 < 1.0
    v = client.get(f"{API}/grids/{st['grid_id']}/validation").json()
    assert v["variogram"]["model"]["nu"] == 1.5
    again = client.post(
        f"{API}/gridding-jobs",
        json={"run_id": run_id, "config": {"method": "rk_matern", "trend_degree": 2, "matern_nu": 1.5}},
    )
    assert client.get(f"{API}/gridding-jobs/{again.json()['job_id']}").json()["status"] == "done"  # cached


def test_reduction_performance(client: TestClient) -> None:
    t0 = time.time()
    client.post(f"{API}/reductions", json={"config": {"density_kg_m3": 2500}})
    assert time.time() - t0 < 1.0


def test_gaussian_rejected(client: TestClient, run_id: str) -> None:
    r = client.post(f"{API}/gridding-jobs", json={"run_id": run_id, "config": {"matern_nu": "gaussian"}})
    _problem(r, 422, "VALIDATION_ERROR")


def test_grid_too_large(client: TestClient, run_id: str) -> None:
    r = client.post(f"{API}/gridding-jobs", json={"run_id": run_id, "config": {"method": "idw", "cell_size_m": 100}})
    st = _wait(client, r.json()["job_id"])
    assert st["status"] == "failed" and st["error"]["code"] in ("GRID_TOO_LARGE", "INSUFFICIENT_DATA")


def test_body_limit(client: TestClient) -> None:
    big = "x" * 1_100_000
    r = client.post(f"{API}/reductions", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_public_mode_no_paths(tmp_path: Path) -> None:
    c = _client(tmp_path, gravanom_public_mode=True)
    ids = [d["id"] for d in c.get(f"{API}/datasets").json()]
    assert ids == ["synthetic"]
    r = c.post(f"{API}/reductions", json={"dataset": "private"})
    _problem(r, 503, "PRIVATE_DATA_UNAVAILABLE")
    for resp in (r, c.get(f"{API}/datasets/private/stations"), c.get(f"{API}/runs/x/manifest")):
        text = resp.text
        assert str(tmp_path) not in text and ":\\" not in text and "/home/" not in text


def test_openapi(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])
    for p in ("/api/v1/health", "/api/v1/reductions", "/api/v1/gridding-jobs", "/api/v1/grids/{grid_id}/profile"):
        assert p in paths


@pytest.mark.parametrize("fmt", ["csv", "geojson", "gpkg", "parquet"])
def test_station_export(client: TestClient, run_id: str, fmt: str) -> None:
    r = client.get(f"{API}/reductions/{run_id}/export", params={"format": fmt})
    assert r.status_code == 200 and len(r.content) > 1000
    assert "attachment" in r.headers["content-disposition"]
    if fmt == "csv":
        assert r.text.startswith("# SYNTHETIC")


def test_station_residual_quantity(client: TestClient, run_id: str) -> None:
    fc = client.get(f"{API}/reductions/{run_id}/stations", params={"quantity": "cba_residual_mgal"}).json()
    vals = [f["properties"]["cba_residual_mgal"] for f in fc["features"] if f["properties"]["cba_residual_mgal"] is not None]
    assert abs(sum(vals) / len(vals)) < 1e-6
