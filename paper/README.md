# Paper

**Reproducible reduction and uncertainty-calibrated gridding of static gravity anomalies from
heterogeneous legacy compilations: a case study in northern Colombia.**

- `main.tex`: manuscript (IMRaD, author-year citations, line numbers for review).
- `references.bib`: references (DOIs verified against Crossref/DataCite).
- `figures/`: figures (PDF for the manuscript, PNG for quick viewing).
- `numbers.json`: every aggregate number quoted in the text, generated with the figures.
- `main.pdf`: compiled manuscript.
- `rbct/`: version for *Boletín de Ciencias de la Tierra* (Word template, blind and full manuscripts,
  cover letter, TIFF figures) and the submission status in `rbct/ESTADO_ENVIO.md`.

## Rebuild

```bash
# 1. Full validation run of the bundled synthetic survey
uv run gravanom run --dataset synthetic --validation full --artifacts artifacts
# 2. Figures and numbers (synthetic survey, simulated legacy subsets, density variants)
uv run python scripts/make_paper_figures.py artifacts/synthetic/<run_id> paper/figures
# 3. PDF (any LaTeX distribution; tested with Tectonic 0.15)
cd paper && tectonic main.tex
```

Every figure and number in the paper refers to fictitious data with known truth. No real station
data are used or distributed.
