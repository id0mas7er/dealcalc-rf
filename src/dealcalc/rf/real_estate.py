"""Deterministic calculation aids for Russian real-estate valuation.

This module deliberately keeps professional judgement outside the formulas:
the appraiser supplies the comparable set, market-supported adjustments,
weights, income assumptions, and depreciation estimates. The functions retain
those inputs in JSON-serializable results so a later report layer can show the
calculation trail.

Amounts are plain numbers. The default currency label is RUB, but the formulas
do not perform currency conversion. Percentages are expressed as percent
numbers (``12`` means 12%).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Optional


def _finite_number(name: str, value: Any) -> float:
    """Return a finite float or raise a useful validation error."""

    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _non_negative(name: str, value: Any) -> float:
    number = _finite_number(name, value)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _percentage(
    name: str,
    value: Any,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    number = _finite_number(name, value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return number


def _currency(currency: str) -> str:
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency must be a non-empty string")
    return currency.strip().upper()


def _round(value: float) -> float:
    return round(value, 2)


def comparative_approach(
    subject_area_sqm: float,
    comparables: Sequence[Mapping[str, Any]],
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Calculate an indicated value from adjusted comparable unit prices.

    Each comparable must contain ``price`` and ``area_sqm``. Optional fields
    are ``adjustment_pct`` (the total adjustment from the comparable to the
    subject), ``weight`` (a positive analyst-supplied weight), ``source`` and
    ``date``. The adjusted unit price is::

        price / area_sqm * (1 + adjustment_pct / 100)

    No standard correction percentage is assumed. The adjustment and weight
    must be supported by the appraiser's market analysis.
    """

    subject_area = _finite_number("subject_area_sqm", subject_area_sqm)
    if subject_area <= 0:
        raise ValueError("subject_area_sqm must be greater than 0")
    currency_code = _currency(currency)
    if not comparables:
        raise ValueError("comparables must contain at least one item")

    normalized = []
    total_weight = 0.0
    weighted_unit_sum = 0.0

    for index, comparable in enumerate(comparables, start=1):
        if not isinstance(comparable, Mapping):
            raise ValueError(f"comparables[{index - 1}] must be an object")

        price = _non_negative(f"comparables[{index - 1}].price", comparable.get("price"))
        area = _finite_number(
            f"comparables[{index - 1}].area_sqm", comparable.get("area_sqm")
        )
        if area <= 0:
            raise ValueError(f"comparables[{index - 1}].area_sqm must be greater than 0")

        adjustment_pct = _percentage(
            f"comparables[{index - 1}].adjustment_pct",
            comparable.get("adjustment_pct", 0),
        )
        if adjustment_pct <= -100:
            raise ValueError(
                f"comparables[{index - 1}].adjustment_pct must be greater than -100"
            )
        weight = _finite_number(
            f"comparables[{index - 1}].weight", comparable.get("weight", 1)
        )
        if weight <= 0:
            raise ValueError(f"comparables[{index - 1}].weight must be greater than 0")

        unit_price = price / area
        adjusted_unit_price = unit_price * (1 + adjustment_pct / 100)
        total_weight += weight
        weighted_unit_sum += adjusted_unit_price * weight

        item: Dict[str, Any] = {
            "index": index,
            "price": _round(price),
            "area_sqm": _round(area),
            "unit_price": _round(unit_price),
            "adjustment_pct": _round(adjustment_pct),
            "adjusted_unit_price": _round(adjusted_unit_price),
            "weight": _round(weight),
        }
        for key in ("source", "date"):
            if key in comparable:
                item[key] = comparable[key]
        normalized.append(item)

    weighted_unit_price = weighted_unit_sum / total_weight
    adjusted_prices = [item["adjusted_unit_price"] for item in normalized]
    return {
        "approach": "comparative",
        "currency": currency_code,
        "subject_area_sqm": _round(subject_area),
        "sample_size": len(normalized),
        "weighted_unit_price": _round(weighted_unit_price),
        "indicated_value": _round(weighted_unit_price * subject_area),
        "adjusted_unit_price_min": _round(min(adjusted_prices)),
        "adjusted_unit_price_max": _round(max(adjusted_prices)),
        "indicated_value_range": {
            "low": _round(min(adjusted_prices) * subject_area),
            "high": _round(max(adjusted_prices) * subject_area),
        },
        "comparables": normalized,
    }


def income_capitalization(
    noi_annual: float,
    cap_rate_pct: float,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Calculate value by direct capitalization of annual NOI.

    Formula: ``value = noi_annual / (cap_rate_pct / 100)``. A capitalization
    rate is a market assumption and must be supported separately; this
    function only performs the arithmetic.
    """

    noi = _non_negative("noi_annual", noi_annual)
    cap_rate = _finite_number("cap_rate_pct", cap_rate_pct)
    if cap_rate <= 0:
        raise ValueError("cap_rate_pct must be greater than 0")
    return {
        "approach": "income",
        "method": "direct_capitalization",
        "currency": _currency(currency),
        "noi_annual": _round(noi),
        "cap_rate_pct": _round(cap_rate),
        "indicated_value": _round(noi / (cap_rate / 100)),
    }


def dcf_valuation(
    cash_flows: Sequence[float],
    discount_rate_pct: float,
    terminal_value: float = 0,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Calculate the present value of annual cash flows and a terminal value.

    ``cash_flows[0]`` is the end-of-year-1 cash flow. The terminal value is
    discounted at the last cash-flow period. The function does not prescribe a
    growth model, exit yield, or discount-rate source.
    """

    if not cash_flows:
        raise ValueError("cash_flows must contain at least one value")
    flows = [_finite_number("cash_flows item", value) for value in cash_flows]
    discount_rate = _finite_number("discount_rate_pct", discount_rate_pct)
    if discount_rate <= -100:
        raise ValueError("discount_rate_pct must be greater than -100")
    terminal = _finite_number("terminal_value", terminal_value)
    rate = discount_rate / 100

    present_values = [flow / ((1 + rate) ** period) for period, flow in enumerate(flows, 1)]
    terminal_present_value = terminal / ((1 + rate) ** len(flows))
    indicated_value = sum(present_values) + terminal_present_value
    return {
        "approach": "income",
        "method": "discounted_cash_flow",
        "currency": _currency(currency),
        "cash_flows": [_round(flow) for flow in flows],
        "discount_rate_pct": _round(discount_rate),
        "terminal_value": _round(terminal),
        "present_value_cash_flows": _round(sum(present_values)),
        "terminal_present_value": _round(terminal_present_value),
        "indicated_value": _round(indicated_value),
    }


def cost_approach(
    replacement_cost: float,
    land_value: float = 0,
    physical_depreciation_pct: float = 0,
    functional_depreciation_pct: float = 0,
    external_depreciation_pct: float = 0,
    entrepreneurial_profit_pct: float = 0,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Calculate a residual improvement value plus land value.

    Formula::

        cost_with_profit = replacement_cost * (1 + entrepreneurial_profit_pct / 100)
        total_depreciation = 1 - (1 - physical) * (1 - functional) * (1 - external)
        value = land_value + cost_with_profit * (1 - total_depreciation)

    The depreciation components are combined multiplicatively. The selected
    depreciation method, entrepreneurial profit and their evidence belong in
    the appraisal assignment and report.
    """

    replacement = _non_negative("replacement_cost", replacement_cost)
    land = _non_negative("land_value", land_value)
    physical = _percentage(
        "physical_depreciation_pct", physical_depreciation_pct, minimum=0, maximum=100
    )
    functional = _percentage(
        "functional_depreciation_pct",
        functional_depreciation_pct,
        minimum=0,
        maximum=100,
    )
    external = _percentage(
        "external_depreciation_pct", external_depreciation_pct, minimum=0, maximum=100
    )
    profit_pct = _non_negative("entrepreneurial_profit_pct", entrepreneurial_profit_pct)

    entrepreneurial_profit = replacement * profit_pct / 100
    cost_with_profit = replacement + entrepreneurial_profit
    remaining_share = (1 - physical / 100) * (1 - functional / 100) * (1 - external / 100)
    total_depreciation = (1 - remaining_share) * 100

    depreciated_improvements = cost_with_profit * remaining_share
    return {
        "approach": "cost",
        "currency": _currency(currency),
        "replacement_cost": _round(replacement),
        "entrepreneurial_profit_pct": _round(profit_pct),
        "entrepreneurial_profit": _round(entrepreneurial_profit),
        "replacement_cost_with_profit": _round(cost_with_profit),
        "land_value": _round(land),
        "depreciation": {
            "physical_pct": _round(physical),
            "functional_pct": _round(functional),
            "external_pct": _round(external),
            "total_pct": _round(total_depreciation),
        },
        "depreciated_improvements": _round(depreciated_improvements),
        "indicated_value": _round(land + depreciated_improvements),
    }


def reconcile_approaches(
    approach_values: Mapping[str, float],
    weights: Optional[Mapping[str, float]] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Reconcile indicated values using analyst-supplied positive weights.

    Weights must sum to 1 (tolerance 0.0001); without weights all approaches
    get equal weight. This produces a transparent weighted result and range.
    It does not choose
    which approaches should be used or claim that a particular weight is
    required by Russian standards.
    """

    if not approach_values:
        raise ValueError("approach_values must contain at least one approach")
    values = {
        str(name): _non_negative(f"approach_values[{name}]", value)
        for name, value in approach_values.items()
    }
    if weights is None:
        normalized_weights = {name: 1 / len(values) for name in values}
    else:
        missing = set(values) - set(weights)
        extra = set(weights) - set(values)
        if missing or extra:
            raise ValueError("weights must have exactly the same approach names")
        normalized_weights = {
            name: _finite_number(f"weights[{name}]", weights[name]) for name in values
        }
        if any(weight <= 0 for weight in normalized_weights.values()):
            raise ValueError("all approach weights must be greater than 0")
        if not math.isclose(sum(normalized_weights.values()), 1, abs_tol=1e-4):
            raise ValueError("weights must sum to 1")

    reconciled = sum(values[name] * normalized_weights[name] for name in values)
    return {
        "currency": _currency(currency),
        "approach_values": {name: _round(value) for name, value in values.items()},
        "weights": normalized_weights,
        "reconciled_value": _round(reconciled),
        "value_range": {
            "low": _round(min(values.values())),
            "high": _round(max(values.values())),
        },
    }
