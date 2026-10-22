# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [SemVer](https://semver.org/).

## [0.1.0] - 2026-10-22

### Added
- P0: environment report and legacy-reproduction checks (kept private).
- P1: package scaffold, configuration models, constants, CI, docs and ADRs 0001-0014.
- P2: legacy readers with explicit column maps, harmonization, QC rules, deterministic synthetic dataset.
- P3: reduction engine (GRS80, Honkasalo, atmospheric, second-order height, LaFehr cap), legacy mode.
- P4: linear and Monte Carlo station uncertainty; Nettleton/Parasnis diagnostics with block bootstrap.
- P5: Matérn WLS variography, regression kriging, EqS, IDW/spline baselines, nested block CV, calibration, masks.
- P6: trend/residual decomposition, profiles, contours, run comparisons.
- P7: FastAPI backend (`/api/v1`).
- P8: React + MapLibre frontend (design system in Figma), static demo mode, light/dark themes.
- P9: Playwright acceptance tests AT-01..AT-08 and axe checks, Docker deployment, Pages workflow.
- Paper (`paper/`): methods paper verified on the synthetic benchmark (simulated legacy subsets,
  density variants, random versus spatial block cross-validation).

### Test-private log
- 2026-10-22: private legacy-reproduction tests and e2e AT-05 passed (local only).
