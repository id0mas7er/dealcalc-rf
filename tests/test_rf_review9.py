"""Review 9 (06.10.2026): import keeps rows with warnings, nothing is lost silently."""

from __future__ import annotations

from pathlib import Path

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2026-10-01", "value_type": "рыночная", "vat": "included", "vat_rate_pct": 20}


def _csv(tmp_path: Path, text: str) -> str:
    path = tmp_path / "listings.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


# --- import ------------------------------------------------------------------

def test_floor_written_as_floor_of_total_floors():
    listing = rf.normalize_listing({"price": "10 000 000", "area": 50, "этаж": "3/9"}, "ЦИАН")
    assert (listing["floor"], listing["total_floors"]) == (3, 9)
    assert "import_warnings" not in listing


def test_unreadable_optional_number_is_a_warning_not_an_error():
    listing = rf.normalize_listing({"price": 10_000_000, "area": 50, "комнат": "две"}, "ЦИАН")
    assert listing["rooms"] is None
    assert any("rooms" in warning for warning in listing["import_warnings"])


def test_price_is_still_required():
    with pytest.raises(ValueError, match="price"):
        rf.normalize_listing({"price": "договорная", "area": 50}, "ЦИАН")


def test_load_listings_reads_floor_3_of_9(tmp_path):
    path = _csv(tmp_path, "цена,площадь,этаж\n10000000,50,3/9\n")
    assert rf.load_listings(path, "ЦИАН")[0]["floor"] == 3  # было: падал весь файл


@pytest.mark.parametrize("column", ["Дата", "Дата сделки", "Дата продажи", "Дата предложения"])
def test_date_columns(tmp_path, column):
    path = _csv(tmp_path, f"цена,площадь,{column}\n10000000,50,2026-09-01\n")
    assert rf.load_listings(path, "ЦИАН")[0]["date"] == "2026-09-01"


def test_read_listings_reports_skipped_rows_and_duplicates(tmp_path):
    path = _csv(
        tmp_path,
        "цена,площадь,ссылка\n"
        "10000000,50,https://x.test/1\n"
        "договорная,45,https://x.test/2\n"
        "10000000,50,https://x.test/1\n"
        "9000000,48,https://x.test/3\n",
    )
    result = rf.read_listings(path, "ЦИАН")
    assert result["count"] == 2
    assert [item["row"] for item in result["skipped"]] == ["line 3"]
    assert "price" in result["skipped"][0]["reason"]
    assert result["removed_duplicates"] == [{"row": "line 4", "listing_id": result["listings"][0]["listing_id"],
                                             "duplicate_of": "line 2"}]


# --- result ------------------------------------------------------------------

def _analogs(**fields):
    return [
        {"price_rub": 10_000_000 + i, "area_sqm": 50, "source": "S", "date": "2026-09-01",
         "price_type": "предложение", **{k: (v[i] if isinstance(v, list) else v) for k, v in fields.items()}}
        for i in range(3)
    ]


def test_comparables_carry_the_characteristics():
    result = rf.comparative_approach(
        50, _analogs(floor=3, total_floors=9, rooms=2, city="Москва", title="2-комн. квартира", condition="ремонт"),
        context=CONTEXT,
    )
    item = result["comparables"][0]
    assert (item["floor"], item["total_floors"], item["rooms"]) == (3, 9, 2)
    assert (item["city"], item["title"], item["condition"]) == ("Москва", "2-комн. квартира", "ремонт")


def test_analog_older_than_five_years_is_a_reminder():
    result = rf.comparative_approach(50, _analogs(date=["2021-09-01", "2026-09-01", "2026-09-02"]), context=CONTEXT)
    old = [text for text in result["guardrails"] if "5 лет" in text]
    assert old and "[1]" in old[0]
    assert not any("5 лет" in text for text in result["checks"])  # напоминание, не дефект данных


def test_three_years_is_not_old():
    result = rf.comparative_approach(50, _analogs(date="2023-10-02"), context=CONTEXT)
    assert not any("5 лет" in text for text in result["guardrails"])


def test_different_cities_are_a_reminder():
    result = rf.comparative_approach(50, _analogs(city=["Москва", "Москва", "Химки"]), context=CONTEXT)
    assert any("разных городов" in text and "Химки" in text for text in result["guardrails"])


def test_unknown_context_field_lists_the_allowed_ones():
    with pytest.raises(ValueError, match="valuation_date"):
        rf.comparative_approach(50, _analogs(), context={**CONTEXT, "currency": "RUB"})


# --- vehicles ----------------------------------------------------------------

def test_rejected_vehicles_are_named_with_reasons():
    base = {"price_type": "предложение", "source": "Drom", "date": "2026-09-01"}
    analogs = [
        {**base, "brand": "Kia", "model": "Rio", "price_rub": 1_000_000, "year": 2021, "mileage_km": 50_000},
        {**base, "brand": "", "model": "Rio", "price_rub": 1_100_000, "year": 2021, "mileage_km": 50_000},
        {**base, "brand": "Kia", "model": "Ceed", "price_rub": 1_200_000, "year": 2021, "mileage_km": 50_000},
        {**base, "brand": "Kia", "model": "Rio", "price_rub": 900_000, "year": 2012, "mileage_km": 50_000},
        {**base, "brand": "Kia", "model": "Rio", "price_rub": 950_000, "year": 2021, "mileage_km": 190_000},
    ]
    result = rf.vehicle_comparative_approach(
        {"brand": "Kia", "model": "Rio", "year": 2021, "mileage_km": 50_000}, analogs,
        max_year_diff=3, max_mileage_diff=40_000, context=CONTEXT,
    )
    reasons = {item["index"]: item["reason"] for item in result["rejected"]}
    assert set(reasons) == {2, 3, 4, 5}
    assert "марк" in reasons[2] and "модел" in reasons[3]
    assert "год" in reasons[4] and "пробег" in reasons[5]
    assert result["rejected_count"] == 4
