"""Check of the valuation assignment before any calculation (ФСО III, IV).

The agent must not start with a formula: object, rights, purpose, type of
value, premises and valuation date come first. Missing critical items stop
the calculation with the status "недостаточно данных".
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Dict, List

from ._meta import STATUS_INSUFFICIENT, method_card

_OBJECT_TYPES = {
    "real_estate": ("недвижимость", "ФСО №7"),
    "business": ("бизнес, акции, доли", "ФСО №8"),
    "machinery": ("машины и оборудование", "ФСО №10"),
    "vehicle": ("машины и оборудование (транспортное средство)", "ФСО №10"),
}

_VALUE_TYPES = (
    "рыночная", "инвестиционная", "равновесная", "ликвидационная",
    "действительная стоимость доли", "иная",
)

_CRITICAL = {
    "object_description": "объект оценки и его состав",
    "rights": "оцениваемые права и обременения",
    "purpose": "цель оценки и использование результата",
    "value_type": "вид стоимости",
    "value_premises": "предпосылки стоимости",
    "valuation_date": "дата оценки",
}

_RECOMMENDED = {
    "common": ["intended_use", "currency", "assumptions", "limitations", "users"],
    "real_estate": [
        "location",
        "areas_or_units",
        "land_rights",
        "encumbrances",
        "physical_condition",
        "permitted_use",
        "actual_use",
        "lease_terms",
        "inspection_status",
    ],
    "business": [
        "security_or_interest_type",
        "share_fraction",
        "capital_structure",
        "owner_rights",
        "corporate_agreements",
        "historical_financials",
        "forecasts",
        "debt",
        "non_operating_assets_and_liabilities",
    ],
    "machinery": [
        "inventory",
        "manufacturer",
        "model",
        "serial_number",
        "year",
        "technical_characteristics",
        "completeness",
        "condition",
        "location",
        "operating_hours_or_load",
        "integrated_assets",
        "required_intangibles",
        "valuation_scenario",
    ],
}

APPROACH_DIAGNOSTICS = {
    "сравнительный": {
        "supports": [
            "активный рынок",
            "достаточно надёжных цен сделок или предложений",
            "близкие аналоги из того же сегмента",
            "сопоставимые ценообразующие факторы",
        ],
        "reject_or_limit_when": [
            "недостаточно данных",
            "иной сегмент",
            "неизвестны права или условия сделок",
            "поправки не обоснованы",
        ],
    },
    "доходный": {
        "supports": [
            "объект приносит или может приносить доход",
            "суммы и сроки выгод можно прогнозировать",
        ],
        "reject_or_limit_when": [
            "выгоду нельзя отнести к объекту",
            "высокая неопределённость",
            "ставка не согласована с потоком",
        ],
    },
    "затратный": {
        "supports": [
            "специализированный объект",
            "слабый рынок",
            "затраты на замещение или воспроизводство и обесценение оценимы",
        ],
        "reject_or_limit_when": [
            "необоснованная база затрат",
            "неопределённое обесценение",
            "двойной учёт износа",
        ],
    },
}

STOP_CONDITIONS = [
    "Не определены объект или оцениваемые права.",
    "Не установлены цель, дата, вид стоимости или предпосылки.",
    "Критические данные отсутствуют или цена/характеристики не проверяются.",
    "Ограничения не позволяют собрать достаточные данные или получить достоверный результат.",
    "Для доходного подхода невозможно согласовать поток и ставку.",
    "Для сравнительного подхода нет достаточных аналогов и поправки не обосновать.",
    "Для затратного подхода невозможно оценить замещение/воспроизводство или обесценение.",
    "Для ликвидации бизнеса нет обоснованной ликвидационной предпосылки.",
]


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


@method_card(
    "ASSIGNMENT_CHECK",
    "ФСО III; ФСО IV; ФСО II",
    "проверка состава задания на оценку до расчёта",
    "процедурная проверка, не расчётная формула",
    source_url="https://srosovet.ru/activities/npa/fso-iii/",
    context_reminder=False,
)
def check_assignment(assignment: Mapping[str, Any]) -> Dict[str, Any]:
    """Check the valuation assignment before calculations.

    ``assignment`` holds ``object_type`` (``real_estate``, ``business``,
    ``machinery`` or ``vehicle``), the critical items ``object_description``,
    ``rights``, ``purpose``, ``value_type`` (рыночная, инвестиционная,
    равновесная, ликвидационная), ``value_premises`` and ``valuation_date``
    (YYYY-MM-DD), and recommended items of the input contract for the object
    type. Missing critical items give the status "недостаточно данных"; the
    result also lists the approach diagnostics and stop conditions.
    """

    if not isinstance(assignment, Mapping):
        raise ValueError("assignment must be an object")
    object_type = str(assignment.get("object_type") or "").strip().lower()
    if object_type not in _OBJECT_TYPES:
        raise ValueError(
            "object_type must be 'real_estate', 'business', 'machinery' or 'vehicle'"
        )
    object_name, standard = _OBJECT_TYPES[object_type]

    missing_critical = [
        f"{field} — {label}" for field, label in _CRITICAL.items()
        if not _present(assignment.get(field))
    ]
    contract = "machinery" if object_type == "vehicle" else object_type
    missing_recommended = [
        field
        for field in _RECOMMENDED["common"] + _RECOMMENDED[contract]
        # The inspection status may be a boolean: False is an answer.
        if not _present(assignment.get(field))
        and not (field == "inspection_status" and isinstance(assignment.get(field), bool))
    ]

    checks: List[str] = []
    value_type = str(assignment.get("value_type") or "").strip().lower()
    if value_type and not any(value_type.startswith(name) for name in _VALUE_TYPES):
        # Как нераспознанная дата: расчёт с таким видом стоимости не начнётся (ревью 30, M10).
        missing_critical.append(
            f"value_type — вид стоимости «{assignment.get('value_type')}» не из ФСО II "
            f"({', '.join(_VALUE_TYPES)})"
        )
    raw_date = assignment.get("valuation_date")
    if _present(raw_date):
        try:
            date.fromisoformat(str(raw_date))
        except ValueError:
            missing_critical.append(
                f"valuation_date — дата оценки «{raw_date}» не распознана (нужна ГГГГ-ММ-ДД)"
            )
    if contract == "real_estate":
        raw_inspection = assignment.get("inspection_status")
        inspection = "false" if raw_inspection is False else str(raw_inspection or "").strip().lower()
        if inspection in ("нет", "не проводился", "не проведён", "false", "no"):
            checks.append(
                "Осмотр не проводился: по ФСО №7 нужно объяснить причину и раскрыть допущения."
            )
    if value_type.startswith("ликвидационн"):
        checks.append(
            "Ликвидационная стоимость: зафиксируйте основание прекращения, срок экспозиции "
            "и добровольность или вынужденность продажи."
        )
    if missing_recommended:
        checks.append(
            f"Не заполнены рекомендуемые сведения: {', '.join(missing_recommended)}."
        )

    result: Dict[str, Any] = {
        "object_type": object_type,
        "object_kind": object_name,
        "profile_standard": standard,
        "missing_critical": missing_critical,
        "missing_recommended": missing_recommended,
        "can_proceed": not missing_critical,
        "approach_diagnostics": APPROACH_DIAGNOSTICS,
        "stop_conditions": STOP_CONDITIONS,
        "checks": checks,
    }
    if missing_critical:
        result["status"] = STATUS_INSUFFICIENT
        checks.insert(0, "Расчёт останавливается: не хватает критических сведений задания.")
    return result
