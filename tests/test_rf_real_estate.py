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
    assert result["indicated_value"] == pytest.approx(10_166_666.67, abs=0.01)
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

    assert result["depreciation"]["total_pct"] == 30.0
    assert result["depreciated_improvements"] == 14_000_000.0
    assert result["indicated_value"] == 19_000_000.0


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
