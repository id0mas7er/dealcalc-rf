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
    range_position,
    round_step,
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
    zero_weight_checks,
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
    (method 1: K = (S − M) / ((N − 1) S)) or ``count_share_2`` (method 2:
    K ∝ 1 − S_i / Σ(S_j + 1)), both by the number of adjustments.

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
            "adjustments_count": adjusted["adjustments_count"],
            "sum_abs_adjustments_pct": round(adjusted["weights_sum_abs_pct"], 4),
            "adjusted_unit_price": _round(adjusted_unit_price),
            "weight": round(weight, 6),
            **observation_fields(comparable, prefix),
        }
        normalized.append(item)

    share_checks = []
    given = [comparable.get("weight") for comparable in comparables]
    if weighting == "manual" and all(weight is not None for weight in given):
        total_given = sum(raw_weights)
        # Доли, которые в сумме почти 1, но не 1, — ошибка округления (отчёт 46/25-ю: 1,001).
        if 0.98 <= total_given <= 1.02 and not math.isclose(total_given, 1, abs_tol=1e-9):
            share_checks.append(
                f"Веса оценщика в сумме {round(total_given, 6)}, а не 1: они нормированы к 1; "
                "проверьте доли — при умножении на ненормированные веса итог был бы другим."
            )
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
    # Statistics of the sample come from unrounded prices, as the weighted mean
    # does, and only from analogs that carry weight (ревью 30, M4).
    adjusted_prices = [price for price, weight in zip(raw_prices, raw_weights) if weight > 0]
    zero_weight = [item["index"] for item, weight in zip(normalized, raw_weights) if weight == 0]
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
        + variation_checks(sample_variation, len(adjusted_prices))
        + zero_weight_checks(zero_weight)
        + share_checks,
    }


@method_card(
    "COMPARABLE_ITEM_PRICE",
    "ФСО V; ФСО №10, п. 13",
    "P_adj,i — цена аналога с последовательными поправками; V = n × Σ w_i P_adj,i / Σ w_i",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso-10/",
)
def item_comparative_approach(
    comparables: Sequence[Mapping[str, Any]],
    weighting: str = "manual",
    quantity: float = 1,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Comparative approach per object (a machine, equipment without area,
    brand matching or a model dictionary): the price of each analog is
    adjusted step by step (``adjustments``, the step types of
    :func:`comparative_approach`), the value is the weighted mean of the
    adjusted prices times ``quantity`` (identical objects).

    Each comparable is ``{"price", "adjustments", "weight", "source", "date",
    "url", "price_type", "description"}``; ``weighting`` — as in
    :func:`comparative_approach`.
    """

    count = _finite_number("quantity", quantity)
    if count <= 0:
        raise ValueError("quantity must be greater than 0")
    if not comparables:
        raise ValueError("comparables must contain at least one item")
    for index, comparable in enumerate(comparables):
        if not isinstance(comparable, Mapping):
            raise ValueError(f"comparables[{index}] must be an object")
        if "area_sqm" in comparable:
            raise ValueError(f"comparables[{index}].area_sqm: the approach is per object — use comparative_approach")
    base = comparative_approach.__wrapped__(
        1, [dict(comparable, area_sqm=1) for comparable in comparables], currency, weighting
    )
    items = []
    for item in base["comparables"]:
        item = {key: value for key, value in item.items() if key not in ("area_sqm", "unit_price")}
        item["adjusted_price"] = item.pop("adjusted_unit_price")
        items.append(item)
    weighted = base["weighted_unit_price"]
    return {
        "approach": "comparative_per_item",
        "currency": base["currency"],
        "quantity": count,
        "sample_size": base["sample_size"],
        "weighting": weighting,
        "weighting_formula": base["weighting_formula"],
        "weighted_price": weighted,
        "indicated_value": _round(weighted * count),
        "adjusted_price_min": base["adjusted_unit_price_min"],
        "adjusted_price_max": base["adjusted_unit_price_max"],
        "variation": base["variation"],
        "comparables": items,
        "checks": base["checks"],
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
    "pgi"``, of ПВД (the shares of reference books), with ``"base":
    "occupied"`` — of the occupied ПВД, ПВД × (1 − vacancy_pct/100), for
    costs that arise only while the premises are let. Every item is shown in
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
            # occupied: ПВД × occupancy, for costs that arise only while the
            # premises are let (Leifer, «Операционные расходы»).
            bases = {"egi": egi, "pgi": pgi, "occupied": pgi - vacancy_loss}
            if base not in bases:
                raise ValueError(f"{prefix}.base must be 'egi', 'pgi' or 'occupied'")
            amount = bases[base] * value / 100
            item["base"] = base
        else:
            raise ValueError(f"{prefix}.type must be 'abs' or 'pct'")
        total_expenses += amount
        item["amount"] = _round(amount)
        if expense.get("range") is not None:
            bounds = source_range(f"{prefix}.range", expense["range"])
            item["range"] = dict(bounds)
            item.update(range_position(bounds, value))
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
    land_adjustments: Optional[Mapping[str, float]] = None,
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

    ``land_adjustments`` — ``{approach: amount}``, the excess (+) or deficit
    (−) of land (:func:`land_sufficiency`) taken into each approach. The same
    object has the same land: different amounts are flagged unless a
    ``justification`` explains them (the analogs of that approach already
    reflect the land).
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
    land = None
    land_notes: List[str] = []
    if land_adjustments is not None:
        if not isinstance(land_adjustments, Mapping) or set(land_adjustments) != set(values):
            raise ValueError("land_adjustments must name exactly the same approaches as approach_values")
        land = {
            name: _finite_number(f"land_adjustments[{name}]", land_adjustments[name]) for name in values
        }
        if len({round(amount, 2) for amount in land.values()}) > 1:
            text = (
                f"Излишек/недостаток земли учтён в подходах по-разному ({land}): объект один и земля "
                "одна — учтите её одинаково или обоснуйте, почему аналоги подхода её уже отражают"
            )
            if note is None:
                checks.append(f"{text}.")
            else:  # justified by the appraiser: what the report must show (ревью Codex 15.10.2026)
                land_notes.append(f"{text}; приведено обоснование оценщика — оно должно быть в отчёте.")
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
        "land_adjustments": None if land is None else {name: _round(amount) for name, amount in land.items()},
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
    result["guardrails"] += land_notes
    if status == STATUS_NOT_RECONCILED:
        result["weighted_value_diagnostic"] = _round(reconciled)
    if status is not None:
        result["status"] = status
    return result


@method_card(
    "LAND_SUFFICIENCY",
    "ФСО V; ФСО №7, п. 22",
    "S_треб = S_здания / плотность (или задана); ΔS = S_факт − S_треб; Δ = ΔS × c_земли",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
)
def land_sufficiency(
    actual_land_sqm: float,
    land_unit_value: float,
    building_area_sqm: Optional[float] = None,
    building_density: Optional[float] = None,
    required_land_sqm: Optional[float] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Excess (+) or deficit (−) of land of a single property object.

    The land the building typically needs is ``required_land_sqm`` or
    ``building_area_sqm / building_density`` (the typical density of
    development of the analogs: building area per m² of land). The
    difference with the actual plot times the value of 1 m² of land is the
    amount to add (excess) or subtract (deficit) — in every approach whose
    analogs have typical land (:func:`reconcile_approaches`,
    ``land_adjustments``).
    """

    actual = _non_negative("actual_land_sqm", actual_land_sqm)
    unit_value = _non_negative("land_unit_value", land_unit_value)
    if required_land_sqm is not None:
        if building_density is not None:
            raise ValueError("give required_land_sqm or building_density, not both")
        required = _non_negative("required_land_sqm", required_land_sqm)
    else:
        if building_density is None or building_area_sqm is None:
            raise ValueError("give required_land_sqm or building_area_sqm with building_density")
        density = _finite_number("building_density", building_density)
        if density <= 0:
            raise ValueError("building_density must be greater than 0")
        required = _non_negative("building_area_sqm", building_area_sqm) / density
    difference = actual - required
    amount = difference * unit_value
    return {
        "currency": _currency(currency),
        "actual_land_sqm": _round(actual),
        "required_land_sqm": _round(required),
        "difference_sqm": _round(difference),
        "kind": "излишек" if difference > 0 else ("недостаток" if difference < 0 else "нет"),
        "land_unit_value": _round(unit_value),
        "adjustment": _round(amount),
        "guardrails": [
            "Учтите излишек/недостаток земли одинаково во всех подходах, аналоги которых имеют типичную "
            "обеспеченность землёй (сравнительный и доходный), и передайте суммы в "
            "reconcile_approaches (land_adjustments). Цена 1 м² земли — по рынку земли, не из цен ЕОН."
        ] if amount else [],
    }


@method_card(
    "VALUE_ALLOCATION",
    "ФСО V; ФСО №7",
    "V_земли — задана (или V × доля); V_i = (V − V_земли) × A_i k_i / Σ A_j k_j",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
)
def allocate_value(
    total_value: float,
    parts: Sequence[Mapping[str, Any]],
    land_value: Optional[float] = None,
    land_share_pct: Optional[float] = None,
    round_to: Optional[float] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Split the value of a single property object into land and buildings.

    The land is ``land_value`` or ``total_value × land_share_pct / 100``;
    the rest is shared between ``parts`` (``{"name", "area_sqm", "coef"}`` or
    ``{"name", "components": [{"area_sqm", "coef"}]}`` — parts of a building
    with different coefficients, such as heated and unheated premises) in
    proportion to ``Σ area × coef``. ``round_to`` rounds every share (1000 —
    to thousands); if the rounded shares do not add up to the total, the
    difference is reported.
    """

    total = _non_negative("total_value", total_value)
    if (land_value is None) == (land_share_pct is None) and land_value is not None:
        raise ValueError("give land_value or land_share_pct, not both")
    if land_share_pct is not None:
        land = total * _percentage("land_share_pct", land_share_pct, minimum=0, maximum=100) / 100
    else:
        land = _non_negative("land_value", land_value or 0)
    if land > total:
        raise ValueError("land value must not exceed total_value")
    if not parts:
        raise ValueError("parts must contain at least one building or premises")
    weighted = []
    for index, part in enumerate(parts):
        prefix = f"parts[{index}]"
        if not isinstance(part, Mapping) or not isinstance(part.get("name"), str) or not part["name"].strip():
            raise ValueError(f"{prefix} must be an object with a non-empty name")
        components = part.get("components")
        if components is None:
            components = [{"area_sqm": part.get("area_sqm"), "coef": part.get("coef", 1)}]
        if not isinstance(components, Sequence) or not components:
            raise ValueError(f"{prefix}.components must be a non-empty list")
        area = weight = 0.0
        for number, component in enumerate(components):
            if not isinstance(component, Mapping):
                raise ValueError(f"{prefix}.components[{number}] must be an object")
            square = _finite_number(f"{prefix}.components[{number}].area_sqm", component.get("area_sqm"))
            coef = _finite_number(f"{prefix}.components[{number}].coef", component.get("coef", 1))
            if square <= 0 or coef <= 0:
                raise ValueError(f"{prefix}.components[{number}]: area_sqm and coef must be greater than 0")
            area += square
            weight += square * coef
        weighted.append((part["name"].strip(), area, weight))
    step = None
    if round_to is not None:
        step = _finite_number("round_to", round_to)
        if step <= 0:
            raise ValueError("round_to must be greater than 0")

    def rounded(value: float) -> float:
        return round_step(value, step)

    rest = total - land
    weight_total = sum(weight for _, _, weight in weighted)
    items = [
        {
            "name": name,
            "area_sqm": _round(area),
            "weighted_area_sqm": _round(weight),
            "share": round(weight / weight_total, 6),
            "value": _round(rounded(rest * weight / weight_total)),
            "value_per_sqm": _round(rest * weight / weight_total / area),
        }
        for name, area, weight in weighted
    ]
    land_rounded = _round(rounded(land))
    difference = _round(total - land_rounded - sum(item["value"] for item in items))
    return {
        "currency": _currency(currency),
        "total_value": _round(total),
        "land_value": land_rounded,
        "buildings_value": _round(rest),
        "parts": items,
        "rounding_difference": difference,
        "checks": [
            f"Сумма округлённых частей отличается от итога на {difference}: распределите разницу явно."
        ] if difference else [],
    }


@method_card(
    "WEIGHTS_FROM_SCORES",
    "ФСО V, п. 3",
    "w_i = b_i / Σ b_j (b — баллы подхода)",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso-v/",
    context_reminder=False,
)
def weights_from_scores(scores: Mapping[str, float]) -> Dict[str, Any]:
    """Weights of approaches from the appraiser's scores (``{approach:
    score}``): ``w = b / Σ b`` — for :func:`reconcile_approaches`."""

    if not isinstance(scores, Mapping) or not scores:
        raise ValueError("scores must name at least one approach")
    values = {str(name): _non_negative(f"scores[{name}]", value) for name, value in scores.items()}
    total = sum(values.values())
    if total <= 0:
        raise ValueError("scores must not all be zero")
    return {
        "scores": {name: _round(value) for name, value in values.items()},
        "weights": {name: round(value / total, 6) for name, value in values.items()},
        "guardrails": ["Баллы подходов — суждение оценщика: раскройте критерии и оценки по каждому."],
    }


def _iso_date(name: str, value: Any) -> "date":
    from datetime import date

    if not isinstance(value, str):
        raise ValueError(f"{name} must be a date 'YYYY-MM-DD'")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a date 'YYYY-MM-DD'") from exc


@method_card(
    "INDEX_INTERPOLATION",
    "ФСО V; ФСО №7, п. 24 (индексы цен в строительстве)",
    "I(t) = I_1 + (I_2 − I_1) × (t − t_1) / (t_2 − t_1); к базе: I(t) / I_база",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
    context_reminder=False,
)
def interpolate_index(
    on_date: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    base_value: Optional[float] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Linear interpolation of a price index (КО-ИНВЕСТ, Минстрой) to the
    valuation date between two published values ``{"date", "value"}`` (days
    between dates). With ``base_value`` — the index of the base date — the
    ratio ``I(t) / I_base`` is the step for :func:`indexed_replacement_cost`."""

    when = _iso_date("on_date", on_date)
    points = []
    for name, point in (("before", before), ("after", after)):
        if not isinstance(point, Mapping):
            raise ValueError(f"{name} must be an object with date and value")
        value = _finite_number(f"{name}.value", point.get("value"))
        if value <= 0:
            raise ValueError(f"{name}.value must be greater than 0")
        points.append((_iso_date(f"{name}.date", point.get("date")), value))
    (d1, v1), (d2, v2) = points
    if not d1 < d2:
        raise ValueError("before.date must be earlier than after.date")
    share = (when - d1).days / (d2 - d1).days
    value = v1 + (v2 - v1) * share
    if value <= 0:
        raise ValueError(
            f"индекс на {when.isoformat()} получается {round(value, 4)} (экстраполяция за пределы дат): "
            "возьмите опубликованные значения, между которыми лежит дата"
        )
    ratio = None
    if base_value is not None:
        base = _finite_number("base_value", base_value)
        if base <= 0:
            raise ValueError("base_value must be greater than 0")
        ratio = value / base
    return {
        "on_date": when.isoformat(),
        "share": round(share, 6),
        "days": f"{(when - d1).days} / {(d2 - d1).days}",
        "index_value": round(value, 6),
        "ratio_to_base": None if ratio is None else round(ratio, 6),
        "source": source,
        "checks": [] if 0 <= share <= 1 else [
            "Дата оценки вне интервала дат индексов: это экстраполяция — обоснуйте или возьмите опубликованный индекс."
        ],
        "guardrails": [] if source else ["Укажите источник индексов (выпуск КО-ИНВЕСТ, таблица) и класс конструктивной системы."],
    }


@method_card(
    "COMPOSITE_REPLACEMENT_COST",
    "ФСО V; ФСО №7, п. 24",
    "C = Σ_части C_баз,i × Π I_i,k (× общие индексы)",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
)
def composite_replacement_cost(
    parts: Sequence[Mapping[str, Any]],
    common_indices: Optional[Sequence[Mapping[str, Any]]] = None,
    regional_coefficient: float = 1,
    vat_pct: float = 0,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Replacement cost of a building made of parts priced by different
    references (the main building and a veranda by different УПВС
    collections): each part ``{"name", "base_cost"}`` or ``{"name",
    "volume", "unit_cost"}`` with its own ``indices`` goes through its chain
    and then ``common_indices``; the parts are summed, each shown."""

    if not parts:
        raise ValueError("parts must contain at least one part")
    rows = []
    checks: List[str] = []
    total = 0.0
    for index, part in enumerate(parts):
        prefix = f"parts[{index}]"
        if not isinstance(part, Mapping) or not isinstance(part.get("name"), str) or not part["name"].strip():
            raise ValueError(f"{prefix} must be an object with a non-empty name")
        if part.get("base_cost") is not None:
            base = _non_negative(f"{prefix}.base_cost", part["base_cost"])
            volume = unit = None
        else:
            volume = _non_negative(f"{prefix}.volume", part.get("volume"))
            unit = _non_negative(f"{prefix}.unit_cost", part.get("unit_cost"))
            base = volume * unit
        chain = list(part.get("indices") or []) + list(common_indices or [])
        if not chain:
            raise ValueError(f"{prefix}: нужен хотя бы один индекс — indices части или common_indices")
        result = indexed_replacement_cost.__wrapped__(base, chain, regional_coefficient, vat_pct, part["name"], currency)
        checks += [f"{part['name'].strip()}: {text}" for text in result["checks"]]
        total += result["replacement_cost"]
        rows.append({"name": part["name"].strip(), "volume": volume, "unit_cost": unit, "base_cost": _round(base),
                     "steps": result["steps"], "total_index": result["total_index"],
                     "replacement_cost": result["replacement_cost"]})
    return {
        "approach": "cost",
        "currency": _currency(currency),
        "parts": rows,
        "replacement_cost": _round(total),
        "vat_pct": _round(_non_negative("vat_pct", vat_pct)),
        "guardrails": [
            "Индекс каждой части — по её назначению и конструктивной системе (сборник, отрасль): "
            "не переносите индекс одного вида зданий на склады, сети и сооружения."
        ],
        "checks": checks,
    }


@method_card(
    "VAT_BREAKDOWN",
    "НК РФ, ст. 164, 146 (п. 2, пп. 6 — земля)",
    "НДС «в т.ч.» = V_обл × s / (100 + s); сверху = V_обл × s / 100; земля — без НДС",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso-v/",
    context_reminder=False,
)
def vat_breakdown(
    value: float,
    vat_rate_pct: float,
    vat_included: bool = True,
    land_value: float = 0,
    round_to: Optional[float] = None,
) -> Dict[str, Any]:
    """VAT of a value: ``vat_included`` — the value already includes VAT
    («в т.ч.»), otherwise VAT is added on top. ``land_value`` is the part
    that is not subject to VAT (land); it is taken without VAT both ways.
    ``round_to`` rounds the value before the breakdown (as reports round the
    total), VAT is shown to kopecks."""

    total = _non_negative("value", value)
    rate = _non_negative("vat_rate_pct", vat_rate_pct)
    land = _non_negative("land_value", land_value)
    if not isinstance(vat_included, bool):
        raise ValueError("vat_included must be true or false")
    if round_to is not None:
        step = _finite_number("round_to", round_to)
        if step <= 0:
            raise ValueError("round_to must be greater than 0")
    if land > total:
        raise ValueError("land_value must not exceed value")
    if round_to is not None:
        total = round_step(total, step)
        # A total rounded below the land would show land worth more than the
        # whole object (ревью Codex 15.10.2026).
        if land > total:
            raise ValueError(
                f"rounded value {total:g} is less than land_value {land:g}: use a smaller round_to"
            )
    taxable = total - land
    if vat_included:
        vat = taxable * rate / (100 + rate)
        gross, net = total, total - vat
    else:
        vat = taxable * rate / 100
        gross, net = total + vat, total
    return {
        "vat_rate_pct": rate,
        "vat_included": vat_included,
        "land_value": _round(land),
        "taxable_value": _round(taxable),
        "value_without_vat": _round(net),
        "vat": _round(vat),
        "value_with_vat": _round(gross),
    }

