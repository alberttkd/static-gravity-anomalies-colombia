"""Application services: orchestration of the scientific core, caching and artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.datasets import DatasetService
from app.services.grids import GridService
from app.services.runs import RunService
from app.settings import Settings


@dataclass
class Services:
    settings: Settings
    datasets: DatasetService
    runs: RunService
    grids: GridService


def build_services(settings: Settings) -> Services:
    datasets = DatasetService(settings)
    runs = RunService(settings, datasets)
    return Services(settings, datasets, runs, GridService(settings, runs))
