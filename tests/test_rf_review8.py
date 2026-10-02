"""Fixes from review 8: a pct_group counts once; interval of value (ФСО №7, п. 30)."""

import pytest

from dealcalc import rf

M = {"source": "S", "date": "2026-10-01", "price_type": "сделка"}


def _inverse_count(steps):
    return rf.comparative_approach(
        1,
        [{**M, "price": 100, "area_sqm": 1, "adjustments": steps}, {**M, "price": 100, "area_sqm": 1}],
        weighting="inverse_count",
    )["indicated_value"]


def test_group_counts_as_one_adjustment():
    one = _inverse_count([{"name": "a", "type": "pct_group", "value": 20}])
    two = _inverse_count([{"name": "a", "type": "pct_group", "value": 10}, {"name": "b", "type": "pct_group", "value": 10}])

    assert one == two == 106.67


def test_group_and_separate_steps_are_counted_apart():
    steps = [
        {"name": "Торг", "type": "pct", "value": -5},
        {"name": "a", "type": "pct_group", "value": 10},
        {"name": "b", "type": "pct_group", "value": 5},
        {"name": "Парковка", "type": "abs", "value": 2},
    ]
    result = rf.comparative_approach(
        1, [{**M, "price": 100, "area_sqm": 1, "adjustments": steps}, {**M, "price": 100, "area_sqm": 1}],
        weighting="inverse_count",
    )

    # three adjustments: bargaining, one group, parking → weight 1/4 against 1/1
    assert result["comparables"][0]["weight_share"] == 0.2


def test_reconcile_keeps_appraiser_interval():
    result = rf.reconcile_approaches(
        {"a": 100, "b": 110}, {"a": 0.5, "b": 0.5},
        value_interval={"low": 95, "high": 115, "justification": "разброс аналогов и чувствительность ставки"},
    )

    assert result["value_interval"] == {
        "low": 95.0, "high": 115.0, "justification": "разброс аналогов и чувствительность ставки",
    }
    assert result["checks"] == []


def test_interval_must_contain_the_value():
    result = rf.reconcile_approaches(
        {"a": 100, "b": 110}, {"a": 0.5, "b": 0.5}, value_interval={"low": 106, "high": 120, "justification": "x"}
    )

    assert any("интервал" in check for check in result["checks"])


def test_interval_needs_justification_and_order():
    with pytest.raises(ValueError, match="justification"):
        rf.reconcile_approaches({"a": 100}, {"a": 1}, value_interval={"low": 90, "high": 110})
    with pytest.raises(ValueError, match="low"):
        rf.reconcile_approaches({"a": 100}, {"a": 1}, value_interval={"low": 120, "high": 110, "justification": "x"})


def test_reconcile_without_interval_reminds_fso7_p30():
    result = rf.reconcile_approaches({"a": 100, "b": 110}, {"a": 0.5, "b": 0.5})

    assert any("п. 30" in note for note in result["guardrails"])
