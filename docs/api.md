# API reference (v1)

Generated from the FastAPI OpenAPI schema (`scripts/export_openapi.py`; full schema in `openapi.json`).
Errors use `application/problem+json` (RFC 9457) with the stable codes `VALIDATION_ERROR`, `NOT_FOUND`,
`GRID_TOO_LARGE`, `INSUFFICIENT_DATA`, `VARIOGRAM_FIT_FAILED`, `PRIVATE_DATA_UNAVAILABLE` and `INTERNAL`.

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/datasets` | Datasets |
| GET | `/api/v1/datasets/{ds}/qc` | Dataset Qc |
| GET | `/api/v1/datasets/{ds}/stations` | Dataset Stations |
| POST | `/api/v1/gridding-jobs` | Create Gridding Job |
| GET | `/api/v1/gridding-jobs/{job_id}` | Gridding Job |
| GET | `/api/v1/grids/{grid_id}` | Grid Meta |
| GET | `/api/v1/grids/{grid_id}/contours` | Grid Contours |
| GET | `/api/v1/grids/{grid_id}/download` | Grid Download |
| GET | `/api/v1/grids/{grid_id}/image` | Grid Image |
| GET | `/api/v1/grids/{grid_id}/image-meta` | Grid Image Meta |
| POST | `/api/v1/grids/{grid_id}/profile` | Grid Profile |
| GET | `/api/v1/grids/{grid_id}/sample` | Grid Sample |
| GET | `/api/v1/grids/{grid_id}/validation` | Grid Validation |
| GET | `/api/v1/health` | Health |
| POST | `/api/v1/reductions` | Create Reduction |
| GET | `/api/v1/reductions/{run_id}/export` | Reduction Export |
| GET | `/api/v1/reductions/{run_id}/stations` | Reduction Stations |
| GET | `/api/v1/runs/{run_id}/manifest` | Run Manifest |
| POST | `/api/v1/sensitivity/density` | Density Sensitivity |
