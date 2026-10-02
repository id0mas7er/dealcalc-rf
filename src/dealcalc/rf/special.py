"""Special methods from the Expert Council recommendations (srosovet.ru).

These are recommendations for particular tasks, not FSO norms: market rent
by the cost-plus model (МРз–1/26), rent of a site for cellular equipment
(МР–3/26 (2)), external obsolescence of grid assets (МРз–8/23-2) and units of
closed-end funds (МРз–5/23). Formulas for external obsolescence are
engineering records: the source gives its equations as images.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from ._adjustments import money
from ._meta import FORMULA_RECOMMENDATION, method_card

FORMULA_ENGINEERING = (
    "инженерная запись приёма рекомендации; формулы источника даны изображениями"
)


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


def _non_negative(name: str, value: Any) -> float:
    number = _number(name, value)
    if number < 0:
        raise ValueError(f"{name} must be non-negative")
    return number


def _positive(name: str, value: Any) -> float:
    number = _number(name, value)
    if number <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return number


def _loss_pct(name: str, value: Any) -> float:
    number = _non_negative(name, value)
    if number >= 100:
        raise ValueError(f"{name} must be less than 100")
    return number


def _rate(name: str, value: Any) -> float:
    number = _number(name, value)
    if number <= -100:
        raise ValueError(f"{name} must be greater than -100")
    return number


def _currency(currency: Any) -> str:
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency must be a non-empty string")
    return currency.strip().upper()


def _flows(values: Any, name: str) -> List[float]:
    if isinstance(values, (str, bytes)) or not values:
        raise ValueError(f"{name} must contain at least one value")
    return [_number(f"{name}[{index}]", value) for index, value in enumerate(values)]


@method_card(
    "MARKET_RENT_COST_PLUS",
    "МРз–1/26, затратный подход (метод компенсации затрат); ФСО №7; ФСО V",
    "ЧОД_треб = V × R; ДВД = (ЧОД + расходы руб.) / (1 − расходы % ДВД); "
    "ПВД = ДВД / ((1 − недозагрузка)(1 − недосбор))",
    FORMULA_RECOMMENDATION,
    source_url="https://srosovet.ru/Metod/metodicheskierecommenrazn123/120126/",
)
def market_rent_cost_plus(
    property_value: float,
    cap_rate_pct: float,
    owner_expenses: Optional[Sequence[Mapping[str, Any]]] = None,
    vacancy_pct: float = 0,
    collection_loss_pct: float = 0,
    rentable_area_sqm: Optional[float] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Market rent by the cost-plus (compensation) model.

    Required NOI = market value of the property × overall capitalization
    rate. Owner expenses not passed to the tenant (``{"name", "type",
    "value"}``: ``abs`` RUB per year, ``pct`` percent of ДВД) and losses are
    added back to reach the gross rent (ПВД). This is the inverse of the NOI
    build-up. Market rent is a separate value, not the value of the
    property or of the leasehold.
    """

    value = _non_negative("property_value", property_value)
    rate = _positive("cap_rate_pct", cap_rate_pct)
    vacancy = _loss_pct("vacancy_pct", vacancy_pct)
    collection = _loss_pct("collection_loss_pct", collection_loss_pct)
    area = None if rentable_area_sqm is None else _positive("rentable_area_sqm", rentable_area_sqm)

    abs_total = 0.0
    pct_total = 0.0
    items = []
    for index, expense in enumerate(owner_expenses or []):
        prefix = f"owner_expenses[{index}]"
        if not isinstance(expense, Mapping):
            raise ValueError(f"{prefix} must be an object")
        name = expense.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{prefix}.name must be a non-empty string")
        kind = expense.get("type")
        amount = _non_negative(f"{prefix}.value", expense.get("value"))
        if kind == "abs":
            abs_total += amount
        elif kind == "pct":
            pct_total += amount
        else:
            raise ValueError(f"{prefix}.type must be 'abs' or 'pct'")
        items.append({"name": name.strip(), "type": kind, "value": amount})
    if pct_total >= 100:
        raise ValueError("owner expenses in percent of ДВД must be less than 100 in total")

    noi = value * rate / 100
    egi = (noi + abs_total) / (1 - pct_total / 100)
    for item in items:
        item["amount"] = money(item["value"] if item["type"] == "abs" else egi * item["value"] / 100)
        item["value"] = money(item["value"]) if item["type"] == "abs" else item["value"]
    pgi = egi / ((1 - vacancy / 100) * (1 - collection / 100))
    return {
        "value_kind": "рыночная арендная плата",
        "currency": _currency(currency),
        "property_value": money(value),
        "cap_rate_pct": money(rate),
        "required_noi": money(noi),
        "owner_expenses": items,
        "total_owner_expenses": money(egi - noi),
        "effective_gross_income": money(egi),
        "vacancy_pct": money(vacancy),
        "collection_loss_pct": money(collection),
        "gross_rent_year": money(pgi),
        "gross_rent_month": money(pgi / 12),
        "rentable_area_sqm": None if area is None else money(area),
        "rent_sqm_year": None if area is None else money(pgi / area),
        "rent_sqm_month": None if area is None else money(pgi / area / 12),
        "guardrails": [
            "Сначала проверьте сравнительный подход по рыночным ставкам аренды.",
            "Рыночная арендная плата — самостоятельная величина, не стоимость объекта или права аренды.",
            "Отделите доход бизнеса и прибыль предпринимателя; укажите НДС, эксплуатационные платежи, индексацию.",
        ],
        "checks": [],
    }


@method_card(
    "CELLULAR_REVERSE_CAPITALIZATION",
    "МР–3/26 (2), § 9.4 (метод обратной капитализации); ФСО №7; ФСО V",
    "V_комплекта = V_объекта × доля; ЧОД = V_комплекта × R; "
    "аренда = (ЧОД + расходы собственника) / (1 − недосбор)",
    FORMULA_RECOMMENDATION,
    source_url="https://srosovet.ru/Metod/metodicheskierecommenrazn123/3-26-v2/",
)
def cellular_site_rent(
    comparable_asset_value: float,
    kit_share_pct: float,
    cap_rate_pct: float,
    owner_costs_annual: float = 0,
    collection_loss_pct: float = 0,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Rent of a site for one standard set of cellular equipment.

    Reverse capitalization: the market value of a comparable-utility asset
    (e.g. a typical antenna mast with land rights, delivery, installation
    and entrepreneurial profit) × the supported share of one standard kit ×
    the market capitalization rate gives the base NOI; owner costs not
    reimbursed by the tenant and collection losses lead to the gross rent.
    Use it only when comparable rent data are missing or doubtful.
    """

    value = _non_negative("comparable_asset_value", comparable_asset_value)
    share = _positive("kit_share_pct", kit_share_pct)
    if share > 100:
        raise ValueError("kit_share_pct must be at most 100")
    rate = _positive("cap_rate_pct", cap_rate_pct)
    costs = _non_negative("owner_costs_annual", owner_costs_annual)
    collection = _loss_pct("collection_loss_pct", collection_loss_pct)

    allocated = value * share / 100
    noi = allocated * rate / 100
    gross = (noi + costs) / (1 - collection / 100)
    return {
        "value_kind": "арендная плата за место под стандартный комплект оборудования",
        "currency": _currency(currency),
        "comparable_asset_value": money(value),
        "kit_share_pct": round(share, 4),
        "allocated_value_kit": money(allocated),
        "cap_rate_pct": money(rate),
        "base_noi": money(noi),
        "owner_costs_annual": money(costs),
        "collection_loss_pct": money(collection),
        "gross_rent_year": money(gross),
        "gross_rent_month": money(gross / 12),
        "guardrails": [
            "Обратная капитализация — только при отсутствии или сомнительности данных сравнения.",
            "Не подменяйте объект сопоставимой полезности стоимостью крыши или стойки.",
            "Укажите число комплектов, срок, индексацию, периодичность платежей и НДС.",
        ],
        "checks": [],
    }


def _obsolescence_checks(amount: float) -> List[str]:
    if amount < 0:
        return [
            "Расчёт дал отрицательное обесценение: не навязывайте положительную скидку, "
            "проверьте границы объекта, потоки и предпосылки."
        ]
    return []


@method_card(
    "EXTERNAL_OBSOLESCENCE_COST_INCOME",
    "МРз–8/23-2, § 4.1; ФСО V, п. 33",
    "E_abs = V_затр без внешнего фактора − V_доход с фактором; E_% = E_abs / V_затр",
    FORMULA_ENGINEERING,
    source_url="https://srosovet.ru/Metod/metodicheskierecommenrazn123/8-23-2/",
)
def external_obsolescence_cost_income(
    cost_value_without_external: float,
    income_value_with_external: float,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """External obsolescence as the gap between the cost value without the
    external factor and the income value with it (grid assets with rare
    paired sales). The factor must not be counted twice."""

    cost = _positive("cost_value_without_external", cost_value_without_external)
    income = _non_negative("income_value_with_external", income_value_with_external)
    amount = cost - income
    return {
        "currency": _currency(currency),
        "cost_value_without_external": money(cost),
        "income_value_with_external": money(income),
        "external_obsolescence": money(amount),
        "external_obsolescence_pct": money(amount / cost * 100),
        "guardrails": [
            "Затратная и доходная стоимости должны отличаться только внешним фактором: если "
            "в затратной стоимости уже вычтены физический износ и функциональное устаревание, "
            "а доходная их не отражает (или наоборот), разница включит их повторно."
        ],
        "checks": _obsolescence_checks(amount),
    }


@method_card(
    "EXTERNAL_OBSOLESCENCE_PAIRED_SALES",
    "МРз–8/23-2, § 4.2; ФСО V, п. 33",
    "E_ratio = 1 − V_с фактором / V_без фактора; E_abs = V_база × E_ratio",
    FORMULA_ENGINEERING,
    source_url="https://srosovet.ru/Metod/metodicheskierecommenrazn123/8-23-2/",
)
def external_obsolescence_paired_sales(
    value_without_impact: float,
    value_with_impact: float,
    base_value: float,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """External obsolescence from a pair of sales that differ only in the
    external factor; the ratio is applied to the base value."""

    without = _positive("value_without_impact", value_without_impact)
    impacted = _non_negative("value_with_impact", value_with_impact)
    base = _non_negative("base_value", base_value)
    ratio = 1 - impacted / without
    checks = _obsolescence_checks(ratio)
    return {
        "currency": _currency(currency),
        "value_without_impact": money(without),
        "value_with_impact": money(impacted),
        "obsolescence_ratio_pct": money(ratio * 100),
        "base_value": money(base),
        "external_obsolescence": money(base * ratio),
        "guardrails": ["Убедитесь, что пара продаж изолирует именно внешний фактор."],
        "checks": checks,
    }


@method_card(
    "EXTERNAL_OBSOLESCENCE_DISCOUNTED_LOSSES",
    "МРз–8/23-2, § 4.3; ФСО V, п. 33",
    "PV_loss = Σ (CF_без фактора − CF_с фактором)_t / (1 + r)^t",
    FORMULA_ENGINEERING,
    source_url="https://srosovet.ru/Metod/metodicheskierecommenrazn123/8-23-2/",
)
def external_obsolescence_lost_income(
    cash_flows_without: Sequence[float],
    cash_flows_with: Sequence[float],
    discount_rate_pct: float,
    cost_value: Optional[float] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """External obsolescence as the present value of lost cash flows
    (years 1..n) between a verifiable counterfactual and the actual
    scenario; with ``cost_value`` the loss is also shown as a percent."""

    without = _flows(cash_flows_without, "cash_flows_without")
    with_factor = _flows(cash_flows_with, "cash_flows_with")
    if len(without) != len(with_factor):
        raise ValueError("cash_flows_with must have the same length as cash_flows_without")
    rate = _rate("discount_rate_pct", discount_rate_pct) / 100
    base = None if cost_value is None else _positive("cost_value", cost_value)

    rows = []
    total = 0.0
    for period, (a, b) in enumerate(zip(without, with_factor), start=1):
        loss = a - b
        factor = 1 / (1 + rate) ** period
        total += loss * factor
        rows.append({"period": period, "loss": money(loss), "present_value": money(loss * factor)})
    return {
        "currency": _currency(currency),
        "discount_rate_pct": money(rate * 100),
        "periods": rows,
        "present_value_loss": money(total),
        "cost_value": None if base is None else money(base),
        "external_obsolescence_pct": None if base is None else money(total / base * 100),
        "checks": _obsolescence_checks(total),
    }


@method_card(
    "PIF_UNIT_DCF",
    "МРз–5/23; ФСО V, п. 15",
    "V_пая = Σ выплаты_t / (1 + r)^t + (финальная компенсация − расходы прекращения) / (1 + r)^T",
    FORMULA_RECOMMENDATION,
    source_url="https://srosovet.ru/press/news/030823/",
)
def fund_unit_value(
    distributions: Sequence[float],
    final_compensation: float,
    discount_rate_pct: float,
    termination_costs: float = 0,
    final_period: Optional[float] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Income value of one closed-end fund unit.

    ``distributions`` are expected payouts per unit for years 1..n, net of
    management fees, fund expenses and owner taxes; the final compensation
    at the end of the trust agreement (year ``final_period``, default n) is
    reduced by termination costs. No separate terminal value is added.
    """

    if isinstance(distributions, (str, bytes)):
        raise ValueError("distributions must be a list")
    payouts = [_non_negative(f"distributions[{index}]", value) for index, value in enumerate(distributions or [])]
    final = _non_negative("final_compensation", final_compensation)
    costs = _non_negative("termination_costs", termination_costs)
    rate = _rate("discount_rate_pct", discount_rate_pct) / 100
    period_final = len(payouts) if final_period is None else _positive("final_period", final_period)
    if period_final <= 0:
        raise ValueError("final_period is required when there are no distributions")
    if period_final < len(payouts):
        raise ValueError(
            f"final_period {period_final:g} is before the last distribution (year {len(payouts)}): "
            "payouts cannot follow the termination of the fund"
        )

    rows = []
    pv_payouts = 0.0
    for period, payout in enumerate(payouts, start=1):
        factor = 1 / (1 + rate) ** period
        pv_payouts += payout * factor
        rows.append({"period": period, "distribution": money(payout), "present_value": money(payout * factor)})
    pv_final = (final - costs) / (1 + rate) ** period_final

    checks = []
    if final < costs:
        checks.append("Расходы прекращения больше финальной компенсации: проверьте условия договора.")
    return {
        "currency": _currency(currency),
        "discount_rate_pct": money(rate * 100),
        "distributions": rows,
        "present_value_distributions": money(pv_payouts),
        "final_compensation": money(final),
        "termination_costs": money(costs),
        "final_period": period_final,
        "present_value_final": money(pv_final),
        "unit_value": money(pv_payouts + pv_final),
        "guardrails": [
            "Сравнительный подход — только при сделках с паями того же фонда.",
            "Не дублируйте скидку за неликвидность, если она отражена в потоках или ставке.",
        ],
        "checks": checks,
    }
