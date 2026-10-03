"""Reference-book data in calculations: table coefficients, source ranges, weights."""

import pytest

from dealcalc import rf


def _analog(steps, price=10_000_000, area=100, **extra):
    return {"price": price, "area_sqm": area, "adjustments": steps, **extra}


# Step types for reference-book tables.


def test_coef_step_multiplies_by_the_table_coefficient():
    result = rf.comparative_approach(100, [_analog([{"name": "Торг", "type": "coef", "value": 0.94}])])
    step = result["comparables"][0]["adjustments"][0]

    assert result["weighted_unit_price"] == 94_000
    assert step["value"] == 0.94
    assert step["change"] == -6_000


def test_coef_must_be_positive():
    with pytest.raises(ValueError, match="value must be greater than 0"):
        rf.comparative_approach(100, [_analog([{"name": "Торг", "type": "coef", "value": 0}])])


def test_ratio_step_divides_subject_by_analog_coefficient():
    steps = [{"name": "Этаж", "type": "ratio", "subject": 0.99, "analog": 0.94}]
    step = rf.comparative_approach(100, [_analog(steps)])["comparables"][0]["adjustments"][0]

    assert step["factor"] == round(0.99 / 0.94, 4)
    assert step["price_after"] == round(100_000 * 0.99 / 0.94, 2)


def test_ratio_needs_positive_coefficients():
    with pytest.raises(ValueError, match="analog must be greater than 0"):
        rf.comparative_approach(100, [_analog([{"name": "Этаж", "type": "ratio", "subject": 1, "analog": 0}])])


def test_page_travels_with_the_step():
    steps = [{"name": "Торг", "type": "coef", "value": 0.94, "source": "СтатРиелт", "date": "2026-07-01", "page": "табл. 1"}]
    step = rf.comparative_approach(100, [_analog(steps)])["comparables"][0]["adjustments"][0]

    assert (step["source"], step["date"], step["page"]) == ("СтатРиелт", "2026-07-01", "табл. 1")


# Bounds given by the source.


def _range_result(value, **extra):
    step = {"name": "Торг", "type": "coef", "value": value, "range": {"low": 0.93, "high": 0.96}, **extra}
    return rf.comparative_approach(100, [_analog([step])])


def test_value_within_the_source_range():
    result = _range_result(0.94)
    step = result["comparables"][0]["adjustments"][0]

    assert step["range"] == {"low": 0.93, "high": 0.96}
    assert step["within_range"] is True
    assert not any("границ" in check for check in result["checks"])


def test_value_outside_the_source_range_is_a_check():
    result = _range_result(0.90)

    assert result["comparables"][0]["adjustments"][0]["within_range"] is False
    assert any("Торг" in check and "границ" in check for check in result["checks"])
    assert result["status"] == "нужна проверка оценщика"


def test_justified_value_outside_the_range_is_a_reminder():
    result = _range_result(0.90, justification="объект требует ремонта")

    assert not any("границ" in check for check in result["checks"])
    assert any("границ" in item for item in result["guardrails"])


def test_range_applies_to_percent_steps():
    step = {"name": "Торг", "type": "pct", "value": -10, "range": {"low": -7, "high": -4}}
    result = rf.comparative_approach(100, [_analog([step])])

    assert any("границ" in check for check in result["checks"])


def test_range_must_be_ordered():
    with pytest.raises(ValueError, match="range"):
        _range_result(0.94, range={"low": 0.96, "high": 0.93})


def test_range_is_not_supported_for_ratio():
    step = {"name": "Этаж", "type": "ratio", "subject": 1, "analog": 1, "range": {"low": 0.9, "high": 1.1}}

    with pytest.raises(ValueError, match="range"):
        rf.comparative_approach(100, [_analog([step])])


def test_source_range_of_a_rate():
    result = rf.income_capitalization(
        1_000_000, 15, source_ranges={"cap_rate_pct": {"low": 7, "high": 13, "source": "СтатРиелт"}}
    )

    assert result["source_ranges"]["cap_rate_pct"]["within_range"] is False
    assert any("cap_rate_pct" in check for check in result["checks"])


def test_source_range_of_a_rate_within_bounds():
    result = rf.income_capitalization(1_000_000, 10, source_ranges={"cap_rate_pct": {"low": 7, "high": 13}})

    assert result["source_ranges"]["cap_rate_pct"]["within_range"] is True
    assert result["checks"] == []


def test_justified_source_range_is_a_reminder():
    result = rf.income_capitalization(
        1_000_000, 15, source_ranges={"cap_rate_pct": {"low": 7, "high": 13, "justification": "промзона"}}
    )

    assert result["checks"] == []
    assert any("cap_rate_pct" in item for item in result["guardrails"])


def test_source_range_of_exposure_period():
    result = rf.asset_liquidation_value(
        10_000_000, 12, 9, 3, source_ranges={"typical_exposure_months": {"low": 3, "high": 6}}
    )

    assert any("typical_exposure_months" in check for check in result["checks"])


def test_source_range_of_an_unknown_parameter():
    with pytest.raises(ValueError, match="source_ranges"):
        rf.income_capitalization(1_000_000, 10, source_ranges={"rate": {"low": 7, "high": 13}})


def test_source_range_of_a_non_numeric_parameter():
    with pytest.raises(ValueError, match="source_ranges"):
        rf.income_capitalization(1_000_000, 10, source_ranges={"currency": {"low": 7, "high": 13}})


# Weights of analogs (methods 1 and 2).


def _three(kind_values):
    return [_analog(steps) for steps in kind_values]


def test_count_share_weights():
    analogs = _three([
        [{"name": "a", "type": "pct", "value": 5}],
        [{"name": "a", "type": "pct", "value": 5}, {"name": "b", "type": "pct", "value": 5}],
        [{"name": "a", "type": "pct", "value": 5}, {"name": "b", "type": "pct", "value": 5}, {"name": "c", "type": "pct", "value": 5}],
    ])
    result = rf.comparative_approach(100, analogs, weighting="count_share")

    # K = (S - M) / ((N - 1) * S): S = 6, N = 3.
    assert [item["weight_share"] for item in result["comparables"]] == [0.4167, 0.3333, 0.25]
    assert "(S − M_i)" in result["weighting_formula"]


def test_count_share_without_adjustments_gives_equal_weights():
    result = rf.comparative_approach(100, _three([[], [], []]), weighting="count_share")

    assert [item["weight_share"] for item in result["comparables"]] == [0.3333, 0.3333, 0.3333]


def test_count_share_single_analog():
    result = rf.comparative_approach(100, [_analog([{"name": "a", "type": "pct", "value": 5}])], weighting="count_share")

    assert result["comparables"][0]["weight_share"] == 1


def test_gross_share_weights():
    analogs = _three([
        [{"name": "a", "type": "pct", "value": 10}],
        [{"name": "a", "type": "pct", "value": -20}],
        [{"name": "a", "type": "pct", "value": 30}],
    ])
    result = rf.comparative_approach(100, analogs, weighting="gross_share")

    # K ∝ 1 − S_i / Σ(S_j + 1): S = 10, 20, 30 %.
    assert [item["weight_share"] for item in result["comparables"]] == [
        round(53 / 129, 4), round(43 / 129, 4), round(33 / 129, 4)
    ]


def test_sample_weighting_rejects_manual_weights():
    analogs = [_analog([], weight=2), _analog([])]

    with pytest.raises(ValueError, match="weighting='manual'"):
        rf.comparative_approach(100, analogs, weighting="gross_share")


def test_sample_weightings_are_reminded_as_heuristics():
    result = rf.comparative_approach(100, _three([[], [], []]), weighting="count_share")

    assert any("эвристика" in item for item in result["guardrails"])


def test_vehicle_count_share():
    analogs = [
        {"price_rub": 1_000_000, "brand": "Kia", "model": "Rio", "adjustments": [{"name": "a", "type": "coef", "value": 0.95}]},
        {"price_rub": 1_100_000, "brand": "Kia", "model": "Rio"},
    ]
    result = rf.vehicle_comparative_approach({"brand": "Kia", "model": "Rio"}, analogs, weighting="count_share")

    assert [item["weight_share"] for item in result["comparables"]] == [0, 1]


def test_mcp_tools_accept_source_ranges():
    server = pytest.importorskip("mcp_server.server", exc_type=ImportError)
    result = server.rf_income_capitalization(1_000_000, 15, source_ranges={"cap_rate_pct": {"low": 7, "high": 13}})

    assert result["source_ranges"]["cap_rate_pct"]["within_range"] is False
