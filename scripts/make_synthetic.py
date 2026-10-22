"""Generate the committed synthetic dataset in ``data/synthetic/`` (deterministic)."""

from __future__ import annotations

import sys
from pathlib import Path

from gravanom.synthetic import make_synthetic_survey, write_synthetic


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "synthetic"
    paths = write_synthetic(make_synthetic_survey(), out)
    for name, p in paths.items():
        print(f"{name}: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
