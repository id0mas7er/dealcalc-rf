"""Methodology added in 0.3.0: grouped corrections, analog weighting, rate
build-up and capital recovery, reversion, indexed costs, vehicle matching."""

import pytest

from dealcalc.rf import (
    capital_recovery_rate,
    comparative_approach,
    cost_approach,
    discount_rate_build_up,
    indexed_replacement_cost,
    reversion_value,
    vehicle_comparative_approach,
)


def test_grouped_corrections_are_summed_and_applied_once():
    result = comparative_approach(
        1,
        [
            {
                "price": 100_000,
                "area_sqm": 1,
                "adjustments": [
                    {"name": "Торг", "type": "pct", "value": -10},
                    {"name": "Этаж", "type": "pct_group", "value": 5},
                    {"name": "Ремонт", "type": "pct_group", "value": -3},
                    {"name": "Парковка", "type": "abs", "value": 1_000},
                ],
            }
        ],
    )
    steps = result["comparables"][0]["adjustments"]

    # after bargaining 90 000; group +5 −3 = +2% of 90 000 once: 91 800; then +1 000
    assert [step["price_after"] for step in steps] == [90_000.0, 94_500.0, 91_800.0, 92_800.0]
    assert steps[2]["group_base"] == 90_000.0
    assert steps[2]["group_total_pct"] == 2.0


def test_weighting_inverse_gross():
    comparables = [
        {"price": 100, "area_sqm": 1, "adjustments": [{"name": "a", "type": "pct", "value": 10}]},
        {"price": 100, "area_sqm": 1, "adjustments": [{"name": "a", "type": "pct", "value": 30}]},
    ]

    result = comparative_approach(1, comparables, weighting="inverse_gross")

    # w ∝ 1/1.1 and 1/1.3 -> shares 0.5417 and 0.4583
    assert [item["weight_share"] for item in result["comparables"]] == [0.5417, 0.4583]
    assert result["weighted_unit_price"] == pytest.approx(110 * 0.541667 + 130 * 0.458333, abs=0.01)
    assert result["weighting"] == "inverse_gross"


def test_weighting_inverse_count():
    comparables = [
        {"price": 100, "area_sqm": 1, "adjustments": [{"name": "a", "type": "pct", "value": 1}]},
        {"price": 100, "area_sqm": 1},
    ]

    result = comparative_approach(1, comparables, weighting="inverse_count")

    # w ∝ 1/2 and 1/1 -> shares 1/3 and 2/3
    assert [item["weight_share"] for item in result["comparables"]] == [0.3333, 0.6667]


def test_weighting_rejects_manual_weight_with_automatic_rule():
    with pytest.raises(ValueError, match="weighting='manual'"):
        comparative_approach(1, [{"price": 100, "area_sqm": 1, "weight": 2}], weighting="inverse_gross")


@pytest.mark.parametrize(
    "subject, comparable",
    [
        ({"brand": "Lada", "model": "Vesta"}, {"brand": "ВАЗ (Lada)", "model": "Веста"}),
        ({"brand": "Лада", "model": "VESTA"}, {"brand": "LADA", "model": "vesta"}),
        ({"brand": "Хендай", "model": "Крета"}, {"brand": "Hyundai", "model": "Kreta"}),
    ],
)
def test_vehicle_brand_synonyms_and_transliteration(subject, comparable):
    result = vehicle_comparative_approach(subject, [{**comparable, "price_rub": 1_000_000}])

    assert result["sample_size"] == 1


def test_vehicle_contains_match():
    comparables = [
        {"brand": "Lada", "model": "Vesta SW Cross", "price_rub": 1_200_000},
        {"brand": "Lada", "model": "Granta", "price_rub": 800_000},
    ]

    with pytest.raises(ValueError, match="no comparable"):
        vehicle_comparative_approach({"brand": "Lada", "model": "Vesta"}, comparables)
    result = vehicle_comparative_approach({"brand": "Lada", "model": "Vesta"}, comparables, match="contains")

    assert result["sample_size"] == 1
    assert result["selection"]["match"] == "contains"


def test_vehicle_model_synonyms_cover_irregular_transliteration():
    comparables = [{"brand": "Kia", "model": "Ceed", "price_rub": 1_000_000}]

    with pytest.raises(ValueError, match="no comparable"):
        vehicle_comparative_approach({"brand": "Киа", "model": "Сид"}, comparables)
    result = vehicle_comparative_approach(
        {"brand": "Киа", "model": "Сид"}, comparables, synonyms={"ceed": ["сид"]}
    )

    assert result["sample_size"] == 1


def test_vehicle_custom_synonyms():
    result = vehicle_comparative_approach(
        {"brand": "Соллерс"},
        [{"brand": "Sollers", "price_rub": 2_000_000}],
        synonyms={"sollers": ["соллерс", "sollers"]},
    )

    assert result["sample_size"] == 1


def test_discount_rate_build_up():
    result = discount_rate_build_up(
        14.5,
        [{"name": "Риск вложения", "value": 2, "source": "анализ рынка"}, {"name": "Низкая ликвидность", "value": 1.5}],
        risk_free_source="ОФЗ 26240, доходность на 2026-10-01",
    )

    assert result["discount_rate_pct"] == 18.0
    assert any("Низкая ликвидность" in check for check in result["checks"])


@pytest.mark.parametrize(
    "method, safe, expected",
    [("ring", None, 17.0), ("inwood", None, 13.3879), ("hoskold", 8, 14.1852)],
)
def test_capital_recovery_rate(method, safe, expected):
    result = capital_recovery_rate(12, 20, method, safe_rate_pct=safe)

    assert result["capitalization_rate_pct"] == pytest.approx(expected, abs=0.0001)


def test_hoskold_requires_safe_rate():
    with pytest.raises(ValueError, match="safe_rate_pct"):
        capital_recovery_rate(12, 20, "hoskold")


def test_reversion_value():
    result = reversion_value(1_100_000, 11, selling_costs_pct=3)

    assert result["gross_reversion"] == 10_000_000.0
    assert result["reversion_value"] == 9_700_000.0


def test_indexed_replacement_cost_shows_every_step():
    result = indexed_replacement_cost(
        10_000,
        [
            {"name": "1969 → 1984", "value": 1.18, "source": "Письмо Госстроя № 14-Д"},
            {"name": "1984 → дата оценки", "value": 150, "source": "КО-ИНВЕСТ"},
        ],
        regional_coefficient=0.95,
        vat_pct=20,
        base_label="УПВС 1969, сб. 28",
    )

    assert [step["cost_after"] for step in result["steps"]] == [11_800.0, 1_770_000.0, 1_681_500.0, 2_017_800.0]
    assert result["replacement_cost"] == 2_017_800.0
    assert result["checks"] == []


def test_cost_approach_profit_base_land_and_improvements():
    improvements_only = cost_approach(1_000_000, land_value=500_000, entrepreneurial_profit_pct=10)
    with_land = cost_approach(
        1_000_000, land_value=500_000, entrepreneurial_profit_pct=10, profit_base="land_and_improvements"
    )

    assert improvements_only["entrepreneurial_profit"] == 100_000.0
    assert with_land["entrepreneurial_profit"] == 150_000.0
    assert with_land["indicated_value"] == 1_650_000.0
