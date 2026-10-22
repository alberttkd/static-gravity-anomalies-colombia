"""Configuration models (MASTER_GUIDE §5.7 and §6.9).

One set of Pydantic models serves the YAML configuration files, the API request
validation and the OpenAPI schema. Every product records the resolved
configuration and its hash (:func:`config_hash`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gravanom.flags import QCFlag


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReductionConfig(_Model):
    """Parameters of the station reduction chain (§5.5.2)."""

    normal_gravity: Literal["GRS80_closed_form"] = "GRS80_closed_form"
    height_correction: Literal["hinze2005_second_order", "legacy_0.3086_0.073"] = "hinze2005_second_order"
    honkasalo: bool = True
    atmospheric: bool = True
    density_kg_m3: Annotated[float, Field(ge=1000, le=3500)] = 2670.0
    curvature: Literal["lafehr1991_closed_form", "supplied_bb_legacy", "none"] = "lafehr1991_closed_form"
    terrain_source: Literal["supplied"] = "supplied"
    terrain_reference_density_kg_m3: Annotated[float, Field(ge=1000, le=3500)] = 2670.0
    legacy_mode: bool = False
    """When True, the legacy spreadsheet formulas of App. B are applied exactly."""


class MaskConfig(_Model):
    """Reliability masks (§5.5.8)."""

    max_distance_m: Annotated[float, Field(ge=1000, le=20000)] = 5000.0
    use_convex_hull: bool = True
    max_sigma_mgal: Annotated[float, Field(ge=0.5, le=50)] = 5.0


class CVConfig(_Model):
    """Spatial block cross-validation (§4.7, DEC-11)."""

    block_size_m: Annotated[float, Field(ge=5000, le=50000)] = 15000.0
    n_splits: Annotated[int, Field(ge=3, le=10)] = 5
    random_state: int = 20261022


class GriddingConfig(_Model):
    """Gridding of station anomalies (§5.5.5)."""

    target: Literal["FAA", "SBA", "CBA", "residual"] = "CBA"
    method: Literal["auto", "rk_matern", "eqs", "idw", "spline"] = "auto"
    cell_size_m: Annotated[float, Field(ge=100, le=5000)] = 500.0
    trend_degree: Literal[0, 1, 2, "auto"] = "auto"
    matern_nu: float | Literal["auto"] = "auto"
    """Matérn smoothness: 0.5, 1.5, 2.5 or "auto". The Gaussian model is excluded (F-09)."""
    max_lag_m: Annotated[float, Field(ge=5_000, le=100_000)] = 30_000.0
    bin_m: Annotated[float, Field(ge=250, le=5_000)] = 1_500.0
    eqs_depths_m: tuple[float, ...] = (7_000.0, 10_000.0, 14_000.0, 20_000.0)
    eqs_dampings: tuple[float, ...] = (0.01, 0.1, 1.0)
    exclude_flags: tuple[QCFlag, ...] = (
        QCFlag.ERROR_SCHEMA,
        QCFlag.ERROR_RANGE,
        QCFlag.CONFLICT_SHARED_ID,
    )
    mask: MaskConfig = MaskConfig()
    cv: CVConfig = CVConfig()

    @field_validator("matern_nu", mode="before")
    @classmethod
    def _admissible_nu(cls, v: object) -> object:
        if v == "auto" or (isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) in (0.5, 1.5, 2.5)):
            return v
        raise ValueError("matern_nu must be 0.5, 1.5, 2.5 or 'auto' (the Gaussian model is excluded)")


class UncertaintyConfig(_Model):
    """Station error budget (§5.5.3). Defaults pending Q8."""

    sigma_g_mgal: Annotated[float, Field(ge=0)] = 0.10
    sigma_h_m: Annotated[float, Field(ge=0)] = 1.0
    sigma_tc_rel: Annotated[float, Field(ge=0)] = 0.10
    sigma_pos_m: Annotated[float, Field(ge=0)] = 50.0
    mc_draws: Annotated[int, Field(ge=100, le=100_000)] = 2000
    random_state: int = 20261022


class DensityConfig(_Model):
    """Density diagnostics (§5.5.4)."""

    rho_min_kg_m3: float = 1800.0
    rho_max_kg_m3: float = 3000.0
    rho_step_kg_m3: float = 10.0
    trend_degree: Literal[0, 1, 2] = 2
    bootstrap_block_m: float = 15_000.0
    bootstrap_replicates: Annotated[int, Field(ge=50, le=10_000)] = 1000
    scenarios_kg_m3: tuple[float, ...] = (2300.0, 2670.0)
    random_state: int = 20261022


class PipelineConfig(_Model):
    """All stage configurations of one pipeline run."""

    reduction: ReductionConfig = ReductionConfig()
    gridding: GriddingConfig = GriddingConfig()
    uncertainty: UncertaintyConfig = UncertaintyConfig()
    density: DensityConfig = DensityConfig()


def canonical_json(model: BaseModel) -> str:
    """Serialize a model to canonical JSON (sorted keys, no whitespace)."""
    return json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def config_hash(model: BaseModel) -> str:
    """SHA-256 of the canonical JSON of a configuration model (hex string)."""
    return hashlib.sha256(canonical_json(model).encode("utf-8")).hexdigest()


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Read a YAML file into a dictionary (empty file gives an empty dict)."""
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return data


def load_reduction_config(path: str | Path) -> ReductionConfig:
    """Load a :class:`ReductionConfig` from YAML (keys under ``reduction:`` or top-level)."""
    data = load_yaml(path)
    return ReductionConfig.model_validate(data.get("reduction", data))


def load_gridding_config(path: str | Path) -> GriddingConfig:
    """Load a :class:`GriddingConfig` from YAML (keys under ``gridding:`` or top-level)."""
    data = load_yaml(path)
    return GriddingConfig.model_validate(data.get("gridding", data))
