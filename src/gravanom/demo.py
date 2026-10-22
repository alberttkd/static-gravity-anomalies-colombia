"""Export a synthetic run as static files for the public web demo (§6.10, deployment 2).

Refuses any run that is not synthetic: real data are never deployed publicly.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from gravanom.analysis.trend import station_residual
from gravanom.config import ReductionConfig
from gravanom.flags import ERROR_FLAGS, QCFlag
from gravanom.io.geojson import stations_feature_collection
from gravanom.io.readers import read_grid_dir
from gravanom.io.writers import write_json
from gravanom.qc import exclusion_mask
from gravanom.reduction import compute_anomalies
from gravanom.render import render_layer

COPY = (
    "qc_report.json",
    "reduction_report.json",
    "uncertainty_report.json",
    "density_report.json",
    "variogram.json",
    "selection.json",
    "sensitivity.json",
    "metadata.json",
    "manifest.json",
)
IMAGE_LAYERS = ("value", "sigma_cal", "trend", "residual", "lowconf_hatch")


class NotSyntheticError(PermissionError):
    """Raised when asked to export a non-synthetic run."""


def export_demo(run_dir: str | Path, out_dir: str | Path) -> Path:
    """Write ``index.json``, stations, reports, CV, PNG layers and contours to ``out_dir``."""
    rd, out = Path(run_dir), Path(out_dir)
    manifest = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("dataset_kind") != "synthetic":
        raise NotSyntheticError("only synthetic runs can be exported to the public demo")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for name in COPY:
        if (rd / name).exists():
            shutil.copy2(rd / name, out / name)
    if (rd / "cv").exists():
        shutil.copytree(rd / "cv", out / "cv")

    import geopandas as gpd

    cat = pd.DataFrame(gpd.read_parquet(rd / "stations.parquet").drop(columns="geometry"))
    an = pd.read_parquet(rd / "anomalies.parquet")
    cba2300 = compute_anomalies(cat, ReductionConfig(density_kg_m3=2300.0))["cba_mgal"].to_numpy()
    usable = ~exclusion_mask(cat, [*ERROR_FLAGS, QCFlag.TC_SUSPECT])
    resid = station_residual(cat["x_9377"].to_numpy(), cat["y_9377"].to_numpy(), an["cba_mgal"].to_numpy(), usable)
    fc = stations_feature_collection(
        cat, an, label=manifest["label"], extra={"cba_2300_mgal": cba2300, "cba_residual_mgal": resid}
    )
    write_json(fc, out / "stations.geojson")

    grids: list[dict[str, Any]] = []
    for gdir in sorted((rd / "grids").iterdir()):
        ds = read_grid_dir(gdir)
        gmeta = json.loads((gdir / "grid.json").read_text(encoding="utf-8"))
        images = {}
        for layer in IMAGE_LAYERS:
            if layer != "lowconf_hatch" and layer not in ds:
                continue
            png, meta = render_layer(ds, layer)
            fname = f"{gdir.name}_{layer}.png"
            (out / fname).write_bytes(png)
            images[layer] = {**meta, "file": fname}
        for c in ("contours.geojson", "contours_residual.geojson"):
            shutil.copy2(gdir / c, out / f"{gdir.name}_{c}")
        grids.append(
            {
                **gmeta,
                "grid_id": gdir.name,
                "images": images,
                "contours": f"{gdir.name}_contours.geojson",
                "contours_residual": f"{gdir.name}_contours_residual.geojson",
            }
        )
    write_json(
        {
            "label": manifest["label"],
            "run_id": manifest["run_id"],
            "dataset": {"id": "synthetic", "kind": "synthetic", "n_stations": len(cat)},
            "grids": grids,
            "cv": sorted(p.stem for p in (out / "cv").glob("*.json")) if (out / "cv").exists() else [],
        },
        out / "index.json",
    )
    return out
