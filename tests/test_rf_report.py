"""Check of the valuation report against ФСО VI."""

import pytest

from dealcalc import rf
from dealcalc.rf._meta import STATUS_INSUFFICIENT

ASSIGNMENT = {
    "object_type": "real_estate",
    "object_description": "квартира 54 м²",
    "rights": "право собственности",
    "purpose": "залог",
    "value_type": "рыночная",
    "value_premises": "текущее использование",
    "valuation_date": "2026-10-01",
}
CONTEXT = {"valuation_date": "2026-10-01", "value_type": "рыночная", "vat": "not_applicable"}
BASIS = {"price_level": "nominal", "tax": "post_tax", "currency": "RUB"}


def _calculation():
    return rf.income_capitalization(
        1_200_000, 12, context=CONTEXT, flow_rate_basis={"flow": BASIS, "rate": BASIS}
    )


def _report(**changes):
    report = {
        "report_number": "ОЦ-15/2026",
        "report_date": "2026-10-05",
        "basis": "договор № 15 от 20.09.2026",
        "assignment": ASSIGNMENT,
        "appraisers": [{
            "full_name": "Иванов Иван Иванович", "phone": "+7 900 000-00-00",
            "postal_address": "г. Казань, ул. Ленина, 1", "email": "appraiser@example.ru",
            "sro_registry_number": "0001", "sro_name": "СРОО «Экспертный совет»",
            "sro_address": "г. Москва, Потаповский пер., д. 16/5, стр. 1",
        }],
        "customer": {"full_name": "Петров Пётр Петрович"},
        "private_practice": True,
        "independence": "оценщик независим в соответствии со ст. 16 135-ФЗ",
        "engaged_specialists": [],
        "standards": ["ФСО I–VI", "ФСО №7"],
        "recommendations_not_used_reason": "одобренные Советом рекомендации к объекту не относятся",
        "object": {"description": "квартира 54 м², 3 этаж", "rights": "право собственности"},
        "assumptions": ["осмотр 28.09.2026"],
        "market_analysis": "раздел 4",
        "approaches": {
            "selection_justification": "доходный подход: объект сдаётся в аренду",
            "rejected": ["затратный"],
            "rejected_comment": "затратный не применяется к квартирам в МКД",
            "calculations": [_calculation()],
        },
        "final_value": 10_000_000,
        "limits_of_use": "для залога, 6 месяцев",
        "documents": ["выписка ЕГРН"],
        "sources": [{"url": "https://www.cian.ru/sale/flat/1", "date": "2026-09-20"}],
        "signing": {"form": "electronic", "confirmed": ["appraiser_qualified_signature", "employer_signature"]},
    }
    report.update(changes)
    return report


def test_complete_report_can_be_issued():
    result = rf.check_report(_report())

    assert result["missing"] == []
    assert result["can_issue"] is True
    assert result["checks"] == []
    assert result["status"] == "черновой расчёт"


def test_missing_items_are_listed_with_fso_vi_points():
    report = _report()
    for key in ("basis", "market_analysis", "sources"):
        report.pop(key)
    result = rf.check_report(report)

    assert result["can_issue"] is False
    assert result["status"] == STATUS_INSUFFICIENT
    assert any(item.startswith("п. 7 (2) basis") for item in result["missing"])
    assert any(item.startswith("п. 7 (12)") for item in result["missing"])
    assert any(item.startswith("п. 8 sources") for item in result["missing"])


def test_appraiser_and_employer_details():
    result = rf.check_report(_report(
        appraisers=[{"full_name": "Иванов И. И."}], private_practice=False
    ))

    assert any("appraisers[0].sro_registry_number" in item for item in result["missing"])
    assert any("employer" in item for item in result["missing"])


def test_calculation_with_checks_or_other_context_is_reported():
    unresolved = rf.reconcile_approaches({"a": 10e6, "b": 100e6}, {"a": 0.5, "b": 0.5}, context=CONTEXT)
    other_date = rf.income_capitalization(1, 10, context={**CONTEXT, "valuation_date": "2026-09-01"})
    report = _report()
    report["approaches"] = {**report["approaches"], "calculations": [unresolved, other_date]}
    result = rf.check_report(report)

    assert any("RECONCILIATION" in check and "итоговой стоимости нет" in check for check in result["checks"])
    assert any("дата оценки в расчёте «2026-09-01»" in check for check in result["checks"])


def test_sources_need_reference_and_date():
    result = rf.check_report(_report(sources=[{"url": "https://x"}, {"date": "2026-09-01"}]))

    assert any("sources[0]: нет даты" in check for check in result["checks"])
    assert any("sources[1]: нет ссылки" in check for check in result["checks"])


def test_signing_requirements_by_form():
    paper = rf.check_report(_report(signing={"form": "paper", "confirmed": ["signed"]}))

    assert any("прошит" in item for item in paper["missing"])
    assert any("signing.form" in item for item in rf.check_report(_report(signing={}))["missing"])


def test_final_value_must_be_a_number_without_form():
    result = rf.check_report(_report(final_value="около 10 млн"))

    assert any("числом" in check for check in result["checks"])


def test_rejected_approach_needs_comment():
    report = _report()
    report["approaches"] = {**report["approaches"], "rejected_comment": ""}

    assert any("rejected_comment" in item for item in rf.check_report(report)["missing"])


def test_invalid_assignment_in_report():
    result = rf.check_report(_report(assignment={**ASSIGNMENT, "rights": ""}))

    assert any("задание: rights" in item for item in result["missing"])


def test_report_must_be_an_object():
    with pytest.raises(ValueError, match="report"):
        rf.check_report([])
