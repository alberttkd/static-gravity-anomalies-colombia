"""Request and response models of the API (reusing the core configuration models)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from gravanom.config import GriddingConfig, ReductionConfig

DatasetId = Literal["synthetic", "private"]


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReductionRequest(_Req):
    dataset: DatasetId = "synthetic"
    config: ReductionConfig = ReductionConfig()


class ReductionResponse(BaseModel):
    run_id: str
    config_hash: str
    dataset: str
    label: str
    summary: dict[str, Any]
    units: str = "mGal"


class DensityRequest(_Req):
    dataset: DatasetId = "synthetic"
    densities: Annotated[list[Annotated[float, Field(ge=1000, le=3500)]], Field(min_length=2, max_length=2)] = [
        2670.0,
        2300.0,
    ]


class GriddingRequest(_Req):
    run_id: str
    config: GriddingConfig = GriddingConfig()


class JobAccepted(BaseModel):
    job_id: str
    status: str


class ProfileRequest(_Req):
    coordinates: Annotated[
        list[Annotated[list[float], Field(min_length=2, max_length=2)]], Field(min_length=2, max_length=200)
    ]
    buffer_m: Annotated[float, Field(ge=0, le=20_000)] = 2000.0


class Health(BaseModel):
    status: str
    version: str
    git_sha: str | None
