"""Check of a valuation report against ФСО VI before the appraiser signs it.

The library does not write the report. :func:`check_report` checks that the
information the report must contain under ФСО VI (п. 7), the disclosure of
sources (п. 8) and the form of signing (пп. 3–5) are present, and that the
attached calculations are consistent with the assignment and free of
unresolved checks.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Dict, List

from ._meta import STATUS_DRAFT, STATUS_INSUFFICIENT, method_card
from .assignment import check_assignment

# ФСО VI, п. 7: required information (sub-item, field, label).
_REQUIRED = [
    ("1", "report_number", "порядковый номер отчёта"),
    ("1", "report_date", "дата составления отчёта"),
    ("2", "basis", "основание для проведения оценки"),
    ("3", "assignment", "информация из задания на оценку"),
    ("4", "appraisers", "сведения об оценщике (оценщиках)"),
    ("5", "customer", "сведения о заказчике"),
    ("7", "independence", "сведения о независимости оценщика и юридического лица"),
    ("8", "engaged_specialists", "привлечённые организации и специалисты (пустой список — их нет)"),
    ("9", "standards", "применённые стандарты оценки"),
    ("10", "object", "точное описание объекта оценки"),
    ("11", "assumptions", "допущения и ограничения оценки"),
    ("12", "market_analysis", "анализ рынка и внешних факторов"),
    ("13", "approaches", "описание процесса оценки: выбор подходов, расчёты, согласование"),
    ("14", "final_value", "итоговая стоимость"),
    ("14", "limits_of_use", "ограничения и пределы применения результата"),
    ("15", "documents", "перечень документов о характеристиках объекта"),
]
_APPRAISER_FIELDS = {
    "full_name": "ФИО",
    "phone": "телефон",
    "postal_address": "почтовый адрес",
    "email": "электронная почта",
    "sro_registry_number": "регистрационный номер в СРО",
    "sro_name": "наименование СРО",
    "sro_address": "адрес СРО",
}
# Sections whose content is checked: a value of another type is missing.
_SECTION_TYPES = [
    ("п. 7 (3)", "assignment", "объект"),
    ("п. 7 (5)", "customer", "объект"),
    ("п. 7 (10)", "object", "объект"),
    ("п. 7 (13)", "approaches", "объект"),
    ("п. 8", "sources", "список"),
    ("п. 7 (8)", "engaged_specialists", "список"),
    ("п. 7 (2)", "basis", "текст"),
    ("п. 7 (7)", "independence", "текст"),
    ("п. 7 (9)", "standards", "текст"),
    ("п. 7 (11)", "assumptions", "текст"),
    ("п. 7 (12)", "market_analysis", "текст"),
    ("п. 7 (14)", "limits_of_use", "текст"),
    ("п. 7 (15)", "documents", "текст"),
]
_LEGAL_FIELDS = {"name": "наименование", "ogrn": "ОГРН или иной регистрационный номер", "address": "место нахождения"}
_SIGNING = {
    "paper": {
        "pages_numbered": "страницы пронумерованы",
        "bound": "отчёт прошит",
        "signed": "подписан оценщиком (оценщиками)",
        "sealed": "скреплён печатью оценщика или юридического лица",
    },
    "electronic": {
        "appraiser_qualified_signature": "усиленная квалифицированная подпись оценщика",
        "employer_signature": "подпись руководителя юридического лица или уполномоченного лица",
    },
}


# The result of each method that is a value (or a rent) of the object, not
# an input or an intermediate figure (the value of the whole business behind
# an interest, the market value behind a liquidation value, NOI, rates).
_VALUE_KEYS = {
    "RECONCILIATION": ("reconciled_value",),
    "COMPARABLE_UNIT_PRICE": ("indicated_value",),
    "VEHICLE_COMPARATIVE": ("indicated_value",),
    "DIRECT_CAPITALIZATION": ("indicated_value",),
    "DCF": ("indicated_value",),
    "GROSS_RENT_MULTIPLIER": ("indicated_value",),
    "PROPERTY_COST_APPROACH": ("indicated_value",),
    "MACHINERY_COST": ("residual_value",),
    "QUALITATIVE_ADJUSTMENTS": ("weighted_value", "range_value"),
    "BUSINESS_EQUITY_DCF": ("equity_value_100pct",),
    "BUSINESS_MULTIPLE": ("value_100pct",),
    "BUSINESS_NET_ASSETS": ("equity_value_100pct",),
    "BUSINESS_INTEREST_VALUE": ("interest_value",),
    "BUSINESS_LIQUIDATION": ("business_liquidation_value",),
    "ASSET_LIQUIDATION_VALUE": ("liquidation_value",),
    "DSD_NET_ASSETS": ("actual_share_value",),
    "PIF_UNIT_DCF": ("unit_value",),
    "MARKET_RENT_COST_PLUS": ("gross_rent_year", "gross_rent_month", "rent_sqm_year", "rent_sqm_month"),
    "CELLULAR_REVERSE_CAPITALIZATION": ("gross_rent_year", "gross_rent_month"),
}
# Rounding of the final value against the calculated one.
FINAL_VALUE_TOLERANCE_PCT = 1.0


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def _same(key: str, actual: Any, expected: Any) -> bool:
    """«рыночная» and «рыночная стоимость» are one value type, as in the context."""

    first, second = str(actual).strip().lower(), str(expected).strip().lower()
    if key == "value_type":
        return first.startswith(second) or second.startswith(first)
    return first == second


def _missing_fields(data: Any, fields: Mapping[str, str], prefix: str) -> List[str]:
    if not isinstance(data, Mapping):
        return [f"{prefix}: нужен объект с полями {', '.join(fields)}"]
    return [f"{prefix}.{key} — {label}" for key, label in fields.items() if not _present(data.get(key))]


@method_card(
    "REPORT_CHECK",
    "ФСО VI, пп. 2–8; ФСО III; ФСО IV",
    "проверка состава отчёта об оценке перед подписанием",
    "процедурная проверка, не расчётная формула",
    source_url="https://srosovet.ru/activities/npa/fso-vi/",
    context_reminder=False,
)
def check_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    """Check a valuation report before signing (ФСО VI).

    ``report`` holds the information of ФСО VI, п. 7: ``report_number``,
    ``report_date``, ``basis``, ``assignment`` (as for
    :func:`check_assignment`), ``appraisers`` (list of objects with
    ``full_name``, ``phone``, ``postal_address``, ``email``,
    ``sro_registry_number``, ``sro_name``, ``sro_address``), ``customer``
    (``full_name`` of a person or ``name``, ``ogrn``, ``address`` of a legal
    entity), ``employer`` (legal entity of the appraiser) or
    ``private_practice: true``, ``independence``, ``engaged_specialists``
    (list, empty when there are none), ``standards``, ``methodical_recommendations``
    or ``recommendations_not_used_reason``, ``object`` (``description``,
    ``rights``), ``assumptions``, ``market_analysis``, ``approaches``
    (``selection_justification``, ``rejected`` — approaches not used, with
    ``rejected_comment``, ``calculations`` — results of this library), ``final_value``,
    ``limits_of_use``, ``value_interval`` (``low``, ``high``,
    ``justification``; required for real estate by ФСО №7, п. 30 unless the
    assignment sets ``interval_not_required``), ``documents``, ``sources`` (п. 8: each with ``url`` or
    ``reference`` and ``date``) and ``signing`` (``form``: ``paper`` or
    ``electronic`` and the confirmed requirements of пп. 4–5).

    A numeric ``final_value`` must match a value result of one of the
    calculations (``reconciled_value``, ``indicated_value`` and the like)
    within 1 % for rounding, or the transition is explained in
    ``final_value_justification``; calculations of intermediate figures only
    (NOI, rates) are a check. ``assignment.assignment_id`` is compared with
    the context of the calculations; the checks of the assignment are kept as
    guardrails. In private practice no employer signature is required.

    ``can_issue`` is true when nothing required is missing and no check is
    left to resolve; checks name the points to review. A section of the wrong
    type (a string instead of an object or a list) is missing. Signing and
    keeping the materials (п. 12) remain the appraiser's duty.
    """

    if not isinstance(report, Mapping):
        raise ValueError("report must be an object")

    missing = [
        f"п. 7 ({item}) {field} — {label}"
        for item, field, label in _REQUIRED
        if not (_present(report.get(field)) or (field == "engaged_specialists" and report.get(field) == []))
    ]
    checks: List[str] = []
    guardrails: List[str] = [
        "Проверяется состав отчёта и связь итога с расчётами, а не обоснованность суждений оценщика; "
        "подписание и хранение копий отчёта и материалов (ФСО VI, п. 12) — обязанность оценщика.",
    ]
    for point, field, kind in _SECTION_TYPES:
        value = report.get(field)
        is_list = isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        if kind == "текст":
            # Text, a list of items or an object with subsections — not a number or a flag.
            valid = isinstance(value, (str, Mapping)) or is_list
        else:
            valid = is_list if kind == "список" else isinstance(value, Mapping)
        if _present(value) and not valid:
            missing.append(f"{point} {field} — нужен {kind}, а не {type(value).__name__}")

    raw_date = report.get("report_date")
    if _present(raw_date):
        try:
            date.fromisoformat(str(raw_date))
        except ValueError:
            missing.append(f"п. 7 (1) report_date — дата «{raw_date}» не распознана (нужна ГГГГ-ММ-ДД)")

    assignment = report.get("assignment")
    if isinstance(assignment, Mapping) and assignment:
        try:
            assignment_result = check_assignment(assignment)
        except ValueError as exc:
            missing.append(f"п. 7 (3) задание: {exc}")
        else:
            missing += [f"п. 7 (3) задание: {item}" for item in assignment_result["missing_critical"]]
            guardrails += [f"Задание: {item}" for item in assignment_result["checks"]]

    appraisers = report.get("appraisers")
    if _present(appraisers):
        if not isinstance(appraisers, Sequence) or isinstance(appraisers, (str, bytes)):
            missing.append("п. 7 (4) appraisers — нужен список оценщиков")
        else:
            for index, appraiser in enumerate(appraisers):
                missing += [f"п. 7 (4) {item}" for item in _missing_fields(
                    appraiser, _APPRAISER_FIELDS, f"appraisers[{index}]"
                )]

    customer = report.get("customer")
    if isinstance(customer, Mapping) and customer and not _present(customer.get("full_name")):
        missing += [f"п. 7 (5) {item}" for item in _missing_fields(customer, _LEGAL_FIELDS, "customer")]

    if report.get("private_practice") is not True:
        missing += [f"п. 7 (6) {item}" for item in _missing_fields(report.get("employer"), _LEGAL_FIELDS, "employer")]

    if not (_present(report.get("methodical_recommendations")) or _present(report.get("recommendations_not_used_reason"))):
        missing.append(
            "п. 7 (9) methodical_recommendations — применённые методические рекомендации или "
            "обоснование их неиспользования (recommendations_not_used_reason)"
        )

    subject = report.get("object")
    if isinstance(subject, Mapping) and subject:
        missing += [f"п. 7 (10) {item}" for item in _missing_fields(
            subject, {"description": "количественные и качественные характеристики", "rights": "права на объект"},
            "object",
        )]

    approaches = report.get("approaches")
    calculations: List[Mapping[str, Any]] = []
    if isinstance(approaches, Mapping) and approaches:
        if not _present(approaches.get("selection_justification")):
            missing.append("п. 7 (13) approaches.selection_justification — обоснование выбора подходов и методов")
        if approaches.get("rejected") and not _present(approaches.get("rejected_comment")):
            missing.append("п. 7 (13) approaches.rejected_comment — комментарий отказа от подхода")
        raw_calculations = approaches.get("calculations") or []
        if isinstance(raw_calculations, Sequence) and not isinstance(raw_calculations, (str, bytes)):
            for index, item in enumerate(raw_calculations):
                card = item.get("method_card") if isinstance(item, Mapping) else None
                if not isinstance(item, Mapping):
                    missing.append(f"п. 7 (13) approaches.calculations[{index}] — нужен результат расчёта (объект)")
                elif not (isinstance(card, Mapping) and _present(card.get("id")) and _present(item.get("status"))):
                    missing.append(
                        f"п. 7 (13) approaches.calculations[{index}] — нет method_card.id или status: "
                        "передайте результат расчёта целиком"
                    )
                else:
                    calculations.append(item)
        if not calculations:
            missing.append("п. 7 (13) approaches.calculations — расчёты методов")

    context = assignment if isinstance(assignment, Mapping) else {}
    for number, calculation in enumerate(calculations, start=1):
        label = (calculation.get("method_card") or {}).get("id", f"расчёт {number}")
        # Unresolved checks count whatever the status says (ревью 30, M9).
        if calculation.get("status") not in (None, STATUS_DRAFT) or calculation.get("checks"):
            reasons = "; ".join(calculation.get("checks") or [])
            checks.append(f"{label}: статус «{calculation.get('status')}» — {reasons or 'проверьте результат'}.")
        calc_context = calculation.get("context") or {}
        for key, name in (("valuation_date", "дата оценки"), ("value_type", "вид стоимости")):
            expected, actual = context.get(key), calc_context.get(key)
            if expected and actual is None:
                checks.append(f"{label}: в расчёте не указан контекст ({name}).")
            elif expected and actual and not _same(key, actual, expected):
                checks.append(f"{label}: {name} в расчёте «{actual}», в задании «{expected}».")
        expected_id, actual_id = context.get("assignment_id"), calc_context.get("assignment_id")
        if _present(expected_id) and _present(actual_id) and str(actual_id).strip() != str(expected_id).strip():
            checks.append(f"{label}: расчёт выполнен к заданию «{actual_id}», отчёт — к заданию «{expected_id}».")
        if calculation.get("reconciled_value", 0) is None:
            checks.append(f"{label}: согласование не завершено — итоговой стоимости нет.")

    final_value = report.get("final_value")
    form_given = isinstance(assignment, Mapping) and _present(assignment.get("final_value_form"))

    # ФСО VI, пп. 1–2, 7: the final value follows from the calculations.
    values = [
        calculation[key]
        for calculation in calculations
        for key in _VALUE_KEYS.get((calculation.get("method_card") or {}).get("id"), ())
        if _number(calculation.get(key))
    ]
    if calculations and not values:
        checks.append(
            "п. 7 (13) approaches.calculations: нет расчёта стоимости — только промежуточные показатели "
            "(ЧОД, ставки, износ); приложите расчёт стоимости или согласование подходов."
        )
    elif (
        _number(final_value)
        and values
        and not _present(report.get("final_value_justification"))
        and not any(
            math.isclose(final_value, value, rel_tol=FINAL_VALUE_TOLERANCE_PCT / 100) for value in values
        )
    ):
        checks.append(
            f"final_value {final_value} не совпадает (с точностью до 1 %) ни с одним результатом расчёта "
            "стоимости — приложите расчёт, из которого он получен, или объясните переход "
            "(final_value_justification: округление, учёт НДС и т. п.)."
        )

    # ФСО №7, п. 30: for real estate, the appraiser's judgment of the bounds of
    # the interval, unless the assignment says otherwise.
    interval = report.get("value_interval")
    real_estate = isinstance(assignment, Mapping) and assignment.get("object_type") == "real_estate"
    if real_estate and not (isinstance(assignment, Mapping) and assignment.get("interval_not_required") is True):
        missing_bounds = not isinstance(interval, Mapping) or not all(
            _present(interval.get(key)) for key in ("low", "high", "justification")
        )
        if missing_bounds:
            missing.append(
                "ФСО №7, п. 30 value_interval — суждение о границах интервала стоимости "
                "(low, high, justification), если задание не указывает иное (interval_not_required)"
            )
    if (
        isinstance(interval, Mapping)
        and isinstance(final_value, (int, float))
        and not isinstance(final_value, bool)
        and all(isinstance(interval.get(key), (int, float)) for key in ("low", "high"))
        and not interval["low"] <= final_value <= interval["high"]
    ):
        checks.append("ФСО №7, п. 30: итоговая стоимость вне интервала value_interval.")
    if isinstance(final_value, (int, float)) and not isinstance(final_value, bool) and not math.isfinite(final_value):
        checks.append(f"п. 14: итоговая стоимость {final_value} — не конечное число.")
    if _present(final_value) and not form_given and (
        isinstance(final_value, bool) or not isinstance(final_value, (int, float))
    ):
        checks.append("п. 14: форма итоговой стоимости в задании не указана — результат должен быть числом.")

    sources = report.get("sources")
    if not _present(sources):
        missing.append("п. 8 sources — источники существенной информации")
    elif isinstance(sources, Sequence) and not isinstance(sources, (str, bytes)):
        for index, source in enumerate(sources):
            if not isinstance(source, Mapping):
                checks.append(f"п. 8 sources[{index}]: нужен объект со ссылкой и датой.")
                continue
            if not (_present(source.get("url")) or _present(source.get("reference"))):
                checks.append(f"п. 8 sources[{index}]: нет ссылки или реквизитов источника.")
            if not _present(source.get("date")):
                checks.append(f"п. 8 sources[{index}]: нет даты появления (публикации) информации.")

    signing = report.get("signing")
    form = signing.get("form") if isinstance(signing, Mapping) else None
    if form not in _SIGNING:
        missing.append("пп. 3–5 signing.form — форма отчёта: paper или electronic")
    else:
        confirmed = signing.get("confirmed") or []
        # ФСО VI, п. 5: the head of the legal entity signs only when the
        # appraiser works under an employment contract with it.
        private = report.get("private_practice") is True
        missing += [
            f"п. {4 if form == 'paper' else 5} signing — {label}"
            for key, label in _SIGNING[form].items()
            if key not in confirmed and not (private and key == "employer_signature")
        ]

    result: Dict[str, Any] = {
        "missing": missing,
        # Checks are data defects: a report with any of them is not ready either.
        "can_issue": not missing and not checks,
        "calculations_checked": len(calculations),
        "guardrails": guardrails,
        "checks": checks,
    }
    if missing:
        result["status"] = STATUS_INSUFFICIENT
        checks.insert(0, "Отчёт не готов к подписанию: не хватает обязательных сведений ФСО VI.")
    return result
