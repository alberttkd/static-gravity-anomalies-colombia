"""Dataset service: loads, harmonizes and QC-checks datasets once and caches them."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.errors import not_found
from app.settings import Settings
from gravanom.pipeline import PrivateDataUnavailableError, build_catalogue, load_dataset, private_data_dir
from gravanom.qc import QCReport, add_post_reduction_flags
from gravanom.reduction import compute_anomalies


@dataclass
class DatasetEntry:
    """A loaded dataset (catalogue after QC) and its input hashes."""

    id: str
    kind: str
    label: str
    catalogue: pd.DataFrame
    qc: QCReport
    inputs: dict[str, str]

    def summary(self) -> dict[str, Any]:
        lon, lat = self.catalogue["lon"].to_numpy(), self.catalogue["lat"].to_numpy()
        ok = np.isfinite(lon) & np.isfinite(lat)
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "n_stations": len(self.catalogue),
            "extent": [float(lon[ok].min()), float(lat[ok].min()), float(lon[ok].max()), float(lat[ok].max())],
        }


class DatasetService:
    """Cache of datasets. The private dataset exists only outside public mode."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[str, DatasetEntry] = {}
        self._lock = threading.Lock()

    def available_ids(self) -> list[str]:
        ids = ["synthetic"]
        # The server settings are authoritative: no fallback to the process environment.
        if not self.settings.gravanom_public_mode and self.settings.gravanom_private_data_dir:
            try:
                private_data_dir(self.settings.gravanom_private_data_dir)
                ids.append("private")
            except PrivateDataUnavailableError:
                pass
        return ids

    def get(self, ds_id: str) -> DatasetEntry:
        if ds_id == "private" and self.settings.gravanom_public_mode:
            raise PrivateDataUnavailableError("the private dataset is disabled in public mode")
        if ds_id == "private" and not self.settings.gravanom_private_data_dir:
            raise PrivateDataUnavailableError("no private data directory is configured")
        if ds_id not in ("synthetic", "private"):
            raise not_found(f"dataset '{ds_id}'")
        with self._lock:
            if ds_id not in self._cache:
                ds = load_dataset(ds_id, private_dir=self.settings.gravanom_private_data_dir)
                cat, qc = build_catalogue(ds)
                cat = add_post_reduction_flags(cat, compute_anomalies(cat))
                self._cache[ds_id] = DatasetEntry(ds_id, ds.kind, ds.label, cat, qc, ds.inputs)
            return self._cache[ds_id]
