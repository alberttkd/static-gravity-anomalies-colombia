"""Spatial block cross-validation, nested hyper-parameter selection and calibration (§4.7, §5.5.5).

Nested scheme (per outer fold):

1. Inner block CV on the outer-training set evaluates every candidate
   (trend degree x Matérn nu for RK; depth x damping for EqS).
2. The candidate with the lowest inner RMSE is chosen; the calibration factor
   ``c = sd(z_inner)`` is estimated from its inner standardized errors.
3. The chosen candidate is refitted on the whole outer-training set and evaluated
   on the outer-test fold with ``sigma_cal = c * sigma_raw``.

The outer-fold scores are therefore honest estimates of predictive skill and of
uncertainty calibration.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import verde as vd
from numpy.typing import NDArray

from gravanom.config import GriddingConfig
from gravanom.gridding.gridders import EqSGridder, Gridder, IDWGridder, RegressionKriging, SplineGridder
from gravanom.gridding.variography import VariogramFitError

F64 = NDArray[np.float64]
log = logging.getLogger(__name__)

Factory = Callable[[], Gridder]


@dataclass(frozen=True)
class Points:
    """Gridding input: projected coordinates [m], values [mGal], heights [m]."""

    x: F64
    y: F64
    z: F64
    h: F64

    def take(self, idx: NDArray[np.int64]) -> Points:
        return Points(self.x[idx], self.y[idx], self.z[idx], self.h[idx])

    def __len__(self) -> int:
        return len(self.z)


@dataclass(frozen=True)
class Candidate:
    """A named gridder configuration."""

    label: str
    method: str
    factory: Factory
    params: dict[str, Any]


def block_folds(
    x: F64, y: F64, block_size_m: float, n_splits: int, random_state: int, max_reseed: int = 10
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    """Spatial block K-fold splits (``verde.BlockKFold``, shuffled, balanced).

    Folds with an empty test set trigger re-seeding (logged).
    """
    coords = np.column_stack([x, y])
    for attempt in range(max_reseed):
        seed = random_state + attempt
        kf = vd.BlockKFold(spacing=block_size_m, n_splits=n_splits, shuffle=True, random_state=seed, balance=True)
        folds = [(np.asarray(tr), np.asarray(te)) for tr, te in kf.split(coords)]
        if all(len(te) > 0 and len(tr) > 0 for tr, te in folds):
            if attempt:
                log.warning("block_folds: re-seeded %d time(s) to avoid empty folds", attempt)
            return folds
    raise RuntimeError("could not build non-empty block folds")


def metrics(obs: F64, pred: F64) -> dict[str, float]:
    """RMSE, MAE, mean error (obs - pred) and R² [mGal]."""
    e = obs - pred
    sst = float(np.sum((obs - obs.mean()) ** 2))
    return {
        "rmse": float(np.sqrt(np.mean(e**2))),
        "mae": float(np.mean(np.abs(e))),
        "me": float(np.mean(e)),
        "r2": 1.0 - float(np.sum(e**2)) / sst if sst > 0 else float("nan"),
        "n": len(e),
    }


def calibration_stats(z: F64) -> dict[str, float]:
    """sd(z) and the share with |z| < 1.96 (95 % coverage)."""
    z = z[np.isfinite(z)]
    return {"sd_z": float(np.std(z, ddof=1)), "coverage95": float(np.mean(np.abs(z) < 1.96)), "n": len(z)}


def cross_validate(
    factory: Factory, pts: Points, folds: list[tuple[NDArray[np.int64], NDArray[np.int64]]]
) -> dict[str, Any]:
    """Plain block CV of one candidate. Returns predictions, raw σ and fold metrics."""
    pred = np.full(len(pts), np.nan)
    sig = np.full(len(pts), np.nan)
    fold_id = np.full(len(pts), -1)
    per_fold = []
    for k, (tr, te) in enumerate(folds):
        g = factory().fit(*_args(pts.take(tr)))
        p, s = g.predict(pts.x[te], pts.y[te], pts.h[te])
        pred[te] = p
        if s is not None:
            sig[te] = s
        fold_id[te] = k
        per_fold.append(metrics(pts.z[te], p))
    out: dict[str, Any] = {
        "pred": pred,
        "sigma": sig,
        "fold": fold_id,
        "per_fold": per_fold,
        **metrics(pts.z, pred),
    }
    if np.isfinite(sig).all():
        out["z"] = (pts.z - pred) / sig
    return out


def _args(p: Points) -> tuple[F64, F64, F64, F64]:
    return p.x, p.y, p.z, p.h


def rk_candidates(cfg: GriddingConfig, anisotropy: tuple[float, float] | None = None) -> list[Candidate]:
    """RK candidates: trend degree x nu (``auto`` expands to {0,1,2} x {0.5,1.5,2.5})."""
    degrees = [0, 1, 2] if cfg.trend_degree == "auto" else [int(cfg.trend_degree)]
    nus = [0.5, 1.5, 2.5] if cfg.matern_nu == "auto" else [float(cfg.matern_nu)]
    anis: list[tuple[float, float] | None] = [None] if anisotropy is None else [None, anisotropy]
    out = []
    for d in degrees:
        for nu in nus:
            for a in anis:

                def f(d: int = d, nu: float = nu, a: tuple[float, float] | None = a) -> Gridder:
                    return RegressionKriging(d, nu, cfg.bin_m, cfg.max_lag_m, a)

                lab = f"rk_d{d}_nu{nu:g}" + ("_aniso" if a else "")
                out.append(
                    Candidate(
                        lab,
                        "rk_matern",
                        f,
                        {"trend_degree": d, "nu": nu, "anisotropy": list(a) if a else None},
                    )
                )
    return out


def eqs_candidates(cfg: GriddingConfig) -> list[Candidate]:
    """EqS candidates: depth x damping."""
    out = []
    for depth in cfg.eqs_depths_m:
        for damp in cfg.eqs_dampings:

            def f(depth: float = depth, damp: float = damp) -> Gridder:
                return EqSGridder(depth, damp)

            out.append(Candidate(f"eqs_{depth / 1000:g}km_{damp:g}", "eqs", f, {"depth_m": depth, "damping": damp}))
    return out


def baseline_candidates(method: str) -> list[Candidate]:
    """Single fixed configuration for IDW or spline."""
    if method == "idw":
        return [Candidate("idw_p2_k12", "idw", lambda: IDWGridder(), {"power": 2.0, "k": 12})]
    if method == "spline":
        return [Candidate("trend1_spline", "spline", lambda: SplineGridder(), {"trend_degree": 1})]
    raise ValueError(method)


def candidates_for(method: str, cfg: GriddingConfig, anisotropy: tuple[float, float] | None = None) -> list[Candidate]:
    if method == "rk_matern":
        return rk_candidates(cfg, anisotropy)
    if method == "eqs":
        return eqs_candidates(cfg)
    return baseline_candidates(method)


def select_candidate(
    cands: list[Candidate], pts: Points, folds: list[tuple[NDArray[np.int64], NDArray[np.int64]]]
) -> tuple[Candidate, dict[str, Any], list[dict[str, Any]]]:
    """Choose the candidate with the lowest block-CV RMSE; failed candidates are skipped."""
    scores: list[dict[str, Any]] = []
    best: tuple[Candidate, dict[str, Any]] | None = None
    for c in cands:
        try:
            res = cross_validate(c.factory, pts, folds)
        except (VariogramFitError, np.linalg.LinAlgError, ValueError) as exc:
            scores.append({"label": c.label, "failed": str(exc)[:200]})
            continue
        if not np.isfinite(res["rmse"]):
            scores.append({"label": c.label, "failed": "non-finite RMSE"})
            continue
        scores.append(
            {
                "label": c.label,
                "rmse": res["rmse"],
                **({"sd_z": calibration_stats(res["z"])["sd_z"]} if "z" in res else {}),
            }
        )
        if best is None or res["rmse"] < best[1]["rmse"]:
            best = (c, res)
    if best is None:
        raise VariogramFitError("every candidate failed")
    return best[0], best[1], scores


def nested_cv(
    method: str,
    pts: Points,
    cfg: GriddingConfig,
    anisotropy: tuple[float, float] | None = None,
    block_size_m: float | None = None,
    random_state: int | None = None,
) -> dict[str, Any]:
    """Nested spatial block CV for one method; see the module docstring.

    Returns a CV report with pooled outer metrics, per-fold details, the chosen
    candidates, calibrated z statistics and per-point outer residuals.
    """
    block = block_size_m or cfg.cv.block_size_m
    seed = cfg.cv.random_state if random_state is None else random_state
    outer = block_folds(pts.x, pts.y, block, cfg.cv.n_splits, seed)
    cands = candidates_for(method, cfg, anisotropy)
    pred = np.full(len(pts), np.nan)
    sig_raw = np.full(len(pts), np.nan)
    sig_cal = np.full(len(pts), np.nan)
    folds_out = []
    for k, (tr, te) in enumerate(outer):
        train = pts.take(tr)
        if len(cands) > 1 or method == "rk_matern":
            inner = block_folds(train.x, train.y, block, cfg.cv.n_splits, seed + 1000 + k)
            chosen, inner_res, scores = select_candidate(cands, train, inner)
            c = calibration_stats(inner_res["z"])["sd_z"] if "z" in inner_res else None
        else:
            chosen, scores, c = cands[0], [], None
        g = chosen.factory().fit(*_args(train))
        p, s = g.predict(pts.x[te], pts.y[te], pts.h[te])
        pred[te] = p
        if s is not None and c is not None:
            sig_raw[te] = s
            sig_cal[te] = c * s
        folds_out.append(
            {
                "fold": k,
                "n_train": len(tr),
                "n_test": len(te),
                "chosen": chosen.label,
                "params": g.params(),
                "calibration_c": c,
                "inner_scores": scores,
                **metrics(pts.z[te], p),
                **({"calibration": calibration_stats((pts.z[te] - p) / (c * s))} if s is not None and c is not None else {}),
            }
        )
    rep: dict[str, Any] = {
        "method": method,
        "block_size_m": block,
        "n_splits": cfg.cv.n_splits,
        "random_state": seed,
        "n_points": len(pts),
        "outer": metrics(pts.z, pred),
        "fold_rmse_mean": float(np.mean([f["rmse"] for f in folds_out])),
        "fold_rmse_sd": float(np.std([f["rmse"] for f in folds_out], ddof=1)),
        "folds": folds_out,
        "residual": pts.z - pred,
        "pred": pred,
    }
    if np.isfinite(sig_cal).all():
        rep["calibrated"] = calibration_stats((pts.z - pred) / sig_cal)
        rep["raw"] = calibration_stats((pts.z - pred) / sig_raw)
        rep["sigma_cal"] = sig_cal
    return rep


def select_method(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Selection rule of §5.12 / DEC-10.

    RK-Matérn is the default. EqS is chosen only if its outer block-CV RMSE is lower
    by more than 5 % *and* it has a calibrated uncertainty (not implemented in the
    MVP, so RK stays selected). Ties favour calibrated uncertainty.
    """
    rmse = {m: r["outer"]["rmse"] for m, r in reports.items()}
    choice = "rk_matern" if "rk_matern" in rmse else min(rmse, key=lambda m: rmse[m])
    rationale = ["RK-Matérn is the default (DEC-10)."]
    if "eqs" in rmse and "rk_matern" in rmse:
        better = rmse["eqs"] < 0.95 * rmse["rk_matern"]
        has_unc = "calibrated" in reports["eqs"]
        rationale.append(
            f"EqS RMSE {rmse['eqs']:.3f} vs RK {rmse['rk_matern']:.3f} mGal: "
            + ("more than 5 % lower" if better else "not more than 5 % lower")
            + ("; EqS has calibrated uncertainty." if has_unc else "; EqS has no calibrated uncertainty.")
        )
        if better and has_unc:
            choice = "eqs"
    idw = rmse.get("idw")
    ratio = rmse[choice] / idw if idw else None
    if ratio is not None:
        rationale.append(f"Selected/IDW RMSE ratio {ratio:.3f} (criterion <= 0.70).")
    return {"selected": choice, "rmse": rmse, "ratio_to_idw": ratio, "rationale": rationale}
