"""Result envelope and data-quality checks shared by all calculations.

Every public calculation returns its numbers together with a ``status``
(the agent's result is always a draft for the appraiser), a
``method_card`` (standard, formula and the status of that formula) and a
list of ``checks`` — warnings the appraiser has to review.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Sequence

from ._adjustments import json_value

STATUS_DRAFT = "черновой расчёт"
STATUS_REVIEW = "нужна проверка оценщика"
STATUS_NOT_RECONCILED = "расчёт выполнен — согласование не автоматизировано"
STATUS_INSUFFICIENT = "недостаточно данных"

FORMULA_NORM = "норма ФСО"
FORMULA_TECHNICAL = "расчётное представление метода, не универсальная формула ФСО"
FORMULA_RECOMMENDATION = "частная методическая рекомендация, не норма ФСО"
FORMULA_METHODICAL = "методическая формула учебного источника, не норма ФСО"


def method_card(
    method_id: str, standard: str, formula: str, formula_status: str
) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
    """Wrap a calculation result into the common envelope.

    The wrapped function may return ``checks`` (warnings) and ``status``;
    without an explicit status any check turns the result into
    "нужна проверка оценщика".
    """

    def decorate(func: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            result = dict(func(*args, **kwargs))
            checks = list(result.pop("checks", []))
            guardrails = list(result.pop("guardrails", []))
            conditions = list(result.pop("conditions", []))
            guardrails += offer_guardrails(result)
            status = result.pop("status", None) or (STATUS_REVIEW if checks else STATUS_DRAFT)
            return {
                "status": status,
                "method_card": {
                    "id": method_id,
                    "standard": standard,
                    "formula": formula,
                    "formula_status": formula_status,
                },
                **result,
                "conditions": conditions,
                "guardrails": guardrails,
                "checks": checks,
            }

        return wrapper

    return decorate


OBSERVATION_FIELDS = ("source", "date", "url", "price_type", "conditions", "reliability")
_PRICE_TYPES = {
    "сделка": "сделка",
    "transaction": "сделка",
    "предложение": "предложение",
    "offer": "предложение",
}


def observation_fields(comparable: Mapping[str, Any], prefix: str) -> Dict[str, Any]:
    """Copy the provenance of a market observation (source, date, terms...)."""

    fields: Dict[str, Any] = {}
    for key in OBSERVATION_FIELDS:
        value = comparable.get(key)
        if value in (None, ""):
            continue
        if key == "price_type":
            normalized = _PRICE_TYPES.get(str(value).strip().lower())
            if normalized is None:
                raise ValueError(f"{prefix}.price_type must be 'сделка' or 'предложение'")
            value = normalized
        fields[key] = json_value(value)
    return fields


def observation_checks(items: Sequence[Mapping[str, Any]], date_keys: Sequence[str] = ("date",)) -> List[str]:
    """Warnings about missing provenance of market observations."""

    checks = []
    no_source = [item["index"] for item in items if not item.get("source")]
    no_date = [item["index"] for item in items if not any(item.get(key) for key in date_keys)]
    no_type = [item["index"] for item in items if not item.get("price_type")]
    if no_source:
        checks.append(f"Не указан источник у аналогов {no_source}.")
    if no_date:
        checks.append(f"Не указана дата цены у аналогов {no_date}.")
    if no_type:
        checks.append(f"Не указан тип цены (сделка/предложение) у аналогов {no_type}.")
    return checks


def offer_guardrails(result: Mapping[str, Any]) -> List[str]:
    """Reminder for offer prices; a reminder, not a data defect."""

    items = result.get("comparables") or result.get("analogs") or []
    offers = [
        item.get("index")
        for item in items
        if isinstance(item, Mapping) and item.get("price_type") == "предложение"
    ]
    if not offers:
        return []
    return [
        f"Аналоги {offers} — цены предложения: обоснуйте скидку к цене сделки, "
        "срок экспозиции и изменение цены."
    ]


def variation_checks(variation: Mapping[str, Any], sample_size: int) -> List[str]:
    """Warnings about sample size and homogeneity."""

    if sample_size < 2:
        return ["Один аналог: разброс и однородность выборки не оцениваются."]
    if variation.get("homogeneous") is False:
        return [
            f"Выборка неоднородна: коэффициент вариации {variation['coefficient_pct']}% "
            f"больше {variation['threshold_pct']}%."
        ]
    return []
