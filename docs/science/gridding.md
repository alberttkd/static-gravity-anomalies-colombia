# Gridding

All gridding is done in EPSG:9377 metres.

- **Regression kriging (default):** an OLS polynomial trend (degree 0–2) plus simple kriging of
  the residuals with a Matérn covariance (ν ∈ {0.5, 1.5, 2.5}; the Gaussian model is
  excluded). The parameters come from a weighted-least-squares fit (Cressie, 1985) to the
  experimental variogram, with 1.5 km bins and lags up to 30 km. If the fit fails, the fallback
  order is: max lag 20 km → fixed nugget → ν = 0.5 → error.
- **Equivalent sources** (Harmonica): depth ∈ {7, 10, 14, 20} km × damping ∈ {0.01, 0.1, 1}.
- **Baselines:** IDW (p = 2, k = 12; the legacy configuration), and a linear trend plus a
  Verde biharmonic spline.

Inner block CV chooses the hyper-parameters. The grid σ is the kriging σ of the field
(nugget excluded) multiplied by the calibration factor $c = \mathrm{sd}(z)$ from block CV.

**Masks:** cells farther than 5 km from a station, or outside the convex hull, are
*unsupported* and are never rendered. Cells with σ_cal > 5 mGal are hatched.

**Regional/residual:** the regional field is a degree-2 polynomial, and the residual is the
gridded CBA minus that field (D-008).
