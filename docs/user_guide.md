# User guide

The web application has three areas: **controls** (left), the **map** (centre) and the
**inspector** (right). On small screens they stack vertically.

## Running it

| Mode | Command | Data |
|---|---|---|
| Full (API + UI, development) | `make run-api` and `make run-web`, then open http://localhost:5173 | Synthetic; private if `GRAVANOM_PRIVATE_DATA_DIR` is set |
| Full (Docker) | `docker compose -f docker/compose.yaml up --build`, then open http://localhost:8000 | Same; set `PRIVATE_DATA_HOST_DIR` to mount the real data read-only |
| Static demo | `make demo`, then serve `frontend/dist-static/` | Synthetic only, precomputed |

In the static demo, actions that need computation (arbitrary reduction parameters, new
gridding jobs, profiles, exports) explain that they need the API. The demo still shows the
2670 and 2300 kg/m³ runs, the precomputed grid, validation, QC, density diagnostics and provenance.

## Functional requirements and where to find them

| ID | Requirement | Where |
|---|---|---|
| FR-01 | Choose the synthetic or the private dataset | Header, **Dataset** selector. A badge always shows `SYNTHETIC DATA` or `PRIVATE DATA, NOT FOR REDISTRIBUTION`. |
| FR-02 | Station map coloured by FAA, SBA, CBA, residual, H, σ or QC flag; term-by-term breakdown | Left, **Station layer**. Click a station to see its principal facts and every reduction term in **Inspector → Station**. Flagged stations have an outlined marker. |
| FR-03 | QC report | **Inspector → QC**: flag counts, harmonization (shared ids, merged duplicates, σ_g from repeat pairs), the BB audit for the private data and a JSON download. |
| FR-04 | Reduction with editable parameters, including legacy mode | Left, **Reduction**: density (validated 1000-3500), curvature, Honkasalo, atmospheric, legacy mode. **Station layer → Δ vs reference** shows the difference from the default run. |
| FR-05 | Density sensitivity | **Inspector → Density**: ΔCBA statistics, the **Δ CBA (density)** map layer, the Nettleton curve, the Parasnis estimate and 95 % CIs, and the H5 verdict. |
| FR-06 | Gridding job | Left, **Gridding**: method (auto, RK Matérn, EqS, IDW, spline), target, cell size and mask distance. A progress bar is shown while the job runs. |
| FR-07 | Grid display | Left, **Grid layer**: value, calibrated σ, regional, residual. Unsupported cells are transparent and cells with σ > 5 mGal are hatched. Labelled contours (5 mGal, or 1 mGal for the residual), opacity slider, and a colour bar in mGal. |
| FR-08 | Validation | **Inspector → Validation**: RMSE, sd(z) and coverage; method comparison; variogram (experimental points sized by pair count, fitted Matérn and directional curves); predicted vs observed; z histogram with N(0,1); per-fold table. |
| FR-09 | Profile tool | **Inspector → Profile**: draw on the map or type `lon,lat; lon,lat` (keyboard alternative). The chart shows the grid ± 2σ, the stations within the buffer with error bars, and H on a secondary axis. |
| FR-10 | Regional/residual | **Grid layer → Regional / Residual** (degree-2 regional field); **Station layer → Residual**. |
| FR-11 | Exports | Header, **Export**: stations as CSV, GeoPackage, GeoParquet or GeoJSON; grids as a COG GeoTIFF or NetCDF. Every download includes `metadata.json` and the manifest. |
| FR-12 | Provenance | Header **Provenance** or **Inspector → Provenance**: run, config hash, input SHA-256, seeds, versions, Git commit, resolved configuration and references. |

## Reading the maps

- **Anomalies** use a diverging blue-red map (ColorBrewer RdBu, colour-blind safe) centred at
  0 mGal, with symmetric limits at the robust 2-98 % range. **Heights and σ** use viridis. The
  amber interface colour never encodes data.
- The basemap is Natural Earth. Display is in EPSG:3857; all analysis is in EPSG:9377 metres.
- Geological readings of the anomalies are hypotheses (MASTER_GUIDE §4.9), not results.

## Design

The interface follows the Figma file *Grav Anomaly Explorer - UI* (foundations, light and dark
explorer screens). It uses Geist and Geist Mono with tabular figures, 1 px rules instead of
cards, a 6 px radius, one amber accent, and light/dark themes that follow the system setting
(toggle in the header). Press feedback is a 160 ms scale, and reduced motion is respected.
