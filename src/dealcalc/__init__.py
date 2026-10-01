"""DealCalc Core — a pure-Python real estate investment calculation engine.

Public API re-exports every primitive and calculator so callers can do
``from dealcalc import cap_rate`` or ``from dealcalc import calculators as calc``.
"""

from __future__ import annotations

from . import calculators, primitives, rf
from .calculators import (
    arv,
    brrrr,
    build_cash_flows,
    cap_rate,
    cash_on_cash,
    closing_costs,
    construction_cost,
    dscr,
    fix_and_flip,
    gross_rent_multiplier,
    irr,
    mao,
    mortgage,
    multifamily_analysis,
    noi,
    rental_cash_flow,
    rental_property_analysis,
    seventy_percent_rule,
    wholesale,
)
from .primitives import (
    amortization_summary,
    effective_gross_income,
    monthly_mortgage_payment,
    net_operating_income,
)

__version__ = "0.2.0"

__all__ = [
    "calculators",
    "primitives",
    "rf",
    # primitives
    "monthly_mortgage_payment",
    "effective_gross_income",
    "net_operating_income",
    "amortization_summary",
    # group A
    "arv",
    "seventy_percent_rule",
    "mao",
    "wholesale",
    # group B
    "cap_rate",
    "noi",
    "cash_on_cash",
    "dscr",
    "gross_rent_multiplier",
    # group C
    "mortgage",
    "rental_cash_flow",
    "fix_and_flip",
    "brrrr",
    "rental_property_analysis",
    "multifamily_analysis",
    "irr",
    "build_cash_flows",
    # group D
    "closing_costs",
    "construction_cost",
]
