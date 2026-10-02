"""Business valuation aids under FSO No. 8.

Inputs (forecasts, rates, multiples, accepted asset values) come from the
appraiser. The functions keep the capital base explicit — equity versus
invested capital, 100% of the business versus a specific interest — so that
the result is not silently mixed up.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from ._adjustments import apply_adjustments, money, variation
from ._meta import (
    FORMULA_RECOMMENDATION,
    FORMULA_TECHNICAL,
    method_card,
    observation_checks,
    observation_fields,
    variation_checks,
)

_BASES = {
    "equity": "собственный капитал",
    "invested_capital": "инвестированный капитал",
}


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


def _rate(name: str, value: Any) -> float:
    number = _number(name, value)
    if number <= -100:
        raise ValueError(f"{name} must be greater than -100")
    return number


def _basis(basis: Any) -> str:
    if basis not in _BASES:
        raise ValueError("basis must be 'equity' or 'invested_capital'")
    return basis


def _currency(currency: Any) -> str:
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency must be a non-empty string")
    return currency.strip().upper()


def _named_amounts(items: Any, name: str) -> List[Dict[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise ValueError(f"{name} must be a list")
    result = []
    for index, item in enumerate(items):
        prefix = f"{name}[{index}]"
        if not isinstance(item, Mapping):
            raise ValueError(f"{prefix} must be an object")
        label = item.get("name")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{prefix}.name must be a non-empty string")
        result.append({"name": label.strip(), "value": _number(f"{prefix}.value", item.get("value")), "raw": item})
    return result


@method_card(
    "BUSINESS_EQUITY_DCF",
    "ФСО №8, п. 9; ФСО V, п. 15",
    "Equity = PV(FCFE) + НА − НО; Equity = PV(FCFF при WACC) − обязательства вне потока + НА − НО",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso8/",
)
def business_income_approach(
    cash_flows: Sequence[float],
    discount_rate_pct: float,
    basis: str,
    terminal_value: float = 0,
    mid_year: bool = False,
    obligations_not_in_flows: float = 0,
    non_operating_assets: float = 0,
    non_operating_liabilities: float = 0,
    currency: str = "RUB",
    terminal_timing: str = "end",
) -> Dict[str, Any]:
    """Equity value of a business from forecast cash flows.

    ``basis="equity"``: ``cash_flows`` are FCFE, ``discount_rate_pct`` is the
    cost of equity; ``obligations_not_in_flows`` must be 0 because the debt
    is already in the flow. ``basis="invested_capital"``: FCFF at WACC give
    the value of invested capital, then obligations not reflected in the
    flows are subtracted — only those not reflected in the flows, not the
    whole book debt. Non-operating assets and liabilities are added and
    subtracted once. ``cash_flows[0]`` is YEAR 1 (period 1), discounted at
    the end of the year or at its middle (``mid_year``). The result is 100%
    of equity.
    ``terminal_timing`` sets when the terminal value is discounted: ``end``
    (end of year n, default) or ``mid`` (n − 0.5, consistent with a Gordon
    value built from a mid-year flow of year n + 1).
    """

    chosen_basis = _basis(basis)
    if isinstance(cash_flows, (str, bytes)) or not cash_flows:
        raise ValueError("cash_flows must contain at least one value")
    if not isinstance(mid_year, bool):
        raise ValueError("mid_year must be true or false")
    flows = [_number(f"cash_flows[{index}]", flow) for index, flow in enumerate(cash_flows)]
    rate = _rate("discount_rate_pct", discount_rate_pct) / 100
    terminal = _number("terminal_value", terminal_value)
    obligations = _non_negative("obligations_not_in_flows", obligations_not_in_flows)
    nop_assets = _non_negative("non_operating_assets", non_operating_assets)
    nop_liabilities = _non_negative("non_operating_liabilities", non_operating_liabilities)
    if chosen_basis == "equity" and obligations:
        raise ValueError(
            "obligations_not_in_flows applies only to basis 'invested_capital': FCFE already reflect debt"
        )

    shift = 0.5 if mid_year else 0
    periods = []
    pv_flows = 0.0
    for period, flow in enumerate(flows, start=1):
        factor = 1 / (1 + rate) ** (period - shift)
        pv_flows += flow * factor
        periods.append(
            {
                "period": period,
                "cash_flow": money(flow),
                "discount_factor": round(factor, 6),
                "present_value": money(flow * factor),
            }
        )
    if terminal_timing not in ("end", "mid"):
        raise ValueError("terminal_timing must be 'end' or 'mid'")
    terminal_period = len(flows) - 0.5 if terminal_timing == "mid" else len(flows)
    pv_terminal = terminal / (1 + rate) ** terminal_period
    operating_value = pv_flows + pv_terminal
    equity = operating_value - obligations + nop_assets - nop_liabilities

    checks = []
    if equity < 0:
        checks.append("Стоимость собственного капитала отрицательна: проверьте прогноз и обязательства.")
    return {
        "approach": "income",
        "basis": chosen_basis,
        "basis_label": _BASES[chosen_basis],
        "flow_type": "FCFE" if chosen_basis == "equity" else "FCFF",
        "discounting": "mid_year" if mid_year else "end_of_year",
        "first_cash_flow_period": 1,
        "terminal_discount_period": terminal_period,
        "currency": _currency(currency),
        "discount_rate_pct": money(rate * 100),
        "periods": periods,
        "present_value_cash_flows": money(pv_flows),
        "terminal_value": money(terminal),
        "terminal_present_value": money(pv_terminal),
        "invested_capital_value": money(operating_value) if chosen_basis == "invested_capital" else None,
        "obligations_not_in_flows": money(obligations),
        "non_operating_assets": money(nop_assets),
        "non_operating_liabilities": money(nop_liabilities),
        "equity_value_100pct": money(equity),
        "checks": checks,
    }


@method_card(
    "BUSINESS_MULTIPLE",
    "ФСО №8, пп. 10, 10.2",
    "M_i = стоимость_i / показатель_i; V(100% базы) = M × показатель объекта",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso8/",
)
def business_multiples(
    analogs: Sequence[Mapping[str, Any]],
    subject_metric: float,
    multiple_name: str,
    basis: str,
    statistic: str = "median",
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Value of 100% of a capital base by a market multiple.

    ``basis`` is stated explicitly and is the numerator of the multiple:
    ``equity`` (P/E, P/BV...) or ``invested_capital`` (EV/EBITDA, EV/S...);
    the result is 100% of that base. To get equity from an EV multiple,
    subtract the obligations not reflected in the metric separately.
    Each analog has ``value`` (its equity or invested capital, matching
    ``basis``) and ``metric`` (the financial or operating indicator of the
    multiple), plus optional ``name`` and provenance fields. The selected
    ``statistic`` (``median`` or ``mean``) of the multiples is applied to
    ``subject_metric``. The result is 100% of the chosen basis, not a
    specific interest.
    """

    chosen_basis = _basis(basis)
    if not isinstance(multiple_name, str) or not multiple_name.strip():
        raise ValueError("multiple_name must be a non-empty string")
    if statistic not in ("mean", "median"):
        raise ValueError("statistic must be 'mean' or 'median'")
    if not analogs:
        raise ValueError("analogs must contain at least one item")
    metric_subject = _number("subject_metric", subject_metric)
    if metric_subject <= 0:
        raise ValueError("subject_metric must be greater than 0")

    items = []
    multiples = []
    for index, analog in enumerate(analogs):
        prefix = f"analogs[{index}]"
        if not isinstance(analog, Mapping):
            raise ValueError(f"{prefix} must be an object")
        value = _number(f"{prefix}.value", analog.get("value"))
        metric = _number(f"{prefix}.metric", analog.get("metric"))
        if value <= 0:
            raise ValueError(f"{prefix}.value must be greater than 0")
        if metric <= 0:
            raise ValueError(f"{prefix}.metric must be greater than 0")
        multiples.append(value / metric)
        item: Dict[str, Any] = {
            "index": index + 1,
            "value": money(value),
            "metric": money(metric),
            "multiple": round(value / metric, 4),
            **observation_fields(analog, prefix),
        }
        if analog.get("name"):
            item["name"] = str(analog["name"])
        items.append(item)

    chosen = statistics.median(multiples) if statistic == "median" else statistics.mean(multiples)
    multiple_variation = variation(multiples)
    checks = observation_checks(items) + variation_checks(multiple_variation, len(items))
    return {
        "approach": "comparative",
        "multiple_name": multiple_name.strip(),
        "basis": chosen_basis,
        "basis_label": _BASES[chosen_basis],
        "currency": _currency(currency),
        "sample_size": len(items),
        "mean_multiple": round(statistics.mean(multiples), 4),
        "median_multiple": round(statistics.median(multiples), 4),
        "min_multiple": round(min(multiples), 4),
        "max_multiple": round(max(multiples), 4),
        "variation": multiple_variation,
        "statistic": statistic,
        "selected_multiple": round(chosen, 4),
        "subject_metric": money(metric_subject),
        "value_100pct": money(chosen * metric_subject),
        "analogs": items,
        "checks": checks,
    }


@method_card(
    "BUSINESS_NET_ASSETS",
    "ФСО №8, п. 11",
    "Equity = Σ активы − Σ обязательства + обоснованные корректировки",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso8/",
)
def net_assets(
    assets: Sequence[Mapping[str, Any]],
    liabilities: Sequence[Mapping[str, Any]],
    adjustments: Optional[Sequence[Mapping[str, Any]]] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Equity by the net asset method.

    ``assets`` and ``liabilities`` are lists of ``{"name", "value",
    "basis"}`` with ``basis`` ``market`` (рыночная) or ``book``
    (балансовая); book values are flagged because they are not market
    values automatically. ``adjustments`` are ``{"name", "value"}`` items
    with a sign, each to be justified.
    """

    asset_items = _named_amounts(assets, "assets")
    liability_items = _named_amounts(liabilities, "liabilities")
    adjustment_items = _named_amounts(adjustments, "adjustments")
    if not asset_items:
        raise ValueError("assets must contain at least one item")

    def shown(items: List[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
        result = []
        for index, item in enumerate(items):
            if item["value"] < 0:
                raise ValueError(f"{prefix}[{index}].value must be non-negative")
            basis = item["raw"].get("basis")
            if basis not in (None, "market", "book"):
                raise ValueError(f"{prefix}[{index}].basis must be 'market' or 'book'")
            result.append({"name": item["name"], "value": money(item["value"]), "basis": basis})
        return result

    shown_assets = shown(asset_items, "assets")
    shown_liabilities = shown(liability_items, "liabilities")
    total_assets = sum(item["value"] for item in asset_items)
    total_liabilities = sum(item["value"] for item in liability_items)
    total_adjustments = sum(item["value"] for item in adjustment_items)

    checks = []
    not_market = [item["name"] for item in shown_assets + shown_liabilities if item["basis"] != "market"]
    if not_market:
        checks.append(
            f"Позиции не по рыночной стоимости (балансовые или без указания): {not_market}. "
            "Балансовая стоимость не становится рыночной автоматически."
        )
    return {
        "approach": "cost",
        "currency": _currency(currency),
        "assets": shown_assets,
        "liabilities": shown_liabilities,
        "adjustments": [{"name": item["name"], "value": money(item["value"])} for item in adjustment_items],
        "total_assets": money(total_assets),
        "total_liabilities": money(total_liabilities),
        "total_adjustments": money(total_adjustments),
        "equity_value_100pct": money(total_assets - total_liabilities + total_adjustments),
        "guardrails": ["Каждую корректировку чистых активов обоснуйте."] if adjustment_items else [],
        "checks": checks,
    }


@method_card(
    "BUSINESS_LIQUIDATION",
    "ФСО №8, п. 11.2; МРз–1/23",
    "V0 = Σ (поступления − долги − расходы реализации − расходы закрытия)_t / (1 + r)^t",
    FORMULA_RECOMMENDATION,
    source_url="https://srosovet.ru/press/news/070223/",
)
def business_liquidation_value(
    events: Sequence[Mapping[str, Any]],
    discount_rate_pct: float,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Business value under a justified liquidation premise.

    ``events`` are dated cash events: ``period`` (years from the valuation
    date, fractional allowed), ``sale_proceeds``, ``debt_payments``,
    ``disposal_costs`` and ``closure_costs``. Net proceeds of every event
    are discounted at the rate reflecting the risk of receiving liquidation
    proceeds (not automatically the going-concern rate).
    """

    if not events:
        raise ValueError("events must contain at least one item")
    rate = _rate("discount_rate_pct", discount_rate_pct) / 100

    rows = []
    total = 0.0
    for index, event in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(event, Mapping):
            raise ValueError(f"{prefix} must be an object")
        period = _non_negative(f"{prefix}.period", event.get("period"))
        parts = {
            key: _non_negative(f"{prefix}.{key}", event.get(key, 0))
            for key in ("sale_proceeds", "debt_payments", "disposal_costs", "closure_costs")
        }
        net = parts["sale_proceeds"] - parts["debt_payments"] - parts["disposal_costs"] - parts["closure_costs"]
        factor = 1 / (1 + rate) ** period
        total += net * factor
        rows.append(
            {
                "period": period,
                **{key: money(value) for key, value in parts.items()},
                "net_proceeds": money(net),
                "discount_factor": round(factor, 6),
                "present_value": money(net * factor),
            }
        )

    checks = []
    if all(row["period"] == 0 for row in rows):
        checks.append(
            "Все поступления отнесены к дате оценки: учтите срок экспозиции и сроки выплат, "
            "поступления не бывают немедленными."
        )
    if total < 0:
        checks.append("Чистые ликвидационные поступления отрицательны: проверьте долги и расходы.")
    return {
        "approach": "liquidation",
        "currency": _currency(currency),
        "discount_rate_pct": money(rate * 100),
        "events": rows,
        "business_liquidation_value": money(total),
        "checks": checks,
    }


@method_card(
    "DSD_NET_ASSETS",
    "Федеральный закон № 14-ФЗ «Об ООО»: п. 2 ст. 14, п. 6.1 ст. 23, ст. 26; МР–3/25 (2) от 17.04.2026; ФСО №8",
    "ДСД = доля участника × оплаченная часть × (принятые активы − принятые обязательства)",
    FORMULA_RECOMMENDATION,
    source_url="https://srosovet.ru/Metod/metodicheskierecommenrazn123/dsd-2026/",
)
def actual_share_value(
    share_pct: float,
    accepted_assets: float,
    accepted_liabilities: float,
    paid_share_pct: float = 100,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Actual value of an LLC participant's share (ДСД) on exit.

    ДСД is a legal value, not the market value of the share: no control or
    liquidity discounts/premiums are applied. ``accepted_assets`` and
    ``accepted_liabilities`` follow the legal route (book data by default,
    market values when the law requires them). ``paid_share_pct`` is the
    paid part of the contribution where the law takes it into account.
    """

    share = _non_negative("share_pct", share_pct)
    paid = _non_negative("paid_share_pct", paid_share_pct)
    if share > 100:
        raise ValueError("share_pct must be at most 100")
    if paid > 100:
        raise ValueError("paid_share_pct must be at most 100")
    assets = _non_negative("accepted_assets", accepted_assets)
    liabilities = _non_negative("accepted_liabilities", accepted_liabilities)
    net = assets - liabilities
    legal_fraction = share / 100 * paid / 100

    checks = []
    if net < 0:
        checks.append("Принятые чистые активы отрицательны: проверьте состав активов и обязательств.")
    if paid < 100:
        checks.append("Вклад оплачен не полностью: проверьте применимое правило учёта оплаченной части.")
    return {
        "value_kind": "действительная стоимость доли (ДСД)",
        "currency": _currency(currency),
        "share_pct": round(share, 4),
        "paid_share_pct": money(paid),
        "legal_share_fraction": round(legal_fraction, 6),
        "accepted_assets": money(assets),
        "accepted_liabilities": money(liabilities),
        "accepted_net_assets": money(net),
        "actual_share_value": money(legal_fraction * net),
        "guardrails": [
            "ДСД не равна рыночной стоимости доли.",
            "Скидки и премии за контроль и ликвидность к ДСД не применяются.",
            "Проверьте редакцию закона и устава на дату выхода и срок выплаты.",
        ],
        "checks": checks,
    }


@method_card(
    "DEFERRED_TAX_PV",
    "МР–2/22; ФСО №8, п. 9",
    "ΔНалог_t = налог без эффекта ОНА/ОНО − налог с эффектом; PV = Σ ΔНалог_t / (1 + r)^t",
    FORMULA_RECOMMENDATION,
    source_url="https://srosovet.ru/press/news/201222/",
)
def deferred_tax_effect(
    tax_without_effect: Sequence[float],
    tax_with_effect: Sequence[float],
    discount_rate_pct: float,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Present value of the change in tax payments from deferred taxes.

    Both lists hold tax payments for years 1..n. The effect is shown once:
    either include the change in the cash-flow forecast or apply this
    present value as a separate adjustment, not both.
    """

    if isinstance(tax_without_effect, (str, bytes)) or not tax_without_effect:
        raise ValueError("tax_without_effect must contain at least one value")
    if isinstance(tax_with_effect, (str, bytes)) or len(tax_with_effect) != len(tax_without_effect):
        raise ValueError("tax_with_effect must have the same length as tax_without_effect")
    rate = _rate("discount_rate_pct", discount_rate_pct) / 100

    rows = []
    total = 0.0
    for period, (without, with_effect) in enumerate(zip(tax_without_effect, tax_with_effect), start=1):
        base = _number(f"tax_without_effect[{period - 1}]", without)
        after = _number(f"tax_with_effect[{period - 1}]", with_effect)
        delta = base - after
        factor = 1 / (1 + rate) ** period
        total += delta * factor
        rows.append(
            {
                "period": period,
                "tax_without_effect": money(base),
                "tax_with_effect": money(after),
                "tax_change": money(delta),
                "present_value": money(delta * factor),
            }
        )
    return {
        "currency": _currency(currency),
        "discount_rate_pct": money(rate * 100),
        "periods": rows,
        "present_value_effect": money(total),
        "guardrails": [
            "Учитывайте эффект один раз: в прогнозе потоков или отдельной корректировкой.",
            "Без обоснованной будущей налогооблагаемой прибыли ОНА может не иметь экономической ценности.",
        ],
        "checks": [],
    }


@method_card(
    "BUSINESS_INTEREST_VALUE",
    "ФСО №8",
    "V доли = V(100%) × доля, затем обоснованные скидки/премии по шагам",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso8/",
)
def business_interest_value(
    value_100pct: float,
    share_pct: float,
    adjustments: Optional[Sequence[Mapping[str, Any]]] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Move from 100% of equity to the value of a specific interest.

    The pro-rata value ``value_100pct × share_pct`` is followed by optional
    step adjustments (``{"name", "type": "pct" | "abs", "value"}``) such as
    control or liquidity discounts; each must be justified by the rights of
    the interest and market evidence. None is applied automatically.
    """

    total = _non_negative("value_100pct", value_100pct)
    share = _non_negative("share_pct", share_pct)
    if share > 100:
        raise ValueError("share_pct must be at most 100")
    pro_rata = total * share / 100
    steps = list(adjustments or [])
    if steps and pro_rata == 0:
        raise ValueError("adjustments require a positive pro-rata value")
    adjusted = apply_adjustments(pro_rata, steps, "interest") if steps else {
        "adjusted_price": pro_rata,
        "adjustments": [],
    }
    return {
        "currency": _currency(currency),
        "value_100pct": money(total),
        "share_pct": round(share, 4),
        "pro_rata_value": money(pro_rata),
        "adjustments": adjusted["adjustments"],
        "interest_value": money(adjusted["adjusted_price"]),
        "guardrails": [
            "Скидки/премии к доле: обоснуйте их правами пакета, ликвидностью и рыночными данными."
        ]
        if steps
        else [],
        "checks": [],
    }
