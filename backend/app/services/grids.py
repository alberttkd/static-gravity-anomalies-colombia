"""Gridding jobs (thread pool), grid products, rendering cache, profiles and exports."""

from __future__ import annotations

import io
import json
import logging
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from app.errors import ProblemError, not_found
from app.services.runs import ReductionRun, RunService
from app.settings import Settings
from gravanom.analysis.contours import contours
from gravanom.config import GriddingConfig, config_hash
from gravanom.gridding import Points, nested_cv, select_method
from gravanom.gridding.variography import VariogramFitError
from gravanom.io.writers import to_jsonable, write_json
from gravanom.pipeline import _cv_json, grid_stage, gridding_points, validate, variogram_report, write_grid
from gravanom.render import render_layer

log = logging.getLogger("app.grids")


@dataclass
class GridEntry:
    """A finished grid product."""

    grid_id: str
    run: ReductionRun
    config: GriddingConfig
    ds: xr.Dataset
    meta: dict[str, Any]
    validation: dict[str, Any]
    directory: Path
    points: Points
    used: np.ndarray


@dataclass
class Job:
    job_id: str
    status: str = "queued"
    progress: float = 0.0
    grid_id: str | None = None
    error: dict[str, str] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        out: dict[str, Any] = {"job_id": self.job_id, "status": self.status, "progress": self.progress}
        if self.grid_id:
            out["grid_id"] = self.grid_id
        if self.error:
            out["error"] = self.error
        if self.diagnostics:
            out["diagnostics"] = self.diagnostics
        return out


class GridService:
    """Runs gridding jobs and serves grid products."""

    def __init__(self, settings: Settings, runs: RunService) -> None:
        self.settings = settings
        self.runs = runs
        self._jobs: dict[str, Job] = {}
        self._grids: dict[str, GridEntry] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=settings.job_workers, thread_name_prefix="grid")

    # --- jobs --------------------------------------------------------------
    def submit(self, run_id: str, config: GriddingConfig) -> Job:
        run = self.runs.get(run_id)
        grid_id = f"{run_id}-{config_hash(config)[:8]}"
        job = Job(uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.job_id] = job
            if grid_id in self._grids:  # artifact reuse keyed by input + config hash
                job.status, job.progress, job.grid_id = "done", 1.0, grid_id
                return job
        self._pool.submit(self._run_job, job, run, config, grid_id)
        return job

    def job(self, job_id: str) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                raise not_found(f"job '{job_id}'")
            return self._jobs[job_id]

    def _run_job(self, job: Job, run: ReductionRun, cfg: GriddingConfig, grid_id: str) -> None:
        job.status = "running"
        try:
            pts, used = gridding_points(run.dataset.catalogue, run.table, cfg)
            job.progress = 0.1
            aniso = None
            if cfg.method == "auto":
                val = validate(pts, cfg, "quick")
                method = val["selection"]["selected"]
                reports = val["reports"]
                if val.get("anisotropy", {}).get("parameters"):
                    aniso = tuple(val["anisotropy"]["parameters"])
                selection = val["selection"]
            else:
                method = cfg.method
                reports = {method: nested_cv(method, pts, cfg)}
                selection = select_method(reports)
            job.progress = 0.7
            job.diagnostics = {"selection": to_jsonable(selection)}
            fm, ds = grid_stage(pts, cfg, method, aniso)  # type: ignore[arg-type]
            job.progress = 0.9
            directory = self.settings.api_artifacts / run.dataset.id / run.run_id / "grids" / grid_id
            tags = {"label": run.dataset.label, "run_id": run.run_id, "method": fm.gridder.name, "target": cfg.target}
            write_grid(ds, directory, tags)
            rep = reports[method]
            validation = {
                "method": method,
                "selection": selection,
                "cv": {m: _cv_json(r, pts) for m, r in reports.items()},
                "variogram": variogram_report(fm, pts, cfg),
                "units": "mGal",
                "crs": "EPSG:9377",
            }
            write_json(validation, directory / "validation.json")
            sup = int(ds["support_mask"].sum())
            meta = {
                "grid_id": grid_id,
                "run_id": run.run_id,
                "dataset": run.dataset.id,
                "label": run.dataset.label,
                "target": cfg.target,
                "method": fm.gridder.name,
                "params": fm.gridder.params(),
                "calibration_c": fm.calibration_c,
                "config": cfg.model_dump(mode="json"),
                "config_hash": config_hash(cfg),
                "crs": "EPSG:9377",
                "units": "mGal",
                "cell_size_m": cfg.cell_size_m,
                "shape": [int(ds.sizes["y"]), int(ds.sizes["x"])],
                "supported_share": sup / int(ds["support_mask"].size),
                "cv": {"rmse": rep["outer"]["rmse"], **(rep.get("calibrated") or {})},
                "layers": [v for v in ("value", "sigma_raw", "sigma_cal", "trend", "residual") if v in ds],
            }
            write_json(meta, directory / "grid.json")
            entry = GridEntry(grid_id, run, cfg, ds, meta, validation, directory, pts, used)
            with self._lock:
                self._grids[grid_id] = entry
            job.grid_id, job.progress, job.status = grid_id, 1.0, "done"
        except VariogramFitError as exc:
            job.status, job.error = "failed", {"code": "VARIOGRAM_FIT_FAILED", "detail": str(exc)[:300]}
        except ValueError as exc:
            job.status, job.error = "failed", {"code": "INSUFFICIENT_DATA", "detail": str(exc)[:300]}
        except Exception:
            log.exception("gridding job %s failed", job.job_id)
            job.status, job.error = "failed", {"code": "INTERNAL", "detail": "gridding failed"}

    # --- products ----------------------------------------------------------
    def get(self, grid_id: str) -> GridEntry:
        with self._lock:
            if grid_id not in self._grids:
                raise not_found(f"grid '{grid_id}'")
            return self._grids[grid_id]

    def render(
        self, grid_id: str, layer: str, cmap: str | None, vmin: float | None, vmax: float | None
    ) -> tuple[bytes, dict[str, Any]]:
        entry = self.get(grid_id)
        if layer not in (*entry.meta["layers"], "lowconf_hatch"):
            raise ProblemError(422, "VALIDATION_ERROR", "Unknown layer", f"layer must be one of {entry.meta['layers']}")
        return _render_cached(self, grid_id, layer, cmap, vmin, vmax)

    def contours(self, grid_id: str, interval: float, layer: str) -> dict[str, Any]:
        entry = self.get(grid_id)
        ds = entry.ds if layer == "value" else entry.ds[[layer, "support_mask"]].rename({layer: "value"})
        return contours(ds, interval)

    def sample(self, grid_id: str, lon: float, lat: float) -> dict[str, Any]:
        from gravanom.crs import to_analysis

        entry = self.get(grid_id)
        x, y = to_analysis(lon, lat)
        xs, ys = entry.ds["x"].values, entry.ds["y"].values
        cell = float(entry.meta["cell_size_m"])
        i = int(np.round((float(y) - ys[0]) / cell))
        j = int(np.round((float(x) - xs[0]) / cell))
        if not (0 <= i < len(ys) and 0 <= j < len(xs)):
            return {"value": None, "sigma_cal": None, "supported": False, "confident": False, "units": "mGal"}
        sup = bool(entry.ds["support_mask"].values[i, j])
        v = entry.ds["value"].values[i, j]
        s = entry.ds["sigma_cal"].values[i, j]
        return {
            "value": float(v) if sup and np.isfinite(v) else None,
            "sigma_cal": float(s) if sup and np.isfinite(s) else None,
            "supported": sup,
            "confident": bool(entry.ds["confidence_mask"].values[i, j]),
            "units": "mGal",
        }

    def download(self, grid_id: str, fmt: str, layer: str) -> tuple[bytes, str, str]:
        entry = self.get(grid_id)
        if layer not in entry.meta["layers"] and layer not in ("support_mask", "confidence_mask"):
            raise ProblemError(422, "VALIDATION_ERROR", "Unknown layer", f"layer must be one of {entry.meta['layers']}")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if fmt == "cog":
                zf.write(entry.directory / f"{layer}.tif", f"{grid_id}_{layer}.tif")
            else:
                nc = entry.ds[[layer]].assign_attrs(crs="EPSG:9377", Conventions="CF-1.8")
                zf.writestr(f"{grid_id}_{layer}.nc", nc.to_netcdf(engine="scipy"))
            zf.writestr("metadata.json", json.dumps(to_jsonable(self.metadata(entry)), indent=2, sort_keys=True))
            zf.writestr("manifest.json", entry.run.manifest.model_dump_json(indent=2))
        return buf.getvalue(), "application/zip", f"{grid_id}_{layer}_{fmt}.zip"

    def metadata(self, entry: GridEntry) -> dict[str, Any]:
        return {
            "title": f"{entry.meta['target']} grid ({entry.meta['method']}) - {entry.run.dataset.label}",
            "label": entry.run.dataset.label,
            "lineage": [
                "reduction run " + entry.run.run_id,
                "gridding " + entry.meta["method"],
                "block CV calibration",
                "masks",
            ],
            "crs": "EPSG:9377",
            "units": "mGal",
            "grid": entry.meta,
            "licence": "CC BY 4.0" if entry.run.dataset.kind == "synthetic" else "not redistributable (Q1 pending)",
        }


@lru_cache(maxsize=64)
def _render_cached(
    svc: GridService, grid_id: str, layer: str, cmap: str | None, vmin: float | None, vmax: float | None
) -> tuple[bytes, dict[str, Any]]:
    return render_layer(svc.get(grid_id).ds, layer, cmap, vmin, vmax)
