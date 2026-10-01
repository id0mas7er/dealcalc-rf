"""Methods for machinery, equipment and vehicles (FSO No. 10).

Based on Kozlov V.V., Frolov I.S. "Оценка машин и оборудования", published by
the Expert Council association (srosovet.ru). Coefficients are inputs of the
appraiser; no reference tables from the source are embedded.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from ._adjustments import json_value


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive(name: str, value: Any) -> float:
    number = _number(name, value)
    if number <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return number


def braking_coefficient(
    price_1: float, param_1: float, price_2: float, param_2: float
) -> Dict[str, Any]:
    """Braking coefficient of a parameter from two analogs (formula 24).

    ``b = ln(price_2 / price_1) / ln(param_2 / param_1)``. The analogs should
    differ only in this parameter. Use ``b`` as the ``exponent`` of a
    ``param`` adjustment step: ``price * (subject / analog) ** b``.
    """

    p1 = _positive("price_1", price_1)
    x1 = _positive("param_1", param_1)
    p2 = _positive("price_2", price_2)
    x2 = _positive("param_2", param_2)
    if x1 == x2:
        raise ValueError("param_1 and param_2 must be different")
    return {
        "price_1": p1,
        "param_1": x1,
        "price_2": p2,
        "param_2": x2,
        "braking_coefficient": round(math.log(p2 / p1) / math.log(x2 / x1), 4),
    }


def new_equivalent_price(price: float, total_depreciation_pct: float) -> Dict[str, Any]:
    """Price a used analog would have as new (formula 22).

    ``new_equivalent_price = price / (1 - total_depreciation_pct / 100)``,
    where ``total_depreciation_pct`` is the analog's total depreciation.
    """

    analog_price = _positive("price", price)
    depreciation = _number("total_depreciation_pct", total_depreciation_pct)
    if not 0 <= depreciation < 100:
        raise ValueError("total_depreciation_pct must be in [0, 100)")
    return {
        "price": round(analog_price, 2),
        "total_depreciation_pct": round(depreciation, 2),
        "new_equivalent_price": round(analog_price / (1 - depreciation / 100), 2),
    }


def _non_negative(name: str, value: Any) -> float:
    number = _number(name, value)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def parameter_unit_price(
    price_1: float, param_1: float, price_2: float, param_2: float
) -> Dict[str, Any]:
    """Price of one unit of a parameter from two analogs.

    ``g = (price_1 - price_2) / (param_1 - param_2)``. The analogs should
    differ only in this parameter. Use it for an ``abs`` adjustment step:
    ``g * (subject_param - analog_param)``.
    """

    p1 = _non_negative("price_1", price_1)
    x1 = _number("param_1", param_1)
    p2 = _non_negative("price_2", price_2)
    x2 = _number("param_2", param_2)
    if x1 == x2:
        raise ValueError("param_1 and param_2 must be different")
    return {
        "price_1": p1,
        "param_1": x1,
        "price_2": p2,
        "param_2": x2,
        "unit_price": round((p1 - p2) / (x1 - x2), 4),
    }


def chain_index(price_start: float, price_end: float, periods: float) -> Dict[str, Any]:
    """Average chain price index between two prices of a similar object.

    ``h = (price_end / price_start) ** (1 / periods)``.
    """

    start = _positive("price_start", price_start)
    end = _positive("price_end", price_end)
    count = _positive("periods", periods)
    return {
        "price_start": start,
        "price_end": end,
        "periods": count,
        "chain_index": round((end / start) ** (1 / count), 6),
    }


def index_price(base_price: float, chain_index: float, periods: float) -> Dict[str, Any]:
    """Index a known past price to the valuation date (index method).

    ``indexed_price = base_price * chain_index ** periods``; ``chain_index``
    is the average chain index per period (e.g. month), ``periods`` the
    number of periods from the base date to the valuation date.
    """

    base = _non_negative("base_price", base_price)
    index = _positive("chain_index", chain_index)
    count = _non_negative("periods", periods)
    total = index**count
    return {
        "base_price": round(base, 2),
        "chain_index": index,
        "periods": count,
        "total_index": round(total, 6),
        "indexed_price": round(base * total, 2),
    }


def physical_depreciation(
    age_years: float,
    economic_life_years: float,
    replacement_cost: Optional[float] = None,
    annual_repair_cost: float = 0,
    salvage_value: float = 0,
    actual_load: float = 1,
    normative_load: float = 1,
) -> Dict[str, Any]:
    """Physical depreciation under the linear model (table 5, row 15).

    ::

        curable   = annual_repair_cost * n / ПВС
        incurable = (Кз факт / Кз норм) * n / (Nэж * ПВС)
                    * (ПВС - salvage_value - annual_repair_cost * Nэж)

    ``annual_repair_cost`` is Кт/р × Нз × Рсл — annual repair costs at
    current prices. Without repair costs and salvage value the formula
    reduces to ``(Кз факт / Кз норм) * n / Nэж`` and ``replacement_cost``
    is not needed. The total is capped at 100%.
    """

    age = _non_negative("age_years", age_years)
    life = _positive("economic_life_years", economic_life_years)
    repair = _non_negative("annual_repair_cost", annual_repair_cost)
    salvage = _number("salvage_value", salvage_value)
    load_ratio = _positive("actual_load", actual_load) / _positive(
        "normative_load", normative_load
    )

    if repair == 0 and salvage == 0:
        cost = None if replacement_cost is None else _positive("replacement_cost", replacement_cost)
        curable = 0.0
        incurable = load_ratio * age / life
    else:
        if replacement_cost is None:
            raise ValueError(
                "replacement_cost is required with annual_repair_cost or salvage_value"
            )
        cost = _positive("replacement_cost", replacement_cost)
        curable = repair * age / cost
        incurable = load_ratio * age / (life * cost) * (cost - salvage - repair * life)

    total = (curable + incurable) * 100
    capped = total > 100
    return {
        "age_years": age,
        "economic_life_years": life,
        "replacement_cost": None if cost is None else round(cost, 2),
        "annual_repair_cost": round(repair, 2),
        "salvage_value": round(salvage, 2),
        "load_ratio": round(load_ratio, 4),
        "curable_pct": round(curable * 100, 2),
        "incurable_pct": round(incurable * 100, 2),
        "total_pct": 100.0 if capped else round(total, 2),
        "capped": capped,
    }


def scrap_value(
    mass_kg: float, scrap_price_per_kg: float, disposal_cost: float = 0
) -> Dict[str, Any]:
    """Salvage value by scrap metal: ``mass_kg * scrap_price_per_kg - disposal_cost``.

    A negative result means the owner pays for disposal.
    """

    mass = _non_negative("mass_kg", mass_kg)
    price = _non_negative("scrap_price_per_kg", scrap_price_per_kg)
    cost = _non_negative("disposal_cost", disposal_cost)
    return {
        "mass_kg": mass,
        "scrap_price_per_kg": price,
        "disposal_cost": round(cost, 2),
        "scrap_value": round(mass * price - cost, 2),
    }


def residual_value(
    replacement_cost: float, total_depreciation_pct: float, salvage_value: float = 0
) -> Dict[str, Any]:
    """Residual (market) value with salvage value (formula 10).

    ``value = replacement_cost * (1 - total_depreciation_pct / 100) + salvage_value``;
    a negative ``salvage_value`` is a disposal cost.
    """

    cost = _non_negative("replacement_cost", replacement_cost)
    depreciation = _number("total_depreciation_pct", total_depreciation_pct)
    if not 0 <= depreciation <= 100:
        raise ValueError("total_depreciation_pct must be in [0, 100]")
    salvage = _number("salvage_value", salvage_value)
    depreciated = cost * (1 - depreciation / 100)
    return {
        "replacement_cost": round(cost, 2),
        "total_depreciation_pct": round(depreciation, 2),
        "depreciated_value": round(depreciated, 2),
        "salvage_value": round(salvage, 2),
        "residual_value": round(depreciated + salvage, 2),
    }


def _price_structure(
    profitability_pct: Any, vat_pct: Any, profit_tax_pct: Any
) -> Dict[str, Optional[float]]:
    profitability = _non_negative("profitability_pct", profitability_pct) / 100
    if profitability >= 1:
        raise ValueError("profitability_pct must be less than 100")
    vat = _non_negative("vat_pct", vat_pct) / 100
    tax = None
    if profit_tax_pct is not None:
        tax = _non_negative("profit_tax_pct", profit_tax_pct) / 100
        if tax + profitability >= 1:
            raise ValueError("profit_tax_pct plus profitability_pct must be less than 100")
    return {"profitability": profitability, "vat": vat, "tax": tax}


def _cost_share(structure: Dict[str, Optional[float]]) -> float:
    """Full cost as a share of the price without VAT (formulas 13 and 16)."""

    profitability = structure["profitability"]
    tax = structure["tax"]
    if tax is None:
        return 1 - profitability
    return (1 - tax - profitability) / (1 - tax)


def _price_breakdown(price: float, cost: float, vat: float) -> Dict[str, float]:
    price_without_vat = price / (1 + vat)
    return {
        "price": round(price, 2),
        "vat": round(price - price_without_vat, 2),
        "price_without_vat": round(price_without_vat, 2),
        "profit": round(price_without_vat - cost, 2),
        "full_cost": round(cost, 2),
    }


def _structure_fields(structure: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    tax = structure["tax"]
    return {
        "profitability_pct": round(structure["profitability"] * 100, 2),
        "vat_pct": round(structure["vat"] * 100, 2),
        "profit_tax_pct": None if tax is None else round(tax * 100, 2),
    }


def cost_from_price(
    price: float,
    profitability_pct: float,
    vat_pct: float = 0,
    profit_tax_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Full production cost from the manufacturer's price.

    ``profitability_pct`` is the return on sales (profit / price without
    VAT): ``cost = (1 - Кр) * price / (1 + НДС)`` (formula 13). When
    ``profit_tax_pct`` is given, ``profitability_pct`` is the net return on
    sales and ``cost = (1 - Нпр - Кчр) * price / ((1 + НДС) * (1 - Нпр))``
    (formula 16). The VAT rate is an input; no default rate is assumed.
    """

    value = _non_negative("price", price)
    structure = _price_structure(profitability_pct, vat_pct, profit_tax_pct)
    cost = value / (1 + structure["vat"]) * _cost_share(structure)
    return {**_structure_fields(structure), **_price_breakdown(value, cost, structure["vat"])}


def price_from_cost(
    cost: float,
    profitability_pct: float,
    vat_pct: float = 0,
    profit_tax_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Manufacturer's price from full production cost (formulas 12 and 15).

    The inverse of :func:`cost_from_price` with the same parameters.
    """

    full_cost = _non_negative("cost", cost)
    structure = _price_structure(profitability_pct, vat_pct, profit_tax_pct)
    price = full_cost / _cost_share(structure) * (1 + structure["vat"])
    return {**_structure_fields(structure), **_price_breakdown(price, full_cost, structure["vat"])}


def qualitative_adjustments(analogs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Method of directed qualitative adjustments (formulas 26 and 27).

    Each analog has ``price`` and ``adjustments``: a list of
    ``{"name", "direction": "up" | "down", "weight"}`` items (weight 1 by
    default; e.g. 3/2/1 for strong/medium/weak). Up and down adjustments
    neutralize each other. An analog with more up adjustments is a lower
    analog, with more down adjustments an upper analog, otherwise neutral
    (reported, not used in pairs). For each lower/upper pair::

        value = (Цн * N−в + Цв * N+н) / (N−в + N+н)

    ``weighted_value`` averages all pairs with weights inversely proportional
    to the total adjustments of the pair; ``range_value`` uses the upper
    analog with the fewest effective adjustments (lowest price on ties) and
    the lower analog with the fewest effective adjustments (highest price on
    ties). The appraiser chooses between them.
    """

    if not analogs:
        raise ValueError("analogs must contain at least one item")

    described = []
    for index, analog in enumerate(analogs):
        prefix = f"analogs[{index}]"
        if not isinstance(analog, Mapping):
            raise ValueError(f"{prefix} must be an object")
        price = _non_negative(f"{prefix}.price", analog.get("price"))
        steps = analog.get("adjustments") or []
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
            raise ValueError(f"{prefix}.adjustments must be a list")
        up = down = 0.0
        shown: List[Dict[str, Any]] = []
        for number, step in enumerate(steps):
            step_prefix = f"{prefix}.adjustments[{number}]"
            if not isinstance(step, Mapping):
                raise ValueError(f"{step_prefix} must be an object")
            name = step.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{step_prefix}.name must be a non-empty string")
            direction = step.get("direction")
            if direction not in ("up", "down"):
                raise ValueError(f"{step_prefix}.direction must be 'up' or 'down'")
            weight = _positive(f"{step_prefix}.weight", step.get("weight", 1))
            if direction == "up":
                up += weight
            else:
                down += weight
            shown.append({"name": name.strip(), "direction": direction, "weight": weight})
        effective = up - down
        item: Dict[str, Any] = {
            "index": index + 1,
            "price": round(price, 2),
            "adjustments": shown,
            "up": up,
            "down": down,
            "effective": abs(effective),
            "role": "lower" if effective > 0 else "upper" if effective < 0 else "neutral",
        }
        for key in ("source", "date"):
            if key in analog:
                item[key] = json_value(analog[key])
        described.append((item, price, effective, up + down))

    lower = [entry for entry in described if entry[2] > 0]
    upper = [entry for entry in described if entry[2] < 0]
    if not lower or not upper:
        raise ValueError("at least one lower and one upper analog are required")

    def pair_value(low: Any, high: Any) -> float:
        n_up, n_down = low[2], -high[2]
        return (low[1] * n_down + high[1] * n_up) / (n_down + n_up)

    pairs = []
    raw_weights = []
    for low in lower:
        for high in upper:
            raw_weights.append(1 / (low[3] + high[3]))
            pairs.append(
                {"lower": low[0]["index"], "upper": high[0]["index"], "value": pair_value(low, high)}
            )
    weight_sum = sum(raw_weights)
    weighted = 0.0
    for pair, raw in zip(pairs, raw_weights):
        pair["weight"] = raw / weight_sum
        weighted += pair["value"] * pair["weight"]
        pair["value"] = round(pair["value"], 2)

    best_upper = min(upper, key=lambda entry: (-entry[2], entry[1]))
    best_lower = min(lower, key=lambda entry: (entry[2], -entry[1]))
    return {
        "method": "qualitative_adjustments",
        "analogs": [entry[0] for entry in described],
        "pairs": pairs,
        "weighted_value": round(weighted, 2),
        "range_value": round(pair_value(best_lower, best_upper), 2),
        "range_pair": {"lower": best_lower[0]["index"], "upper": best_upper[0]["index"]},
    }
