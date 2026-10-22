"""Smoke test: package imports and constants (P1)."""

from __future__ import annotations

import gravanom
from gravanom.constants import GRS80, G


def test_import_and_constants() -> None:
    assert gravanom.__version__
    assert G == 6.67430e-11
    assert GRS80.a_m == 6_378_137.0 and GRS80.f == 0.003_352_810_681
