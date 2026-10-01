"""Methods for machinery, equipment and vehicles (FSO No. 10).

Based on Kozlov V.V., Frolov I.S. "Оценка машин и оборудования", published by
the Expert Council association (srosovet.ru). Coefficients are inputs of the
appraiser; no reference tables from the source are embedded.
"""

from __future__ import annotations

import math
from typing import Any, Dict


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
