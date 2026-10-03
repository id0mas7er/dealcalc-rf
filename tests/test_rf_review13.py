"""Codex review of 0.10.1 (03.10.2026): N1–N3 and R5."""

import pytest

from dealcalc import rf
from test_rf_report import CONTEXT, _report

META = {"source": "S", "date": "2026-10-01", "price_type": "transaction"}


def _first_step(step):
    result = rf.comparative_approach(1, [
        dict(META, price=100, area_sqm=1, adjustments=[step]),
        dict(META, price=100, area_sqm=1),
    ], context=CONTEXT)
    return result, result["comparables"][0]["adjustments"][0]


# N1: an adjustment of exactly 30 % is within the threshold despite float error.


@pytest.mark.parametrize("variant", [
    {"type": "pct", "value": 30},
    {"type": "pct", "value": -30},
    {"type": "coef", "value": 1.3},
    {"type": "coef", "value": 0.7},
])
def test_staged_exactly_30_pct_stops_at_first_stage(variant):
    result, step = _first_step({"name": "area", "type": "staged", "stages": [
        [dict(variant, label="mean")],
        [{"label": "fallback", "type": "pct", "value": 10}],
    ]})

    assert step["chosen"]["stage"] == 1
    assert step["selection"] == "within_threshold"
    assert result["checks"] == []


def test_staged_just_over_30_pct_goes_to_next_stage():
    _, step = _first_step({"name": "area", "type": "staged", "stages": [
        [{"label": "mean", "type": "coef", "value": 1.3001}],
        [{"label": "fallback", "type": "pct", "value": 10}],
    ]})

    assert step["chosen"]["stage"] == 2


@pytest.mark.parametrize("value, low, high", [(1.3, 1.1, 1.5), (0.7, 0.5, 0.9)])
def test_choice_exactly_30_pct_takes_the_mean(value, low, high):
    result, step = _first_step({"name": "coef", "type": "coef", "value": value,
                                "range": {"low": low, "high": high, "mean": value}})

    assert step["choice"]["rule"] == "mean"
    assert step["choice"]["follows_rule"] is True
    assert result["checks"] == []


def test_choice_just_over_30_pct_takes_minimal_adjustment():
    _, step = _first_step({"name": "coef", "type": "coef", "value": 1.1, "choice_rule": "minimal",
                           "range": {"low": 1.1, "high": 1.5, "mean": 1.3001}})

    assert step["choice"]["rule"] == "minimal_interval"
    assert step["choice"]["expected"] == 1.1


# N2: steps at the root of a result (the value of an interest) are reviewed too.


def _interest(**step):
    return rf.business_interest_value(1_000_000, 50, value_basis="equity", context=CONTEXT, adjustments=[
        dict({"name": "discount", "type": "pct", "value": -50, "range": {"low": -20, "high": -10}}, **step)
    ])


def test_interest_step_out_of_range_is_a_check():
    result = _interest()

    assert result["adjustments"][0]["within_range"] is False
    assert any("«discount»" in check and "вне границ" in check for check in result["checks"])


def test_interest_step_out_of_range_blocks_the_report():
    report = _report(final_value=250_000, value_interval={"low": 200_000, "high": 300_000, "justification": "t"})
    report["approaches"]["calculations"] = [_interest()]

    assert rf.check_report(report)["can_issue"] is False


def test_interest_step_with_justification_is_a_guardrail():
    result = _interest(justification="пакет без права блокирования")

    assert result["checks"] == []
    assert any("«discount»" in item and "обоснование" in item for item in result["guardrails"])


# N3: every evaluated variant of a cascade keeps its inputs and evidence.


@pytest.mark.parametrize("variant, inputs", [
    ({"type": "param", "subject": 80, "analog": 100, "exponent": -0.25},
     {"subject": 80, "analog": 100, "exponent": -0.25}),
    ({"type": "ratio", "subject": 1.1, "analog": 1.0}, {"subject": 1.1, "analog": 1.0}),
    ({"type": "pct", "value": 5}, {"value": 5}),
    ({"type": "coef", "value": 1.05}, {"value": 1.05}),
    ({"type": "abs", "value": 5}, {"value": 5}),
])
def test_staged_variant_keeps_inputs_and_evidence(variant, inputs):
    evidence = {"source": "Book", "page": "12", "date": "2026-01-01"}
    _, step = _first_step({"name": "area", "type": "staged", "stages": [
        [dict(variant, label="mean", **evidence)],
    ]})

    for item in (step["chosen"], step["variants"][0]):
        assert {key: item[key] for key in inputs} == inputs
        assert {key: item[key] for key in evidence} == evidence
        assert item["label"] == "mean" and item["stage"] == 1
        assert "factor" in item and "adjustment_pct" in item


# R5: an object that is not a calculation result is not counted as one.


@pytest.mark.parametrize("calculation", [
    {"context": CONTEXT},
    {"context": CONTEXT, "status": "черновой расчёт"},
    {"context": CONTEXT, "method_card": {"id": "X"}},
])
def test_object_without_method_card_or_status_is_missing(calculation):
    report = _report()
    report["approaches"]["calculations"] = [calculation]
    result = rf.check_report(report)

    assert result["can_issue"] is False
    assert any("approaches.calculations[0]" in item for item in result["missing"])
