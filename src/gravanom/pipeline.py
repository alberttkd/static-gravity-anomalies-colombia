"""Staged pipeline S1-S9 (MASTER_GUIDE §5.6) and artifact layout (§6.5).

``artifacts/<dataset>/<run_id>/{stations.parquet, anomalies.parquet, qc_report.json,
reduction_report.json, uncertainty_report.json, density_report.json, variogram.json,
selection.json, sensitivity.json, cv/*.json, grids/<name>/*.tif, metadata.json,
manifest.json}``
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import RegularGridInterpolator

from gravanom.analysis.compare import term_decomposition
from gravanom.analysis.contours import contours
from gravanom.analysis.trend import PolynomialTrend, decompose
from gravanom.config import GriddingConfig, PipelineConfig, ReductionConfig, canonical_json, config_hash
from gravanom.constants import CRS_ANALYSIS, VERTICAL_REFERENCE
from gravanom.density import density_diagnostics, density_scenarios
from gravanom.flags import ERROR_FLAGS, QCFlag
from gravanom.gridding.cv import Points, block_folds, nested_cv, select_method
from gravanom.gridding.gridders import RegressionKriging
from gravanom.gridding.products import FinalModel, fit_final_model, grid_axes, make_grid, mask_statistics
from gravanom.gridding.variography import directional_lengths, experimental_variogram
from gravanom.harmonize import harmonize
from gravanom.io.legacy import LegacySourcesError, LegacyTables, load_source_specs, read_sources
from gravanom.io.readers import read_station_csv
from gravanom.io.writers import to_jsonable, write_cog, write_geojson, write_geoparquet, write_json
from gravanom.provenance import (
    Manifest,
    finalize_manifest,
    git_commit,
    make_run_id,
    package_versions,
    sha256_file,
)
from gravanom.qc import (
    QCReport,
    add_flag,
    add_post_reduction_flags,
    bb_comparison,
    exclusion_mask,
    legacy_comparison,
    run_qc,
)
from gravanom.qc.rules import rule_spatial_outlier
from gravanom.reduction import compute_anomalies
from gravanom.synthetic import SYNTHETIC_LABEL
from gravanom.uncertainty import monte_carlo, propagate, uncertainty_report

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYNTHETIC = REPO_ROOT / "data" / "synthetic" / "synthetic_survey.csv"
GRID_LAYERS = ("value", "sigma_raw", "sigma_cal", "trend", "residual", "support_mask", "confidence_mask")
Validation = Literal["full", "quick", "none"]
#: Polynomial degree of the regional field in the regional/residual products.
REGIONAL_DEGREE = 2


class PrivateDataUnavailableError(RuntimeError):
    """``GRAVANOM_PRIVATE_DATA_DIR`` unset or invalid (API code PRIVATE_DATA_UNAVAILABLE)."""


@dataclass
class Dataset:
    """Loaded input dataset."""

    name: str
    kind: Literal["synthetic", "private"]
    records: list[pd.DataFrame]
    inputs: dict[str, str]
    legacy: dict[str, LegacyTables] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return SYNTHETIC_LABEL if self.kind == "synthetic" else "PRIVATE - not redistributable"


def private_data_dir(override: str | Path | None = None) -> Path:
    """The private data directory (``override`` or ``GRAVANOM_PRIVATE_DATA_DIR``), validated."""
    env = str(override) if override else os.environ.get("GRAVANOM_PRIVATE_DATA_DIR")
    if not env:
        raise PrivateDataUnavailableError("GRAVANOM_PRIVATE_DATA_DIR is not set")
    root = Path(env)
    try:
        specs = load_source_specs()
    except LegacySourcesError as exc:
        raise PrivateDataUnavailableError("legacy source description is missing") from exc
    if not all((root / s.path).exists() for s in specs):
        raise PrivateDataUnavailableError("private data directory does not contain the legacy workbooks")
    return root


def load_dataset(
    name: str = "synthetic", synthetic_path: Path | None = None, private_dir: str | Path | None = None
) -> Dataset:
    """Load ``synthetic`` (bundled CSV) or ``private`` (legacy workbooks via the env var)."""
    if name == "synthetic":
        p = synthetic_path or DEFAULT_SYNTHETIC
        return Dataset("synthetic", "synthetic", [read_station_csv(p)], {p.name: sha256_file(p)})
    if name == "private":
        root = private_data_dir(private_dir)
        specs = load_source_specs()
        tables = read_sources(root, specs)
        # Inputs are recorded by subset label only: manifests never carry private file names.
        inputs = {f"subset {s.label}": sha256_file(root / s.path) for s in specs}
        for s in specs:
            if s.duplicate_xls and (root / s.duplicate_xls).exists():
                inputs[f"subset {s.label} (xls copy)"] = sha256_file(root / s.duplicate_xls)
        return Dataset("private", "private", [t.records for t in tables.values()], inputs, tables)
    raise ValueError(f"unknown dataset {name!r}")


# --- S1-S3 --------------------------------------------------------------------
def build_catalogue(ds: Dataset) -> tuple[pd.DataFrame, QCReport]:
    """S1-S3: harmonize the sources and apply the pre-reduction QC rules."""
    cat, hlog = harmonize(ds.records)
    cat, report = run_qc(cat, hlog)
    if ds.kind == "private":
        report.bb_comparison = bb_comparison(cat)
    return cat, report


# --- S4-S6 --------------------------------------------------------------------
def reduce_stations(cat: pd.DataFrame, cfg: PipelineConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """S4-S5: anomalies, station σ and the QC-08 flag. Returns (catalogue, anomaly table)."""
    an = compute_anomalies(cat, cfg.reduction)
    cat = add_post_reduction_flags(cat, an)
    sig = propagate(cat, cfg.reduction, cfg.uncertainty)
    table = pd.concat(
        [cat[["station_uid"]].reset_index(drop=True), an.reset_index(drop=True), sig.reset_index(drop=True)],
        axis=1,
    )
    table["config_hash"] = config_hash(cfg.reduction)
    return cat, table


def legacy_reproduction(ds: Dataset) -> dict[str, Any]:
    """QC-10 and App. C C10/C11 per legacy source (private only)."""
    out: dict[str, Any] = {}
    for src, tables in ds.legacy.items():
        rec = tables.records
        leg = compute_anomalies(rec, ReductionConfig(legacy_mode=True))
        recomputed = pd.DataFrame({"aaa": leg["faa_mgal"], "abs": leg["sba_mgal"], "abt": leg["cba_mgal"]})
        std2300 = compute_anomalies(rec, ReductionConfig(density_kg_m3=2300.0))
        d = std2300["cba_mgal"].to_numpy() - tables.legacy["abt"].to_numpy()
        out[src] = {
            "n": len(rec),
            "legacy_mode_vs_cached": legacy_comparison(recomputed, tables.legacy),
            "standard_2300_minus_legacy_abt": {
                "mean_mgal": float(d.mean()),
                "min_mgal": float(d.min()),
                "max_mgal": float(d.max()),
            },
            "term_decomposition_standard2670_vs_legacy": term_decomposition(compute_anomalies(rec), leg),
        }
    return out


def reduction_report(cat: pd.DataFrame, ds: Dataset, cfg: PipelineConfig) -> dict[str, Any]:
    """RQ1 material: density scenarios, curvature/Honkasalo effects, legacy comparison."""
    usable = ~exclusion_mask(cat, list(ERROR_FLAGS))
    sub = cat[usable]
    by_rho = {
        rho: compute_anomalies(sub, cfg.reduction.model_copy(update={"density_kg_m3": rho}))["cba_mgal"].to_numpy()
        for rho in cfg.density.scenarios_kg_m3
    }
    base = compute_anomalies(sub, cfg.reduction)["cba_mgal"].to_numpy()

    def effect(update: dict[str, Any]) -> dict[str, float]:
        alt = compute_anomalies(sub, cfg.reduction.model_copy(update=update))["cba_mgal"].to_numpy()
        dd = (base - alt)[np.isfinite(base - alt)]
        return {
            "mean_mgal": float(dd.mean()),
            "min_mgal": float(dd.min()),
            "max_mgal": float(dd.max()),
            "rms_mgal": float(np.sqrt(np.mean(dd**2))),
        }

    rep: dict[str, Any] = {
        "config": cfg.reduction.model_dump(mode="json"),
        "n_stations": int(usable.sum()),
        "density_scenarios": density_scenarios(by_rho),
        "effects_on_cba": {
            "curvature (cap vs slab)": effect({"curvature": "none"}),
            "honkasalo": effect({"honkasalo": False}),
            "atmospheric": effect({"atmospheric": False}),
            "height_correction (hinze vs legacy)": effect({"height_correction": "legacy_0.3086_0.073"}),
        },
    }
    if ds.legacy:
        rep["legacy"] = legacy_reproduction(ds)
    return rep


def density_stage(cat: pd.DataFrame, anomalies: pd.DataFrame, cfg: PipelineConfig) -> dict[str, Any]:
    """S6: Nettleton/Parasnis diagnostics on usable stations (error flags and TC_SUSPECT excluded)."""
    use = ~exclusion_mask(cat, [*ERROR_FLAGS, QCFlag.TC_SUSPECT])
    return density_diagnostics(
        anomalies.loc[use, "faa_mgal"].to_numpy(),
        cat.loc[use, "height_m"].to_numpy(),
        cat.loc[use, "tc_mgal"].to_numpy(),
        cat.loc[use, "x_9377"].to_numpy(),
        cat.loc[use, "y_9377"].to_numpy(),
        cfg.density,
        cfg.reduction.terrain_reference_density_kg_m3,
    )


# --- S7-S9 --------------------------------------------------------------------
def gridding_points(cat: pd.DataFrame, anomalies: pd.DataFrame, gcfg: GriddingConfig) -> tuple[Points, np.ndarray]:
    """Points for gridding the configured target, excluding flagged stations and NaN values."""
    col = {"FAA": "faa_mgal", "SBA": "sba_mgal", "CBA": "cba_mgal", "residual": "cba_mgal"}[gcfg.target]
    flags = list(gcfg.exclude_flags) + ([QCFlag.TC_SUSPECT] if col == "cba_mgal" else [])
    z = anomalies[col].to_numpy(dtype=float)
    use = ~exclusion_mask(cat, flags) & np.isfinite(z)
    x, y = cat["x_9377"].to_numpy()[use], cat["y_9377"].to_numpy()[use]
    zz = z[use]
    if gcfg.target == "residual":
        deg = 2 if gcfg.trend_degree == "auto" else int(gcfg.trend_degree)
        zz = zz - PolynomialTrend(deg).fit(x, y, zz).predict(x, y)
    return Points(x, y, zz, cat["height_m"].to_numpy()[use]), use


def _cv_json(rep: dict[str, Any], pts: Points) -> dict[str, Any]:
    out = {k: v for k, v in rep.items() if k not in ("residual", "pred", "sigma_cal")}
    out["points"] = {"observed": pts.z.tolist(), "predicted": rep["pred"].tolist()}
    if "sigma_cal" in rep:
        out["points"]["z"] = ((pts.z - rep["pred"]) / rep["sigma_cal"]).tolist()
    return out


def validate(
    pts: Points, gcfg: GriddingConfig, level: Validation = "full", methods: tuple[str, ...] | None = None
) -> dict[str, Any]:
    """S8: nested block CV per method, anisotropy test, selection and sensitivities.

    ``quick`` runs IDW and RK only, without block-size/seed sensitivities.
    """
    if methods is None:
        methods = ("idw", "spline", "rk_matern", "eqs") if level == "full" else ("idw", "rk_matern")
    out: dict[str, Any] = {}
    aniso_param = None
    if "rk_matern" in methods:
        out["anisotropy"] = anisotropy_test(pts, gcfg)
        aniso_param = out["anisotropy"]["parameters"]
    reports: dict[str, dict[str, Any]] = {}
    for m in methods:
        log.info("nested CV: %s", m)
        reports[m] = nested_cv(m, pts, gcfg, anisotropy=aniso_param if m == "rk_matern" else None)
    selection = select_method(reports)
    selection["anisotropy_candidate"] = list(aniso_param) if aniso_param else None
    out.update({"reports": reports, "selection": selection})

    if level == "full":
        sens: dict[str, Any] = {"block_size": {}, "seeds": {}}
        sel = selection["selected"]
        an_sel = aniso_param if sel == "rk_matern" else None
        for b in (10_000.0, 25_000.0):
            r_sel = nested_cv(sel, pts, gcfg, anisotropy=an_sel, block_size_m=b)
            r_idw = nested_cv("idw", pts, gcfg, block_size_m=b)
            sens["block_size"][f"{b / 1000:g}km"] = _sens_entry(r_sel, r_idw)
        for seed in (gcfg.cv.random_state + 1, gcfg.cv.random_state + 2):
            r_sel = nested_cv(sel, pts, gcfg, anisotropy=an_sel, random_state=seed)
            r_idw = nested_cv("idw", pts, gcfg, random_state=seed)
            sens["seeds"][str(seed)] = _sens_entry(r_sel, r_idw)
        sens["seeds"][str(gcfg.cv.random_state)] = _sens_entry(reports[sel], reports["idw"])
        ratios = [v["ratio_to_idw"] for v in sens["seeds"].values()]
        sens["seed_mean_ratio_to_idw"] = float(np.mean(ratios))
        out["sensitivity"] = sens
    return out


def anisotropy_test(pts: Points, gcfg: GriddingConfig, degree: int = 2, nu: float = 1.5) -> dict[str, Any]:
    """Directional variograms per outer-fold training set (§5.5.5).

    A preliminary isotropic RK (degree 2, nu 1.5) supplies the trend residuals and the
    model; geometric anisotropy is modelled if the minor/major ratio is < 0.7 in at
    least 4 of 5 folds. The candidate parameters are the circular-mean major azimuth
    and the median ratio.
    """
    per_fold: list[dict[str, Any]] = []
    outer = block_folds(pts.x, pts.y, gcfg.cv.block_size_m, gcfg.cv.n_splits, gcfg.cv.random_state)
    for idx, _ in outer:
        tp = pts.take(idx)
        try:
            rk = RegressionKriging(degree, nu, gcfg.bin_m, gcfg.max_lag_m).fit(tp.x, tp.y, tp.z, tp.h)
        except Exception as exc:
            per_fold.append({"error": str(exc)[:200], "ratio": None})
            continue
        r = tp.z - rk.trend_at(tp.x, tp.y)
        per_fold.append(directional_lengths(tp.x, tp.y, r, rk.variogram, gcfg.bin_m, gcfg.max_lag_m))
    ratios: list[float] = [float(f["ratio"]) for f in per_fold if f.get("ratio") is not None]
    n_aniso = sum(1 for r in ratios if r < 0.7)
    modelled = n_aniso >= 4
    params = None
    if modelled:
        az = np.radians([2 * f["major_azimuth_deg"] for f in per_fold if f.get("ratio") is not None])
        mean_az = float(np.degrees(np.arctan2(np.sin(az).mean(), np.cos(az).mean())) / 2 % 180)
        params = (round(mean_az, 1), round(float(np.median(ratios)), 3))
    return {
        "per_fold": per_fold,
        "n_folds_ratio_lt_0p7": n_aniso,
        "modelled": modelled,
        "parameters": params,
        "rule": "model geometric anisotropy if minor/major < 0.7 in >= 4 of 5 folds",
    }


def _sens_entry(r_sel: dict[str, Any], r_idw: dict[str, Any]) -> dict[str, Any]:
    e: dict[str, Any] = {
        "rmse": r_sel["outer"]["rmse"],
        "idw_rmse": r_idw["outer"]["rmse"],
        "ratio_to_idw": r_sel["outer"]["rmse"] / r_idw["outer"]["rmse"],
    }
    if "calibrated" in r_sel:
        e["calibrated"] = r_sel["calibrated"]
    return e


def cell_size_sensitivity(model: FinalModel, pts: Points, grid: xr.Dataset, gcfg: GriddingConfig) -> dict[str, Any]:
    """RMS of (250 m prediction - bilinear 500 m grid) on supported 250 m nodes (criterion < 0.2 mGal)."""
    fine = gcfg.cell_size_m / 2
    gx, gy = grid_axes(pts.x, pts.y, fine)
    xx, yy = np.meshgrid(gx, gy)
    interp = RegularGridInterpolator(
        (grid["y"].values, grid["x"].values), grid["value"].values, bounds_error=False, fill_value=np.nan
    )
    coarse = interp(np.column_stack([yy.ravel(), xx.ravel()]))
    ok = np.isfinite(coarse)
    g = model.gridder
    hh = np.full(int(ok.sum()), float(np.median(pts.h)))
    if isinstance(g, RegressionKriging):
        p, _ = g.predict(xx.ravel()[ok], yy.ravel()[ok], hh, return_std=False)
    else:
        p, _ = g.predict(xx.ravel()[ok], yy.ravel()[ok], hh)
    d = p - coarse[ok]
    return {
        "fine_cell_m": fine,
        "coarse_cell_m": gcfg.cell_size_m,
        "n_nodes": int(ok.sum()),
        "rms_mgal": float(np.sqrt(np.mean(d**2))),
        "max_abs_mgal": float(np.max(np.abs(d))),
        "pass_lt_0p2": bool(np.sqrt(np.mean(d**2)) < 0.2),
    }


def grid_stage(
    pts: Points, gcfg: GriddingConfig, method: str, anisotropy: tuple[float, float] | None = None
) -> tuple[FinalModel, xr.Dataset]:
    """S9: fit the final model on all points and predict the grid (with residual layer)."""
    fm = fit_final_model(method, pts, gcfg, anisotropy if method == "rk_matern" else None)
    grid = make_grid(fm, pts, gcfg)
    # Regional field for SO5: degree-2 OLS polynomial at the stations (F-10, §5.5.6). It is
    # independent of the kriging drift, which block CV may set to degree 0 (D-008).
    xx, yy = np.meshgrid(grid["x"].values, grid["y"].values)
    regional = PolynomialTrend(REGIONAL_DEGREE).fit(pts.x, pts.y, pts.z).predict(xx.ravel(), yy.ravel()).reshape(xx.shape)
    regional = np.where(grid["support_mask"].values == 1, regional, np.nan)
    grid["trend"] = (
        ("y", "x"),
        regional,
        {"units": "mGal", "long_name": f"regional field (degree-{REGIONAL_DEGREE} polynomial)"},
    )
    grid["residual"] = (
        ("y", "x"),
        grid["value"].values - regional,
        {"units": "mGal", "long_name": "residual (value - regional)"},
    )
    return fm, grid


def variogram_report(fm: FinalModel, pts: Points, gcfg: GriddingConfig) -> dict[str, Any]:
    """Experimental (omni + 4 directions) and fitted variograms of the final RK model."""
    g = fm.gridder
    if not isinstance(g, RegressionKriging):
        return {"method": g.name, "note": "no variogram for this method"}
    r = pts.z - g.trend_at(pts.x, pts.y)
    vm = g.variogram
    lags = np.linspace(0, gcfg.max_lag_m, 61)
    return {
        "method": g.name,
        "model": vm.to_dict(),
        "params": g.params(),
        "experimental": experimental_variogram(pts.x, pts.y, r, gcfg.bin_m, gcfg.max_lag_m).to_dict(),
        "directional": [
            experimental_variogram(pts.x, pts.y, r, gcfg.bin_m, gcfg.max_lag_m, direction_deg=a).to_dict()
            for a in (0.0, 45.0, 90.0, 135.0)
        ],
        "fitted_curve": {"lag_m": lags.tolist(), "gamma_mgal2": vm.gamma(lags).tolist()},
        "anisotropy_full_data": directional_lengths(pts.x, pts.y, r, vm, gcfg.bin_m, gcfg.max_lag_m),
        "calibration_c": fm.calibration_c,
        "selection": fm.selection,
    }


def write_grid(grid: xr.Dataset, out_dir: Path, tags: dict[str, str]) -> dict[str, Path]:
    """Write each layer as a COG (float64 values, uint8 masks) plus contours and metadata."""
    paths: dict[str, Path] = {}
    x, y = grid["x"].values, grid["y"].values
    for layer in GRID_LAYERS:
        if layer not in grid:
            continue
        dtype = "uint8" if layer.endswith("_mask") else "float64"
        paths[layer] = write_cog(
            grid[layer].values,
            x,
            y,
            out_dir / f"{layer}.tif",
            tags={**tags, "layer": layer, "units": grid[layer].attrs.get("units", "")},
            dtype=dtype,
        )
    paths["contours"] = write_geojson(contours(grid, 5.0), out_dir / "contours.geojson")
    resid = grid[["residual", "support_mask"]].rename({"residual": "value"})
    paths["contours_residual"] = write_geojson(contours(resid, 1.0), out_dir / "contours_residual.geojson")
    return paths


def run_pipeline(
    dataset: str = "synthetic",
    config: PipelineConfig | None = None,
    artifacts_dir: Path | None = None,
    validation: Validation = "full",
    synthetic_path: Path | None = None,
    run_id: str | None = None,
) -> Path:
    """Run S1-S9 and write all artifacts. Returns the run directory."""
    cfg = config or PipelineConfig()
    chash = config_hash(cfg)
    rid = run_id or make_run_id(chash)
    root = artifacts_dir or Path(os.environ.get("GRAVANOM_ARTIFACTS_DIR", REPO_ROOT / "artifacts"))
    run_dir = root / dataset / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    ds = load_dataset(dataset, synthetic_path)
    manifest = Manifest(
        run_id=rid,
        dataset=ds.name,
        dataset_kind=ds.kind,
        label=ds.label,
        config=cfg.model_dump(mode="json"),
        config_hash=chash,
        inputs=ds.inputs,
        versions=package_versions(),
        git_commit=git_commit(REPO_ROOT),
        seeds={
            "cv": cfg.gridding.cv.random_state,
            "uncertainty": cfg.uncertainty.random_state,
            "density": cfg.density.random_state,
        },
    )

    log.info("S1-S3 ingest/harmonize/QC")
    cat, qc_report = build_catalogue(ds)
    manifest.stages.append("S1-S3")

    log.info("S4-S5 reduction and uncertainty")
    cat, anomalies = reduce_stations(cat, cfg)
    mc = monte_carlo(cat, cfg.reduction, cfg.uncertainty)
    lin = anomalies[["sigma_faa_mgal", "sigma_sba_mgal", "sigma_cba_mgal"]]
    write_json(
        uncertainty_report(lin, mc.set_axis(lin.columns, axis=1), cfg.uncertainty),
        run_dir / "uncertainty_report.json",
    )
    write_json(reduction_report(cat, ds, cfg), run_dir / "reduction_report.json")
    manifest.stages.append("S4-S5")

    log.info("S6 density diagnostics")
    write_json(density_stage(cat, anomalies, cfg), run_dir / "density_report.json")
    manifest.stages.append("S6")

    log.info("S7-S9 gridding")
    pts, used = gridding_points(cat, anomalies, cfg.gridding)
    method = cfg.gridding.method
    aniso: tuple[float, float] | None = None
    if validation != "none":
        val = validate(pts, cfg.gridding, validation)
        for m, rep in val["reports"].items():
            write_json(_cv_json(rep, pts), run_dir / "cv" / f"{m}.json")
        write_json(val["selection"], run_dir / "selection.json")
        sens = {k: v for k, v in val.items() if k in ("anisotropy", "sensitivity")}
        if "anisotropy" in val and val["anisotropy"]["parameters"]:
            aniso = tuple(val["anisotropy"]["parameters"])  # type: ignore[assignment]
        if method == "auto":
            method = val["selection"]["selected"]
        sel_rep = val["reports"].get(method)
        if sel_rep is not None:
            flag = np.zeros(len(cat), bool)
            flag[np.flatnonzero(used)] = rule_spatial_outlier(sel_rep["residual"])
            cat = add_flag(cat, flag, QCFlag.SPATIAL_OUTLIER)
    else:
        sens = {}
        method = "rk_matern" if method == "auto" else method
    fm, grid = grid_stage(pts, cfg.gridding, method, aniso)
    sens["cell_size"] = cell_size_sensitivity(fm, pts, grid, cfg.gridding)
    sens["masks"] = mask_statistics(grid)
    write_json(sens, run_dir / "sensitivity.json")
    write_json(variogram_report(fm, pts, cfg.gridding), run_dir / "variogram.json")
    dec = decompose(pts.x, pts.y, pts.z, REGIONAL_DEGREE)
    write_json(
        {
            "degree": REGIONAL_DEGREE,
            "variance_explained": dec["variance_explained"],
            "sd_total_mgal": float(np.std(pts.z)),
            "sd_residual_mgal": float(np.std(dec["residual"])),
            "kriging_trend_degree": fm.gridder.params().get("trend_degree"),
        },
        run_dir / "decomposition.json",
    )
    name = f"{cfg.gridding.target.lower()}_{fm.gridder.name}"
    tags = {
        "label": ds.label,
        "run_id": rid,
        "config_hash": chash,
        "method": fm.gridder.name,
        "target": cfg.gridding.target,
    }
    write_grid(grid, run_dir / "grids" / name, tags)
    write_json(
        {
            "name": name,
            "target": cfg.gridding.target,
            "method": fm.gridder.name,
            "params": fm.gridder.params(),
            "calibration_c": fm.calibration_c,
            "crs": CRS_ANALYSIS,
            "cell_size_m": cfg.gridding.cell_size_m,
            "shape": [int(grid.sizes["y"]), int(grid.sizes["x"])],
            "x_range_m": [float(grid["x"].values[0]), float(grid["x"].values[-1])],
            "y_range_m": [float(grid["y"].values[0]), float(grid["y"].values[-1])],
            "n_points": len(pts),
            "masks": sens["masks"],
            "label": ds.label,
        },
        run_dir / "grids" / name / "grid.json",
    )
    manifest.stages.append("S7-S9")

    # Final station tables and QC report (with post-reduction flags).
    qc_final = qc_report.model_copy(
        update={"flag_counts": {f.value: int(sum(f.value in fl for fl in cat["qc_flags"])) for f in QCFlag}}
    )
    qc_final.flagged_station_uids = {
        f.value: cat.loc[[f.value in fl for fl in cat["qc_flags"]], "station_uid"].astype(str).tolist()
        for f in QCFlag
        if qc_final.flag_counts[f.value] and f is not QCFlag.DUPLICATE_POSITION
    }
    write_json(qc_final, run_dir / "qc_report.json")
    write_geoparquet(cat, run_dir / "stations.parquet")
    anomalies.to_parquet(run_dir / "anomalies.parquet", index=False, compression="zstd")
    write_json(run_metadata(ds, cfg, rid, grid), run_dir / "metadata.json")
    finalize_manifest(manifest, run_dir)
    return run_dir


def run_metadata(ds: Dataset, cfg: PipelineConfig, run_id: str, grid: xr.Dataset) -> dict[str, Any]:
    """ISO 19115-inspired metadata for the run's products."""
    from gravanom.crs import to_geographic

    lon, lat = to_geographic(grid["x"].values[[0, -1]], grid["y"].values[[0, -1]])
    return {
        "title": f"Static gravity anomalies - {ds.label}",
        "abstract": "Free-air, simple Bouguer and complete Bouguer anomalies reduced following Hinze et al. (2005), "
        "gridded by regression kriging with block-cross-validated, calibrated uncertainty and data-support masks.",
        "label": ds.label,
        "run_id": run_id,
        "lineage": [
            "S1 ingestion",
            "S2 harmonization",
            "S3 QC flags",
            "S4 reduction",
            "S5 station uncertainty",
            "S6 density diagnostics",
            "S7 variography and gridding",
            "S8 block CV, calibration, masks",
            "S9 products",
        ],
        "config": to_jsonable(cfg),
        "crs": {
            "storage": "EPSG:4326",
            "analysis": CRS_ANALYSIS,
            "web": "EPSG:3857",
            "vertical": VERTICAL_REFERENCE,
        },
        "units": "mGal",
        "extent_lonlat": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
        "licence": {
            "code": "BSD-3-Clause",
            "products": "CC BY 4.0" if ds.kind == "synthetic" else "not redistributable (Q1 pending)",
        },
        "citation": "Herrera, A. J. (2026). grav-anomaly-explorer. See CITATION.cff.",
        "config_json": canonical_json(cfg),
    }
