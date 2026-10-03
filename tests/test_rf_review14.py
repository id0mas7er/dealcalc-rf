"""Methodology review of 0.11.0 (03.10.2026): R01–R09."""

import pytest

from dealcalc import rf
from test_rf_report import CONTEXT, _report

META = {"source": "S", "date": "2026-09-01", "price_type": "transaction"}


def _first(step, **kwargs):
    result = rf.comparative_approach(1, [
        dict(META, price=100, area_sqm=1, adjustments=[step]),
        dict(META, price=100, area_sqm=1),
    ], context=CONTEXT, **kwargs)
    return result, result["comparables"][0]["adjustments"][0]


FACTOR = {"low": 1.1, "high": 1.6, "mean": 1.5, "extended_low": 1.0, "extended_high": 1.8}


# R01: the mean by default; the smallest adjustment only by the appraiser's rule.


def test_default_rule_expects_the_mean_even_for_a_large_adjustment():
    result, step = _first({"name": "Фактор", "type": "coef", "value": 1.5, "range": FACTOR})

    assert step["choice"]["policy"] == "mean"
    assert step["choice"]["expected"] == 1.5
    assert step["choice"]["follows_rule"] is True
    assert step["choice"]["adjustment_pct"] == 50.0
    assert not any("среднее" in check for check in result["checks"])
    assert any("«Фактор»" in check and "сопоставимость" in check for check in result["checks"])


def test_default_rule_does_not_prefer_neutralising_the_factor():
    result, step = _first({"name": "Фактор", "type": "coef", "value": 1.0, "range": FACTOR})

    assert step["choice"]["follows_rule"] is False
    assert any("«Фактор»" in check and "среднее" in check for check in result["checks"])


def test_large_adjustment_with_justification_is_a_guardrail():
    result, _ = _first({"name": "Фактор", "type": "coef", "value": 1.5, "range": FACTOR,
                        "justification": "аналог сопоставим: других сделок нет"})

    assert not any("сопоставимость" in check for check in result["checks"])
    assert any("сопоставимость" in item for item in result["guardrails"])


def test_minimal_rule_on_request():
    result, step = _first({"name": "Фактор", "type": "coef", "value": 1.0, "range": FACTOR, "choice_rule": "minimal"})

    assert step["choice"]["policy"] == "minimal"
    assert step["choice"]["rule"] == "minimal_extended"
    assert step["choice"]["follows_rule"] is True
    assert result["checks"] == []


def test_minimal_rule_keeps_the_mean_up_to_30_pct():
    _, step = _first({"name": "Торг", "type": "coef", "value": 0.9, "choice_rule": "minimal",
                      "range": {"low": 0.86, "high": 0.93, "mean": 0.9}})

    assert step["choice"]["rule"] == "mean"
    assert step["choice"]["follows_rule"] is True


@pytest.mark.parametrize("step, message", [
    ({"name": "Т", "type": "coef", "value": 1, "choice_rule": "nearest", "range": FACTOR}, "choice_rule"),
    ({"name": "Т", "type": "coef", "value": 1.2, "choice_rule": "minimal", "range": {"low": 1.1, "high": 1.6}},
     "choice_rule needs range.mean"),
    ({"name": "Т", "type": "coef", "value": 1.2, "choice_rule": "minimal"}, "choice_rule needs range.mean"),
])
def test_invalid_choice_rule(step, message):
    with pytest.raises(ValueError, match=message):
        _first(step)


# R02: the confidence interval of the mean is not a bound of the value.


def test_outside_the_confidence_interval_is_a_guardrail():
    result, step = _first({"name": "Парковка", "type": "coef", "value": 0.88,
                           "range": {"low": 0.90, "high": 0.97, "kind": "confidence"}})

    assert step["range"]["kind"] == "confidence"
    assert step["within_range"] is None
    assert step["within_confidence"] is False
    assert result["checks"] == []
    assert any("«Парковка»" in item and "доверительного интервала среднего" in item for item in result["guardrails"])


def test_confidence_interval_with_extended_checks_the_extended():
    result, step = _first({"name": "Парковка", "type": "coef", "value": 0.80,
                           "range": {"low": 0.90, "high": 0.97, "kind": "confidence",
                                     "extended_low": 0.85, "extended_high": 0.99}})

    assert step["within_range"] is False
    assert any("«Парковка»" in check and "вне границ" in check for check in result["checks"])


def test_range_of_values_by_default():
    result, step = _first({"name": "Торг", "type": "coef", "value": 0.80, "range": {"low": 0.90, "high": 0.97}})

    assert step["range"]["kind"] == "values"
    assert step["within_range"] is False
    assert "within_confidence" not in step
    assert any("вне границ" in check for check in result["checks"])


def test_invalid_range_kind():
    with pytest.raises(ValueError, match="kind"):
        _first({"name": "Торг", "type": "coef", "value": 0.9, "range": {"low": 0.8, "high": 1, "kind": "tolerance"}})


def test_source_range_of_the_mean():
    result = rf.income_capitalization(
        1_000_000, 15, context=CONTEXT, source_ranges={"cap_rate_pct": {"low": 7, "high": 13, "kind": "confidence"}}
    )

    assert result["source_ranges"]["cap_rate_pct"]["within_confidence"] is False
    assert not any("cap_rate_pct" in check for check in result["checks"])
    assert any("cap_rate_pct" in item for item in result["guardrails"])


def test_expense_range_of_the_mean():
    result = rf.net_operating_income(1_000_000, operating_expenses=[
        {"name": "Отопление", "type": "pct", "value": 8, "base": "pgi",
         "range": {"low": 5.2, "high": 6.5, "mean": 5.9, "kind": "confidence"}}])

    assert result["checks"] == []
    assert any("«Отопление»" in item for item in result["guardrails"])


# R03: the final value comes from a calculation of value.


def test_final_value_not_from_any_calculation_is_a_check():
    report = _report(final_value=1_000_000_000,
                     value_interval={"low": 999_000_000, "high": 1_001_000_000, "justification": "t"})
    result = rf.check_report(report)

    assert result["can_issue"] is False
    assert any("final_value" in check and "не совпадает" in check for check in result["checks"])


def test_final_value_with_rounding_passes():
    report = _report()
    value = report["approaches"]["calculations"][0]["indicated_value"]
    report["final_value"] = round(value * 1.004)
    report["value_interval"] = {"low": value * 0.9, "high": value * 1.1, "justification": "t"}

    assert rf.check_report(report)["can_issue"] is True


def test_final_value_with_justified_transition_passes():
    report = _report(final_value=10_600_000, final_value_justification="округление до сотен тысяч и учёт НДС")
    report["value_interval"] = {"low": 9_000_000, "high": 11_000_000, "justification": "t"}

    assert rf.check_report(report)["can_issue"] is True


def test_only_intermediate_results_is_a_check():
    report = _report()
    report["approaches"]["calculations"] = [rf.net_operating_income(1_200_000, context=CONTEXT)]
    result = rf.check_report(report)

    assert result["can_issue"] is False
    assert any("нет расчёта стоимости" in check for check in result["checks"])


def test_reconciled_value_is_a_value():
    reconciled = rf.reconcile_approaches({"a": 9_900_000, "b": 10_100_000}, {"a": 0.5, "b": 0.5}, context=CONTEXT)
    report = _report(final_value=10_000_000)
    report["approaches"]["calculations"] = [reconciled]

    assert rf.check_report(report)["can_issue"] is True


# R04: the assignment of the report and of the calculations.


def test_other_assignment_id_is_a_check():
    report = _report()
    report["assignment"] = {**report["assignment"], "assignment_id": "A"}
    report["approaches"]["calculations"] = [
        rf.income_capitalization(1_200_000, 12, context={**CONTEXT, "assignment_id": "B"})
    ]
    result = rf.check_report(report)

    assert result["can_issue"] is False
    assert any("«B»" in check and "«A»" in check for check in result["checks"])


def test_same_assignment_id_passes():
    report = _report()
    report["assignment"] = {**report["assignment"], "assignment_id": "A"}
    report["approaches"]["calculations"] = [
        rf.income_capitalization(1_200_000, 12, context={**CONTEXT, "assignment_id": "A"})
    ]

    assert rf.check_report(report)["can_issue"] is True


def test_assignment_checks_are_carried_as_guardrails():
    own = rf.check_assignment(_report()["assignment"])["checks"]
    result = rf.check_report(_report())

    assert own
    assert all(any(item in guardrail for guardrail in result["guardrails"]) for item in own)


# R05: different factors in a pct_group are different adjustments.


def _weights(steps_a, steps_b, weighting="count_share"):
    result = rf.comparative_approach(1, [
        dict(META, price=100, area_sqm=1, adjustments=steps_a),
        dict(META, price=100, area_sqm=1, adjustments=steps_b),
    ], weighting=weighting)
    return [item["weight_share"] for item in result["comparables"]], result


def test_group_of_three_factors_counts_three():
    group = [{"name": name, "type": "pct_group", "value": 10} for name in ("Площадь", "Состояние", "Место")]
    shares, result = _weights(group, [{"name": "Площадь", "type": "pct", "value": -10}])

    assert result["comparables"][0]["adjustments_count"] == 3
    assert shares == [0.25, 0.75]
    assert result["weighted_unit_price"] == 100.0


def test_one_factor_split_in_a_group_counts_once():
    split = [{"name": "Площадь", "type": "pct_group", "value": 5}, {"name": "Площадь", "type": "pct_group", "value": 5}]
    tagged = [{"name": "Площадь, часть 1", "type": "pct_group", "value": 5, "factor": "Площадь"},
              {"name": "Площадь, часть 2", "type": "pct_group", "value": 5, "factor": "Площадь"}]

    for steps in (split, tagged):
        _, result = _weights(steps, [])
        assert result["comparables"][0]["adjustments_count"] == 1


# R06: a source dated after the valuation date.


def test_step_source_after_the_valuation_date_is_a_check():
    result, _ = _first({"name": "Торг", "type": "coef", "value": 0.95, "source": "Справочник", "date": "2027-01-01"})

    assert any("«Торг»" in check and "позже даты оценки" in check for check in result["checks"])


def test_range_source_after_the_valuation_date_is_a_check():
    result, _ = _first({"name": "Торг", "type": "coef", "value": 0.95,
                        "range": {"low": 0.9, "high": 1, "date": "01.01.2027"}})

    assert any("позже даты оценки" in check for check in result["checks"])


def test_later_source_with_justification_is_a_guardrail():
    result, _ = _first({"name": "Торг", "type": "coef", "value": 0.95, "date": "2027-01-01",
                        "justification": "выпуск отражает рынок на дату оценки"})

    assert not any("позже даты оценки" in check for check in result["checks"])
    assert any("позже даты оценки" in item for item in result["guardrails"])


def test_source_before_the_valuation_date_passes():
    result, _ = _first({"name": "Торг", "type": "coef", "value": 0.95, "date": "2026-07-01"})

    assert result["checks"] == []


def test_source_range_after_the_valuation_date_is_a_check():
    result = rf.income_capitalization(
        1_000_000, 10, context=CONTEXT, source_ranges={"cap_rate_pct": {"low": 7, "high": 13, "date": "2027-01-01"}}
    )

    assert any("cap_rate_pct" in check and "позже даты оценки" in check for check in result["checks"])


def test_expense_source_after_the_valuation_date_is_a_check():
    result = rf.net_operating_income(1_000_000, context=CONTEXT, operating_expenses=[
        {"name": "Отопление", "type": "pct", "value": 6, "date": "2027-01-01"}])

    assert any("«Отопление»" in check and "позже даты оценки" in check for check in result["checks"])


# R07: the evidence inside range is kept.


def test_range_evidence_is_kept_and_justifies():
    evidence = {"source": "Справочник", "date": "2026-07-01", "page": "42", "justification": "старый фонд"}
    result, step = _first({"name": "Торг", "type": "coef", "value": 0.85,
                           "range": {"low": 0.9, "high": 1, **evidence}})

    assert {key: step["range"][key] for key in evidence} == evidence
    assert not any("вне границ" in check for check in result["checks"])
    assert any("вне границ" in item for item in result["guardrails"])


def test_expense_range_evidence_is_kept():
    result = rf.net_operating_income(1_000_000, operating_expenses=[
        {"name": "Отопление", "type": "pct", "value": 6, "range": {"low": 5, "high": 7, "page": "табл. 8"}}])

    assert result["operating_expenses"][0]["range"]["page"] == "табл. 8"


# R08: the cascade skips equations outside their domain.


def test_staged_skips_a_variant_outside_its_domain():
    result, step = _first({"name": "Площадь", "type": "staged", "stages": [
        [{"label": "вне области", "type": "param", "subject": 10000, "analog": 100, "exponent": 0.01,
          "domain": {"low": 50, "high": 1000}}],
        [{"label": "таблица", "type": "coef", "value": 1.2}],
    ]})

    assert step["chosen"]["label"] == "таблица"
    assert len(step["variants"]) == 2
    assert not any("области применимости" in check for check in result["checks"])


def test_staged_with_every_variant_outside_its_domain_is_a_check():
    result, step = _first({"name": "Площадь", "type": "staged", "stages": [
        [{"label": "вне области", "type": "param", "subject": 10000, "analog": 100, "exponent": 0.01,
          "domain": {"low": 50, "high": 1000}}],
    ]})

    assert step["chosen"]["label"] == "вне области"
    assert any("области применимости" in check for check in result["checks"])


# R09: no employer signature in private practice.


def test_private_practice_needs_no_employer_signature():
    report = _report(signing={"form": "electronic", "confirmed": ["appraiser_qualified_signature"]})

    assert report["private_practice"] is True
    assert rf.check_report(report)["can_issue"] is True


def test_employer_signature_needed_with_an_employer():
    report = _report(
        private_practice=False,
        employer={"name": "ООО «Оценка»", "ogrn": "1000000000000", "address": "г. Казань"},
        signing={"form": "electronic", "confirmed": ["appraiser_qualified_signature"]},
    )

    assert any("руководителя" in item for item in rf.check_report(report)["missing"])
