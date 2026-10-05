"""Result envelope and data-quality checks shared by all calculations.

Every public calculation returns its numbers together with a ``status``
(the agent's result is always a draft for the appraiser), a
``method_card`` (standard, formula and the status of that formula) and a
list of ``checks`` — warnings the appraiser has to review.
"""

from __future__ import annotations

import functools
import inspect
import math
from datetime import date, datetime
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Optional, Sequence

from ._adjustments import json_value, range_position, source_range

STATUS_DRAFT = "черновой расчёт"
STATUS_REVIEW = "нужна проверка оценщика"
STATUS_NOT_RECONCILED = "расчёт выполнен — согласование не автоматизировано"
STATUS_INSUFFICIENT = "недостаточно данных"

FORMULA_NORM = "норма ФСО"
FORMULA_TECHNICAL = "расчётное представление метода, не универсальная формула ФСО"
FORMULA_RECOMMENDATION = "частная методическая рекомендация, не норма ФСО"
FORMULA_METHODICAL = "методическая формула учебного источника, не норма ФСО"


# ФСО II types of value plus special legal values (ДСД) and "иная" for
# other values required by law or the assignment.
VALUE_TYPES = (
    "рыночная", "инвестиционная", "равновесная", "ликвидационная",
    "действительная стоимость доли", "иная",
)
# Results of a specific kind need the matching type of value in the context.
_KIND_VALUE_TYPES = {
    "ликвидационная стоимость": "ликвидационная",
    "действительная стоимость доли (ДСД)": "действительная стоимость доли",
}
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


def _parse_date(value: Any) -> Optional[date]:
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        return None


def _observations(result: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    items = result.get("comparables") or result.get("analogs") or []
    return [item for item in items if isinstance(item, Mapping)]


def _later_price_checks(context: Mapping[str, Any], result: Mapping[str, Any]) -> List[str]:
    """Prices dated after the valuation date (ФСО III, п. 12; ФСО №10, п. 12).

    ``price_collected_at`` (живой поиск dealcalc-rf-collect) — когда цену
    реально видели; ``date`` у таких аналогов — дата размещения объявления,
    которая для ретроспективной выборки может быть задолго до даты цены."""

    if not context.get("valuation_date"):
        return []
    valuation = date.fromisoformat(context["valuation_date"])
    later = []
    for item in _observations(result):
        price_date = item.get("price_collected_at") or item.get("date")
        if price_date and (_parse_date(price_date) or valuation) > valuation:
            later.append(item.get("index"))
    if not later:
        return []
    return [
        f"Цены аналогов {later} датированы позже даты оценки: обоснуйте, что они отражают "
        "состояние рынка на дату оценки, скорректируйте на дату или исключите (ФСО III, п. 12)."
    ]


def _kind_checks(context: Mapping[str, Any], result: Mapping[str, Any]) -> List[str]:
    """The kind of the result against the type of value in the assignment."""

    required = _KIND_VALUE_TYPES.get(result.get("value_kind"))
    value_type = context.get("value_type")
    if not required or not value_type or value_type.startswith(required):
        return []
    label = "ДСД" if required.startswith("действительн") else required
    return [
        f"Результат — {result['value_kind']}, а в задании вид стоимости «{value_type}»: "
        f"проверьте задание ({label} — отдельная величина, ФСО II)."
    ]


_VAT_INCLUDED = ("с ндс", "включая ндс", "в т.ч. ндс", "в том числе ндс", "вкл. ндс")
_VAT_EXCLUDED = ("без ндс", "не облагается ндс", "ндс не облагается", "без учета ндс", "без учёта ндс")


def _analog_vat(item: Mapping[str, Any]) -> Optional[str]:
    if item.get("vat") in VAT_MODES:
        return item["vat"]
    text = str(item.get("conditions") or "").lower()
    if any(marker in text for marker in _VAT_EXCLUDED):
        return "excluded"
    if any(marker in text for marker in _VAT_INCLUDED):
        return "included"
    return None


def _analog_vat_checks(context: Mapping[str, Any], result: Mapping[str, Any]) -> List[str]:
    """VAT basis of every analog price: one basis, matching the assignment."""

    bases: Dict[str, List[Any]] = {}
    for item in _observations(result):
        vat = _analog_vat(item)
        if vat:
            bases.setdefault("excluded" if vat == "not_applicable" else vat, []).append(item.get("index"))
    checks = []
    if "included" in bases and "excluded" in bases:
        checks.append(
            f"Цены аналогов {bases['included']} — с НДС, {bases['excluded']} — без НДС: "
            "приведите их к одной базе."
        )
    expected = context.get("vat")
    if expected:
        expected = "excluded" if expected == "not_applicable" else expected
        other = [index for basis, indices in bases.items() if basis != expected for index in indices]
        if other and len(bases) == 1:
            checks.append(
                f"Цены аналогов {other} — {VAT_MODES[next(iter(bases))]}, а в задании "
                f"«{context['vat_label']}»: приведите цены к базе задания."
            )
    return checks


def _weighting_guardrails(result: Mapping[str, Any]) -> List[str]:
    if result.get("weighting") in (None, "manual"):
        return []
    return [
        "Автоматические веса аналогов — эвристика, а не мера достоверности: обоснуйте выбор "
        "правила или задайте веса вручную."
    ]


def _review(text: str, justified: bool) -> tuple:
    if justified:
        return [], [f"{text}; приведено обоснование оценщика."]
    return [f"{text} — обоснуйте выбор (justification) или исправьте значение."], []


def _out_of_range_text(label: str, value: Any, low: float, high: float) -> str:
    return f"{label}: значение {value} вне границ источника [{low}; {high}]"


def _out_of_range(label: str, value: Any, low: float, high: float, justified: bool) -> tuple:
    return _review(_out_of_range_text(label, value, low, high), justified)


def _domain_text(label: str, step: Mapping[str, Any]) -> str:
    domain = step["domain"]
    bounds = "; ".join(
        f"{word} {domain[key]}" for word, key in (("от", "low"), ("до", "high")) if domain[key] is not None
    )
    return (
        f"{label}: объект {step['subject']}, аналог {step['analog']} — вне области применимости "
        f"уравнения ({bounds})"
    )


def _confidence_text(label: str, value: Any, bounds: Mapping[str, Any], justified: bool) -> str:
    text = (
        f"{label}: значение {value} вне доверительного интервала среднего [{bounds['low']}; {bounds['high']}] — "
        "этот интервал не ограничивает само значение; обоснуйте сдвиг от среднего дополнительными факторами"
    )
    return f"{text}; приведено обоснование оценщика." if justified else f"{text}."


def _later_source_text(label: str, raw: Any, valuation: Optional[date]) -> Optional[str]:
    """A source dated after the valuation date (ФСО III, п. 12)."""

    found = None if valuation is None or raw in (None, "") else _parse_date(raw)
    if found is None or found <= valuation:
        return None
    return (
        f"{label}: источник датирован {raw}, позже даты оценки {valuation.isoformat()}; он должен отражать "
        "состояние рынка на дату оценки (ФСО III, п. 12)"
    )


def _valuation_date(context: Mapping[str, Any]) -> Optional[date]:
    return date.fromisoformat(context["valuation_date"]) if context.get("valuation_date") else None


_CHOICE_TEXT = {
    "mean": "без обоснованного сдвига берётся среднее {expected}",
    "minimal_extended": (
        "поправка больше 30 % — по правилу выбора берётся значение с минимальной поправкой "
        "в расширенном интервале ({expected})"
    ),
    "minimal_interval": (
        "поправка больше 30 % — по правилу выбора берётся значение с минимальной поправкой "
        "в интервале ({expected})"
    ),
}


def _step_range_review(result: Mapping[str, Any], valuation: Optional[date] = None) -> tuple:
    """Adjustment steps whose value lies outside the bounds of their source,
    departs from the rule of choice, is larger than 30 %, ends a cascade above
    the threshold, applies an equation outside its domain or cites a source
    dated after the valuation date — in the analogs, at the root of the
    result (the value of an interest) and in operating expenses."""

    checks: List[str] = []
    guardrails: List[str] = []
    owners = [(f"Аналог {item.get('index')}, шаг", item, "adjustments") for item in _observations(result)]
    owners += [("Шаг", result, "adjustments"), ("Статья расходов", result, "operating_expenses")]
    for owner, item, key in owners:
        steps = item.get(key)
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
            continue
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            value = step.get("value", step.get("exponent"))
            label = f"{owner} «{step.get('name')}»"
            choice = step.get("choice") or {}
            chosen = step.get("chosen") or {}
            bounds = step.get("range") if isinstance(step.get("range"), Mapping) else {}
            justified = any(
                str(item.get("justification") or "").strip() for item in (step, bounds)
            )
            texts = []
            if step.get("selection") == "smallest_of_all":
                texts.append(
                    f"{label}: все варианты дают поправку больше 30 % — взята наименьшая "
                    f"({chosen['adjustment_pct']} %, «{chosen['label']}»)"
                )
            if step.get("within_domain") is False:
                texts.append(_domain_text(label, step))
            if chosen.get("within_domain") is False:
                texts.append(_domain_text(f"{label}, вариант «{chosen['label']}»", chosen))
            if step.get("within_range") is False:
                texts.append(_out_of_range_text(
                    label, value, bounds.get("extended_low", bounds["low"]), bounds.get("extended_high", bounds["high"])
                ))
            elif choice.get("follows_rule") is False:
                rule = _CHOICE_TEXT[choice["rule"]].format(expected=choice["expected"])
                texts.append(f"{label}: {rule}, взято {value}")
            elif step.get("within_confidence") is False:
                guardrails.append(_confidence_text(label, value, bounds, justified))
            if choice.get("within_threshold") is False:
                texts.append(
                    f"{label}: поправка {choice['adjustment_pct']} % больше 30 % — существенное различие в "
                    "ценообразовании объекта и аналога; проверьте сопоставимость аналога"
                )
            for raw in (step.get("date"), bounds.get("date"), chosen.get("date")):
                later = _later_source_text(label, raw, valuation)
                if later:
                    texts.append(later)
            for text in texts:
                found = _review(text, justified)
                checks += found[0]
                guardrails += found[1]
    return checks, guardrails


def _source_range_review(
    func: Callable[..., Any], args: tuple, kwargs: dict, ranges: Any, valuation: Optional[date] = None
) -> tuple:
    """Parameters of a calculation compared with the bounds of their source."""

    if not isinstance(ranges, Mapping):
        raise ValueError("source_ranges must be an object {parameter: {low, high}}")
    bound = inspect.signature(func).bind(*args, **kwargs)
    bound.apply_defaults()
    review: Dict[str, Any] = {}
    checks: List[str] = []
    guardrails: List[str] = []
    for name, bounds in ranges.items():
        if name not in bound.arguments:
            raise ValueError(f"source_ranges: {name} is not a parameter of this calculation")
        value = bound.arguments[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"source_ranges: {name} is not a numeric parameter of this calculation")
        item = source_range(f"source_ranges.{name}", bounds)
        item["value"] = value
        item.update(range_position(item, value))
        justified = "justification" in item
        texts = []
        if item["within_range"] is False:
            texts.append(_out_of_range_text(
                name, value, item.get("extended_low", item["low"]), item.get("extended_high", item["high"])
            ))
        elif item.get("within_confidence") is False:
            guardrails.append(_confidence_text(name, value, item, justified))
        later = _later_source_text(name, item.get("date"), valuation)
        if later:
            texts.append(later)
        for text in texts:
            found = _review(text, justified)
            checks += found[0]
            guardrails += found[1]
        review[name] = item
    return review, checks, guardrails


_FLOW_RATE_FIELDS = {
    "price_level": ("nominal", "real"),
    "tax": ("pre_tax", "post_tax"),
    "currency": None,
}
_FLOW_RATE_LABELS = {"price_level": "уровню цен", "tax": "налогам", "currency": "валюте"}


def validate_flow_rate_basis(value: Any) -> Optional[Dict[str, Dict[str, str]]]:
    """Validate the basis of the cash flow and of the rate:
    ``{"flow": {...}, "rate": {...}}`` with ``price_level`` (nominal | real),
    ``tax`` (pre_tax | post_tax) and ``currency``."""

    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) - {"flow", "rate"}:
        raise ValueError("flow_rate_basis must be an object with 'flow' and 'rate'")
    result: Dict[str, Dict[str, str]] = {}
    for side in ("flow", "rate"):
        part = value.get(side) or {}
        if not isinstance(part, Mapping) or set(part) - set(_FLOW_RATE_FIELDS):
            raise ValueError(f"flow_rate_basis.{side} may hold price_level, tax and currency")
        normalized = {}
        for key, allowed in _FLOW_RATE_FIELDS.items():
            item = part.get(key)
            if item in (None, ""):
                continue
            item = str(item).strip()
            if allowed and item not in allowed:
                raise ValueError(f"flow_rate_basis.{side}.{key} must be one of {', '.join(allowed)}")
            normalized[key] = item.upper() if key == "currency" else item
        result[side] = normalized
    return result


def _flow_rate_review(basis: Optional[Mapping[str, Mapping[str, str]]]) -> tuple:
    """Checks for a flow and a rate on different bases; a reminder when the
    basis is not described (ФСО V, п. 15: the rate matches the flow)."""

    reminder = (
        "Не описана база потока и ставки (flow_rate_basis: номинальная или реальная, до или "
        "после налогов, валюта): ставка должна соответствовать потоку."
    )
    if basis is None:
        return [], [reminder]
    checks = []
    incomplete = False
    for key, label in _FLOW_RATE_LABELS.items():
        flow, rate = basis["flow"].get(key), basis["rate"].get(key)
        if flow and rate and flow != rate:
            checks.append(f"Поток и ставка различаются по {label}: поток — {flow}, ставка — {rate}.")
        elif not (flow and rate):
            incomplete = True
    return checks, [reminder] if incomplete else []


def _condition_review(
    required: Mapping[str, str], confirmed: Any
) -> tuple:
    """Conditions of a private model confirmed by the appraiser."""

    if confirmed is None:
        confirmed = []
    if isinstance(confirmed, (str, bytes)) or not isinstance(confirmed, Sequence):
        raise ValueError("confirmed_conditions must be a list of condition ids")
    unknown = set(confirmed) - set(required)
    if unknown:
        raise ValueError(f"confirmed_conditions has unknown ids {sorted(unknown)}; known: {sorted(required)}")
    items = [{"id": key, "text": text, "confirmed": key in confirmed} for key, text in required.items()]
    missing = [f"{item['id']} — {item['text']}" for item in items if not item["confirmed"]]
    checks = (
        [f"Не подтверждены условия применения модели (confirmed_conditions): {'; '.join(missing)}."]
        if missing
        else []
    )
    return items, checks


def method_card(
    method_id: str,
    standard: str,
    formula: str,
    formula_status: str,
    source_url: str = "",
    context_reminder: bool = True,
    income_model: bool = False,
    required_conditions: Optional[Mapping[str, str]] = None,
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

    Income models (``income_model``) also accept ``flow_rate_basis``: the
    basis of the flow and of the rate, checked for consistency. Private
    models with ``required_conditions`` accept ``confirmed_conditions`` — the
    ids of the conditions of application confirmed by the appraiser; an
    unconfirmed condition is a check.

    Every calculation accepts ``source_ranges`` — ``{parameter: {"low",
    "high", "source", "page", "justification"}}``, the bounds given by the
    source of a numeric parameter (a rate, a period, a share). A value
    outside them is a check, or a reminder when it is justified. Adjustment
    steps carry their own ``range``, reviewed the same way.
    """

    def decorate(func: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(
            *args: Any,
            context: Any = None,
            flow_rate_basis: Any = None,
            confirmed_conditions: Any = None,
            source_ranges: Any = None,
            **kwargs: Any,
        ) -> Dict[str, Any]:
            assignment = assignment_context(context)
            if flow_rate_basis is not None and not income_model:
                raise ValueError("flow_rate_basis applies only to income models")
            if confirmed_conditions is not None and not required_conditions:
                raise ValueError("this calculation has no conditions to confirm")
            basis = validate_flow_rate_basis(flow_rate_basis) if income_model else None
            result = dict(func(*args, **kwargs))
            checks = list(result.pop("checks", [])) + _vat_checks(assignment, result)
            checks += _later_price_checks(assignment, result) + _kind_checks(assignment, result)
            checks += _analog_vat_checks(assignment, result)
            guardrails = list(result.pop("guardrails", []))
            step_checks, step_guardrails = _step_range_review(result, _valuation_date(assignment))
            checks += step_checks
            guardrails += step_guardrails
            if source_ranges is not None:
                review, range_checks, range_guardrails = _source_range_review(
                    func, args, kwargs, source_ranges, _valuation_date(assignment)
                )
                result["source_ranges"] = review
                checks += range_checks
                guardrails += range_guardrails
            conditions = list(result.pop("conditions", []))
            guardrails += offer_guardrails(result) + identifier_guardrails(result)
            guardrails += _weighting_guardrails(result)
            if context_reminder:
                guardrails += _context_guardrails(assignment)
            if income_model:
                basis_checks, basis_guardrails = _flow_rate_review(basis)
                checks += basis_checks
                guardrails += basis_guardrails
                result["flow_rate_basis"] = basis
            if required_conditions:
                items, condition_checks = _condition_review(required_conditions, confirmed_conditions)
                checks += condition_checks
                result["required_conditions"] = items
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
    "source", "date", "date_updated", "price_collected_at", "url", "price_type", "conditions",
    "reliability", "import_warnings", "listing_id_basis", "listing_id", "address", "vat",
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
    if variation.get("within_threshold") is False:
        return [
            f"Коэффициент вариации {variation['coefficient_pct']}% больше {variation['threshold_pct']}%: "
            "проверьте сопоставимость аналогов по ценообразующим факторам."
        ]
    return []
