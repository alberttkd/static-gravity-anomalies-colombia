"""Golden vectors (App. A) and reference cross-checks for the reduction formulas (P3 a-c)."""

from __future__ import annotations

import boule
import numpy as np
import pytest

from gravanom.reduction import (
    atmospheric,
    bb_cubic_approximation,
    bouguer_slab,
    curvature_bb,
    height_correction,
    honkasalo,
    normal_gravity_grs80,
    spherical_cap,
)


def test_normal_gravity_golden(golden: dict) -> None:
    g = golden["normal_gravity"]
    for lat, val in g["cases"]:
        assert normal_gravity_grs80(lat) == pytest.approx(val, abs=g["tolerance_mgal"])


def test_normal_gravity_matches_boule() -> None:
    lat = np.arange(-90, 90.01, 0.5)
    ref = boule.GRS80.normal_gravity((np.zeros_like(lat), lat, np.zeros_like(lat)))
    assert np.max(np.abs(normal_gravity_grs80(lat) - ref)) < 1e-3


@pytest.mark.parametrize(
    ("key", "func"),
    [("honkasalo", honkasalo), ("atmospheric", atmospheric)],
)
def test_single_argument_terms(golden: dict, key: str, func) -> None:  # type: ignore[no-untyped-def]
    g = golden[key]
    for arg, val in g["cases"]:
        assert func(arg) == pytest.approx(val, abs=g["tolerance_mgal"])


def test_height_correction_golden(golden: dict) -> None:
    g = golden["height_correction"]
    for lat, h, val in g["cases"]:
        assert height_correction(lat, h) == pytest.approx(val, abs=g["tolerance_mgal"])


def test_slab_golden(golden: dict) -> None:
    g = golden["slab"]
    for rho, h, val in g["cases"]:
        assert bouguer_slab(h, rho) == pytest.approx(val, abs=g["tolerance_mgal"])


def test_spherical_cap_golden(golden: dict) -> None:
    g = golden["spherical_cap"]
    for h, cap, bb in g["cases"]:
        assert spherical_cap(h, g["density_kg_m3"]) == pytest.approx(cap, abs=g["tolerance_mgal"])
        assert curvature_bb(h, g["density_kg_m3"]) == pytest.approx(bb, abs=g["tolerance_mgal"])


def test_cap_vs_cubic_approximation() -> None:
    h = np.linspace(0, 300, 3001)
    assert np.max(np.abs(curvature_bb(h, 2670.0) - bb_cubic_approximation(h))) < 5e-4


def test_cap_rejects_deep_negative_heights() -> None:
    with pytest.raises(ValueError):
        spherical_cap(-600.0, 2670.0)
