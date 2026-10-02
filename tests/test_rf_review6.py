"""Fixes from the sixth external review."""

import pytest

from dealcalc import rf
from dealcalc.rf.data import parse_number

M = {"source": "S", "date": "2026-10-01", "price_type": "сделка"}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("120 тыс. км", 120_000.0),
        ("45,5 кв. м", 45.5),
        ("45,5 кв.м", 45.5),
        ("45,5 кв. м.", 45.5),
        ("45,5 м²", 45.5),
        ("150 л. с.", 150.0),
    ],
)
def test_mileage_and_area_units(text, expected):
    assert parse_number(text, "area_sqm") == expected


def test_characteristic_ids_give_a_reminder_not_a_check():
    listings = [
        rf.normalize_listing({"price": 100, "area": 1, "address": "A", **M}, "S"),
        rf.normalize_listing({"price": 110, "area": 1, "url": "https://x/2", **M}, "S"),
    ]
    result = rf.comparative_approach(1, [{**item, "price": item["price_rub"]} for item in listings])

    assert result["comparables"][0]["listing_id_basis"] == "characteristics"
    assert any("[1]" in note and "характеристикам" in note for note in result["guardrails"])
    assert not any("характеристикам" in check for check in result["checks"])
    assert result["status"] == "черновой расчёт"


def test_vehicle_characteristic_ids_reminder():
    listing = rf.normalize_listing({"price": 900_000, "brand": "Lada", **M}, "S", listing_type="vehicle")
    result = rf.vehicle_comparative_approach({"brand": "Lada"}, [listing])

    assert any("характеристикам" in note for note in result["guardrails"])
