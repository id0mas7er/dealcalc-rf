"""Result envelope and data-quality checks shared by all calculations.

Every public calculation returns its numbers together with a ``status``
(the agent's result is always a draft for the appraiser), a
``method_card`` (standard, formula and the status of that formula) and a
list of ``checks`` — warnings the appraiser has to review.
"""

from __future__ import annotations

import functools
import math
from datetime import date, datetime
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


VALUE_TYPES = ("рыночная", "инвестиционная", "равновесная", "ликвидационная")
VAT_MODES = {
    "included": "с НДС",
    "excluded": "без НДС",
    "not_applicable": "НДС не применяется",
}


def assignment_context(context: Any) -> Dict[str, Any]:
    """Validate the assignment context carried by a calculation.

    ``context`` may hold ``valuation_date`` (YYYY-MM-DD), ``value_type``
    (ФСО II), ``vat`` (``included``, ``excluded``, ``not_applicable``),
    ``vat_rate_pct`` and ``assignment_id``.
    """

    if context is None:
        context = {}
    if not isinstance(context, Mapping):
        raise ValueError("context must be an object")
    unknown = set(context) - {"valuation_date", "value_type", "vat", "vat_rate_pct", "assignment_id"}
    if unknown:
        raise ValueError(f"context has unknown fields: {sorted(unknown)}")

    valuation_date = context.get("valuation_date")
    if valuation_date not in (None, ""):
        try:
            valuation_date = date.fromisoformat(str(valuation_date)).isoformat()
        except ValueError as exc:
            raise ValueError("context.valuation_date must be YYYY-MM-DD") from exc
    else:
        valuation_date = None

    value_type = context.get("value_type")
    if value_type not in (None, ""):
        value_type = str(value_type).strip().lower()
        if not any(value_type.startswith(name) for name in VALUE_TYPES):
            raise ValueError(f"context.value_type must be one of {', '.join(VALUE_TYPES)}")
    else:
        value_type = None

    vat = context.get("vat")
    if vat not in (None, ""):
        if vat not in VAT_MODES:
            raise ValueError("context.vat must be 'included', 'excluded' or 'not_applicable'")
    else:
        vat = None
    vat_rate = context.get("vat_rate_pct")
    if vat_rate is not None:
        if (
            isinstance(vat_rate, bool)
            or not isinstance(vat_rate, (int, float))
            or not math.isfinite(vat_rate)
            or vat_rate < 0
        ):
            raise ValueError("context.vat_rate_pct must be a finite non-negative number")
        vat_rate = float(vat_rate)

    assignment_id = context.get("assignment_id")
    return {
        "assignment_id": None if assignment_id in (None, "") else str(assignment_id),
        "valuation_date": valuation_date,
        "value_type": value_type,
        "vat": vat,
        "vat_label": VAT_MODES.get(vat) if vat else None,
        "vat_rate_pct": vat_rate,
    }


def _context_guardrails(context: Mapping[str, Any]) -> List[str]:
    missing = [
        label
        for key, label in (
            ("valuation_date", "дата оценки"),
            ("value_type", "вид стоимости"),
            ("vat", "признак НДС"),
        )
        if context.get(key) is None
    ]
    if not missing:
        return []
    return [f"Не указаны {', '.join(missing)} (параметр context): результат нельзя переносить в отчёт без них."]


def _vat_checks(context: Mapping[str, Any], result: Mapping[str, Any]) -> List[str]:
    """Compare the VAT treatment of the assignment with the calculation's rate."""

    rate = result.get("vat_pct")
    vat = context.get("vat")
    if not isinstance(rate, (int, float)) or vat is None:
        return []
    checks = []
    if vat in ("excluded", "not_applicable") and rate > 0:
        checks.append(
            f"В context указано «{VAT_MODES[vat]}», а в расчёте ставка НДС {rate:g}%: "
            "проверьте, какая величина переносится в отчёт."
        )
    if vat == "included" and rate == 0:
        checks.append("В context указано «с НДС», а в расчёте ставка НДС 0%.")
    expected = context.get("vat_rate_pct")
    if vat == "included" and expected is not None and rate > 0 and rate != expected:
        checks.append(f"Ставка НДС в расчёте {rate:g}% не совпадает со ставкой в context {expected:g}%.")
    return checks


def method_card(
    method_id: str,
    standard: str,
    formula: str,
    formula_status: str,
    source_url: str = "",
    context_reminder: bool = True,
) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
    """Wrap a calculation result into the common envelope.

    The wrapped function may return ``checks`` (warnings), ``guardrails``
    (reminders), ``conditions`` and ``status``; without an explicit status
    any check turns the result into "нужна проверка оценщика". Every
    wrapped calculation accepts an optional keyword ``context`` with the
    valuation date, type of value and VAT treatment of the assignment; a
    missing context is reminded only where ``context_reminder`` is true —
    calculations returning a value, not auxiliary rates and coefficients. A
    result field ``vat_pct`` is checked against the context VAT treatment.
    """

    def decorate(func: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(*args: Any, context: Any = None, **kwargs: Any) -> Dict[str, Any]:
            assignment = assignment_context(context)
            result = dict(func(*args, **kwargs))
            checks = list(result.pop("checks", [])) + _vat_checks(assignment, result)
            guardrails = list(result.pop("guardrails", []))
            conditions = list(result.pop("conditions", []))
            guardrails += offer_guardrails(result) + identifier_guardrails(result)
            if context_reminder:
                guardrails += _context_guardrails(assignment)
            status = result.pop("status", None) or (STATUS_REVIEW if checks else STATUS_DRAFT)
            card = {
                "id": method_id,
                "standard": standard,
                "formula": formula,
                "formula_status": formula_status,
            }
            if source_url:
                card["source_url"] = source_url
            return {
                "status": status,
                "context": assignment,
                "method_card": card,
                **result,
                "conditions": conditions,
                "guardrails": guardrails,
                "checks": checks,
            }

        return wrapper

    return decorate


OBSERVATION_FIELDS = (
    "source", "date", "url", "price_type", "conditions", "reliability", "import_warnings",
    "listing_id_basis",
)
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
        if key == "import_warnings" and isinstance(value, (list, tuple)):
            fields[key] = [str(warning) for warning in value]
            continue
        fields[key] = json_value(value)
    return fields


def _is_date(value: Any) -> bool:
    """A price date in YYYY-MM-DD (optionally with time) or DD.MM.YYYY."""

    text = str(value).strip()
    try:
        datetime.fromisoformat(text)
        return True
    except ValueError:
        pass
    try:
        datetime.strptime(text, "%d.%m.%Y")
        return True
    except ValueError:
        return False


def observation_checks(items: Sequence[Mapping[str, Any]], date_keys: Sequence[str] = ("date",)) -> List[str]:
    """Warnings about missing provenance of market observations."""

    checks = []
    bad_dates = [item["index"] for item in items if item.get("date") and not _is_date(item["date"])]
    no_source = [item["index"] for item in items if not item.get("source")]
    no_date = [item["index"] for item in items if not any(item.get(key) for key in date_keys)]
    no_type = [item["index"] for item in items if not item.get("price_type")]
    if no_source:
        checks.append(f"Не указан источник у аналогов {no_source}.")
    if no_date:
        checks.append(f"Не указана дата цены у аналогов {no_date}.")
    if bad_dates:
        checks.append(
            f"Дата цены не распознана у аналогов {bad_dates}: ожидается ГГГГ-ММ-ДД или ДД.ММ.ГГГГ."
        )
    if no_type:
        checks.append(f"Не указан тип цены (сделка/предложение) у аналогов {no_type}.")
    for item in items:
        for warning in item.get("import_warnings") or []:
            checks.append(f"Аналог {item['index']}: {warning}")
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


def identifier_guardrails(result: Mapping[str, Any]) -> List[str]:
    """Reminder for imported analogs identified by their characteristics."""

    items = result.get("comparables") or result.get("analogs") or []
    built = [
        item.get("index")
        for item in items
        if isinstance(item, Mapping) and item.get("listing_id_basis") == "characteristics"
    ]
    if not built:
        return []
    return [
        f"Идентификатор аналогов {built} построен по характеристикам (нет номера "
        "объявления, ссылки, VIN или кадастрового номера): проверьте дубли вручную."
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
