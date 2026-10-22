# Environment report (phase P0)

Date: 2026-10-22. Machine: the author's Windows laptop.

## Operating system and shell

| Item | Value |
|---|---|
| OS | Windows 11 Home Single Language 10.0.26200 |
| Shells | PowerShell 5.1; Git Bash (MINGW64 / MSYS 3.6.6) |

## Tools

| Tool | Version | Note |
|---|---|---|
| Python (system) | 3.14.3 | Outside the supported range (≥ 3.11, < 3.14). Not used. |
| Python (project) | 3.12.13 | Installed by `uv python install 3.12` |
| uv | 0.11.21 | Package and environment manager |
| Node.js | 24.14.1 | |
| npm | 11.11.0 | |
| Git | 2.53.0.windows.2 | |
| Docker | 29.6.1 | Optional |

## Scientific libraries resolved

`uv pip install harmonica boule verde gstools rasterio rioxarray pyproj geopandas xarray …` resolved to:

| Package | Version | Guide §6.3 (audit time) |
|---|---|---|
| harmonica | 0.7.0 | 0.7.0 |
| boule | 0.6.0 | 0.6.0 |
| verde | 1.9.0 | 1.9.0 |
| gstools | 1.7.0 | 1.7.0 |
| pyproj | 3.8.0 | 3.8.0 |
| rasterio | 1.5.2 | — |
| rioxarray | 0.23.0 | — |
| numpy | 2.5.4 | — |
| pandas | 3.0.6 | — |
| scipy | 1.18.1 | — |
| xarray | 2026.9.0 | — |
| pydantic | 2.14.1 | — |
| fastapi | (see `uv.lock`) | — |

The exact versions are pinned in `pyproject.toml` / `uv.lock` (phase P1).

## Legacy-file hashes

`docs/audit/legacy_hashes.md` records the SHA-256 of the three legacy workbooks and the subset A archive, by subset label. They were re-checked at the end of each phase and never changed.

## Audit reproduction

`python scripts/audit_reproduction.py` → **18/18 checks passed** (App. C, C1–C16, plus C1b `.xls == .xlsx` and C9b for subset B). Exit code 0. Only aggregate statistics are printed.

## Q12: content of the subset A archive

Listed with `7z l -slt` (no extraction). It contains exactly the 8 files of the subset A folder (report, map exports, workbook and CSV exports). Every member's CRC32 and size equal those of the folder copies. The archive is a duplicate, so it is ignored.
