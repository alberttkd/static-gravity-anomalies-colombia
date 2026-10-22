"""Figures and aggregate numbers for the paper, from synthetic data only (paper/figures, paper/numbers.json).

Usage::

    python scripts/make_paper_figures.py <synthetic_run_dir> [out_dir]

``synthetic_run_dir`` is a full-validation run of the bundled synthetic survey
(``gravanom run --dataset synthetic --validation full``). Every number and figure refers to
fictitious data with known truth; no real station is read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from scipy.interpolate import RegularGridInterpolator

from gravanom.analysis.compare import term_decomposition
from gravanom.config import PipelineConfig, ReductionConfig
from gravanom.density import density_diagnostics
from gravanom.flags import ERROR_FLAGS, QCFlag
from gravanom.gridding.cv import nested_cv
from gravanom.harmonize import harmonize
from gravanom.io.readers import read_grid_dir
from gravanom.io.schema import coerce_records
from gravanom.pipeline import build_catalogue, gridding_points, load_dataset, reduce_stations
from gravanom.qc import exclusion_mask, run_qc
from gravanom.reduction import compute_anomalies, curvature_bb
from gravanom.synthetic import LEGACY_DEFECTS, SyntheticSurvey, make_synthetic_survey, simulate_legacy_subsets

mpl.rcParams.update(
    {
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.labelsize": 8,
        "legend.fontsize": 7,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)
DIV = "RdBu_r"
SEQ = "viridis"
INK = "#27272a"
ACC = "#b45309"
COL = {"A": "#2166ac", "B": "#b2182b"}
METHODS = ("idw", "spline", "eqs", "rk_matern")
NAMES = {"idw": "IDW", "spline": "Trend + spline", "eqs": "Equiv. sources", "rk_matern": "RK Matérn"}


def load(run: Path, name: str) -> Any:
    return json.loads((run / name).read_text(encoding="utf-8"))


def stats(a: np.ndarray) -> dict[str, float]:
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    return {"mean": float(a.mean()), "min": float(a.min()), "max": float(a.max()), "sd": float(a.std())}


def km_axes(ax: plt.Axes) -> None:
    ax.set_aspect("equal")
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}"))
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}"))
    ax.set_xlabel("Easting (km)")
    ax.set_ylabel("Northing (km)")


def grid_extent(ds: Any) -> list[float]:
    x, y = ds["x"].values, ds["y"].values
    d = float(x[1] - x[0])
    return [x[0] - d / 2, x[-1] + d / 2, y[0] - d / 2, y[-1] + d / 2]


def save(fig: plt.Figure, out: Path, name: str) -> None:
    fig.tight_layout()
    fig.savefig(out / f"{name}.pdf")
    fig.savefig(out / f"{name}.png")
    plt.close(fig)


def usable_density_inputs(survey: SyntheticSurvey) -> dict[str, Any]:
    """Harmonize, QC and reduce a synthetic survey, then run the density diagnostics."""
    s = survey.stations
    rec = coerce_records(
        pd.DataFrame(
            {
                "source": "SYN",
                "source_id": s["id"],
                "lon": s["lon"],
                "lat": s["lat"],
                "height_m": s["height_m"],
                "g_obs_mgal": s["g_obs_mgal"],
                "tc_mgal": s["tc_mgal"],
                "bb_supplied_mgal": np.nan,
                "prov_file": "synthetic",
                "prov_sheet": "",
                "prov_row": np.arange(len(s)),
            }
        )
    )
    cat, log = harmonize([rec])
    cat, _ = run_qc(cat, log)
    cat = cat[~exclusion_mask(cat, [*ERROR_FLAGS, QCFlag.TC_SUSPECT])]
    an = compute_anomalies(cat)
    return density_diagnostics(an.faa_mgal, cat.height_m, cat.tc_mgal, cat.x_9377, cat.y_9377)


def main() -> int:
    run = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("paper/figures")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("fig*"):
        old.unlink()
    nums: dict[str, Any] = {"label": "SYNTHETIC - all values refer to fictitious data with known truth"}

    survey = make_synthetic_survey()
    cfg = PipelineConfig()
    sgrid = read_grid_dir(next((run / "grids").iterdir()))
    sup = sgrid["support_mask"].values == 1
    legacy = simulate_legacy_subsets(survey)

    # ---- Survey and QC -------------------------------------------------------------------------
    st = survey.stations
    nums["survey"] = {
        "n_records": len(st),
        "n_traverses": int(st["traverse"].nunique()),
        "height": stats(st["height_true_m"].to_numpy()),
        "cba_true": stats(survey.truth_cba),
        "spec": survey.metadata["spec"],
        "prisms": survey.metadata["prisms"],
    }
    qc = load(run, "qc_report.json")
    expected = {k: len(v) for k, v in survey.metadata["expected_flags"].items()}
    found = {k: qc["flag_counts"].get(k, 0) for k in expected}
    nums["qc"] = {"expected": expected, "found": found, "flag_counts": {k: v for k, v in qc["flag_counts"].items() if v}}
    nums["uncertainty"] = load(run, "uncertainty_report.json")["per_anomaly"]

    # ---- Fig. 1: synthetic survey ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(3.6, 4.0))
    gx, gy = survey.grid_x, survey.grid_y
    ext = [gx[0], gx[-1], gy[0], gy[-1]]
    im = ax.imshow(survey.topography[::-1], extent=ext, cmap="Greys", alpha=0.55, interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.7, label="Topography (m)")
    ax.contour(sgrid["x"].values, sgrid["y"].values, sup.astype(float), levels=[0.5], colors=ACC, linewidths=0.9)
    for lab, df in legacy.items():
        xy = st.set_index("id").loc[df["id"]]
        from gravanom.crs import to_analysis

        x, y = to_analysis(xy["lon"].to_numpy(), xy["lat"].to_numpy())
        ax.scatter(x, y, s=1.2, c=COL[lab], lw=0, label=f"Simulated legacy subset {lab} (n = {len(df)})")
    km_axes(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False, markerscale=4, ncol=1)
    ax.set_title("Synthetic survey and data-support mask")
    save(fig, out, "fig01_survey")

    # ---- Fig. 2 and Table 1: legacy reconciliation ----------------------------------------------------
    rec: dict[str, Any] = {}
    for lab, df in legacy.items():
        std = compute_anomalies(df)
        leg = compute_anomalies(df, ReductionConfig(legacy_mode=True))
        std2300 = compute_anomalies(df, ReductionConfig(density_kg_m3=2300.0))
        bb = curvature_bb(df["height_m"].to_numpy(), 2670.0)
        pos = df["height_m"].to_numpy() > 1.0
        ratio = df["bb_supplied_mgal"].to_numpy()[pos] / bb[pos]
        rec[lab] = {
            "n": len(df),
            "legacy_mode_max_abs_mgal": float(np.max(np.abs(leg["cba_mgal"] - df["abt"]))),
            "terms_standard2670_vs_legacy": term_decomposition(std, leg),
            "standard2300_minus_legacy": stats((std2300["cba_mgal"] - df["abt"]).to_numpy()),
            "bb_ratio_supplied_to_recomputed": {
                "median": float(np.median(ratio)),
                "q05": float(np.quantile(ratio, 0.05)),
                "q95": float(np.quantile(ratio, 0.95)),
            },
        }
    nums["legacy"] = {"injected": LEGACY_DEFECTS, "subsets": rec}
    allst = pd.concat(legacy.values(), ignore_index=True)
    d_rho = (
        compute_anomalies(allst)["cba_mgal"] - compute_anomalies(allst, ReductionConfig(density_kg_m3=2300.0))["cba_mgal"]
    )
    nums["density_scenario_2670_minus_2300"] = stats(d_rho.to_numpy())
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.6))
    axs[0].scatter(allst["height_m"], d_rho, s=2, c=INK, lw=0)
    axs[0].set_xlabel("Station height H (m)")
    axs[0].set_ylabel("CBA(2670) − CBA(2300) (mGal)")
    axs[0].set_title("(a) Reduction-density sensitivity")
    h = np.linspace(0, float(allst["height_m"].max()), 200)
    axs[1].plot(h, curvature_bb(h, 2670.0), color=INK, lw=0.8, ls="--", label="LaFehr (1991), ρ = 2670", zorder=3)
    for lab, df in legacy.items():
        axs[1].scatter(
            df["height_m"],
            -df["bb_supplied_mgal"],
            s=5,
            c=COL[lab],
            lw=0,
            label=f"Supplied BB, subset {lab} (sign-normalized)",
        )
    axs[1].set_xlabel("Station height H (m)")
    axs[1].set_ylabel("Curvature term BB (mGal)")
    axs[1].set_title("(b) Supplied vs recomputed Bullard B")
    axs[1].legend(frameon=False, loc="lower left")
    save(fig, out, "fig02_legacy")

    # ---- Fig. 3: variogram ------------------------------------------------------------------------
    vg = load(run, "variogram.json")
    fig, ax = plt.subplots(figsize=(3.6, 2.8))
    e = vg["experimental"]
    nmax = max(e["n_pairs"])
    ax.scatter(
        np.array(e["lag_m"]) / 1000,
        e["gamma_mgal2"],
        s=[8 + 30 * np.sqrt(n / nmax) for n in e["n_pairs"]],
        c=INK,
        lw=0,
        label="Experimental (omnidirectional)",
        zorder=3,
    )
    for d, ls in zip(vg["directional"], (":", "--", "-.", (0, (5, 1))), strict=False):
        ax.plot(
            np.array(d["lag_m"]) / 1000, d["gamma_mgal2"], ls=ls, color="#71717a", lw=0.8, label=f"{d['direction_deg']:g}°"
        )
    ax.plot(
        np.array(vg["fitted_curve"]["lag_m"]) / 1000,
        vg["fitted_curve"]["gamma_mgal2"],
        color=ACC,
        lw=1.6,
        label="Fitted Matérn",
    )
    ax.set_xlabel("Lag (km)")
    ax.set_ylabel("γ (mGal²)")
    ax.legend(frameon=False, ncol=2)
    save(fig, out, "fig04_variogram")
    nums["variogram"] = {
        "model": vg["model"],
        "params": vg["params"],
        "calibration_c": vg["calibration_c"],
        "anisotropy": vg["anisotropy_full_data"],
    }

    # ---- Fig. 4 and Table 2: block versus random cross-validation -------------------------------------------
    cvs = {m: load(run, f"cv/{m}.json") for m in METHODS}
    ds = load_dataset("synthetic")
    cat, _ = build_catalogue(ds)
    cat, table = reduce_stations(cat, cfg)
    pts, _ = gridding_points(cat, table, cfg.gridding)
    sens = load(run, "sensitivity.json")
    aniso = sens["anisotropy"]["parameters"]
    random_cv = {}
    for m in METHODS:
        r = nested_cv(
            m, pts, cfg.gridding, anisotropy=tuple(aniso) if (m == "rk_matern" and aniso) else None, block_size_m=250.0
        )  # <= 1 station per block: equivalent to random K-fold
        random_cv[m] = {"rmse": r["outer"]["rmse"]} | ({"calibrated": r["calibrated"]} if "calibrated" in r else {})
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.5))
    xs = np.arange(len(METHODS))
    axs[0].bar(
        xs - 0.2,
        [cvs[m]["outer"]["rmse"] for m in METHODS],
        0.4,
        color=[ACC if m == "rk_matern" else "#a1a1aa" for m in METHODS],
        label="Spatial block CV",
    )
    axs[0].bar(
        xs + 0.2,
        [random_cv[m]["rmse"] for m in METHODS],
        0.4,
        color="#e4e4e7",
        edgecolor="#a1a1aa",
        lw=0.6,
        label="Random CV",
    )
    axs[0].set_xticks(xs, [NAMES[m] for m in METHODS], rotation=30)
    axs[0].set_ylabel("Outer CV RMSE (mGal)")
    axs[0].legend(frameon=False)
    axs[0].set_title("(a) Method comparison")
    rk = cvs["rk_matern"]
    obs, pred = np.array(rk["points"]["observed"]), np.array(rk["points"]["predicted"])
    axs[1].scatter(obs, pred, s=1.5, c=INK, lw=0, alpha=0.6)
    lo, hi = obs.min(), obs.max()
    axs[1].plot([lo, hi], [lo, hi], color=ACC, lw=0.8)
    axs[1].set_xlabel("Observed CBA (mGal)")
    axs[1].set_ylabel("Predicted (mGal)")
    axs[1].set_title("(b) RK, held-out blocks")
    z = np.array(rk["points"]["z"])
    axs[2].hist(z, bins=np.linspace(-5, 5, 41), density=True, color="#a1a1aa")
    xx = np.linspace(-5, 5, 200)
    axs[2].plot(xx, np.exp(-(xx**2) / 2) / np.sqrt(2 * np.pi), color=ACC, lw=1)
    axs[2].set_xlabel("z = (obs − pred)/σ_cal")
    axs[2].set_title(f"(c) sd(z) = {rk['calibrated']['sd_z']:.2f}, cov95 = {rk['calibrated']['coverage95']:.3f}")
    save(fig, out, "fig05_validation")
    nums["validation"] = {
        "block": {
            m: {k: cvs[m][k] for k in ("outer", "fold_rmse_mean", "fold_rmse_sd")}
            | ({"calibrated": cvs[m]["calibrated"], "raw": cvs[m]["raw"]} if "calibrated" in cvs[m] else {})
            for m in METHODS
        },
        "random": random_cv,
        "selection": load(run, "selection.json"),
        "sensitivity": sens["sensitivity"],
        "anisotropy": {k: sens["anisotropy"][k] for k in ("n_folds_ratio_lt_0p7", "modelled", "parameters")}
        | {"ratios": [f.get("ratio") for f in sens["anisotropy"]["per_fold"]]},
        "cell_size": sens["cell_size"],
        "masks": sens["masks"],
        "rk_chosen_per_fold": [f["chosen"] for f in rk["folds"]],
    }

    # ---- Fig. 5: truth recovery -----------------------------------------------------------------------
    tr = RegularGridInterpolator((survey.grid_y, survey.grid_x), survey.truth_cba, bounds_error=False, fill_value=np.nan)
    xg, yg = np.meshgrid(sgrid["x"].values, sgrid["y"].values)
    truth = tr(np.column_stack([yg.ravel(), xg.ravel()])).reshape(xg.shape)
    err = np.where(sup, sgrid["value"].values - truth, np.nan)
    sig = sgrid["sigma_cal"].values
    ok = sup & np.isfinite(err) & np.isfinite(sig)
    out_mask = ~sup & np.isfinite(truth)
    pred_all = sgrid["value"].values
    nums["truth"] = {
        "rmse_inside_mask": float(np.sqrt(np.mean(err[ok] ** 2))),
        "coverage95_inside_mask": float(np.mean(np.abs(err[ok]) < 1.96 * sig[ok])),
        "supported_share": float(sup.mean()),
        "sigma_cal": {
            "median": float(np.median(sig[ok])),
            "p95": float(np.percentile(sig[ok], 95)),
            "max": float(np.max(sig[ok])),
        },
    }
    if np.isfinite(pred_all[out_mask]).any():
        e_out = pred_all[out_mask] - truth[out_mask]
        nums["truth"]["rmse_outside_mask"] = float(np.sqrt(np.nanmean(e_out**2)))
    ext2 = grid_extent(sgrid)
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.7))
    im = axs[0].imshow(
        truth[::-1],
        extent=ext2,
        cmap=DIV,
        norm=TwoSlopeNorm(float(np.nanmean(truth)), float(np.nanmin(truth)), float(np.nanmax(truth))),
        interpolation="nearest",
    )
    fig.colorbar(im, ax=axs[0], shrink=0.7, label="mGal")
    axs[0].set_title("(a) True CBA")
    el = float(np.nanpercentile(np.abs(err), 98))
    im = axs[1].imshow(err[::-1], extent=ext2, cmap=DIV, norm=TwoSlopeNorm(0, -el, el), interpolation="nearest")
    fig.colorbar(im, ax=axs[1], shrink=0.7, label="mGal")
    axs[1].set_title("(b) RK prediction − truth")
    im = axs[2].imshow(np.where(sup, sig, np.nan)[::-1], extent=ext2, cmap=SEQ, interpolation="nearest")
    fig.colorbar(im, ax=axs[2], shrink=0.7, label="mGal")
    axs[2].set_title("(c) Calibrated σ")
    for a in axs:
        km_axes(a)
    save(fig, out, "fig06_truth")

    # ---- Fig. 6: density diagnostics --------------------------------------------------------------------
    hr = usable_density_inputs(make_synthetic_survey(variant="high_relief"))
    lc = usable_density_inputs(make_synthetic_survey(variant="low_relief_correlated"))
    fig, axs = plt.subplots(1, 2, figsize=(7.0, 2.6))
    for d, lab, col in ((hr, "High relief, ρ_true = 2400", ACC), (lc, "Low relief, correlated, ρ_true = 2670", INK)):
        axs[0].plot(d["nettleton_curve"]["rho_kg_m3"], d["nettleton_curve"]["corr"], color=col, lw=1.2, label=lab)
    axs[0].axhline(0, color="#a1a1aa", lw=0.6)
    axs[0].set_xlabel("ρ (kg m⁻³)")
    axs[0].set_ylabel("corr(CBA_res(ρ), H_res)")
    axs[0].set_title("(a) Nettleton criterion")
    axs[0].legend(frameon=False)
    rows = [
        ("Nettleton, low relief", lc["nettleton"], INK),
        ("Parasnis, low relief", lc["parasnis"], INK),
        ("Nettleton, high relief", hr["nettleton"], ACC),
        ("Parasnis, high relief", hr["parasnis"], ACC),
    ]
    for i, (_lab, r, col) in enumerate(rows):
        lo_, hi_ = r["ci95_kg_m3"]
        axs[1].errorbar(
            r["estimate_kg_m3"],
            i,
            xerr=[[r["estimate_kg_m3"] - lo_], [hi_ - r["estimate_kg_m3"]]],
            fmt="o",
            color=col,
            capsize=2,
            ms=3,
        )
    axs[1].set_yticks(range(len(rows)), [r[0] for r in rows])
    axs[1].axvspan(1800, 3000, color="#f4f4f5", zorder=0)
    axs[1].axvline(2670, color=INK, lw=0.6, ls="--")
    axs[1].axvline(2400, color=ACC, lw=0.6, ls=":")
    axs[1].set_xlabel("ρ estimate and 95 % block-bootstrap CI (kg m⁻³)")
    axs[1].set_title("(b) Data-driven density estimates")
    save(fig, out, "fig03_density")
    keys = ("nettleton", "parasnis", "h5", "relief")
    nums["density"] = {"high_relief": {k: hr[k] for k in keys}, "low_relief_correlated": {k: lc[k] for k in keys}}

    (out.parent / "numbers.json").write_text(json.dumps(nums, indent=2, default=float) + "\n", encoding="utf-8")
    print("figures:", sorted(p.name for p in out.glob("*.pdf")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
