"""Ревью кода 08.10.2026 (разбор 30): регрессии."""

from __future__ import annotations

from pathlib import Path

import pytest

from dealcalc import rf
from test_rf_report import ASSIGNMENT, _report

CONTEXT = {"valuation_date": "2026-10-01", "value_type": "рыночная", "vat": "not_applicable"}


# --- H1: вид стоимости у ликвидационной стоимости бизнеса ----------------------

def test_business_liquidation_value_is_checked_against_value_type():
    result = rf.business_liquidation_value([{"period": 1, "sale_proceeds": 100}], 10, context=CONTEXT)

    assert result["value_kind"] == "ликвидационная стоимость"
    assert any("ликвидационная стоимость" in check for check in result["checks"])


# --- M1–M3, LOW: автомобили ---------------------------------------------------

def _car(model="Vesta", price=1_000_000, **extra):
    return {"brand": "Lada", "model": model, "price_rub": price, **extra}


def test_contains_match_is_listed_in_guardrails():
    result = rf.vehicle_comparative_approach(
        {"brand": "Lada", "model": "Vesta"}, [_car("Vesta SW Cross", 1_500_000), _car()], match="contains"
    )

    assert result["sample_size"] == 2
    assert any("[1]" in item and "match=contains" in item for item in result["guardrails"])


def test_exact_model_in_contains_mode_has_no_guardrail():
    result = rf.vehicle_comparative_approach({"brand": "Lada", "model": "Vesta"}, [_car()], match="contains")

    assert not any("match=contains" in item for item in result["guardrails"])


def test_foreign_listing_with_bad_price_is_rejected_not_an_error():
    result = rf.vehicle_comparative_approach(
        {"brand": "Lada", "model": "Vesta"},
        [{"brand": "Kia", "model": "Rio", "price_rub": 0}, _car(price=None), _car()],
    )

    assert result["rejected"] == [
        {"index": 1, "reason": "другая марка: Kia"},
        {"index": 2, "reason": "нет цены"},
    ]


def test_negative_mileage_and_implausible_year_are_rejected():
    result = rf.vehicle_comparative_approach(
        {"brand": "Lada", "model": "Vesta"},
        [_car(mileage_km=-5_000), _car(year=-2020), _car(year=2020, mileage_km=10_000)],
    )

    assert [item["index"] for item in result["rejected"]] == [1, 2]
    assert "отрицательный" in result["rejected"][0]["reason"]
    assert "недостоверный" in result["rejected"][1]["reason"]


@pytest.mark.parametrize("subject", [{"mileage_km": -1}, {"year": 1500}])
def test_invalid_subject_year_or_mileage_is_an_error(subject):
    with pytest.raises(ValueError, match="subject"):
        rf.vehicle_comparative_approach(subject, [_car()])


def test_year_limit_is_inclusive():
    result = rf.vehicle_comparative_approach(
        {"brand": "Lada", "model": "Vesta", "year": 2020, "mileage_km": 50_000},
        [_car(year=2018, mileage_km=60_000)],
        max_year_diff=2,
        max_mileage_diff=10_000,
    )

    assert result["sample_size"] == 1 and result["rejected"] == []


def test_brand_with_glued_submodel():
    result = rf.vehicle_comparative_approach({"brand": "Lada"}, [{"brand": "ВАЗ-2107", "price_rub": 100_000}])

    assert result["sample_size"] == 1


# --- M4: аналог с весом 0 ------------------------------------------------------

def test_zero_weight_vehicle_is_out_of_spread():
    discount = [{"name": "торг", "type": "pct", "value": -5}]
    result = rf.vehicle_comparative_approach(
        {"brand": "Lada", "model": "Vesta"},
        [_car(price=1_000_000, adjustments=discount), _car(price=2_000_000)],
        weighting="count_share",
    )

    assert result["comparables"][0]["weight"] == 0
    assert result["analogs_spread"] == {"low": 2_000_000, "high": 2_000_000}
    assert any("вес 0" in check for check in result["checks"])


def test_zero_weight_property_is_out_of_spread():
    discount = [{"name": "торг", "type": "pct", "value": -5}]
    result = rf.comparative_approach(
        10,
        [{"price": 1_000, "area_sqm": 10, "adjustments": discount}, {"price": 2_000, "area_sqm": 10}],
        weighting="count_share",
    )

    assert result["adjusted_unit_price_min"] == result["adjusted_unit_price_max"] == 200
    assert any("вес 0" in check for check in result["checks"])


# --- M5–M7: доходные расчёты ---------------------------------------------------

def test_irr_names_the_root_rule():
    result = rf.irr([-100, 450, -300])

    assert any("ближайший к нулю" in check for check in result["checks"])


@pytest.mark.parametrize("method", ["inwood", "hoskold"])
def test_very_long_life_has_no_overflow(method):
    result = rf.capital_recovery_rate(10, 10_000, method, safe_rate_pct=10)

    assert result["method"] == method


def test_negative_flow_and_rates_are_checks():
    assert rf.gordon_terminal_value(-100, 10, 3)["checks"]
    assert rf.gordon_terminal_value(100, -1, -3)["checks"]
    assert rf.npv([-1000, 300], -50)["checks"]
    assert rf.npv([-1000, 300], 10)["checks"] == []
    build_up = rf.discount_rate_build_up(2, [{"name": "p", "value": -5, "source": "x"}], risk_free_source="ОФЗ")
    assert any("не больше нуля" in check for check in build_up["checks"])
    income = rf.business_income_approach([100], 10, "equity", terminal_value=-50)
    assert any("Постпрогнозная" in check for check in income["checks"])


def test_lost_income_above_cost_is_a_check():
    result = rf.external_obsolescence_lost_income([100, 100], [0, 0], 10, cost_value=50)

    assert any("больше 100 %" in check for check in result["checks"])


# --- report.py, M9 -------------------------------------------------------------

def test_unknown_object_type_is_missing_not_a_crash():
    result = rf.check_report(_report(assignment={**ASSIGNMENT, "object_type": "art"}))

    assert any("object_type" in item for item in result["missing"])
    assert result["can_issue"] is False


def test_value_type_in_full_words_matches_the_calculation():
    result = rf.check_report(_report(assignment={**ASSIGNMENT, "value_type": "рыночная стоимость"}))

    assert result["checks"] == [] and result["can_issue"] is True


@pytest.mark.parametrize("field, value", [("engaged_specialists", "нет"), ("standards", 5), ("independence", True)])
def test_section_of_wrong_type_is_missing(field, value):
    result = rf.check_report(_report(**{field: value}))

    assert any(field in item for item in result["missing"])


def test_checks_count_whatever_the_status():
    report = _report()
    forged = dict(report["approaches"]["calculations"][0], checks=["что-то не так"])
    report["approaches"] = dict(report["approaches"], calculations=[forged])

    result = rf.check_report(report)

    assert any("что-то не так" in check for check in result["checks"])
    assert result["can_issue"] is False


# --- LOW: _meta, machinery, data ----------------------------------------------

def test_mixed_condition_ids_are_a_value_error():
    with pytest.raises(ValueError, match="unknown ids"):
        rf.external_obsolescence_lost_income([100], [50], 10, confirmed_conditions=["x", 5])


def test_input_percent_is_echoed_as_given():
    assert rf.new_equivalent_price(100, 33.333)["total_depreciation_pct"] == 33.333


def test_repeated_column_is_an_error(tmp_path: Path):
    path = tmp_path / "a.csv"
    path.write_text("Цена;Площадь;Цена\n100;10;200\n", encoding="utf-8")

    with pytest.raises(ValueError, match="повторяется"):
        rf.read_listings(str(path), source="file")


def test_one_group_price_is_flagged(tmp_path: Path):
    path = tmp_path / "a.csv"
    path.write_text('Цена;Площадь\n"12,345";10\n1 500 000;10\n', encoding="utf-8")

    listings = rf.read_listings(str(path), source="file")["listings"]

    assert listings[0]["price_rub"] == 12.345
    assert any("12,345" in item for item in listings[0]["import_warnings"])
    assert "import_warnings" not in listings[1]
