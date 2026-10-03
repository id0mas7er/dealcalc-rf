"""Check of a valuation report against ФСО VI before the appraiser signs it.

The library does not write the report. :func:`check_report` checks that the
information the report must contain under ФСО VI (п. 7), the disclosure of
sources (п. 8) and the form of signing (пп. 3–5) are present, and that the
attached calculations are consistent with the assignment and free of
unresolved checks.
"""

from __future__ import annotations

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


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


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
    for point, field, kind in _SECTION_TYPES:
        value = report.get(field)
        is_list = isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        if _present(value) and not (is_list if kind == "список" else isinstance(value, Mapping)):
            missing.append(f"{point} {field} — нужен {kind}, а не {type(value).__name__}")

    raw_date = report.get("report_date")
    if _present(raw_date):
        try:
            date.fromisoformat(str(raw_date))
        except ValueError:
            missing.append(f"п. 7 (1) report_date — дата «{raw_date}» не распознана (нужна ГГГГ-ММ-ДД)")

    assignment = report.get("assignment")
    if isinstance(assignment, Mapping) and assignment:
        assignment_result = check_assignment(assignment)
        missing += [f"п. 7 (3) задание: {item}" for item in assignment_result["missing_critical"]]

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
        if calculation.get("status") not in (None, STATUS_DRAFT):
            reasons = "; ".join(calculation.get("checks") or [])
            checks.append(f"{label}: статус «{calculation.get('status')}» — {reasons or 'проверьте результат'}.")
        calc_context = calculation.get("context") or {}
        for key, name in (("valuation_date", "дата оценки"), ("value_type", "вид стоимости")):
            expected, actual = context.get(key), calc_context.get(key)
            if expected and actual is None:
                checks.append(f"{label}: в расчёте не указан контекст ({name}).")
            elif expected and actual and str(actual).strip().lower() != str(expected).strip().lower():
                checks.append(f"{label}: {name} в расчёте «{actual}», в задании «{expected}».")
        if calculation.get("reconciled_value", 0) is None:
            checks.append(f"{label}: согласование не завершено — итоговой стоимости нет.")

    final_value = report.get("final_value")
    form_given = isinstance(assignment, Mapping) and _present(assignment.get("final_value_form"))

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
        missing += [
            f"п. {4 if form == 'paper' else 5} signing — {label}"
            for key, label in _SIGNING[form].items()
            if key not in confirmed
        ]

    result: Dict[str, Any] = {
        "missing": missing,
        # Checks are data defects: a report with any of them is not ready either.
        "can_issue": not missing and not checks,
        "calculations_checked": len(calculations),
        "guardrails": [
            "Проверяется состав отчёта, а не обоснованность суждений оценщика; подписание и "
            "хранение копий отчёта и материалов (ФСО VI, п. 12) — обязанность оценщика.",
        ],
        "checks": checks,
    }
    if missing:
        result["status"] = STATUS_INSUFFICIENT
        checks.insert(0, "Отчёт не готов к подписанию: не хватает обязательных сведений ФСО VI.")
    return result
