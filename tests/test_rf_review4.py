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
