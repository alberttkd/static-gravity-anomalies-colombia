# Reduction density

Two diagnostics run on degree-2 trend residuals, with 95 % confidence intervals from a 15 km
block bootstrap (1,000 replicates):

- **Nettleton**: the ρ that minimizes |corr(CBA(ρ), H)| over 1800–3000 kg m⁻³.
- **Parasnis**: the OLS slope of FAA on $X = BC_{cap}(H;\rho=1) - TC/\rho_{TC}$.

An estimate is reliable only if both CI half-widths are ≤ 300 kg m⁻³, the value is physically
plausible and the two CIs overlap.

**High relief (synthetic, ρ_true = 2400, height sd 285 m):** Nettleton gives 2440 [2340, 2570]
and Parasnis 2437 [2342, 2570]. Both are within ±60 kg m⁻³, and both CIs contain the truth.

**Low relief with an anomaly that follows the topography (synthetic, ρ_true = 2670, height sd
46 m):** Nettleton hits the 3000 kg m⁻³ boundary and Parasnis gives 4110 [3394, 4839] kg m⁻³.
The CBA stays correlated with topography after detrending, as in sedimentary basins whose
lowlands coincide with light fill. The reliability rule rejects both estimates, and the
standard 2670 kg m⁻³ is used, with 2300 as a scenario.
