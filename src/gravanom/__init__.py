"""gravanom: reproducible static gravity anomalies (FAA, SBA, CBA) with quantified uncertainty."""

from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path

__version__ = "0.1.0"


def _use_bundled_geodata() -> None:
    """Point PROJ/GDAL at the data bundled with the rasterio wheel.

    A foreign ``PROJ_LIB``/``GDAL_DATA`` (e.g. from a PostGIS install) can hold an
    incompatible ``proj.db`` and break EPSG lookups. Set ``GRAVANOM_KEEP_GEO_ENV=1``
    to keep the inherited values.
    """
    if os.environ.get("GRAVANOM_KEEP_GEO_ENV") == "1":
        return
    spec = find_spec("rasterio")
    if spec is None or spec.origin is None:
        return
    base = Path(spec.origin).parent
    proj, gdal = base / "proj_data", base / "gdal_data"
    if proj.is_dir():
        os.environ["PROJ_DATA"] = str(proj)
        os.environ["PROJ_LIB"] = str(proj)
    if gdal.is_dir():
        os.environ["GDAL_DATA"] = str(gdal)


_use_bundled_geodata()
