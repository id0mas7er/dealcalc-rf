import json

import pytest

from dealcalc.rf.data import (
    deduplicate_listings,
    load_listings,
    normalize_listing,
    parse_number,
)


def test_parse_number_supports_russian_price_format():
    assert parse_number("12 500 000 ₽", "price_rub") == 12_500_000.0
    assert parse_number("54,5", "area_sqm") == 54.5


def test_normalize_listing_maps_common_russian_fields():
    result = normalize_listing(
        {
            "Номер объявления": "abc-1",
            "Цена": "12 500 000 ₽",
            "Площадь м²": "54,5",
            "Город": "Казань",
            "Ссылка": "https://example.invalid/abc-1",
        },
        source="cian",
        collected_at="2026-10-01T00:00:00+00:00",
    )

    assert result == {
        "listing_type": "property",
        "source": "cian",
        "listing_id": "abc-1",
        "url": "https://example.invalid/abc-1",
        "collected_at": "2026-10-01T00:00:00+00:00",
        "region": "",
        "city": "Казань",
        "price_rub": 12_500_000.0,
        "area_sqm": 54.5,
        "rooms": None,
        "floor": None,
        "total_floors": None,
        "year": None,
        "condition": "",
        "brand": "",
        "model": "",
        "mileage_km": None,
        "engine_power_hp": None,
        "transmission": "",
        "drive": "",
    }


def test_load_json_deduplicates_by_source_and_listing_id(tmp_path):
    path = tmp_path / "cars.json"
    path.write_text(
        json.dumps(
            [
                {"id": "1", "price": "1 000 000", "brand": "Lada", "model": "Vesta"},
                {"id": "1", "price": "1 000 000", "brand": "Lada", "model": "Vesta"},
                {"id": "2", "price": "1 100 000", "brand": "Lada", "model": "Vesta"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = load_listings(str(path), source="drom", listing_type="vehicle", collected_at="2026-10-01")

    assert len(result) == 2
    assert result[0]["listing_type"] == "vehicle"
    assert result[0]["source"] == "drom"


def test_deduplicate_listings_keeps_first_record():
    listings = [
        {"source": "avito", "listing_id": "1", "price_rub": 10},
        {"source": "avito", "listing_id": "1", "price_rub": 11},
        {"source": "avito", "listing_id": "2", "price_rub": 12},
    ]

    assert deduplicate_listings(listings) == [listings[0], listings[2]]


def test_normalize_listing_requires_price():
    with pytest.raises(ValueError, match="price_rub"):
        normalize_listing({"id": "1"}, source="avito")


STEPS = [
    {"name": "Скидка на торг", "type": "pct", "value": -5},
    {"name": "Пробег", "type": "abs", "value": -20000},
]


def test_load_listings_keeps_adjustment_steps_from_json(tmp_path):
    path = tmp_path / "cars.json"
    path.write_text(
        json.dumps(
            [{"id": "1", "марка": "Lada", "модель": "Vesta", "цена": 1_000_000, "adjustments": STEPS}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    listing = load_listings(str(path), source="drom", listing_type="vehicle")[0]

    assert listing["adjustments"] == STEPS


def test_load_listings_parses_adjustment_steps_from_csv_column(tmp_path):
    path = tmp_path / "cars.csv"
    cell = json.dumps(STEPS, ensure_ascii=False).replace('"', '""')
    path.write_text(
        f'id;марка;модель;цена;корректировки\n1;Lada;Vesta;1000000;"{cell}"\n',
        encoding="utf-8",
    )

    listing = load_listings(str(path), source="avito", listing_type="vehicle")[0]

    assert listing["adjustments"] == STEPS


@pytest.mark.parametrize("value", ["not json", '{"name": "x"}', "[1, 2]"])
def test_normalize_listing_rejects_invalid_adjustments(value):
    with pytest.raises(ValueError, match="adjustments"):
        normalize_listing({"цена": 1, "корректировки": value}, source="avito")
