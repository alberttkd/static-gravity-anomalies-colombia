# static-gravity-anomalies-colombia

Software: **grav-anomaly-explorer** (`gravanom`). Paper: [`paper/`](paper/).

Reproducible reduction, quality control and gridding of **static gravity anomalies**
(free-air, simple Bouguer and complete Bouguer) with quantified uncertainty, plus a
web application to explore them.

Documentation: [`docs/`](docs/) (science notes and decision records).

## Scientific scope

The software computes the static, single-epoch spatial variation of the gravity field
from land gravity compilations, including heterogeneous legacy subsets:

- **FAA**: free-air anomaly, `g + g_H − γ0 + δg_h + δg_atm`
- **SBA**: simple (planar) Bouguer anomaly, `FAA − 2πGρH`
- **CBA**: complete Bouguer anomaly, `FAA − BC_cap + TC_ρ` (Bullard A + B + C)

It follows Hinze et al. (2005): GRS80 normal gravity, the atmospheric correction, the
Honkasalo term, the second-order height correction, the LaFehr (1991) spherical cap
and the supplied terrain corrections. The reference density is 2670 kg m⁻³, and the
legacy value of 2300 kg m⁻³ is kept as a sensitivity scenario.

Temporal gravity change and surface deformation are **out of scope**: the workflow handles
one epoch only. All published results, figures and numbers come from the deterministic synthetic
benchmark.

## Quick start (synthetic data)

Requirements: [uv](https://docs.astral.sh/uv/) (Python 3.12–3.13, installed by uv) and,
for the web app, Node.js 20+.

```bash
uv sync --all-extras            # Python environment from uv.lock
uv run gravanom run --dataset synthetic   # full pipeline S1–S9 into artifacts/
uv run pytest                   # unit, integration, science and API tests
```

On Windows, enable long paths (`git config --global core.longpaths true`) if a checkout fails.

### Web application

```bash
uv run uvicorn app.main:app --app-dir backend --port 8000   # API at /api/v1
cd frontend && npm ci && npm run dev                        # UI at http://localhost:5173
```

Static demo (synthetic only, no backend):

```bash
uv run gravanom export-static-demo --out frontend/public/demo
cd frontend && npm run build:static
```

## Using the private (real) data

The real data are **not** in this repository and are never committed
(see the data policy below). Point the software at the folder that holds them:

```bash
export GRAVANOM_PRIVATE_DATA_DIR="/path/to/legacy-data"
cp config/private_sources.example.yaml config/private_sources.yaml   # then edit the paths
uv run gravanom run --dataset private
uv run pytest -m private        # legacy-reproduction tests (local only)
```

The legacy workbooks are opened read-only.

## Command-line interface

| Command | Stage |
|---|---|
| `gravanom ingest` | S1–S2: read sources, harmonize, write `stations.parquet` |
| `gravanom qc` | S3: QC flags and `qc_report.json` |
| `gravanom reduce` | S4–S6: anomalies, uncertainty, density diagnostics |
| `gravanom grid` | S7–S9: variography, gridding, block CV, masks, products |
| `gravanom run` | All stages |
| `gravanom export-static-demo` | Precomputed synthetic artifacts for the static web demo |

## Data policy

1. The real data have unknown provenance and licence. They are treated as
   **not redistributable**: they are never committed, deployed, or included in issues,
   tests, fixtures or logs beyond aggregate statistics.
2. Synthetic data in `data/synthetic/` are generated deterministically, released under
   CC BY 4.0 and labelled `SYNTHETIC` in every file, map and API response.
3. No station record, grid, figure or statistic derived from real data is published. The paper
   in `paper/` uses the synthetic benchmark only.
4. Third-party data: Natural Earth boundaries (public domain).

## How to cite

See [`CITATION.cff`](CITATION.cff).

## Licence

Code: BSD-3-Clause ([`LICENSE`](LICENSE)). Documentation and synthetic data: CC BY 4.0
([`LICENSE-docs`](LICENSE-docs)).
