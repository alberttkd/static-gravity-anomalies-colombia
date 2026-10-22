"""API v1 routes (MASTER_GUIDE §6.8). Routes only validate, call services and serialize."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query, Request, Response, status

import gravanom
from app.errors import ProblemError
from app.schemas import (
    DatasetId,
    DensityRequest,
    GriddingRequest,
    Health,
    JobAccepted,
    ProfileRequest,
    ReductionRequest,
    ReductionResponse,
)
from app.services import Services
from app.settings import REPO_ROOT
from gravanom.analysis.profiles import profile as make_profile
from gravanom.config import DensityConfig, ReductionConfig
from gravanom.density import density_diagnostics
from gravanom.flags import ERROR_FLAGS, QCFlag
from gravanom.io.geojson import stations_feature_collection
from gravanom.io.writers import to_jsonable
from gravanom.provenance import git_commit
from gravanom.qc import exclusion_mask

router = APIRouter(prefix="/api/v1")

QUANTITIES = (
    "faa_mgal",
    "sba_mgal",
    "cba_mgal",
    "height_m",
    "sigma_faa_mgal",
    "sigma_sba_mgal",
    "sigma_cba_mgal",
    "g_obs_mgal",
    "tc_mgal",
    "cba_residual_mgal",
)
_density_cache: dict[str, dict[str, Any]] = {}


def services(request: Request) -> Services:
    return request.app.state.services  # type: ignore[no-any-return]


Svc = Annotated[Services, Depends(services)]


def _json(obj: Any, media: str = "application/json") -> Response:
    return Response(json.dumps(to_jsonable(obj), allow_nan=False), media_type=media)


@router.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", version=gravanom.__version__, git_sha=git_commit(REPO_ROOT))


@router.get("/datasets")
def datasets(svc: Svc) -> Response:
    return _json([svc.datasets.get(d).summary() for d in svc.datasets.available_ids()])


@router.get("/datasets/{ds}/stations")
def dataset_stations(
    ds: DatasetId, svc: Svc, format: Literal["geojson", "json"] = "geojson", fields: str | None = None
) -> Response:
    entry = svc.datasets.get(ds)
    run = svc.runs.reduce(ds, ReductionConfig())
    fc = stations_feature_collection(entry.catalogue, run.table, entry.label, fields=fields.split(",") if fields else None)
    if format == "json":
        return _json({"label": entry.label, "stations": [f["properties"] for f in fc["features"]]})
    return _json(fc, "application/geo+json")


@router.get("/datasets/{ds}/qc")
def dataset_qc(ds: DatasetId, svc: Svc) -> Response:
    entry = svc.datasets.get(ds)
    return _json({"label": entry.label, **entry.qc.model_dump(mode="json")})


@router.post("/reductions", response_model=ReductionResponse)
def create_reduction(req: ReductionRequest, svc: Svc) -> ReductionResponse:
    run = svc.runs.reduce(req.dataset, req.config)
    return ReductionResponse(
        run_id=run.run_id,
        config_hash=run.manifest.config_hash,
        dataset=req.dataset,
        label=run.dataset.label,
        summary=run.summary(),
    )


@router.get("/reductions/{run_id}/stations")
def reduction_stations(run_id: str, svc: Svc, quantity: str | None = None) -> Response:
    run = svc.runs.get(run_id)
    if quantity is not None and quantity not in QUANTITIES:
        raise ProblemError(422, "VALIDATION_ERROR", "Unknown quantity", f"quantity must be one of {list(QUANTITIES)}")
    fields = [quantity, "lon", "lat"] if quantity else None
    fc = stations_feature_collection(run.dataset.catalogue, run.table, run.dataset.label, fields=fields)
    fc["properties"].update({"run_id": run.run_id, "config_hash": run.manifest.config_hash, "quantity": quantity})
    return _json(fc, "application/geo+json")


@router.get("/reductions/{run_id}/export")
def reduction_export(run_id: str, svc: Svc, format: Literal["csv", "geojson", "gpkg", "parquet"] = "csv") -> Response:
    """Stations with all reduction terms and σ, with metadata (FR-11)."""
    import tempfile
    from pathlib import Path

    from gravanom.io.writers import write_csv, write_geoparquet, write_gpkg

    run = svc.runs.get(run_id)
    table = run.dataset.catalogue.reset_index(drop=True).join(run.table.drop(columns=["station_uid"]))
    name = f"stations_{run.dataset.id}_{run_id}"
    if format == "geojson":
        fc = stations_feature_collection(run.dataset.catalogue, run.table, run.dataset.label)
        fc["properties"]["manifest"] = run.manifest.model_dump(mode="json")
        data, media, ext = json.dumps(to_jsonable(fc)).encode(), "application/geo+json", "geojson"
    else:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"{name}.{format}"
            if format == "csv":
                write_csv(table, out, header_comment=f"{run.dataset.label}; run {run_id}; units mGal; CRS EPSG:4326")
            elif format == "gpkg":
                write_gpkg(table, out)
            else:
                write_geoparquet(table, out)
            data = out.read_bytes()
        media = {"csv": "text/csv", "gpkg": "application/geopackage+sqlite3", "parquet": "application/vnd.apache.parquet"}[
            format
        ]
        ext = format
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'})


@router.post("/sensitivity/density")
def density_sensitivity(req: DensityRequest, svc: Svc) -> Response:
    a, b = req.densities
    ra = svc.runs.reduce(req.dataset, ReductionConfig(density_kg_m3=a))
    rb = svc.runs.reduce(req.dataset, ReductionConfig(density_kg_m3=b))
    d = ra.table["cba_mgal"].to_numpy() - rb.table["cba_mgal"].to_numpy()
    entry = ra.dataset
    if req.dataset not in _density_cache:
        cat = entry.catalogue
        use = ~exclusion_mask(cat, [*ERROR_FLAGS, QCFlag.TC_SUSPECT])
        _density_cache[req.dataset] = density_diagnostics(
            ra.table.loc[use, "faa_mgal"].to_numpy(),
            cat.loc[use, "height_m"].to_numpy(),
            cat.loc[use, "tc_mgal"].to_numpy(),
            cat.loc[use, "x_9377"].to_numpy(),
            cat.loc[use, "y_9377"].to_numpy(),
            DensityConfig(bootstrap_replicates=300),
        )
    fin = d[np.isfinite(d)]
    fc = stations_feature_collection(
        entry.catalogue, None, entry.label, extra={"delta_cba_mgal": d}, fields=["delta_cba_mgal"]
    )
    return _json(
        {
            "label": entry.label,
            "densities_kg_m3": [a, b],
            "run_ids": [ra.run_id, rb.run_id],
            "delta": "CBA(rho_a) - CBA(rho_b)",
            "units": "mGal",
            "stats": {"mean": float(fin.mean()), "min": float(fin.min()), "max": float(fin.max()), "n": int(fin.size)},
            "stations": fc,
            "diagnostics": _density_cache[req.dataset],
        }
    )


@router.post("/gridding-jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
def create_gridding_job(req: GriddingRequest, svc: Svc) -> JobAccepted:
    job = svc.grids.submit(req.run_id, req.config)
    return JobAccepted(job_id=job.job_id, status=job.status)


@router.get("/gridding-jobs/{job_id}")
def gridding_job(job_id: str, svc: Svc) -> Response:
    return _json(svc.grids.job(job_id).public())


@router.get("/grids/{grid_id}")
def grid_meta(grid_id: str, svc: Svc) -> Response:
    return _json(svc.grids.get(grid_id).meta)


@router.get("/grids/{grid_id}/image")
def grid_image(
    grid_id: str,
    svc: Svc,
    layer: Literal["value", "sigma_raw", "sigma_cal", "trend", "residual", "lowconf_hatch"] = "value",
    cmap: Literal["RdBu_r", "viridis", "cividis", "magma"] | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
) -> Response:
    png, meta = svc.grids.render(grid_id, layer, cmap, vmin, vmax)
    headers = {
        "X-Bounds": ",".join(f"{v:.8f}" for v in meta["bounds"]),
        "X-Render-Meta": json.dumps(to_jsonable({k: v for k, v in meta.items() if k != "bounds"})),
        "Cache-Control": "public, max-age=3600",
    }
    return Response(png, media_type="image/png", headers=headers)


@router.get("/grids/{grid_id}/image-meta")
def grid_image_meta(
    grid_id: str,
    svc: Svc,
    layer: Literal["value", "sigma_raw", "sigma_cal", "trend", "residual", "lowconf_hatch"] = "value",
) -> Response:
    _, meta = svc.grids.render(grid_id, layer, None, None, None)
    return _json(meta)


@router.get("/grids/{grid_id}/contours")
def grid_contours(
    grid_id: str,
    svc: Svc,
    interval: Annotated[float, Query(gt=0, le=100)] = 5.0,
    layer: Literal["value", "residual", "trend"] = "value",
) -> Response:
    return _json(svc.grids.contours(grid_id, interval, layer), "application/geo+json")


@router.get("/grids/{grid_id}/sample")
def grid_sample(
    grid_id: str, svc: Svc, lon: Annotated[float, Query(ge=-180, le=180)], lat: Annotated[float, Query(ge=-90, le=90)]
) -> Response:
    return _json(svc.grids.sample(grid_id, lon, lat))


@router.post("/grids/{grid_id}/profile")
def grid_profile(grid_id: str, req: ProfileRequest, svc: Svc) -> Response:
    entry = svc.grids.get(grid_id)
    col = {"FAA": "faa_mgal", "SBA": "sba_mgal", "CBA": "cba_mgal", "residual": "cba_mgal"}[entry.config.target]
    cat = entry.run.dataset.catalogue
    st = pd.DataFrame(
        {
            "station_uid": cat["station_uid"].to_numpy(),
            "x_9377": cat["x_9377"].to_numpy(),
            "y_9377": cat["y_9377"].to_numpy(),
            "height_m": cat["height_m"].to_numpy(),
            "value": entry.run.table[col].to_numpy(),
            "sigma": entry.run.table[f"sigma_{col}"].to_numpy() if f"sigma_{col}" in entry.run.table else np.nan,
        }
    )
    st = st[entry.used] if entry.config.target != "residual" else st.iloc[0:0]
    pr = make_profile(entry.ds, req.coordinates, st, "value", req.buffer_m)
    return _json(
        {**pr, "grid_id": grid_id, "units": "mGal", "target": entry.config.target, "label": entry.run.dataset.label}
    )


@router.get("/grids/{grid_id}/validation")
def grid_validation(grid_id: str, svc: Svc) -> Response:
    return _json(svc.grids.get(grid_id).validation)


@router.get("/grids/{grid_id}/download")
def grid_download(
    grid_id: str,
    svc: Svc,
    format: Literal["cog", "netcdf"] = "cog",
    layer: Literal["value", "sigma_raw", "sigma_cal", "trend", "residual", "support_mask", "confidence_mask"] = "value",
) -> Response:
    data, media, name = svc.grids.download(grid_id, format, layer)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/runs/{run_id}/manifest")
def run_manifest(run_id: str, svc: Svc) -> Response:
    return _json(svc.runs.get(run_id).manifest.model_dump(mode="json"))
