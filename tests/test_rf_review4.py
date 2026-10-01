"""Fixes from the fourth external review."""

from dealcalc.rf import comparative_approach, normalize_listing, reconcile_approaches, vehicle_comparative_approach


def test_reconcile_reports_rounded_weight_shares_next_to_weights():
    third = 1 / 3
    result = reconcile_approaches({"a": 100, "b": 101, "c": 102}, {"a": third, "b": third, "c": third}, 10)

    assert result["weights"]["a"] == third
    assert result["weight_shares"] == {"a": 0.3333, "b": 0.3333, "c": 0.3333}


def test_import_warnings_reach_checks_of_the_calculation():
    listing = normalize_listing(
        {"Цена": "1 000 000", "Площадь": "40", "Тип цены": "Продажа"}, source="avito"
    )
    result = comparative_approach(40, [{**listing, "price": listing["price_rub"]}])

    assert result["comparables"][0]["import_warnings"] == listing["import_warnings"]
    assert any("Аналог 1" in check and "Продажа" in check for check in result["checks"])


def test_import_warnings_reach_vehicle_checks():
    listing = normalize_listing(
        {"Цена": "900 000", "Марка": "Lada", "Тип цены": "Аренда"}, source="avito", listing_type="vehicle"
    )
    result = vehicle_comparative_approach({"brand": "Lada"}, [listing])

    assert any("Аренда" in check for check in result["checks"])


# Codex review of 0.3.1–0.3.2.


def test_reimport_keeps_import_warnings_and_unknown_price_type():
    from dealcalc.rf import comparative_approach as approach

    first = normalize_listing({"price": 1_000, "area_sqm": 10, "price_type": "sale"}, source="avito")
    again = normalize_listing(first, source="avito")

    assert again["price_type"] == ""
    assert again["import_warnings"] == first["import_warnings"]
    result = approach(10, [{**again, "price": again["price_rub"]}])
    assert any("sale" in check for check in result["checks"])


def test_value_growth_of_100_pct_or_more_is_allowed():
    from dealcalc.rf import capital_recovery_rate

    result = capital_recovery_rate(20, 10, "ring", value_change_pct=-100)

    assert result["capitalization_rate_pct"] == 10


def test_dcf_rejects_terminal_value_not_in_the_future():
    import pytest

    from dealcalc.rf import dcf_valuation

    with pytest.raises(ValueError, match="terminal"):
        dcf_valuation([0], 10, terminal_value=100, first_cash_flow_period=0, terminal_timing="mid")


def test_qualitative_adjustments_returns_value_with_context_reminder():
    from dealcalc.rf import qualitative_adjustments

    result = qualitative_adjustments(
        [
            {"price": 100, "adjustments": [{"name": "Состояние", "direction": "up"}]},
            {"price": 120, "adjustments": [{"name": "Пробег", "direction": "down"}]},
        ]
    )

    assert any("context" in note for note in result["guardrails"])
