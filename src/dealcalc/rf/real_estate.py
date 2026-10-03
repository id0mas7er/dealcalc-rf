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
from typing import Any, Dict, List, Optional

from ._adjustments import (
    WEIGHTING_FORMULAS,
    adjustment_steps,
    analog_weight,
    sample_weights,
    apply_adjustments,
    money,
    source_range,
    scaled_weights,
    variation,
    weight_shares,
)
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


def _terminal_period(periods: int, timing: str) -> float:
    if timing not in ("end", "mid"):
        raise ValueError("terminal_timing must be 'end' or 'mid'")
    return periods - 0.5 if timing == "mid" else periods


# Divergence of approaches above this share is material unless the
# appraiser sets another threshold.
MATERIAL_DIVERGENCE_PCT = 30.0


def _round(value: float) -> float:
    return money(value)


@method_card(
    "COMPARABLE_UNIT_PRICE",
    "ФСО V; ФСО №7, п. 22",
    "u_i = P_adj,i / q_i; V = q_subject × u_reconciled; поправки — последовательно",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
)
def comparative_approach(
    subject_area_sqm: float,
    comparables: Sequence[Mapping[str, Any]],
    currency: str = "RUB",
    weighting: str = "manual",
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

    ``weighting``: ``manual`` (``weight`` of each comparable, default 1),
    ``inverse_gross`` (w ∝ 1 / (1 + gross adjustment / 100)),
    ``inverse_count`` (w ∝ 1 / (1 + number of adjustments)), ``count_share``
    (K = (S − M) / ((N − 1) S) by the number of adjustments) or
    ``gross_share`` (K ∝ 1 − S_i / Σ(S_j + 1) by the sum of absolute
    adjustments, %).

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
    raw_weights: List[float] = []
    raw_prices: List[float] = []
    adjusted_all = []

    for index, comparable in enumerate(comparables, start=1):
        if not isinstance(comparable, Mapping):
            raise ValueError(f"comparables[{index - 1}] must be an object")

        price = _finite_number(
            f"comparables[{index - 1}].price", comparable.get("price", comparable.get("price_rub"))
        )
        if price <= 0:
            raise ValueError(f"comparables[{index - 1}].price must be greater than 0")
        area = _finite_number(
            f"comparables[{index - 1}].area_sqm", comparable.get("area_sqm")
        )
        if area <= 0:
            raise ValueError(f"comparables[{index - 1}].area_sqm must be greater than 0")

        unit_price = price / area
        prefix = f"comparables[{index - 1}]"
        adjusted = apply_adjustments(
            unit_price, adjustment_steps(comparable, prefix), prefix
        )
        adjusted_unit_price = adjusted["adjusted_price"]
        weight = analog_weight(comparable, adjusted, weighting, prefix)
        raw_weights.append(weight)
        raw_prices.append(adjusted_unit_price)
        adjusted_all.append(adjusted)

        item: Dict[str, Any] = {
            "index": index,
            "price": _round(price),
            "area_sqm": _round(area),
            "unit_price": _round(unit_price),
            "adjustments": adjusted["adjustments"],
            "net_adjustment_pct": adjusted["net_adjustment_pct"],
            "gross_adjustment_pct": adjusted["gross_adjustment_pct"],
            "adjustments_sum_abs_pct": adjusted["adjustments_sum_abs_pct"],
            "adjusted_unit_price": _round(adjusted_unit_price),
            "weight": round(weight, 6),
            **observation_fields(comparable, prefix),
        }
        normalized.append(item)

    sample = sample_weights(adjusted_all, weighting)
    if sample is not None:
        raw_weights = sample
        for item, weight in zip(normalized, sample):
            item["weight"] = round(weight, 6)
    for item, share in zip(normalized, weight_shares(raw_weights)):
        item["weight_share"] = share
    scaled = scaled_weights(raw_weights)
    weighted_unit_price = _round(
        sum(price * weight for price, weight in zip(raw_prices, scaled)) / sum(scaled)
    )
    adjusted_prices = [item["adjusted_unit_price"] for item in normalized]
    sample_variation = variation(adjusted_prices)
    return {
        "approach": "comparative",
        "currency": currency_code,
        "subject_area_sqm": _round(subject_area),
        "sample_size": len(normalized),
        "weighting": weighting,
        "weighting_formula": WEIGHTING_FORMULAS[weighting],
        "weighted_unit_price": weighted_unit_price,
        "indicated_value": _round(weighted_unit_price * subject_area),
        "adjusted_unit_price_min": _round(min(adjusted_prices)),
        "adjusted_unit_price_max": _round(max(adjusted_prices)),
        # The spread of analogs, not an interval of value (ФСО №7, п. 30).
        "analogs_spread": {
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
    "ФСО V, п. 14; ФСО №7, п. 23 (в)",
    "V = I_1 / R",
    FORMULA_NORM,
    source_url="https://srosovet.ru/activities/npa/fso-v/",
    income_model=True,
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
    "ФСО V; ФСО №7, п. 23",
    "ДВД = ПВД × (1 − недозагрузка) × (1 − недосбор) + прочие доходы; ЧОД = ДВД − расходы",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
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
    ``abs`` is RUB per year, ``pct`` is a percent of ДВД or, with ``"base":
    "pgi"``, of ПВД (the shares of reference books). Every item is shown in
    RUB in the result. An item may carry the bounds of its source
    (``range``) and ``source``, ``date``, ``page``, ``justification``.
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
        base = expense.get("base")
        item: Dict[str, Any] = {"name": name.strip(), "type": kind, "value": _round(value)}
        if kind == "abs":
            if base is not None:
                raise ValueError(f"{prefix}.base applies to pct items")
            amount = value
        elif kind == "pct":
            base = "egi" if base is None else base
            if base not in ("egi", "pgi"):
                raise ValueError(f"{prefix}.base must be 'egi' or 'pgi'")
            amount = (egi if base == "egi" else pgi) * value / 100
            item["base"] = base
        else:
            raise ValueError(f"{prefix}.type must be 'abs' or 'pct'")
        total_expenses += amount
        item["amount"] = _round(amount)
        if expense.get("range") is not None:
            bounds = source_range(f"{prefix}.range", expense["range"])
            item["range"] = {key: bounds[key] for key in ("low", "high", "mean", "extended_low", "extended_high")
                             if key in bounds}
            item["within_range"] = (
                bounds.get("extended_low", bounds["low"]) <= value <= bounds.get("extended_high", bounds["high"])
            )
        for key in ("source", "date", "page", "justification"):
            text = "" if expense.get(key) is None else str(expense[key]).strip()
            if text:
                item[key] = text
        expenses.append(item)

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
    "ФСО №7, п. 23 (в, д): общая ставка по соотношению доходов и цен аналогов",
    "R_i = ЧОД_i / P_i",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
    context_reminder=False,
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
        price = _finite_number(f"{prefix}.price", comparable.get("price", comparable.get("price_rub")))
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
    "ФСО V; ФСО №7, п. 23",
    "ВРМ_i = P_i / ВД_i; V = ВРМ × ВД_объекта",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
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
        price = _finite_number(f"{prefix}.price", comparable.get("price", comparable.get("price_rub")))
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
    chosen = mean if statistic == "mean" else median
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
    "ФСО V, п. 15; ФСО №7, п. 23 (б)",
    "V0 = Σ CF_t / (1 + r)^t + TV_n / (1 + r)^n",
    "математическая реализация требования ФСО V приводить потоки к дате оценки; прогноз и ставка стандартом не установлены",
    source_url="https://srosovet.ru/activities/npa/fso-v/",
    income_model=True,
)
def dcf_valuation(
    cash_flows: Sequence[float],
    discount_rate_pct: float,
    terminal_value: float = 0,
    currency: str = "RUB",
    mid_year: bool = False,
    terminal_timing: str = "end",
    first_cash_flow_period: int = 1,
) -> Dict[str, Any]:
    """Calculate the present value of annual cash flows and a terminal value.

    ``cash_flows[0]`` is the YEAR-1 cash flow (period 1, not period 0 as in
    :func:`npv`), discounted at the end of the year, or at its middle
    (period ``t - 0.5``) when ``mid_year`` is true. With
    ``first_cash_flow_period=0`` the first flow is at period 0 and is not
    discounted, as in :func:`npv` (mid-year discounting is not allowed then).
    ``terminal_timing`` sets when the terminal value is discounted: ``end``
    (end of the last forecast period, default) or ``mid`` (half a period
    earlier, consistent with a Gordon value built from a mid-year flow of
    the next year).
    The function does not prescribe a growth model, exit yield, or
    discount-rate source.
    """

    if isinstance(cash_flows, (str, bytes)) or not cash_flows:
        raise ValueError("cash_flows must be a list with at least one value")
    if not isinstance(mid_year, bool):
        raise ValueError("mid_year must be true or false")
    flows = [_finite_number("cash_flows item", value) for value in cash_flows]
    discount_rate = _finite_number("discount_rate_pct", discount_rate_pct)
    if discount_rate <= -100:
        raise ValueError("discount_rate_pct must be greater than -100")
    terminal = _finite_number("terminal_value", terminal_value)
    rate = discount_rate / 100
    if first_cash_flow_period not in (0, 1) or isinstance(first_cash_flow_period, bool):
        raise ValueError("first_cash_flow_period must be 0 or 1")
    if first_cash_flow_period == 0 and mid_year:
        raise ValueError("mid_year discounting needs first_cash_flow_period=1")
    terminal_period = _terminal_period(len(flows) + first_cash_flow_period - 1, terminal_timing)
    if terminal and terminal_period <= 0:
        raise ValueError("terminal value must be discounted from a future period: add forecast periods")

    shift = 0.5 if mid_year else 0
    present_values = [
        flow / ((1 + rate) ** (period - shift))
        for period, flow in enumerate(flows, first_cash_flow_period)
    ]
    terminal_present_value = terminal / ((1 + rate) ** terminal_period)
    indicated_value = sum(present_values) + terminal_present_value
    return {
        "approach": "income",
        "method": "discounted_cash_flow",
        "discounting": "mid_year" if mid_year else "end_of_year",
        "first_cash_flow_period": first_cash_flow_period,
        "terminal_discount_period": terminal_period,
        "currency": _currency(currency),
        "cash_flows": [_round(flow) for flow in flows],
        "discount_rate_pct": _round(discount_rate),
        "terminal_value": _round(terminal),
        "present_value_cash_flows": _round(sum(present_values)),
        "terminal_present_value": _round(terminal_present_value),
        "indicated_value": _round(indicated_value),
        "guardrails": [
            "Поток ДДП — денежный: при капитальных вложениях и других денежных расходах он не "
            "равен ЧОД."
        ],
    }


@method_card(
    "PROPERTY_COST_APPROACH",
    "ФСО №7, п. 24 (г); ФСО V, пп. 24, 31, 33",
    "V = V_земли + (C × (1 + ПП)) × (1 − Иф)(1 − Ифу)(1 − Иэ)",
    "структурная формула ФСО №7; модель износа (перемножение) — расчётное представление",
    source_url="https://srosovet.ru/activities/npa/fso7/",
)
def cost_approach(
    replacement_cost: float,
    land_value: float = 0,
    physical_depreciation_pct: float = 0,
    functional_depreciation_pct: float = 0,
    external_depreciation_pct: float = 0,
    entrepreneurial_profit_pct: float = 0,
    currency: str = "RUB",
    profit_base: str = "improvements",
    total_depreciation_pct: Optional[float] = None,
    external_obsolescence_amount: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate a residual improvement value plus land value.

    Formula::

        entrepreneurial_profit = base * entrepreneurial_profit_pct / 100
        cost_with_profit = replacement_cost + entrepreneurial_profit
        total_depreciation = 1 - (1 - physical) * (1 - functional) * (1 - external)
        value = land_value + cost_with_profit * (1 - total_depreciation)

    ``profit_base`` is ``improvements`` (replacement cost, default) or
    ``land_and_improvements`` (replacement cost + land value), as different
    methods do.

    The depreciation components are combined multiplicatively by default.
    That is one model, not a rule: when the kinds of depreciation overlap or
    are measured against other bases, give ``total_depreciation_pct`` (the
    combined depreciation by the appraiser's own model, instead of the
    components) or the external loss in money, ``external_obsolescence_amount``
    (subtracted from the improvements after physical and functional
    depreciation, instead of ``external_depreciation_pct``). The selected
    model and its evidence belong in the report.
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
    if profit_base not in ("improvements", "land_and_improvements"):
        raise ValueError("profit_base must be 'improvements' or 'land_and_improvements'")
    base = replacement + (land if profit_base == "land_and_improvements" else 0)

    entrepreneurial_profit = base * profit_pct / 100
    cost_with_profit = replacement + entrepreneurial_profit
    external_amount = None
    if total_depreciation_pct is not None:
        if physical or functional or external or external_obsolescence_amount is not None:
            raise ValueError(
                "total_depreciation_pct replaces the components: leave physical, functional, "
                "external depreciation and external_obsolescence_amount unset"
            )
        model = "total"
        total_depreciation = _percentage(
            "total_depreciation_pct", total_depreciation_pct, minimum=0, maximum=100
        )
        depreciated_improvements = cost_with_profit * (1 - total_depreciation / 100)
    elif external_obsolescence_amount is not None:
        if external:
            raise ValueError(
                "give external depreciation either as external_depreciation_pct or as "
                "external_obsolescence_amount"
            )
        model = "multiplicative + external amount"
        external_amount = _non_negative("external_obsolescence_amount", external_obsolescence_amount)
        before_external = cost_with_profit * (1 - physical / 100) * (1 - functional / 100)
        if external_amount > before_external:
            raise ValueError("external_obsolescence_amount exceeds the depreciated improvements")
        depreciated_improvements = before_external - external_amount
        total_depreciation = (
            (1 - depreciated_improvements / cost_with_profit) * 100 if cost_with_profit else 0.0
        )
    else:
        model = "multiplicative"
        remaining_share = (1 - physical / 100) * (1 - functional / 100) * (1 - external / 100)
        total_depreciation = (1 - remaining_share) * 100
        depreciated_improvements = cost_with_profit * remaining_share
    return {
        "approach": "cost",
        "currency": _currency(currency),
        "replacement_cost": _round(replacement),
        "entrepreneurial_profit_pct": _round(profit_pct),
        "profit_base": profit_base,
        "entrepreneurial_profit": _round(entrepreneurial_profit),
        "replacement_cost_with_profit": _round(cost_with_profit),
        "land_value": _round(land),
        "depreciation": {
            "physical_pct": _round(physical),
            "functional_pct": _round(functional),
            "external_pct": _round(external),
            "external_amount": None if external_amount is None else _round(external_amount),
            "total_pct": _round(total_depreciation),
            "model": model,
        },
        "depreciated_improvements": _round(depreciated_improvements),
        "indicated_value": _round(land + depreciated_improvements),
        "guardrails": [
            "Перемножение видов износа — одна из моделей: если причины износа перекрываются "
            "или проценты взяты от разных баз, задайте total_depreciation_pct или "
            "external_obsolescence_amount."
        ]
        if model == "multiplicative" and sum(1 for pct in (physical, functional, external) if pct) > 1
        else [],
    }


@method_card(
    "INDEXED_REPLACEMENT_COST",
    "ФСО №7, п. 24 (г); ФСО V, п. 24",
    "C = C_база × Π индексов × региональный коэффициент × (1 + НДС)",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
)
def indexed_replacement_cost(
    base_cost: float,
    indices: Sequence[Mapping[str, Any]],
    regional_coefficient: float = 1,
    vat_pct: float = 0,
    base_label: str = "",
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Replacement cost at the valuation date from a base-year cost.

    ``base_cost`` is the cost in base prices (e.g. УПВС 1969, prices of
    1984 or a КО-ИНВЕСТ reference); ``indices`` is the ordered chain
    ``{"name", "value", "source"}`` (e.g. 1969→1984, 1984→date by the
    Ministry of Construction or КО-ИНВЕСТ). Every index, the regional
    coefficient and VAT are shown as separate steps. VAT rate is an input.
    """

    cost = _non_negative("base_cost", base_cost)
    if isinstance(indices, (str, bytes)) or not isinstance(indices, Sequence) or not indices:
        raise ValueError("indices must be a non-empty list")
    regional = _finite_number("regional_coefficient", regional_coefficient)
    if regional <= 0:
        raise ValueError("regional_coefficient must be greater than 0")
    vat = _non_negative("vat_pct", vat_pct)

    steps = []
    value = cost
    no_source = []
    for number, index in enumerate(indices):
        prefix = f"indices[{number}]"
        if not isinstance(index, Mapping):
            raise ValueError(f"{prefix} must be an object")
        name = index.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{prefix}.name must be a non-empty string")
        factor = _finite_number(f"{prefix}.value", index.get("value"))
        if factor <= 0:
            raise ValueError(f"{prefix}.value must be greater than 0")
        before = value
        value *= factor
        step: Dict[str, Any] = {
            "name": name.strip(),
            "factor": factor,
            "cost_before": _round(before),
            "cost_after": _round(value),
        }
        if index.get("source"):
            step["source"] = str(index["source"])
        else:
            no_source.append(name.strip())
        steps.append(step)
    for name, factor in (("Региональный коэффициент", regional), ("НДС", 1 + vat / 100)):
        if factor != 1:
            before = value
            value *= factor
            steps.append({"name": name, "factor": round(factor, 6), "cost_before": _round(before), "cost_after": _round(value)})

    checks = [f"Не указаны источники индексов: {no_source}."] if no_source else []
    return {
        "approach": "cost",
        "currency": _currency(currency),
        "base_cost": _round(cost),
        "base_label": base_label or None,
        "steps": steps,
        "total_index": round(value / cost, 6) if cost else None,
        "vat_pct": _round(vat),
        "replacement_cost": _round(value),
        "guardrails": [
            "Накопление ошибок индексации за длинный период: проверьте результат по рыночным данным, "
            "если они есть.",
        ],
        "checks": checks,
    }


@method_card(
    "RECONCILIATION",
    "ФСО V, п. 3",
    "V = Σ w_i × V_i, Σ w_i = 1",
    "расчётное представление; веса, выбор подхода и анализ расхождений — суждение оценщика",
    source_url="https://srosovet.ru/activities/npa/fso-v/",
)
def reconcile_approaches(
    approach_values: Mapping[str, float],
    weights: Mapping[str, float],
    max_divergence_pct: Optional[float] = None,
    justification: Optional[str] = None,
    currency: str = "RUB",
    divergence_base: str = "min",
    value_interval: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Reconcile indicated values with appraiser-supplied weights.

    There are no default weights: mechanical averaging is not allowed.
    Weights must sum to 1 (tolerance 0.0001); a weight of 0 excludes an
    approach, so one approach can be selected. ``max_divergence_pct`` is the
    threshold of material divergence (more than 30 % by default, or the
    appraiser's own), measured as
    ``(max − min) / base × 100`` over the approaches with positive weight;
    ``divergence_base`` is ``min`` (default), ``mean`` or ``max`` — the base
    of the appraiser's threshold, named in the result.
    Above it the result is not reconciled automatically unless a
    ``justification`` is given; the deviation of every approach from the
    reconciled value is shown.

    ``value_interval`` — ``{"low", "high", "justification"}`` — is the
    appraiser's judgment of the bounds within which the value may lie
    (ФСО №7, п. 30, unless the assignment says otherwise). It is not derived
    from the spread of approaches or analogs.
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
    default_threshold = max_divergence_pct is None
    threshold = (
        MATERIAL_DIVERGENCE_PCT
        if default_threshold
        else _non_negative("max_divergence_pct", max_divergence_pct)
    )
    note = None
    if justification is not None:
        if not isinstance(justification, str) or not justification.strip():
            raise ValueError("justification must be a non-empty string")
        note = justification.strip()

    used = {name: value for name, value in values.items() if given[name] > 0}
    weight_total = sum(given.values())
    reconciled = sum(values[name] * given[name] for name in values) / weight_total
    # Divergence over every calculated approach: a zero weight must not hide it.
    low, high = min(values.values()), max(values.values())
    bases = {"min": low, "mean": sum(values.values()) / len(values), "max": high}
    if divergence_base not in bases:
        raise ValueError("divergence_base must be 'min', 'mean' or 'max'")
    base = bases[divergence_base]
    # Equal values do not diverge (all zero included); a zero base below a
    # positive value makes the divergence unbounded — above any threshold.
    if high == low:
        divergence = 0.0
    elif base == 0:
        divergence = math.inf
    else:
        divergence = (high - low) / base * 100
    shown = (
        "(одно из значений равно 0) не ограничено и"
        if math.isinf(divergence)
        else f"{_round(divergence)}%"
    )

    checks = []
    status = None
    if divergence > threshold:
        if note is None:
            status = STATUS_NOT_RECONCILED
            checks.append(
                f"Расхождение подходов {shown} больше порога {_round(threshold)}%: "
                "исследуйте причины и обоснуйте веса или выбор подхода (justification)."
            )
        else:
            status = STATUS_REVIEW
            checks.append(
                f"Расхождение подходов {shown} больше порога {_round(threshold)}%; "
                "приведено обоснование оценщика."
            )
    excluded = [name for name in values if given[name] == 0]
    interval = None
    if value_interval is not None:
        if not isinstance(value_interval, Mapping):
            raise ValueError("value_interval must be an object with low, high and justification")
        interval_low = _non_negative("value_interval.low", value_interval.get("low"))
        interval_high = _non_negative("value_interval.high", value_interval.get("high"))
        if interval_low > interval_high:
            raise ValueError("value_interval.low must not exceed value_interval.high")
        reason = value_interval.get("justification")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("value_interval.justification is required: the interval is the appraiser's judgment")
        interval = {"low": _round(interval_low), "high": _round(interval_high), "justification": reason.strip()}
        if not interval_low <= reconciled <= interval_high:
            checks.append(
                f"Согласованная стоимость {_round(reconciled)} вне интервала оценщика "
                f"[{interval['low']}; {interval['high']}]: проверьте интервал."
            )
    if excluded and note is None:
        checks.append(
            f"Подходы {excluded} исключены (вес 0) без обоснования: приведите причину "
            "отказа (justification)."
        )

    result: Dict[str, Any] = {
        "currency": _currency(currency),
        "approach_values": {name: _round(value) for name, value in values.items()},
        "weights": given,
        "weight_shares": dict(zip(given, weight_shares(list(given.values())))),
        # An unresolved reconciliation has no final value, only a diagnostic number.
        "reconciled_value": None if status == STATUS_NOT_RECONCILED else _round(reconciled),
        "deviation_from_reconciled_pct": {
            name: None if reconciled == 0 else _round((value - reconciled) / reconciled * 100)
            for name, value in used.items()
        },
        "divergence_pct": None if math.isinf(divergence) else _round(divergence),
        "divergence_base": divergence_base,
        "divergence_formula": f"(max − min) / {divergence_base} × 100",
        "max_divergence_pct": _round(threshold),
        "justification": note,
        # The spread of the approaches, not an interval of value (ФСО №7, п. 30).
        "approaches_spread": {"low": _round(low), "high": _round(high)},
        "value_interval": interval,
        "guardrails": (
            [
                "Для недвижимости после согласования приведите суждение о границах интервала "
                "стоимости (ФСО №7, п. 30), если задание не указывает иное: value_interval."
            ]
            if interval is None
            else []
        )
        + (
            [
                f"Порог существенного расхождения — {MATERIAL_DIVERGENCE_PCT:g} % по умолчанию; "
                "другой порог задайте параметром max_divergence_pct."
            ]
            if default_threshold
            else []
        ),
        "checks": checks,
    }
    if status == STATUS_NOT_RECONCILED:
        result["weighted_value_diagnostic"] = _round(reconciled)
    if status is not None:
        result["status"] = status
    return result
