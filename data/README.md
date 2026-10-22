# Data

| Folder | Content | In Git |
|---|---|---|
| `synthetic/` | Deterministic synthetic survey (`scripts/make_synthetic.py`), **SYNTHETIC**, CC BY 4.0 | Yes |
| `reference/` | Natural Earth 1:10m admin-0 polygon of Colombia (public domain) | Yes |
| `raw/`, `interim/`, `processed/` | Not used; real data are read in place | No (gitignored) |

The real workbooks are read in place through `GRAVANOM_PRIVATE_DATA_DIR`. They have
unknown provenance and licence (question Q1) and are treated as not redistributable.
