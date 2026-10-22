# Station uncertainty

First-order propagation with independent errors in g, H, TC and the north position
(§5.5.3). The partial derivatives come from central differences of the full reduction, and
they reproduce the guide's values: ∂CBA/∂H = 0.195 mGal m⁻¹ at 2670 kg m⁻³ (0.212 at 2300)
and ∂γ₀/∂N ≈ 0.27 mGal km⁻¹ at 9°N.

The default budget (pending Q8) is σ_g = 0.10 mGal, σ_H = 1 m, σ_TC = 10 % of TC and
σ_pos = 50 m. It gives a station σ of about 0.33 mGal for the FAA and about 0.22 mGal for
SBA and CBA.

!!! note "Evidence on σ_g"
    Repeat or duplicate stations give a direct estimate of σ_g. In the synthetic survey, the two
    duplicate pairs with a 0.5 mGal offset imply σ_g ≈ 0.22 mGal. Set the budget from such pairs
    when a compilation contains them.

A Monte Carlo propagation (2,000 draws, fixed seed) re-runs the non-linear reduction. Common
random numbers with moment matching make it agree with the linear σ to about 1e-7
(relative), well within the 5 % criterion (D-009).
