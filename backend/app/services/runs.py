"""Reduction runs: synchronous reductions with per-station σ, cached by dataset + config hash."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from app.errors import not_found
from app.services.datasets import DatasetEntry, DatasetService
from app.settings import REPO_ROOT, Settings
from gravanom.analysis.trend import station_residual
from gravanom.config import ReductionConfig, UncertaintyConfig, config_hash
from gravanom.flags import ERROR_FLAGS, QCFlag
from gravanom.provenance import Manifest, finalize_manifest, git_commit, make_run_id, package_versions
from gravanom.qc import exclusion_mask
from gravanom.reduction import compute_anomalies
from gravanom.uncertainty import propagate

SUMMARY_COLUMNS = ("faa_mgal", "sba_mgal", "cba_mgal", "sigma_cba_mgal")


@dataclass
class ReductionRun:
    """One reduction run on a dataset."""

    run_id: str
    dataset: DatasetEntry
    config: ReductionConfig
    table: pd.DataFrame
    manifest: Manifest

    def summary(self) -> dict[str, Any]:
        usable = ~exclusion_mask(self.dataset.catalogue, list(ERROR_FLAGS))
        out: dict[str, Any] = {
            "n_stations": len(self.table),
            "n_excluded_error_flags": int((~usable).sum()),
            "units": "mGal",
            "label": self.dataset.label,
        }
        for c in SUMMARY_COLUMNS:
            v = self.table[c].to_numpy(dtype=float)[usable]
            v = v[np.isfinite(v)]
            if v.size == 0:
                out[c] = {"mean": None, "min": None, "max": None, "n": 0}
                continue
            out[c] = {"mean": float(v.mean()), "min": float(v.min()), "max": float(v.max()), "n": int(v.size)}
        return out


class RunService:
    """Creates and caches reduction runs; persists anomaly tables and manifests to the artifact store."""

    def __init__(self, settings: Settings, datasets: DatasetService) -> None:
        self.settings = settings
        self.datasets = datasets
        self._runs: dict[str, ReductionRun] = {}
        self._by_key: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def reduce(self, ds_id: str, config: ReductionConfig) -> ReductionRun:
        entry = self.datasets.get(ds_id)
        chash = config_hash(config)
        with self._lock:
            if (ds_id, chash) in self._by_key:
                return self._runs[self._by_key[(ds_id, chash)]]
        an = compute_anomalies(entry.catalogue, config)
        sig = propagate(entry.catalogue, config, UncertaintyConfig())
        table = pd.concat(
            [entry.catalogue[["station_uid"]].reset_index(drop=True), an.reset_index(drop=True), sig.reset_index(drop=True)],
            axis=1,
        )
        cat = entry.catalogue
        usable = ~exclusion_mask(cat, [*ERROR_FLAGS, QCFlag.TC_SUSPECT])
        table["cba_residual_mgal"] = station_residual(
            cat["x_9377"].to_numpy(), cat["y_9377"].to_numpy(), table["cba_mgal"].to_numpy(), usable
        )
        run_id = make_run_id(chash, datetime.now(UTC))
        manifest = Manifest(
            run_id=run_id,
            dataset=ds_id,
            dataset_kind=entry.kind,
            label=entry.label,
            config={"reduction": config.model_dump(mode="json"), "uncertainty": UncertaintyConfig().model_dump(mode="json")},
            config_hash=chash,
            inputs=entry.inputs,
            versions=package_versions(),
            git_commit=git_commit(REPO_ROOT),
            seeds={"uncertainty": UncertaintyConfig().random_state},
        )
        run_dir = self.settings.api_artifacts / ds_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        table.assign(config_hash=chash).to_parquet(run_dir / "anomalies.parquet", index=False)
        finalize_manifest(manifest, run_dir)
        run = ReductionRun(run_id, entry, config, table, manifest)
        with self._lock:
            self._runs[run_id] = run
            self._by_key[(ds_id, chash)] = run_id
        return run

    def get(self, run_id: str) -> ReductionRun:
        with self._lock:
            if run_id not in self._runs:
                raise not_found(f"run '{run_id}'")
            return self._runs[run_id]
