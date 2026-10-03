"""Codex review of 0.12.0 (03.10.2026): the value result of each method in check_report."""

import pytest

from dealcalc import rf
from test_rf_report import CONTEXT, _report

META = {"source": "S", "date": "2026-09-01", "price_type": "transaction"}


def _check(calculation, value, kind="business"):
    report = _report(final_value=value)
    report.pop("value_interval", None)
    report["assignment"] = {**report["assignment"], "object_type": kind,
                            "value_type": calculation["context"]["value_type"]}
    report["approaches"]["calculations"] = [calculation]
    return rf.check_report(report)


INTEREST = rf.business_interest_value(1_000_000, 25, value_basis="equity", context=CONTEXT)


# R01: the input value of the whole business does not confirm the value of an interest.


def test_value_of_the_whole_business_is_not_the_value_of_an_interest():
    result = _check(INTEREST, 1_000_000)

    assert result["can_issue"] is False
    assert any("не совпадает" in check for check in result["checks"])


def test_value_of_the_interest_passes():
    assert _check(INTEREST, 250_000)["can_issue"] is True


def test_market_value_is_an_input_of_liquidation_value():
    liquidation = rf.asset_liquidation_value(
        1_000_000, 20, 6, 3, context={**CONTEXT, "value_type": "ликвидационная"}
    )

    assert _check(liquidation, 1_000_000, "machinery")["can_issue"] is False
    assert _check(liquidation, liquidation["liquidation_value"], "machinery")["can_issue"] is True


def test_calculation_of_an_unknown_method_is_not_a_value():
    report = _report()
    report["approaches"]["calculations"] = [rf.physical_depreciation(5, 20, context=CONTEXT)]
    result = rf.check_report(report)

    assert any("нет расчёта стоимости" in check for check in result["checks"])


# R02: both results of the qualitative method are values.


QUALITATIVE = rf.qualitative_adjustments([
    dict(META, price=100, adjustments=[{"name": "a", "direction": "up", "weight": 1}]),
    dict(META, price=200, adjustments=[{"name": "a", "direction": "up", "weight": 2}]),
    dict(META, price=300, adjustments=[{"name": "a", "direction": "down", "weight": 1}]),
], context=CONTEXT)


@pytest.mark.parametrize("key", ["weighted_value", "range_value"])
def test_qualitative_results_are_values(key):
    assert _check(QUALITATIVE, QUALITATIVE[key], "machinery")["can_issue"] is True


# R03: the final value must be a finite number.


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_final_value_blocks_the_report(value):
    result = _check(INTEREST, value)

    assert result["can_issue"] is False
    assert any("конечн" in check for check in result["checks"])
