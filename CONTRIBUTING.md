# Contributing

## Setup

```bash
uv sync --all-extras
cd frontend && npm ci
```

## Checks before a pull request

```bash
make lint typecheck test      # Python
cd frontend && npm run lint && npm test && npm run build
```

Run `make science` for the scientific validation suite and, locally only, `make test-private`
with `GRAVANOM_PRIVATE_DATA_DIR` set.

## Rules

- **No real data in Git**, ever: not in commits, fixtures, snapshots, logs or screenshots.
  Only aggregate statistics may appear in issues or documentation.
- Every physical formula has a NumPy-style docstring with equation, units, sign convention and reference.
- Units appear in names (`_mgal`, `_m`, `_kg_m3`, `_deg`).
- Conventional Commits; one logical change per commit.
- A design decision that changes a DEC-xx needs a new ADR in `docs/adr/`.

## PR checklist

- [ ] Tests added or updated; `make test` green
- [ ] No real data or absolute private paths in the diff
- [ ] Docs updated (user guide, science pages or ADR)
