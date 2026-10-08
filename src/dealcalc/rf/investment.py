"""Investment metrics for annual cash flows: NPV and IRR."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

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


@method_card("NPV", 'ФСО V, п. 15', "NPV = Σ CF_t / (1 + r)^t, t = 0..n", FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso-v/", income_model=True)
def npv(cash_flows: Sequence[float], discount_rate_pct: float) -> Dict[str, Any]:
    """Net present value of annual cash flows.

    ``cash_flows[0]`` is the flow at PERIOD 0 (usually the investment, a
    negative number, not discounted); ``cash_flows[t]`` is discounted by
    ``(1 + r) ** t``. Unlike :func:`dcf_valuation`, where the first flow is
    year 1.
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
        "first_cash_flow_period": 0,
        "discount_rate_pct": money(rate_pct),
        "npv": money(total),
        "periods": periods,
        "checks": [f"Ставка дисконтирования {money(rate_pct)} % не больше нуля: обоснуйте её или проверьте ввод."] if rate_pct <= 0 else [],
    }


@method_card("IRR", 'ФСО V', "Σ CF_t / (1 + IRR)^t = 0", FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso-v/", context_reminder=False)
def irr(cash_flows: Sequence[float]) -> Dict[str, Any]:
    """Internal rate of return of annual cash flows, in percent.

    ``cash_flows[0]`` is the flow at period 0. The flows must contain both
    negative and positive values. With several sign changes more than one
    IRR may exist; ``numpy_financial.irr`` returns the root closest to zero,
    which may be negative while a positive one exists.
    """

    flows = _flows(cash_flows)
    if not (any(flow < 0 for flow in flows) and any(flow > 0 for flow in flows)):
        raise ValueError("cash_flows must contain both negative and positive values (sign change)")
    result = npf.irr(flows)
    if result is None or not math.isfinite(result):
        raise ValueError("IRR could not be found for these cash flows (sign change)")
    nonzero = [flow for flow in flows if flow != 0]
    sign_changes = sum(
        1 for previous, current in zip(nonzero, nonzero[1:]) if previous * current < 0
    )
    return {
        "cash_flows": [money(flow) for flow in flows],
        "irr_pct": money(result * 100),
        "sign_changes": sign_changes,
        "checks": [
            f"Знак потоков меняется {sign_changes} раз(а): возможны несколько значений IRR; "
            "выбран корень, ближайший к нулю — проверьте профиль NPV."
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
    source_url="https://srosovet.ru/activities/npa/fso-v/",
    income_model=True,
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
    checks = []
    if flow <= 0:
        checks.append(
            "Поток первого постпрогнозного года не больше нуля: модель Гордона даёт "
            "неположительную стоимость — проверьте прогноз."
        )
    if rate <= 0:
        checks.append(f"Ставка дисконтирования {money(rate)} % не больше нуля: обоснуйте её или проверьте ввод.")
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
        "checks": checks,
    }


@method_card(
    "ASSET_LIQUIDATION_VALUE",
    "ФСО II (ликвидационная стоимость; вынужденная продажа)",
    "V_л = V_р × (1 + r)^(−(T_р − T_л) / 12) × (1 − d_вын) − З_доп",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso-ii/",
)
def asset_liquidation_value(
    market_value: float,
    discount_rate_pct: float,
    typical_exposure_months: float,
    liquidation_exposure_months: float,
    additional_costs: float = 0,
    forced_sale_discount_pct: Optional[float] = None,
    forced_sale_justification: Optional[str] = None,
) -> Dict[str, Any]:
    """Liquidation value of a single asset (property, machine, vehicle).

    The market value is discounted for the shortened exposure period of a
    forced sale: ``V_l = V_m × (1 + r) ** (−(T_typical − T_forced) / 12)``,
    where ``r`` is the appraiser's annual rate and the periods are in
    months; ``additional_costs`` (sale costs specific to the forced sale)
    are subtracted. The rate, both periods and the costs must be justified.

    This factor is only the time value of the shorter exposure. The discount
    for the forced nature of the sale (price elasticity of demand) is
    ``forced_sale_discount_pct``, applied after it; it requires
    ``forced_sale_justification``. Without it the result omits that discount.
    """

    value = _rate("market_value", market_value)
    if value < 0:
        raise ValueError("market_value must be non-negative")
    rate = _rate("discount_rate_pct", discount_rate_pct)
    typical = _flows([typical_exposure_months])[0]
    forced = _flows([liquidation_exposure_months])[0]
    if typical <= 0:
        raise ValueError("typical_exposure_months must be greater than 0")
    if forced < 0:
        raise ValueError("liquidation_exposure_months must be non-negative")
    if forced > typical:
        raise ValueError("liquidation_exposure_months must not exceed typical_exposure_months")
    costs = _flows([additional_costs])[0]
    if costs < 0:
        raise ValueError("additional_costs must be non-negative")
    forced_discount = None
    justification = None
    if forced_sale_discount_pct is not None:
        forced_discount = _rate("forced_sale_discount_pct", forced_sale_discount_pct)
        if not 0 <= forced_discount < 100:
            raise ValueError("forced_sale_discount_pct must be from 0 to less than 100")
        if not isinstance(forced_sale_justification, str) or not forced_sale_justification.strip():
            raise ValueError("forced_sale_justification is required with forced_sale_discount_pct")
        justification = forced_sale_justification.strip()

    factor = (1 + rate / 100) ** (-(typical - forced) / 12)
    total_factor = factor * (1 - (forced_discount or 0) / 100)
    discounted = value * total_factor
    # Price of the forced sale and net proceeds after its specific costs.
    liquidation = discounted - costs
    checks = []
    guardrails = [
        "Обоснуйте типичный срок экспозиции, срок вынужденной продажи и ставку дисконтирования.",
        "Ликвидационная стоимость моделирует вынужденную продажу: не подменяйте ею рыночную.",
    ]
    if forced_discount is None:
        guardrails.append(
            "Скидка учитывает только стоимость времени (сокращение экспозиции), "
            "а не вынужденность продажи (эластичность спроса): при необходимости "
            "задайте forced_sale_discount_pct с обоснованием."
        )
    if liquidation < 0:
        checks.append("Ликвидационная стоимость отрицательна: проверьте затраты и ставку.")
    return {
        "value_kind": "ликвидационная стоимость",
        "market_value": money(value),
        "discount_rate_pct": money(rate),
        "typical_exposure_months": typical,
        "liquidation_exposure_months": forced,
        "liquidation_factor": round(factor, 6),
        "liquidation_discount_pct": money((1 - factor) * 100),
        "forced_sale_discount_pct": None if forced_discount is None else money(forced_discount),
        "forced_sale_justification": justification,
        "total_discount_pct": money((1 - total_factor) * 100),
        "liquidation_price": money(discounted),
        "additional_costs": money(costs),
        "liquidation_value": money(liquidation),
        "guardrails": guardrails,
        "checks": checks,
    }


def _named_premiums(premiums: Any) -> List[Dict[str, Any]]:
    if isinstance(premiums, (str, bytes)) or not isinstance(premiums, Sequence):
        raise ValueError("premiums must be a list")
    result = []
    for index, premium in enumerate(premiums):
        prefix = f"premiums[{index}]"
        if not isinstance(premium, Mapping):
            raise ValueError(f"{prefix} must be an object")
        name = premium.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{prefix}.name must be a non-empty string")
        value = _flows([premium.get("value")])[0]
        item: Dict[str, Any] = {"name": name.strip(), "value_pct": value}
        if premium.get("source"):
            item["source"] = str(premium["source"])
        result.append(item)
    return result


@method_card(
    "DISCOUNT_RATE_BUILD_UP",
    "ФСО V, п. 15; ФСО №7, п. 23 (д)",
    "Y = безрисковая ставка + Σ премий за риски",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
    context_reminder=False,
)
def discount_rate_build_up(
    risk_free_rate_pct: float,
    premiums: Sequence[Mapping[str, Any]],
    risk_free_source: str = "",
) -> Dict[str, Any]:
    """Discount rate by the cumulative build-up method.

    ``Y = risk-free rate + Σ premiums``; each premium is ``{"name",
    "value", "source"}`` (e.g. risk of investment, low liquidity through the
    exposure period, investment management). Every component and its source
    come from the appraiser.
    """

    free = _rate("risk_free_rate_pct", risk_free_rate_pct)
    items = _named_premiums(premiums)
    total = free + sum(item["value_pct"] for item in items)
    checks = []
    if not risk_free_source:
        checks.append("Не указан источник безрисковой ставки (например, доходность ОФЗ на дату оценки).")
    no_source = [item["name"] for item in items if "source" not in item]
    if no_source:
        checks.append(f"Не указаны источники премий: {no_source}.")
    if total <= 0:
        checks.append(f"Итоговая ставка {money(total)} % не больше нуля: проверьте знаки премий.")
    return {
        "risk_free_rate_pct": money(free),
        "risk_free_source": risk_free_source or None,
        "premiums": items,
        "discount_rate_pct": money(total),
        "checks": checks,
    }


_RECOVERY_METHODS = {
    "ring": "Ринга (прямолинейный возврат)",
    "inwood": "Инвуда (возврат по ставке дохода)",
    "hoskold": "Хоскольда (возврат по безрисковой ставке)",
}


@method_card(
    "CAPITAL_RECOVERY_RATE",
    "ФСО №7, п. 23 (д): ставка с учётом модели возврата капитала",
    "R = Y + Δ × норма возврата; Ринг: 1/n; Инвуд: Y/((1+Y)^n − 1); Хоскольд: Yб/((1+Yб)^n − 1)",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
    context_reminder=False,
)
def capital_recovery_rate(
    discount_rate_pct: float,
    remaining_life_years: float,
    method: str,
    safe_rate_pct: Optional[float] = None,
    value_change_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Capitalization rate = return on capital + return of capital.

    ``method``: ``ring`` (straight-line, 1/n), ``inwood`` (sinking fund at
    the discount rate) or ``hoskold`` (sinking fund at the safe rate
    ``safe_rate_pct``). ``remaining_life_years`` is the remaining economic
    life of the depreciating part. The choice of model is the appraiser's.

    ``value_change_pct`` (Δ) is the share of value lost over that period:
    ``R = Y + Δ × recovery``; negative when the value grows. Unset means a
    full loss (Δ = 100 %), which overstates the rate when land is a
    substantial part of the value.
    """

    if method not in _RECOVERY_METHODS:
        raise ValueError("method must be 'ring', 'inwood' or 'hoskold'")
    rate = _rate("discount_rate_pct", discount_rate_pct) / 100
    life = _flows([remaining_life_years])[0]
    if life <= 0:
        raise ValueError("remaining_life_years must be greater than 0")

    def sinking_fund(y: float) -> float:
        # expm1/log1p keep (1 + y)^n − 1 accurate for rates close to zero.
        if y == 0:
            return 1 / life
        try:
            return y / math.expm1(life * math.log1p(y))
        except OverflowError:
            # (1 + y)^n beyond the float range: the factor is 0 to any precision.
            return 0.0

    if method == "ring":
        recovery = 1 / life
        safe = None
    elif method == "inwood":
        recovery = sinking_fund(rate)
        safe = None
    else:
        if safe_rate_pct is None:
            raise ValueError("safe_rate_pct is required for the Hoskold method")
        safe = _rate("safe_rate_pct", safe_rate_pct) / 100
        recovery = sinking_fund(safe)
    guardrails = []
    if value_change_pct is None:
        change = 100.0
        guardrails.append(
            "Принята полная потеря стоимости за срок (Δ = 100 %): для объектов с "
            "землёй или растущей стоимостью задайте value_change_pct."
        )
    else:
        # Growth may exceed 100 %, so no lower bound; a loss cannot exceed 100 %.
        if isinstance(value_change_pct, bool) or not isinstance(value_change_pct, (int, float)):
            raise ValueError("value_change_pct must be a number")
        change = float(value_change_pct)
        if not math.isfinite(change) or change > 100:
            raise ValueError("value_change_pct must be a finite number not above 100")
    recovery *= change / 100
    return {
        "method": method,
        "method_label": _RECOVERY_METHODS[method],
        "discount_rate_pct": money(rate * 100),
        "safe_rate_pct": None if safe is None else money(safe * 100),
        "remaining_life_years": life,
        "value_change_pct": change,
        "recovery_rate_pct": round(recovery * 100, 4),
        "capitalization_rate_pct": round((rate + recovery) * 100, 4),
        "guardrails": guardrails,
        "checks": [],
    }


@method_card(
    "REVERSION_VALUE",
    "ФСО V, п. 15; ФСО №7, п. 23 (б)",
    "V_рев = ЧОД_(n+1) / R_терм × (1 − расходы на продажу)",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso7/",
    income_model=True,
)
def reversion_value(
    noi_next_year: float,
    terminal_cap_rate_pct: float,
    selling_costs_pct: float = 0,
) -> Dict[str, Any]:
    """Reversion (resale) value at the end of the forecast period.

    ``NOI of year n + 1 / terminal capitalization rate``, less selling costs
    as a percent of the gross reversion. Use the result as the
    ``terminal_value`` of the discounted cash flow.
    """

    noi = _flows([noi_next_year])[0]
    if noi < 0:
        raise ValueError("noi_next_year must be non-negative")
    rate = _rate("terminal_cap_rate_pct", terminal_cap_rate_pct)
    if rate <= 0:
        raise ValueError("terminal_cap_rate_pct must be greater than 0")
    costs = _flows([selling_costs_pct])[0]
    if not 0 <= costs < 100:
        raise ValueError("selling_costs_pct must be in [0, 100)")
    gross = noi / (rate / 100)
    return {
        "noi_next_year": money(noi),
        "terminal_cap_rate_pct": money(rate),
        "gross_reversion": money(gross),
        "selling_costs_pct": money(costs),
        "selling_costs": money(gross * costs / 100),
        "reversion_value": money(gross * (1 - costs / 100)),
        "checks": [],
    }
