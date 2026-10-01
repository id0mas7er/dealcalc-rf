"""Investment metrics for annual cash flows: NPV and IRR."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Dict, List

import numpy_financial as npf

from ._adjustments import money
from ._meta import FORMULA_TECHNICAL, method_card


def _flows(cash_flows: Sequence[Any]) -> List[float]:
    if isinstance(cash_flows, (str, bytes)) or not cash_flows:
        raise ValueError("cash_flows must contain at least one value")
    flows = []
    for index, value in enumerate(cash_flows):
        if isinstance(value, bool):
            raise ValueError(f"cash_flows[{index}] must be a number")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"cash_flows[{index}] must be a number") from exc
        if not math.isfinite(number):
            raise ValueError(f"cash_flows[{index}] must be finite")
        flows.append(number)
    return flows


@method_card("NPV", "ФСО V", "NPV = Σ CF_t / (1 + r)^t, t = 0..n", FORMULA_TECHNICAL)
def npv(cash_flows: Sequence[float], discount_rate_pct: float) -> Dict[str, Any]:
    """Net present value of annual cash flows.

    ``cash_flows[0]`` is the flow at period 0 (usually the investment, a
    negative number); ``cash_flows[t]`` is discounted by ``(1 + r) ** t``.
    Every period's discount factor and present value are returned.
    """

    flows = _flows(cash_flows)
    if isinstance(discount_rate_pct, bool):
        raise ValueError("discount_rate_pct must be a number")
    try:
        rate_pct = float(discount_rate_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError("discount_rate_pct must be a number") from exc
    if not math.isfinite(rate_pct) or rate_pct <= -100:
        raise ValueError("discount_rate_pct must be a finite number greater than -100")

    periods = []
    total = 0.0
    for period, flow in enumerate(flows):
        factor = 1 / (1 + rate_pct / 100) ** period
        total += flow * factor
        periods.append(
            {
                "period": period,
                "cash_flow": money(flow),
                "discount_factor": round(factor, 6),
                "present_value": money(flow * factor),
            }
        )
    return {
        "discount_rate_pct": money(rate_pct),
        "npv": money(total),
        "periods": periods,
    }


@method_card("IRR", "ФСО V", "Σ CF_t / (1 + IRR)^t = 0", FORMULA_TECHNICAL)
def irr(cash_flows: Sequence[float]) -> Dict[str, Any]:
    """Internal rate of return of annual cash flows, in percent.

    ``cash_flows[0]`` is the flow at period 0. The flows must contain both
    negative and positive values. With several sign changes more than one
    IRR may exist; the one found by ``numpy_financial.irr`` is returned.
    """

    flows = _flows(cash_flows)
    if not (any(flow < 0 for flow in flows) and any(flow > 0 for flow in flows)):
        raise ValueError("cash_flows must contain both negative and positive values (sign change)")
    result = npf.irr(flows)
    if result is None or not math.isfinite(result):
        raise ValueError("IRR could not be found for these cash flows (sign change)")
    sign_changes = sum(
        1 for previous, current in zip(flows, flows[1:]) if previous * current < 0
    )
    return {
        "cash_flows": [money(flow) for flow in flows],
        "irr_pct": money(result * 100),
        "sign_changes": sign_changes,
        "checks": [
            f"Знак потоков меняется {sign_changes} раз(а): возможны несколько значений IRR."
        ]
        if sign_changes > 1
        else [],
    }


def _rate(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number) or number <= -100:
        raise ValueError(f"{name} must be a finite number greater than -100")
    return number


@method_card(
    "GORDON_TERMINAL_VALUE",
    "ФСО V, п. 21",
    "TV_n = CF_(n+1) / (r − g)",
    "частная модель постоянного роста; условия применения — ФСО V, п. 21, параметры не заданы",
)
def gordon_terminal_value(
    cash_flow_next: float, discount_rate_pct: float, growth_rate_pct: float
) -> Dict[str, Any]:
    """Terminal value by the constant-growth (Gordon) model.

    ``TV_n = CF_(n+1) / (r - g)``, where ``cash_flow_next`` is the flow of
    the first post-forecast year. Requires ``r > g``; the model applies to a
    stable flow with a long or unlimited useful life.
    """

    flow = _flows([cash_flow_next])[0]
    rate = _rate("discount_rate_pct", discount_rate_pct)
    growth = _rate("growth_rate_pct", growth_rate_pct)
    if rate <= growth:
        raise ValueError("discount_rate_pct must be greater than growth_rate_pct (r > g)")
    return {
        "cash_flow_next": money(flow),
        "discount_rate_pct": money(rate),
        "growth_rate_pct": money(growth),
        "terminal_value": money(flow / ((rate - growth) / 100)),
        "conditions": [
            "устойчивый поток после прогнозного периода",
            "длительный или неограниченный срок использования",
            "обоснованные ставка r и темп роста g, r > g",
        ],
    }
