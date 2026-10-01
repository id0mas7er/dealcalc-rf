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
import statistics
from collections.abc import Mapping, Sequence
from typing import Any, Dict, Optional

from ._adjustments import adjustment_steps, apply_adjustments, variation
from ._meta import (
    FORMULA_NORM,
    FORMULA_TECHNICAL,
    STATUS_NOT_RECONCILED,
    STATUS_REVIEW,
    method_card,
    observation_checks,
    observation_fields,
    variation_checks,
)


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


@method_card(
    "COMPARABLE_UNIT_PRICE",
    "ФСО V; ФСО №7",
    "u_i = P_adj,i / q_i; V = q_subject × u_reconciled; поправки — последовательно",
    FORMULA_TECHNICAL,
)
def comparative_approach(
    subject_area_sqm: float,
    comparables: Sequence[Mapping[str, Any]],
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Calculate an indicated value from adjusted comparable unit prices.

    Each comparable must contain ``price`` and ``area_sqm``. Optional fields
    are ``adjustments``, ``weight`` (a positive analyst-supplied weight) and
    the provenance of the observation: ``source``, ``date``, ``url``,
    ``price_type`` (``сделка`` or ``предложение``), ``conditions`` and
    ``reliability``; missing provenance is reported in ``checks``.

    ``adjustments`` is a list of ``{"name", "type", "value"}`` steps applied in
    order to the unit price ``price / area_sqm``: ``pct`` multiplies by
    ``1 + value / 100``, ``abs`` adds ``value`` RUB per m². Put the bargaining
    discount first. Every intermediate price is kept in the result. The legacy
    ``adjustment_pct`` field is treated as one step.

    The indicated value is the rounded weighted unit price times the subject
    area. ``variation`` reports the coefficient of variation of adjusted unit
    prices against the 33% homogeneity threshold.

    No standard correction percentage is assumed. The adjustments and weights
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

        weight = _finite_number(
            f"comparables[{index - 1}].weight", comparable.get("weight", 1)
        )
        if weight <= 0:
            raise ValueError(f"comparables[{index - 1}].weight must be greater than 0")

        unit_price = price / area
        prefix = f"comparables[{index - 1}]"
        adjusted = apply_adjustments(
            unit_price, adjustment_steps(comparable, prefix), prefix
        )
        adjusted_unit_price = adjusted["adjusted_price"]
        total_weight += weight
        weighted_unit_sum += adjusted_unit_price * weight

        item: Dict[str, Any] = {
            "index": index,
            "price": _round(price),
            "area_sqm": _round(area),
            "unit_price": _round(unit_price),
            "adjustments": adjusted["adjustments"],
            "net_adjustment_pct": adjusted["net_adjustment_pct"],
            "gross_adjustment_pct": adjusted["gross_adjustment_pct"],
            "adjusted_unit_price": _round(adjusted_unit_price),
            "weight": _round(weight),
            **observation_fields(comparable, prefix),
        }
        normalized.append(item)

    weighted_unit_price = _round(weighted_unit_sum / total_weight)
    adjusted_prices = [item["adjusted_unit_price"] for item in normalized]
    sample_variation = variation(adjusted_prices)
    return {
        "approach": "comparative",
        "currency": currency_code,
        "subject_area_sqm": _round(subject_area),
        "sample_size": len(normalized),
        "weighted_unit_price": weighted_unit_price,
        "indicated_value": _round(weighted_unit_price * subject_area),
        "adjusted_unit_price_min": _round(min(adjusted_prices)),
        "adjusted_unit_price_max": _round(max(adjusted_prices)),
        "indicated_value_range": {
            "low": _round(min(adjusted_prices) * subject_area),
            "high": _round(max(adjusted_prices) * subject_area),
        },
        "variation": sample_variation,
        "comparables": normalized,
        "checks": observation_checks(normalized)
        + variation_checks(sample_variation, len(normalized)),
    }


@method_card(
    "DIRECT_CAPITALIZATION",
    "ФСО V, п. 14; ФСО №7",
    "V = I_1 / R",
    FORMULA_NORM,
)
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


@method_card(
    "NOI_BUILD_UP",
    "ФСО V; ФСО №7",
    "ДВД = ПВД × (1 − недозагрузка) × (1 − недосбор) + прочие доходы; ЧОД = ДВД − расходы",
    FORMULA_TECHNICAL,
)
def net_operating_income(
    potential_gross_income: Optional[float] = None,
    rentable_area_sqm: Optional[float] = None,
    rent_rate_sqm_year: Optional[float] = None,
    vacancy_pct: float = 0,
    collection_loss_pct: float = 0,
    other_income_annual: float = 0,
    operating_expenses: Optional[Sequence[Mapping[str, Any]]] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Build annual NOI from potential gross income (ПВД → ДВД → ЧОД).

    Pass ``potential_gross_income`` or both ``rentable_area_sqm`` and
    ``rent_rate_sqm_year`` (RUB per m² per year)::

        ДВД = ПВД × (1 − vacancy_pct/100) × (1 − collection_loss_pct/100)
              + other_income_annual
        ЧОД = ДВД − operating expenses

    ``operating_expenses`` is a list of ``{"name", "type", "value"}`` items:
    ``abs`` is RUB per year, ``pct`` is a percent of ДВД. Every item is shown
    in RUB in the result.
    """

    has_area_inputs = rentable_area_sqm is not None or rent_rate_sqm_year is not None
    if potential_gross_income is not None and has_area_inputs:
        raise ValueError(
            "use either potential_gross_income or rentable_area_sqm with rent_rate_sqm_year"
        )
    if potential_gross_income is not None:
        pgi = _non_negative("potential_gross_income", potential_gross_income)
        basis: Dict[str, Any] = {}
    elif rentable_area_sqm is not None and rent_rate_sqm_year is not None:
        area = _finite_number("rentable_area_sqm", rentable_area_sqm)
        if area <= 0:
            raise ValueError("rentable_area_sqm must be greater than 0")
        rate = _non_negative("rent_rate_sqm_year", rent_rate_sqm_year)
        pgi = area * rate
        basis = {"rentable_area_sqm": _round(area), "rent_rate_sqm_year": _round(rate)}
    else:
        raise ValueError(
            "potential_gross_income or rentable_area_sqm with rent_rate_sqm_year is required"
        )

    vacancy = _percentage("vacancy_pct", vacancy_pct, minimum=0)
    if vacancy >= 100:
        raise ValueError("vacancy_pct must be less than 100")
    collection = _percentage("collection_loss_pct", collection_loss_pct, minimum=0)
    if collection >= 100:
        raise ValueError("collection_loss_pct must be less than 100")
    other_income = _non_negative("other_income_annual", other_income_annual)

    vacancy_loss = pgi * vacancy / 100
    collection_loss = (pgi - vacancy_loss) * collection / 100
    egi = pgi - vacancy_loss - collection_loss + other_income

    expenses = []
    total_expenses = 0.0
    for index, expense in enumerate(operating_expenses or []):
        prefix = f"operating_expenses[{index}]"
        if not isinstance(expense, Mapping):
            raise ValueError(f"{prefix} must be an object")
        name = expense.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{prefix}.name must be a non-empty string")
        kind = expense.get("type")
        value = _non_negative(f"{prefix}.value", expense.get("value"))
        if kind == "abs":
            amount = value
        elif kind == "pct":
            amount = egi * value / 100
        else:
            raise ValueError(f"{prefix}.type must be 'abs' or 'pct'")
        total_expenses += amount
        expenses.append(
            {"name": name.strip(), "type": kind, "value": _round(value), "amount": _round(amount)}
        )

    return {
        "approach": "income",
        "currency": _currency(currency),
        **basis,
        "potential_gross_income": _round(pgi),
        "vacancy_pct": _round(vacancy),
        "vacancy_loss": _round(vacancy_loss),
        "collection_loss_pct": _round(collection),
        "collection_loss": _round(collection_loss),
        "other_income_annual": _round(other_income),
        "effective_gross_income": _round(egi),
        "operating_expenses": expenses,
        "total_operating_expenses": _round(total_expenses),
        "operating_expense_ratio_pct": None
        if egi == 0
        else _round(total_expenses / egi * 100),
        "net_operating_income": _round(egi - total_expenses),
    }


@method_card(
    "CAP_RATE_EXTRACTION",
    "ФСО №7 (общая ставка по соотношению доходов и цен аналогов)",
    "R_i = ЧОД_i / P_i",
    FORMULA_TECHNICAL,
)
def cap_rate_extraction(
    comparables: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Extract a market capitalization rate from comparable sales.

    Each comparable contains ``price`` and annual ``noi``, with optional
    ``source`` and ``date``. ``cap_rate_pct = noi / price × 100``. The result
    gives the mean, median, range and the coefficient of variation against
    the 33% homogeneity threshold; choosing the rate is up to the appraiser.
    """

    if not comparables:
        raise ValueError("comparables must contain at least one item")

    items = []
    rates = []
    for index, comparable in enumerate(comparables):
        prefix = f"comparables[{index}]"
        if not isinstance(comparable, Mapping):
            raise ValueError(f"{prefix} must be an object")
        price = _finite_number(f"{prefix}.price", comparable.get("price"))
        if price <= 0:
            raise ValueError(f"{prefix}.price must be greater than 0")
        noi = _finite_number(f"{prefix}.noi", comparable.get("noi"))
        if noi <= 0:
            raise ValueError(f"{prefix}.noi must be greater than 0")
        rates.append(noi / price * 100)
        item: Dict[str, Any] = {
            "index": index + 1,
            "price": _round(price),
            "noi": _round(noi),
            "cap_rate_pct": _round(noi / price * 100),
            **observation_fields(comparable, prefix),
        }
        items.append(item)

    rate_variation = variation(rates)
    return {
        "approach": "income",
        "method": "cap_rate_extraction",
        "sample_size": len(items),
        "mean_cap_rate_pct": _round(statistics.mean(rates)),
        "median_cap_rate_pct": _round(statistics.median(rates)),
        "min_cap_rate_pct": _round(min(rates)),
        "max_cap_rate_pct": _round(max(rates)),
        "variation": rate_variation,
        "comparables": items,
        "checks": observation_checks(items) + variation_checks(rate_variation, len(items)),
    }


@method_card(
    "GROSS_RENT_MULTIPLIER",
    "ФСО V; ФСО №7",
    "ВРМ_i = P_i / ВД_i; V = ВРМ × ВД_объекта",
    FORMULA_TECHNICAL,
)
def gross_rent_multiplier(
    comparables: Sequence[Mapping[str, Any]],
    subject_gross_income: Optional[float] = None,
    statistic: str = "mean",
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Value by the gross rent multiplier (ВРМ) of comparable sales.

    Each comparable contains ``price`` and annual ``gross_income``, with
    optional ``source`` and ``date``; ``multiplier = price / gross_income``.
    Use the same income basis (ПВД or ДВД) for the comparables and the
    subject. With ``subject_gross_income`` the indicated value is the
    ``mean`` or ``median`` multiplier times that income.
    """

    if not comparables:
        raise ValueError("comparables must contain at least one item")
    if statistic not in ("mean", "median"):
        raise ValueError("statistic must be 'mean' or 'median'")
    subject_income = (
        None
        if subject_gross_income is None
        else _non_negative("subject_gross_income", subject_gross_income)
    )

    items = []
    multipliers = []
    for index, comparable in enumerate(comparables):
        prefix = f"comparables[{index}]"
        if not isinstance(comparable, Mapping):
            raise ValueError(f"{prefix} must be an object")
        price = _finite_number(f"{prefix}.price", comparable.get("price"))
        if price <= 0:
            raise ValueError(f"{prefix}.price must be greater than 0")
        income = _finite_number(f"{prefix}.gross_income", comparable.get("gross_income"))
        if income <= 0:
            raise ValueError(f"{prefix}.gross_income must be greater than 0")
        multipliers.append(price / income)
        item: Dict[str, Any] = {
            "index": index + 1,
            "price": _round(price),
            "gross_income": _round(income),
            "multiplier": _round(price / income),
            **observation_fields(comparable, prefix),
        }
        items.append(item)

    mean = statistics.mean(multipliers)
    median = statistics.median(multipliers)
    chosen = _round(mean if statistic == "mean" else median)
    multiplier_variation = variation(multipliers)
    return {
        "approach": "income",
        "method": "gross_rent_multiplier",
        "currency": _currency(currency),
        "sample_size": len(items),
        "mean_multiplier": _round(mean),
        "median_multiplier": _round(median),
        "min_multiplier": _round(min(multipliers)),
        "max_multiplier": _round(max(multipliers)),
        "variation": multiplier_variation,
        "statistic": statistic,
        "subject_gross_income": None if subject_income is None else _round(subject_income),
        "indicated_value": None if subject_income is None else _round(chosen * subject_income),
        "comparables": items,
        "checks": observation_checks(items)
        + variation_checks(multiplier_variation, len(items)),
    }


@method_card(
    "DCF",
    "ФСО V; ФСО №7",
    "V0 = Σ CF_t / (1 + r)^t + TV_n / (1 + r)^n",
    "математическая реализация требования ФСО V приводить потоки к дате оценки; прогноз и ставка стандартом не установлены",
)
def dcf_valuation(
    cash_flows: Sequence[float],
    discount_rate_pct: float,
    terminal_value: float = 0,
    currency: str = "RUB",
    mid_year: bool = False,
) -> Dict[str, Any]:
    """Calculate the present value of annual cash flows and a terminal value.

    ``cash_flows[0]`` is the year-1 cash flow, discounted at the end of the
    year, or at its middle (period ``t - 0.5``) when ``mid_year`` is true. The
    terminal value is discounted at the end of the last cash-flow period. The function does not prescribe a
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

    shift = 0.5 if mid_year else 0
    present_values = [
        flow / ((1 + rate) ** (period - shift)) for period, flow in enumerate(flows, 1)
    ]
    terminal_present_value = terminal / ((1 + rate) ** len(flows))
    indicated_value = sum(present_values) + terminal_present_value
    return {
        "approach": "income",
        "method": "discounted_cash_flow",
        "discounting": "mid_year" if mid_year else "end_of_year",
        "currency": _currency(currency),
        "cash_flows": [_round(flow) for flow in flows],
        "discount_rate_pct": _round(discount_rate),
        "terminal_value": _round(terminal),
        "present_value_cash_flows": _round(sum(present_values)),
        "terminal_present_value": _round(terminal_present_value),
        "indicated_value": _round(indicated_value),
    }


@method_card(
    "PROPERTY_COST_APPROACH",
    "ФСО №7, п. 24; ФСО V",
    "V = V_земли + (C × (1 + ПП)) × (1 − Иф)(1 − Ифу)(1 − Иэ)",
    "структурная формула ФСО №7; модель износа (перемножение) — расчётное представление",
)
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


@method_card(
    "RECONCILIATION",
    "ФСО V",
    "V = Σ w_i × V_i, Σ w_i = 1",
    "расчётное представление; веса, выбор подхода и анализ расхождений — суждение оценщика",
)
def reconcile_approaches(
    approach_values: Mapping[str, float],
    weights: Mapping[str, float],
    max_divergence_pct: float,
    justification: Optional[str] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Reconcile indicated values with appraiser-supplied weights.

    There are no default weights: mechanical averaging is not allowed.
    Weights must sum to 1 (tolerance 0.0001); a weight of 0 excludes an
    approach, so one approach can be selected. ``max_divergence_pct`` is the
    appraiser's threshold of material divergence, measured as
    ``(max − min) / min × 100`` over the approaches with positive weight.
    Above it the result is not reconciled automatically unless a
    ``justification`` is given; the deviation of every approach from the
    reconciled value is shown.
    """

    if not approach_values:
        raise ValueError("approach_values must contain at least one approach")
    values = {
        str(name): _non_negative(f"approach_values[{name}]", value)
        for name, value in approach_values.items()
    }
    if not isinstance(weights, Mapping):
        raise ValueError("weights are required: mechanical averaging is not allowed")
    missing = set(values) - set(weights)
    extra = set(weights) - set(values)
    if missing or extra:
        raise ValueError("weights must have exactly the same approach names")
    given = {name: _non_negative(f"weights[{name}]", weights[name]) for name in values}
    if not math.isclose(sum(given.values()), 1, abs_tol=1e-4):
        raise ValueError("weights must sum to 1")
    threshold = _non_negative("max_divergence_pct", max_divergence_pct)
    note = None
    if justification is not None:
        if not isinstance(justification, str) or not justification.strip():
            raise ValueError("justification must be a non-empty string")
        note = justification.strip()

    used = {name: value for name, value in values.items() if given[name] > 0}
    reconciled = sum(values[name] * given[name] for name in values)
    low, high = min(used.values()), max(used.values())
    divergence = None if low == 0 else (high - low) / low * 100

    checks = []
    status = None
    if divergence is None:
        checks.append("Одно из значений равно 0: расхождение подходов не рассчитывается.")
    elif divergence > threshold:
        if note is None:
            status = STATUS_NOT_RECONCILED
            checks.append(
                f"Расхождение подходов {_round(divergence)}% больше порога {_round(threshold)}%: "
                "исследуйте причины и обоснуйте веса или выбор подхода (justification)."
            )
        else:
            status = STATUS_REVIEW
            checks.append(
                f"Расхождение подходов {_round(divergence)}% больше порога {_round(threshold)}%; "
                "приведено обоснование оценщика."
            )
    excluded = [name for name in values if given[name] == 0]
    if excluded:
        checks.append(f"Подходы с весом 0 не участвуют в результате: {excluded}.")

    result: Dict[str, Any] = {
        "currency": _currency(currency),
        "approach_values": {name: _round(value) for name, value in values.items()},
        "weights": given,
        "reconciled_value": _round(reconciled),
        "deviation_from_reconciled_pct": {
            name: None if reconciled == 0 else _round((value - reconciled) / reconciled * 100)
            for name, value in used.items()
        },
        "divergence_pct": None if divergence is None else _round(divergence),
        "max_divergence_pct": _round(threshold),
        "justification": note,
        "value_range": {"low": _round(low), "high": _round(high)},
        "checks": checks,
    }
    if status is not None:
        result["status"] = status
    return result
