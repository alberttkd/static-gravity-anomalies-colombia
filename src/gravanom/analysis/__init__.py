"""Analysis products: trend/residual, profiles, contours, run comparisons."""

from gravanom.analysis.compare import compare_grids, compare_station_runs, term_decomposition
from gravanom.analysis.contours import contours
from gravanom.analysis.profiles import ProfileOutsideSupportError, profile
from gravanom.analysis.trend import PolynomialTrend, decompose

__all__ = [
    "PolynomialTrend",
    "ProfileOutsideSupportError",
    "compare_grids",
    "compare_station_runs",
    "contours",
    "decompose",
    "profile",
    "term_decomposition",
]
