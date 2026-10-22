# Validation

The validation uses nested spatial block cross-validation. The outer loop has 5 folds with
15 km blocks. Inner folds choose the hyper-parameters and estimate the calibration factor, so
the outer scores are honest estimates. For comparison, the same protocol is repeated with
250 m blocks, which hold at most one station each and are equivalent to random 5-fold CV.

## Synthetic benchmark (1,996 stations, known truth)

| Method | Block RMSE (mGal) | Fold RMSE mean ± sd | Random RMSE | sd(z) | 95 % coverage |
|---|---|---|---|---|---|
| IDW p=2, k=12 | 2.49 | 2.42 ± 0.63 | 0.49 | — | — |
| Trend(1) + spline | 0.69 | 0.69 ± 0.11 | 0.40 | — | — |
| EqS | 0.94 | 0.89 ± 0.32 | 0.38 | — | — |
| **RK-Matérn** | **0.74** | 0.72 ± 0.15 | 0.38 | **0.90** | **0.956** |

The RK/IDW RMSE ratio is stable across fold layouts:

- Seeds 20261022, 20261023 and 20261024: 0.297, 0.272 and 0.362 (mean 0.310).
- 10 km blocks: 0.313. 25 km blocks: 0.339.

Calibration holds in every configuration (coverage 0.956–0.972).

Random CV understates the error by a factor of 5.1 for IDW, 2.5 for EqS, 2.0 for RK and 1.7
for the spline, and it would rank the methods differently.

**Truth recovery:** inside the support mask the RK grid differs from the true field by
0.27 mGal RMS, and the calibrated σ covers the truth at the nominal rate (0.953). The mask
retains 65 % of the synthetic square.

**Cell-size sensitivity:** RMS(250 m − bilinear 500 m) = 0.002 mGal, below the 0.2 mGal limit.

Figures and numbers: `scripts/make_paper_figures.py` and `paper/numbers.json`.
