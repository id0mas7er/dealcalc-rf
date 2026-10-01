import pytest

from dealcalc.rf import (
    comparative_approach,
    cost_approach,
    dcf_valuation,
    income_capitalization,
    reconcile_approaches,
)


def test_comparative_approach_preserves_adjustments_and_range():
    result = comparative_approach(
        50,
        [
            {"price": 10_000_000, "area_sqm": 50, "adjustment_pct": 5, "weight": 2},
            {"price": 9_000_000, "area_sqm": 45, "adjustment_pct": -5, "weight": 1},
        ],
    )

    assert result["currency"] == "RUB"
    assert result["sample_size"] == 2
    assert result["weighted_unit_price"] == pytest.approx(203_333.33, abs=0.01)
    # rounded unit price 203 333.33 × 50 m²
    assert result["indicated_value"] == 10_166_666.5
    assert result["indicated_value_range"] == {"low": 9_500_000.0, "high": 10_500_000.0}


def test_comparative_approach_requires_positive_subject_area():
    with pytest.raises(ValueError, match="subject_area_sqm"):
        comparative_approach(0, [{"price": 1, "area_sqm": 1}])


def test_income_capitalization():
    result = income_capitalization(1_200_000, 12)

    assert result["method"] == "direct_capitalization"
    assert result["indicated_value"] == 10_000_000.0


def test_dcf_valuation():
    result = dcf_valuation([1_000_000, 1_100_000], 10, terminal_value=500_000)

    assert result["present_value_cash_flows"] == pytest.approx(1_818_181.82, abs=0.01)
    assert result["terminal_present_value"] == pytest.approx(413_223.14, abs=0.01)
    assert result["indicated_value"] == pytest.approx(2_231_404.96, abs=0.01)


def test_cost_approach():
    result = cost_approach(
        replacement_cost=20_000_000,
        land_value=5_000_000,
        physical_depreciation_pct=10,
        functional_depreciation_pct=5,
        external_depreciation_pct=15,
    )

    # 1 - 0.90 * 0.95 * 0.85 = 27.325%
    assert result["depreciation"]["total_pct"] == pytest.approx(27.33, abs=0.01)
    assert result["depreciated_improvements"] == 14_535_000.0
    assert result["indicated_value"] == 19_535_000.0


def test_reconcile_approaches():
    result = reconcile_approaches(
        {"comparative": 10_000_000, "income": 9_000_000},
        {"comparative": 0.6, "income": 0.4},
    )

    assert result["reconciled_value"] == 9_600_000.0
    assert result["weights"] == {"comparative": 0.6, "income": 0.4}


def test_reconcile_rejects_mismatched_weights():
    with pytest.raises(ValueError, match="same approach names"):
        reconcile_approaches({"comparative": 1}, {"income": 1})


def test_cost_approach_rejects_negative_depreciation():
    with pytest.raises(ValueError, match="physical_depreciation_pct"):
        cost_approach(10_000_000, physical_depreciation_pct=-50)


def test_cost_approach_combines_depreciation_multiplicatively():
    result = cost_approach(100, 0, 40, 30, 30)

    assert result["depreciation"]["total_pct"] == 70.6
    assert result["depreciated_improvements"] == 29.4


def test_cost_approach_accepts_depreciation_summing_over_100():
    result = cost_approach(100, 0, 50, 40, 20)

    assert result["depreciation"]["total_pct"] == 76.0
    assert result["indicated_value"] == 24.0


def test_cost_approach_applies_entrepreneurial_profit_before_depreciation():
    result = cost_approach(
        replacement_cost=20_000_000,
        land_value=5_000_000,
        physical_depreciation_pct=10,
        entrepreneurial_profit_pct=15,
    )

    assert result["entrepreneurial_profit"] == 3_000_000.0
    assert result["replacement_cost_with_profit"] == 23_000_000.0
    assert result["depreciated_improvements"] == 20_700_000.0
    assert result["indicated_value"] == 25_700_000.0


def test_cost_approach_rejects_negative_entrepreneurial_profit():
    with pytest.raises(ValueError, match="entrepreneurial_profit_pct"):
        cost_approach(100, entrepreneurial_profit_pct=-5)


def test_reconcile_rejects_weights_not_summing_to_one():
    with pytest.raises(ValueError, match="sum to 1"):
        reconcile_approaches({"a": 100, "b": 200}, {"a": 0.6, "b": 0.3})


def test_reconcile_returns_weights_as_given():
    third = 1 / 3
    result = reconcile_approaches(
        {"a": 100, "b": 200, "c": 300}, {"a": third, "b": third, "c": third}
    )

    assert sum(result["weights"].values()) == pytest.approx(1)
    assert result["reconciled_value"] == 200.0


def test_reconcile_default_weights_are_equal():
    result = reconcile_approaches({"a": 100, "b": 200, "c": 300})

    assert sum(result["weights"].values()) == pytest.approx(1)
    assert result["reconciled_value"] == 200.0


def test_income_capitalization_rejects_negative_noi():
    with pytest.raises(ValueError, match="noi_annual"):
        income_capitalization(-1_000_000, 10)
