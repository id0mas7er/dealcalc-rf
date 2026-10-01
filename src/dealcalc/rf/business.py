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

from ._adjustments import apply_adjustments, variation
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
    "ФСО №8, п. 9; ФСО V",
    "Equity = PV(FCFE) + НА − НО; Equity = PV(FCFF при WACC) − обязательства вне потока + НА − НО",
    FORMULA_TECHNICAL,
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
) -> Dict[str, Any]:
    """Equity value of a business from forecast cash flows.

    ``basis="equity"``: ``cash_flows`` are FCFE, ``discount_rate_pct`` is the
    cost of equity; ``obligations_not_in_flows`` must be 0 because the debt
    is already in the flow. ``basis="invested_capital"``: FCFF at WACC give
    the value of invested capital, then obligations not reflected in the
    flows are subtracted. Non-operating assets and liabilities are added and
    subtracted once. ``cash_flows[0]`` is year 1, discounted at the end of
    the year or at its middle (``mid_year``); the terminal value is
    discounted at the end of the last year. The result is 100% of equity.
    """

    chosen_basis = _basis(basis)
    if isinstance(cash_flows, (str, bytes)) or not cash_flows:
        raise ValueError("cash_flows must contain at least one value")
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
                "cash_flow": round(flow, 2),
                "discount_factor": round(factor, 6),
                "present_value": round(flow * factor, 2),
            }
        )
    pv_terminal = terminal / (1 + rate) ** len(flows)
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
        "currency": _currency(currency),
        "discount_rate_pct": round(rate * 100, 2),
        "periods": periods,
        "present_value_cash_flows": round(pv_flows, 2),
        "terminal_value": round(terminal, 2),
        "terminal_present_value": round(pv_terminal, 2),
        "invested_capital_value": round(operating_value, 2) if chosen_basis == "invested_capital" else None,
        "obligations_not_in_flows": round(obligations, 2),
        "non_operating_assets": round(nop_assets, 2),
        "non_operating_liabilities": round(nop_liabilities, 2),
        "equity_value_100pct": round(equity, 2),
        "checks": checks,
    }


@method_card(
    "BUSINESS_MULTIPLE",
    "ФСО №8, п. 10.2; ФСО V",
    "M_i = стоимость_i / показатель_i; V(100% базы) = M × показатель объекта",
    FORMULA_TECHNICAL,
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
            "value": round(value, 2),
            "metric": round(metric, 2),
            "multiple": round(value / metric, 4),
            **observation_fields(analog, prefix),
        }
        if analog.get("name"):
            item["name"] = str(analog["name"])
        items.append(item)

    chosen = statistics.median(multiples) if statistic == "median" else statistics.mean(multiples)
    multiple_variation = variation(multiples)
    checks = observation_checks(items) + variation_checks(multiple_variation, len(items))
    label = multiple_name.strip().upper().replace(" ", "")
    if chosen_basis == "equity" and label.startswith("EV"):
        checks.append(f"Мультипликатор {multiple_name} относится к инвестированному капиталу, а база — собственный капитал.")
    if chosen_basis == "invested_capital" and label.startswith("P/"):
        checks.append(f"Мультипликатор {multiple_name} относится к собственному капиталу, а база — инвестированный капитал.")
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
        "subject_metric": round(metric_subject, 2),
        "value_100pct": round(chosen * metric_subject, 2),
        "analogs": items,
        "checks": checks,
    }


@method_card(
    "BUSINESS_NET_ASSETS",
    "ФСО №8, п. 11; ФСО V",
    "Equity = Σ активы − Σ обязательства + обоснованные корректировки",
    FORMULA_TECHNICAL,
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
            result.append({"name": item["name"], "value": round(item["value"], 2), "basis": basis})
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
    if adjustment_items:
        checks.append("Корректировки чистых активов: каждую обоснуйте.")
    return {
        "approach": "cost",
        "currency": _currency(currency),
        "assets": shown_assets,
        "liabilities": shown_liabilities,
        "adjustments": [{"name": item["name"], "value": round(item["value"], 2)} for item in adjustment_items],
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "total_adjustments": round(total_adjustments, 2),
        "equity_value_100pct": round(total_assets - total_liabilities + total_adjustments, 2),
        "checks": checks,
    }


@method_card(
    "BUSINESS_LIQUIDATION",
    "ФСО №8, п. 11.2; МРз–1/23",
    "V0 = Σ (поступления − долги − расходы реализации − расходы закрытия)_t / (1 + r)^t",
    FORMULA_RECOMMENDATION,
)
def liquidation_value(
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
                **{key: round(value, 2) for key, value in parts.items()},
                "net_proceeds": round(net, 2),
                "discount_factor": round(factor, 6),
                "present_value": round(net * factor, 2),
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
        "discount_rate_pct": round(rate * 100, 2),
        "events": rows,
        "liquidation_value": round(total, 2),
        "checks": checks,
    }


@method_card(
    "DSD_NET_ASSETS",
    "МР–3/25 (2) от 17.04.2026; ФСО №8",
    "ДСД = доля участника × оплаченная часть × (принятые активы − принятые обязательства)",
    FORMULA_RECOMMENDATION,
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
        "paid_share_pct": round(paid, 2),
        "legal_share_fraction": round(legal_fraction, 6),
        "accepted_assets": round(assets, 2),
        "accepted_liabilities": round(liabilities, 2),
        "accepted_net_assets": round(net, 2),
        "actual_share_value": round(legal_fraction * net, 2),
        "guardrails": [
            "ДСД не равна рыночной стоимости доли.",
            "Скидки и премии за контроль и ликвидность к ДСД не применяются.",
            "Проверьте редакцию закона и устава на дату выхода и срок выплаты.",
        ],
        "checks": checks,
    }


@method_card(
    "DEFERRED_TAX_PV",
    "МР–2/22; ФСО №8",
    "ΔНалог_t = налог без эффекта ОНА/ОНО − налог с эффектом; PV = Σ ΔНалог_t / (1 + r)^t",
    FORMULA_RECOMMENDATION,
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
                "tax_without_effect": round(base, 2),
                "tax_with_effect": round(after, 2),
                "tax_change": round(delta, 2),
                "present_value": round(delta * factor, 2),
            }
        )
    return {
        "currency": _currency(currency),
        "discount_rate_pct": round(rate * 100, 2),
        "periods": rows,
        "present_value_effect": round(total, 2),
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
    checks = []
    if steps:
        checks.append("Скидки/премии к доле: обоснуйте их правами пакета, ликвидностью и рыночными данными.")
    return {
        "currency": _currency(currency),
        "value_100pct": round(total, 2),
        "share_pct": round(share, 4),
        "pro_rata_value": round(pro_rata, 2),
        "adjustments": adjusted["adjustments"],
        "interest_value": round(adjusted["adjusted_price"], 2),
        "checks": checks,
    }
