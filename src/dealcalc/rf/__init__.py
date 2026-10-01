"""Russian Federation valuation helpers.

The functions in this package are deterministic calculation aids. They do not
select market evidence, establish correction factors, or by themselves make a
valuation report compliant with Russian appraisal standards.
"""

from .real_estate import (
    cap_rate_extraction,
    comparative_approach,
    cost_approach,
    dcf_valuation,
    income_capitalization,
    net_operating_income,
    reconcile_approaches,
)
from .data import deduplicate_listings, load_listings, normalize_listing
from .machinery import braking_coefficient, new_equivalent_price
from .vehicle import vehicle_comparative_approach

__all__ = [
    "comparative_approach",
    "cost_approach",
    "dcf_valuation",
    "income_capitalization",
    "net_operating_income",
    "cap_rate_extraction",
    "reconcile_approaches",
    "deduplicate_listings",
    "load_listings",
    "normalize_listing",
    "braking_coefficient",
    "new_equivalent_price",
    "vehicle_comparative_approach",
]
