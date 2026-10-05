"""Fixes from review 25 (dealcalc-rf 0.12.3 → 0.13.2), group D."""

import json
import re

from dealcalc import rf
from dealcalc.rf import load_listings, normalize_listing

C = {"valuation_date": "2026-09-29", "value_type": "рыночная", "vat": "excluded"}
M = {"source": "S", "date": "2026-07-01", "price_type": "предложение"}


# D1. price_collected_at survives normalization and the file round trip.


def test_normalize_keeps_price_collected_at():
    row = normalize_listing(
        {"price": "10 000 000", "date": "2026-07-01", "price_collected_at": "2026-10-05"},
        source="S",
    )
    assert row["price_collected_at"] == "2026-10-05"
    row = normalize_listing(
        {"Цена": "10 000 000", "Дата": "2026-07-01", "Дата цены": "2026-10-05"},
        source="S",
    )
    assert row["price_collected_at"] == "2026-10-05"


def test_price_collected_at_survives_file_round_trip(tmp_path):
    path = tmp_path / "analogs.json"
    path.write_text(json.dumps([
        {**M, "price": 10e6, "area_sqm": 100, "price_collected_at": "2026-10-05"},
        {**M, "price": 10.5e6, "area_sqm": 100},
    ]), encoding="utf-8")
    listings = load_listings(str(path), source="S")
    assert listings[0]["price_collected_at"] == "2026-10-05"
    # круг «файл → расчёт»: проверка ФСО III, п. 12 снова работает
    result = rf.comparative_approach(100, listings, context=C)
    assert any("позже даты оценки" in check and "[1]" in check for check in result["checks"])


# D2. price_note reaches the calculation output.


def test_price_note_reaches_comparables():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "price_note": "цена «от»"},
         {**M, "price": 10.5e6, "area_sqm": 100}],
        context=C,
    )
    assert result["comparables"][0]["price_note"] == "цена «от»"


# D3. Package version matches the metadata.


def test_version_matches_pyproject():
    import dealcalc
    from pathlib import Path

    pyproject = (Path(dealcalc.__file__).parent.parent.parent / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    version = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert dealcalc.__version__ == version


# D5. price_collected_at / date_updated are validated for the date format.


def test_bad_price_collected_at_is_flagged():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "price_collected_at": "05/10/2026"},
         {**M, "price": 10.5e6, "area_sqm": 100, "date_updated": "5 октября"}],
        context=C,
    )
    assert any("не распознана" in check and "[1, 2]" in check for check in result["checks"])


# C1 (review 24). The listing title survives normalization so that callers can
# filter by keywords (e.g. the commercial-property kind).


def test_title_survives_normalization():
    row = normalize_listing(
        {"price": "10 000 000", "date": "2026-07-01", "title": "Офис, 150 м²"},
        source="S",
    )
    assert row["title"] == "Офис, 150 м²"
    row = normalize_listing(
        {"Цена": "10 000 000", "Дата": "2026-07-01", "Заголовок": "Склад, 300 м²"},
        source="S",
    )
    assert row["title"] == "Склад, 300 м²"
