# ADR 0014: Python core + FastAPI + React/MapLibre with file artifacts

- Status: accepted (2026-10-22)
- Decision record: DEC-14 in MASTER_GUIDE §4.10

## Context

~2k points and grids < 10 MB: no database server needed.

## Decision

gravanom (Python), FastAPI backend, TypeScript/React/MapLibre frontend, GeoParquet/COG/JSON artifacts.

## Change if

More than 10⁶ stations or multi-user editing: add PostGIS and a job queue.
