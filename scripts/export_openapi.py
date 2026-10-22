"""Export the API's OpenAPI schema to docs/openapi.json and a Markdown endpoint list to docs/api.md."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402


def main() -> int:
    spec = create_app(Settings(gravanom_public_mode=True)).openapi()
    (ROOT / "docs" / "openapi.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# API reference (v1)",
        "",
        "Generated from the FastAPI OpenAPI schema (`scripts/export_openapi.py`; full schema in `openapi.json`).",
        "Errors use `application/problem+json` (RFC 9457) with the stable codes `VALIDATION_ERROR`, `NOT_FOUND`,",
        "`GRID_TOO_LARGE`, `INSUFFICIENT_DATA`, `VARIOGRAM_FIT_FAILED`, `PRIVATE_DATA_UNAVAILABLE` and `INTERNAL`.",
        "",
        "| Method | Path | Summary |",
        "|---|---|---|",
    ]
    for path, ops in sorted(spec["paths"].items()):
        for method, op in ops.items():
            lines.append(f"| {method.upper()} | `{path}` | {op.get('summary', '')} |")
    (ROOT / "docs" / "api.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
