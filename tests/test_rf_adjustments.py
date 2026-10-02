import datetime
import json

import pytest

from dealcalc.rf import comparative_approach, dcf_valuation, vehicle_comparative_approach

REAL_ESTATE_STEPS = [
    {"name": "Скидка на торг", "type": "pct", "value": -5},
    {"name": "Этаж", "type": "abs", "value": 3_000},
    {"name": "Ремонт", "type": "pct", "value": 10},
]


def test_real_estate_adjustments_are_applied_step_by_step():
    result = comparative_approach(
        50, [{"price": 10_000_000, "area_sqm": 50, "adjustments": REAL_ESTATE_STEPS}]
    )
    item = result["comparables"][0]

    assert [step["price_after"] for step in item["adjustments"]] == [
        190_000.0,
        193_000.0,
        212_300.0,
    ]
    assert item["adjustments"][0] == {
        "step": 1,
        "name": "Скидка на торг",
        "type": "pct",
        "value": -5.0,
        "price_before": 200_000.0,
        "price_after": 190_000.0,
        "change": -10_000.0,
    }
    assert item["adjusted_unit_price"] == 212_300.0
    assert item["net_adjustment_pct"] == 6.15
    assert item["gross_adjustment_pct"] == 16.15


def test_legacy_adjustment_pct_becomes_single_visible_step():
    result = comparative_approach(
        50, [{"price": 10_000_000, "area_sqm": 50, "adjustment_pct": 5}]
    )
    steps = result["comparables"][0]["adjustments"]

    assert len(steps) == 1
    assert steps[0]["name"] == "Общая корректировка"
    assert steps[0]["price_after"] == 210_000.0


def test_adjustment_pct_and_adjustments_together_are_rejected():
    with pytest.raises(ValueError, match="either adjustment_pct or adjustments"):
        comparative_approach(
            50,
            [{"price": 1, "area_sqm": 1, "adjustment_pct": 5, "adjustments": []}],
        )


@pytest.mark.parametrize(
    "step, message",
    [
        ({"type": "pct", "value": 1}, "name"),
        ({"name": "x", "type": "rub", "value": 1}, "type"),
        ({"name": "x", "type": "pct", "value": -100}, "greater than -100"),
        ({"name": "x", "type": "abs", "value": -300_000}, "greater than 0"),
    ],
)
def test_invalid_adjustment_steps_are_rejected(step, message):
    with pytest.raises(ValueError, match=message):
        comparative_approach(
            50, [{"price": 10_000_000, "area_sqm": 50, "adjustments": [step]}]
        )


def test_vehicle_adjustments_are_applied_step_by_step():
    result = vehicle_comparative_approach(
        {},
        [
            {
                "price_rub": 1_000_000,
                "adjustments": [
                    {"name": "Скидка на торг", "type": "pct", "value": -5},
                    {"name": "Пробег", "type": "abs", "value": -20_000},
                ],
            }
        ],
    )
    item = result["comparables"][0]

    assert [step["price_after"] for step in item["adjustments"]] == [950_000.0, 930_000.0]
    assert item["adjusted_price_rub"] == 930_000.0
    assert item["net_adjustment_pct"] == -7.0
    assert item["gross_adjustment_pct"] == 7.0
    assert result["indicated_value"] == 930_000.0


def test_coefficient_of_variation_flags_homogeneous_sample():
    result = comparative_approach(
        1,
        [
            {"price": 100, "area_sqm": 1},
            {"price": 120, "area_sqm": 1},
            {"price": 140, "area_sqm": 1},
        ],
    )

    assert result["variation"] == {
        "coefficient_pct": 16.67,
        "threshold_pct": 33.0,
        "within_threshold": True,
    }


def test_coefficient_of_variation_flags_heterogeneous_vehicle_sample():
    result = vehicle_comparative_approach(
        {}, [{"price_rub": 100}, {"price_rub": 300}]
    )

    assert result["variation"]["coefficient_pct"] == 70.71
    assert result["variation"]["within_threshold"] is False


def test_coefficient_of_variation_is_undefined_for_single_comparable():
    result = comparative_approach(1, [{"price": 100, "area_sqm": 1}])

    assert result["variation"]["coefficient_pct"] is None
    assert result["variation"]["within_threshold"] is None


def test_indicated_value_matches_rounded_unit_price_times_area():
    result = comparative_approach(
        10_000, [{"price": 1, "area_sqm": 3}, {"price": 2, "area_sqm": 3}]
    )

    assert result["indicated_value"] == pytest.approx(
        result["weighted_unit_price"] * 10_000
    )


def test_dcf_mid_year_discounting():
    result = dcf_valuation([1_000_000, 1_100_000], 10, terminal_value=500_000, mid_year=True)

    # 1 000 000 / 1.1^0.5 + 1 100 000 / 1.1^1.5; terminal value at the end of year 2
    assert result["discounting"] == "mid_year"
    assert result["present_value_cash_flows"] == pytest.approx(1_906_925.18, abs=0.01)
    assert result["terminal_present_value"] == pytest.approx(413_223.14, abs=0.01)


def test_dcf_end_of_year_is_default():
    assert dcf_valuation([1], 10)["discounting"] == "end_of_year"


def test_comparable_dates_are_json_serializable():
    result = comparative_approach(
        10,
        [{"price": 1, "area_sqm": 1, "source": "ЦИАН", "date": datetime.date(2026, 1, 1)}],
    )

    assert result["comparables"][0]["date"] == "2026-01-01"
    json.dumps(result)
