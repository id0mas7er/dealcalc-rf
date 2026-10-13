"""Intellectual property and intangible assets (FSO XI) and claims to a
debtor in bankruptcy.

Added after the study of appraisers' reports (13.10.2026): the cost method
for intangible assets (report ГНТТП), relief from royalty (report НИЦЭМ) and
the value of a secured creditor's claim under art. 138 of the Federal Law
"On insolvency (bankruptcy)" (report РСХБ). Every rate, term and share is an
input of the appraiser.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from ._adjustments import apply_adjustments, money
from ._meta import FORMULA_TECHNICAL, method_card, observation_checks, observation_fields


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


@method_card(
    "INTANGIBLE_COST_METHOD",
    "ФСО XI, п. 18 (затратный подход)",
    "C = Σ З_i × I_i × (1 + ПП); V = C × (1 − Т_исп / Т_пи)",
    FORMULA_TECHNICAL,
    source_url="https://fsosro.ru/01.01.031/664.aspx",
)
def intangible_cost_method(
    items: Sequence[Mapping[str, Any]],
    entrepreneurial_profit_pct: float = 0,
    useful_life_years: Optional[float] = None,
    currency: str = "RUB",
) -> Dict[str, Any]:
    """Cost method for intangible assets: the actual costs of creation
    brought to the valuation date, the entrepreneurial profit and the
    depreciation by the term of use.

    Each item is ``{"name", "costs": [{"amount", "steps", "source", "date"}],
    "used_years", "useful_life_years", "protection_years_left"}``; ``steps`` of
    a cost bring it to the valuation date (a price index — the step types of
    the comparative approach). Depreciation is ``used / useful life`` (an
    item's life overrides the common one); with ``protection_years_left`` the
    useful life is checked against the remaining legal protection.
    """

    if not items:
        raise ValueError("items must contain at least one intangible asset")
    profit = _rate("entrepreneurial_profit_pct", entrepreneurial_profit_pct)
    rows: List[Dict[str, Any]] = []
    checks: List[str] = []
    lives = []
    total = 0.0
    costs_seen: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError(f"{prefix} must be an object with a non-empty name")
        costs = item.get("costs")
        if isinstance(costs, (str, bytes)) or not isinstance(costs, Sequence) or not costs:
            raise ValueError(f"{prefix}.costs must be a non-empty list")
        brought = 0.0
        cost_rows = []
        for number, cost in enumerate(costs):
            cost_prefix = f"{prefix}.costs[{number}]"
            if not isinstance(cost, Mapping):
                raise ValueError(f"{cost_prefix} must be an object")
            amount = _non_negative(f"{cost_prefix}.amount", cost.get("amount"))
            chain = apply_adjustments(amount, list(cost.get("steps") or []), cost_prefix) if amount else None
            value = chain["adjusted_price"] if chain else 0.0
            brought += value
            row = {"index": len(costs_seen) + 1, "amount": money(amount), "steps": chain["adjustments"] if chain else [],
                   "value": money(value), **observation_fields(cost, cost_prefix)}
            costs_seen.append(row)
            cost_rows.append(row)
        reproduction = brought * (1 + profit / 100)
        life_value = item.get("useful_life_years", useful_life_years)
        if life_value is None:
            raise ValueError(f"{prefix}.useful_life_years is required (or give it for all items)")
        life = _number(f"{prefix}.useful_life_years", life_value)
        if life <= 0:
            raise ValueError(f"{prefix}.useful_life_years must be greater than 0")
        used = _non_negative(f"{prefix}.used_years", item.get("used_years", 0))
        wear = min(used / life, 1.0)
        value = reproduction * (1 - wear)
        total += value
        lives.append(life)
        left = item.get("protection_years_left")
        if left is not None:
            left = _non_negative(f"{prefix}.protection_years_left", left)
            if life - used > left:
                checks.append(
                    f"{item['name'].strip()}: остаток срока полезного использования {money(life - used)} лет "
                    f"больше остатка правовой охраны {money(left)} лет."
                )
        rows.append({"name": item["name"].strip(), "costs": cost_rows, "costs_brought": money(brought),
                     "reproduction_cost": money(reproduction), "used_years": used, "useful_life_years": life,
                     "depreciation_pct": round(wear * 100, 4), "value": money(value)})
    guardrails = [
        "Затратный подход для НМА не отражает их доходность: обоснуйте отказ от доходного подхода "
        "(нет коммерческого использования, нет данных) или проверьте результат доходным."
    ]
    if len(rows) > 1 and len(set(lives)) == 1:
        guardrails.append(
            "Срок полезного использования одинаков у всех НМА: обоснуйте его по каждому виду (срок охраны "
            "изобретения, программы, ноу-хау; экономическая жизнь)."
        )
    return {
        "currency": currency.strip().upper() if isinstance(currency, str) and currency.strip() else "RUB",
        "entrepreneurial_profit_pct": profit,
        "items": rows,
        "total_value": money(total),
        "costs": costs_seen,
        "checks": checks + observation_checks(costs_seen),
        "guardrails": guardrails,
    }


@method_card(
    "RELIEF_FROM_ROYALTY",
    "ФСО XI, пп. 14–15 (доходный подход: освобождение от роялти)",
    "R_t = Выручка_t × ставка роялти × (1 − налог); V = Σ R_t / (1 + r)^t_i + паушальный платёж",
    FORMULA_TECHNICAL,
    source_url="https://fsosro.ru/01.01.031/664.aspx",
)
def relief_from_royalty(
    revenues: Sequence[float],
    royalty_rate_pct: float,
    discount_rate_pct: float,
    periods: Optional[Sequence[float]] = None,
    tax_rate_pct: float = 0,
    lump_sum: float = 0,
    royalty_source: Optional[str] = None,
) -> Dict[str, Any]:
    """Value of an intellectual property right (or a licence) by relief from
    royalty: the royalty saved on the revenue of each period, after tax if
    ``tax_rate_pct`` is given, discounted at the rate for the IP.

    ``periods`` are the discount moments in years (0.38, 1.38… — a partial
    first year, mid-year); by default 1, 2, … ``lump_sum`` is a one-off
    payment at the valuation date (licence with a lump sum plus royalty).
    """

    flows = [_non_negative(f"revenues[{index}]", value) for index, value in enumerate(revenues or [])]
    if not flows:
        raise ValueError("revenues must contain at least one period")
    royalty = _non_negative("royalty_rate_pct", royalty_rate_pct)
    rate = _rate("discount_rate_pct", discount_rate_pct)
    tax = _non_negative("tax_rate_pct", tax_rate_pct)
    if tax >= 100:
        raise ValueError("tax_rate_pct must be less than 100")
    moments = list(range(1, len(flows) + 1)) if periods is None else [
        _non_negative(f"periods[{index}]", value) for index, value in enumerate(periods)
    ]
    if len(moments) != len(flows):
        raise ValueError("periods must have one moment per revenue")
    lump = _non_negative("lump_sum", lump_sum)
    rows = []
    total = lump
    for revenue, moment in zip(flows, moments):
        saved = revenue * royalty / 100 * (1 - tax / 100)
        factor = 1 / (1 + rate / 100) ** moment
        total += saved * factor
        rows.append({"period": moment, "revenue": money(revenue), "royalty": money(saved),
                     "factor": round(factor, 6), "present_value": money(saved * factor)})
    checks = [] if rate > 0 else [f"Ставка дисконтирования {money(rate)} % не больше нуля."]
    return {
        "royalty_rate_pct": royalty,
        "royalty_source": royalty_source,
        "discount_rate_pct": rate,
        "tax_rate_pct": tax,
        "lump_sum": money(lump),
        "periods": rows,
        "value": money(total),
        "checks": checks,
        "guardrails": [
            "Ставка роялти — по сопоставимым лицензионным договорам (источник), прогноз выручки и объёма "
            "использования — с анализом чувствительности; ставка для ИС — с обоснованием премий за риск."
        ] + ([] if royalty_source else ["Укажите источник ставки роялти (royalty_source)."]),
    }


# Shares of the net proceeds of a pledge (art. 138 of the Law on bankruptcy):
# secured creditor / claims of the 1st–2nd priority / court costs and the
# manager's fee.
_SHARES = {"credit": (80, 15, 5), "other": (70, 20, 10)}


@method_card(
    "BANKRUPTCY_SECURED_CLAIM",
    "ФСО I–V; ФЗ «О несостоятельности (банкротстве)», ст. 138",
    "П' = П − расходы на сохранность и торги; В = min(требование, П' × (доля кредитора + доля 1–2 очереди) "
    "− направлено на 1–2 очередь); V = В / (1 + r)^(t/12)",
    FORMULA_TECHNICAL,
    source_url="https://www.consultant.ru/document/cons_doc_LAW_39331/",
)
def bankruptcy_claim_value(
    collateral_proceeds: float,
    claim_amount: float,
    discount_rate_pct: float,
    months_to_payment: float,
    pledge_type: str = "credit",
    priority_claims: float = 0,
    other_estate_for_priority: float = 0,
    sale_costs: float = 0,
) -> Dict[str, Any]:
    """Value of a secured creditor's claim to a debtor in bankruptcy.

    ``sale_costs`` — the costs of keeping the pledge and selling it at
    auction — are covered from the proceeds before the creditors (art. 138,
    p. 6). The rest is split by art. 138: for a pledge securing a credit
    agreement (``pledge_type="credit"``) 80 % to the secured creditor, 15 % to
    the claims of the 1st–2nd priority, 5 % to the court costs and the
    manager's fee; otherwise 70 / 20 / 10. The share of the priority claims
    is used only for what the other estate does not cover
    (``priority_claims − other_estate_for_priority``); its unused part goes to
    the secured creditor. The share of the costs is not the creditor's. The
    creditor receives no more than ``claim_amount`` (the secured debt with
    interest) — it is required: without it the value is not defined. The
    payment is discounted for ``months_to_payment``.
    """

    proceeds = _non_negative("collateral_proceeds", collateral_proceeds)
    claim = _non_negative("claim_amount", claim_amount)
    rate = _rate("discount_rate_pct", discount_rate_pct)
    months = _non_negative("months_to_payment", months_to_payment)
    if pledge_type not in _SHARES:
        raise ValueError("pledge_type must be 'credit' or 'other'")
    costs = _non_negative("sale_costs", sale_costs)
    if costs > proceeds:
        raise ValueError("sale_costs must not exceed collateral_proceeds")
    secured_share, priority_share, costs_share = _SHARES[pledge_type]
    net = proceeds - costs
    need = max(0.0, _non_negative("priority_claims", priority_claims)
               - _non_negative("other_estate_for_priority", other_estate_for_priority))
    to_priority = min(net * priority_share / 100, need)
    to_creditor = net * (secured_share + priority_share) / 100 - to_priority
    capped = to_creditor > claim
    if capped:
        to_creditor = claim
    factor = 1 / (1 + rate / 100) ** (months / 12)
    return {
        "pledge_type": pledge_type,
        "shares_pct": dict(zip(("secured", "priority_1_2", "costs"), _SHARES[pledge_type])),
        "collateral_proceeds": money(proceeds),
        "sale_costs": money(costs),
        "net_proceeds": money(net),
        "priority_need": money(need),
        "to_priority_claims": money(to_priority),
        "reserve_for_costs": money(net * costs_share / 100),
        "claim_amount": money(claim),
        "to_secured_creditor": money(to_creditor),
        "capped_by_claim": capped,
        "discount_factor": round(factor, 6),
        "value": money(to_creditor * factor),
        "guardrails": [
            "Очерёдность, требования 1–2 очереди, текущие платежи и иное имущество должника — по реестру "
            "требований и данным управляющего; распределение выручки проверьте с юристом."
        ] + ([] if priority_claims else [
            "Требования 1–2 очереди не заданы: подтвердите, что их нет или они покрываются иным имуществом "
            "(ст. 138: иначе до 15–20 % выручки от залога идёт на них)."
        ]) + ([] if sale_costs else [
            "Расходы на сохранность залога и торги (ст. 138, п. 6) не заданы: они покрываются из выручки до "
            "распределения — подтвердите их размер."
        ]),
    }
