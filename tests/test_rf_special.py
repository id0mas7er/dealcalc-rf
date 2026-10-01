"""Special methods from the Expert Council recommendations."""

import pytest

from dealcalc.rf import (
    cellular_site_rent,
    external_obsolescence_cost_income,
    external_obsolescence_lost_income,
    external_obsolescence_paired_sales,
    fund_unit_value,
    market_rent_cost_plus,
    net_operating_income,
)

EXPENSES = [
    {"name": "Налог на имущество", "type": "abs", "value": 330_000},
    {"name": "Управление", "type": "pct", "value": 3},
]


def test_market_rent_cost_plus():
    result = market_rent_cost_plus(
        20_000_000, 10, EXPENSES, vacancy_pct=8, collection_loss_pct=2, rentable_area_sqm=120
    )

    assert result["required_noi"] == 2_000_000.0
    assert result["effective_gross_income"] == pytest.approx(2_402_061.86, abs=0.01)
    assert result["gross_rent_year"] == pytest.approx(2_664_221.22, abs=0.01)
    assert result["rent_sqm_month"] == pytest.approx(2_664_221.22 / 120 / 12, abs=0.01)
    assert result["owner_expenses"][1]["amount"] == pytest.approx(72_061.86, abs=0.01)
    assert result["method_card"]["formula_status"].startswith("частная методическая")


def test_market_rent_cost_plus_is_inverse_of_noi_build_up():
    rent = market_rent_cost_plus(20_000_000, 10, EXPENSES, vacancy_pct=8, collection_loss_pct=2)

    noi = net_operating_income(
        potential_gross_income=rent["gross_rent_year"],
        vacancy_pct=8,
        collection_loss_pct=2,
        operating_expenses=EXPENSES,
    )

    assert noi["net_operating_income"] == pytest.approx(2_000_000, abs=0.05)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"cap_rate_pct": 0}, "cap_rate_pct"),
        ({"vacancy_pct": 100}, "vacancy_pct"),
        ({"owner_expenses": [{"name": "x", "type": "pct", "value": 100}]}, "less than 100"),
        ({"owner_expenses": [{"name": "x", "type": "rub", "value": 1}]}, "type"),
    ],
)
def test_market_rent_cost_plus_rejects_invalid_input(kwargs, message):
    params = {"property_value": 1_000_000, "cap_rate_pct": 10, **kwargs}
    with pytest.raises(ValueError, match=message):
        market_rent_cost_plus(**params)


def test_cellular_site_rent():
    result = cellular_site_rent(3_000_000, 25, 12, owner_costs_annual=10_000, collection_loss_pct=5)

    assert result["allocated_value_kit"] == 750_000.0
    assert result["base_noi"] == 90_000.0
    assert result["gross_rent_year"] == pytest.approx(105_263.16, abs=0.01)


def test_external_obsolescence_cost_income():
    result = external_obsolescence_cost_income(1_000_000, 800_000)

    assert result["external_obsolescence"] == 200_000.0
    assert result["external_obsolescence_pct"] == 20.0
    assert result["status"] == "черновой расчёт"


def test_external_obsolescence_negative_is_not_forced():
    result = external_obsolescence_cost_income(1_000_000, 1_100_000)

    assert result["external_obsolescence"] == -100_000.0
    assert "не навязывайте" in result["checks"][0]


def test_external_obsolescence_paired_sales():
    result = external_obsolescence_paired_sales(500, 400, 1_000_000)

    assert result["obsolescence_ratio_pct"] == 20.0
    assert result["external_obsolescence"] == 200_000.0


def test_external_obsolescence_lost_income():
    result = external_obsolescence_lost_income([100, 100], [80, 80], 10, cost_value=200)

    assert result["present_value_loss"] == pytest.approx(34.71, abs=0.01)
    assert result["external_obsolescence_pct"] == pytest.approx(17.36, abs=0.01)


def test_external_obsolescence_lost_income_requires_equal_lengths():
    with pytest.raises(ValueError, match="same length"):
        external_obsolescence_lost_income([100, 100], [80], 10)


def test_fund_unit_value():
    result = fund_unit_value([10, 10], 100, 10, termination_costs=5)

    assert result["present_value_distributions"] == pytest.approx(17.36, abs=0.01)
    assert result["present_value_final"] == pytest.approx(78.51, abs=0.01)
    assert result["unit_value"] == pytest.approx(95.87, abs=0.01)


def test_fund_unit_value_without_distributions_needs_final_period():
    with pytest.raises(ValueError, match="final_period"):
        fund_unit_value([], 100, 10)

    assert fund_unit_value([], 121, 10, final_period=2)["unit_value"] == 100.0
