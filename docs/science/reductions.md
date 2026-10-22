# Station reductions

All corrections are values *added* to the observed-gravity side (Hinze et al., 2005):

| Term | Formula | Typical value |
|---|---|---|
| Honkasalo | $0.0371(1-3\sin^2\varphi)$ | +0.034 mGal at 9°N |
| Atmospheric | $0.874-9.9\times10^{-5}h+3.56\times10^{-9}h^2$ | +0.87 mGal near sea level |
| Height | $(0.3087691-0.0004398\sin^2\varphi)h-7.2125\times10^{-8}h^2$ | 0.309 mGal/m |
| Slab | $2\pi G\rho h$ | 0.112 mGal/m at 2670 |
| Spherical cap | LaFehr (1991) closed form | BB = 0.13 mGal at 92 m |

$$FAA = g + g_H - \gamma_0 + \delta g_h + \delta g_{atm},\quad SBA = FAA - BC_{slab},\quad CBA = FAA - BC_{cap} + TC\,\rho/\rho_{TC}.$$

## Legacy mode

`ReductionConfig(legacy_mode=True)` reproduces typical legacy spreadsheet formulas exactly:
ρ = 2300 kg m⁻³, the 0.3086 h − 0.073 (h/1000)² free-air term, and the *supplied* BB added
to ABS and ABT.

## Term-by-term reconciliation (synthetic benchmark)

`gravanom.synthetic.simulate_legacy_subsets` splits the synthetic survey into two simulated
legacy subsets and reduces them with the legacy formulas. Subset A supplies the curvature term
with the correct sign; subset B supplies it with the opposite sign and 8 % too large.

| Term (standard ρ = 2670 minus legacy) | Subset A mean (min) | Subset B mean (min) |
|---|---|---|
| Bouguer density (2670 vs 2300) | −2.31 (−4.16) mGal | −2.10 (−3.87) mGal |
| Curvature (recomputed vs supplied BB) | 0.00 mGal | −0.40 (−0.71) mGal |
| Height-correction coefficients | +0.02 mGal | +0.02 mGal |
| Normal gravity, Honkasalo, atmospheric | < 1e-5 mGal | < 1e-5 mGal |

The decomposition closes to 2.3e-10 mGal. The ratio of supplied to recomputed BB is −0.999 for
subset A (correct convention) and +1.079 for subset B, which exposes the injected defect.
With the density fixed at 2300 kg m⁻³, the standard CBA differs from legacy A by −0.04 mGal on
average and from legacy B by −0.42 mGal (minimum −0.75 mGal).
