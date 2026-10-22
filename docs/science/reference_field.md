# Reference field and normal gravity

Normal gravity on the GRS80 ellipsoid (Moritz, 2000) uses Somigliana's closed form

$$\gamma_0(\varphi)=\gamma_e\,\frac{1+k\sin^2\varphi}{\sqrt{1-e^2\sin^2\varphi}},$$

with $\gamma_e = 978\,032.67715$ mGal, $k = 0.001\,931\,851\,353$ and $e^2 = 0.006\,694\,380\,022\,90$.
The implementation agrees with Boule's GRS80 to better than $10^{-3}$ mGal from pole to pole
(test `test_normal_gravity_matches_boule`). WGS84 normal gravity is not allowed: it differs by
about 0.14 mGal at 9.5°N.

The products are classical (geoid-referenced) anomalies, because only heights above mean sea
level are available (question Q3). The gravity disturbance needs ellipsoidal heights.
