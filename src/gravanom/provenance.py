"""Run manifests (§5.9): input/output hashes, configuration, versions, seeds, timestamps."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from gravanom.io.writers import write_json

#: Packages whose versions are recorded in every manifest.
TRACKED_PACKAGES = (
    "gravanom",
    "numpy",
    "pandas",
    "scipy",
    "xarray",
    "pyproj",
    "shapely",
    "rasterio",
    "harmonica",
    "verde",
    "gstools",
    "boule",
    "pydantic",
)


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file (hex)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def package_versions() -> dict[str, str]:
    """Installed versions of :data:`TRACKED_PACKAGES`."""
    out = {}
    for p in TRACKED_PACKAGES:
        try:
            out[p] = importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError:
            out[p] = "not installed"
    return out


def git_commit(cwd: str | Path | None = None) -> str | None:
    """Current Git commit (with ``-dirty`` suffix when the tree has changes), or None."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return sha + ("-dirty" if dirty else "")


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_run_id(config_hash: str, when: datetime | None = None) -> str:
    """``YYYYMMDDThhmmssZ-<config_hash[:8]>``."""
    t = (when or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{t}-{config_hash[:8]}"


class Manifest(BaseModel):
    """Provenance record of one run."""

    run_id: str
    dataset: str
    dataset_kind: str
    label: str = ""
    config: dict[str, Any]
    config_hash: str
    inputs: dict[str, str] = Field(default_factory=dict)
    """Input name -> SHA-256 (names only; never absolute private paths)."""
    outputs: dict[str, str] = Field(default_factory=dict)
    """Output path relative to the run directory -> SHA-256."""
    versions: dict[str, str] = Field(default_factory=dict)
    git_commit: str | None = None
    seeds: dict[str, int] = Field(default_factory=dict)
    python: str = Field(default_factory=platform.python_version)
    platform: str = Field(default_factory=platform.platform)
    started_utc: str = Field(default_factory=utc_now)
    finished_utc: str | None = None
    stages: list[str] = Field(default_factory=list)


def finalize_manifest(manifest: Manifest, run_dir: str | Path) -> Path:
    """Hash every file under ``run_dir`` (except the manifest) and write ``manifest.json``."""
    root = Path(run_dir)
    manifest.outputs = {
        p.relative_to(root).as_posix(): sha256_file(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    manifest.finished_utc = utc_now()
    return write_json(manifest, root / "manifest.json")
