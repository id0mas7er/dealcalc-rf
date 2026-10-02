"""Import of analogs: Excel, ready-to-use fields, rent, income, business, machinery."""

from datetime import datetime

import pytest

from dealcalc import rf


def _csv(tmp_path, text, name="analogs.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


# Excel.


def _xlsx(tmp_path, rows, sheet="Аналоги"):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.active.title = "Титул"
    workbook.active["A1"] = "Отчёт"
    sheet_obj = workbook.create_sheet(sheet)
    for row in rows:
        sheet_obj.append(row)
    path = tmp_path / "analogs.xlsx"
    workbook.save(path)
    return str(path)


def test_load_xlsx_sheet_with_dates(tmp_path):
    path = _xlsx(tmp_path, [
        [None],
        ["Цена", "Площадь", "Дата публикации", "Ссылка"],
        [9_800_000, 52, datetime(2026, 9, 20), "https://x/1"],
        ["10 400 000 ₽", "56", "25.09.2026", "https://x/2"],
    ])
    listings = rf.load_listings(path, source="ЦИАН", sheet="Аналоги")

    assert [item["price_rub"] for item in listings] == [9_800_000, 10_400_000]
    assert listings[0]["date"] == "2026-09-20"


def test_xlsx_errors_name_the_sheet_row(tmp_path):
    path = _xlsx(tmp_path, [["Цена", "Площадь"], [100, 1], [0, 1]])

    with pytest.raises(ValueError, match="row 3"):
        rf.load_listings(path, source="S", sheet="Аналоги")


def test_xlsx_unknown_sheet(tmp_path):
    path = _xlsx(tmp_path, [["Цена"], [100]])

    with pytest.raises(ValueError, match="sheet"):
        rf.load_listings(path, source="S", sheet="Нет такого")


# Imported analogs go straight into the calculations.


def test_property_listings_go_straight_into_comparative_approach(tmp_path):
    path = _csv(tmp_path, "Цена;Площадь;Дата публикации\n9 800 000;52;20.09.2026\n10 400 000;56;25.09.2026\n")
    listings = rf.load_listings(path, source="ЦИАН")
    result = rf.comparative_approach(54, listings)

    assert result["comparables"][0]["price"] == 9_800_000
    assert result["sample_size"] == 2


# Rent.


def test_rent_listings_are_annualized(tmp_path):
    path = _csv(tmp_path, "Арендная плата;Площадь\n100 000;50\n")
    listing = rf.load_listings(path, source="ЦИАН", listing_type="rent", rent_period="month")[0]

    assert listing["rent_rub"] == 100_000
    assert listing["rent_period"] == "month"
    assert listing["price_rub"] == 1_200_000
    assert rf.comparative_approach(50, [listing])["indicated_value"] == 1_200_000


def test_rent_rate_per_sqm(tmp_path):
    path = _csv(tmp_path, "Ставка аренды за м2;Площадь;Период\n2 000;50;месяц\n")
    listing = rf.load_listings(path, source="ЦИАН", listing_type="rent")[0]

    assert listing["price_rub"] == 2_000 * 50 * 12


def test_rent_period_is_required(tmp_path):
    path = _csv(tmp_path, "Арендная плата;Площадь\n100 000;50\n")

    with pytest.raises(ValueError, match="rent_period"):
        rf.load_listings(path, source="ЦИАН", listing_type="rent")


# Income properties: capitalization rate and GRM.


def test_income_listings_for_cap_rate_and_grm(tmp_path):
    path = _csv(tmp_path, "Цена;ЧОД;Валовой доход\n100 000 000;10 000 000;14 000 000\n120 000 000;11 400 000;16 000 000\n")
    listings = rf.load_listings(path, source="ЦИАН", listing_type="income")

    assert listings[0]["noi"] == 10_000_000
    assert rf.cap_rate_extraction(listings)["sample_size"] == 2
    assert rf.gross_rent_multiplier(listings, 15_000_000)["sample_size"] == 2


def test_income_listing_needs_income(tmp_path):
    path = _csv(tmp_path, "Цена\n100 000 000\n")

    with pytest.raises(ValueError, match="noi"):
        rf.load_listings(path, source="S", listing_type="income")


# Business multiples.


def test_business_listings_for_multiples(tmp_path):
    path = _csv(tmp_path, "Компания;Отрасль;Стоимость;Показатель\nАльфа;ритейл;1 000 000 000;100 000 000\nБета;ритейл;1 200 000 000;110 000 000\n")
    listings = rf.load_listings(path, source="СПАРК", listing_type="business")

    assert listings[0]["name"] == "Альфа"
    assert listings[0]["value"] == 1_000_000_000
    assert listings[0]["metric"] == 100_000_000
    result = rf.business_multiples(listings, 50_000_000, "EV/EBITDA", "invested_capital")
    assert result["sample_size"] == 2


def test_business_listing_needs_metric(tmp_path):
    path = _csv(tmp_path, "Компания;Стоимость\nАльфа;1 000 000\n")

    with pytest.raises(ValueError, match="metric"):
        rf.load_listings(path, source="S", listing_type="business")


# Machinery.


def test_machinery_listings(tmp_path):
    path = _csv(tmp_path, "Наименование;Марка;Модель;Год;Цена;Наработка\nЭкскаватор;Hitachi;ZX200;2019;7 500 000;6 200\n")
    listing = rf.load_listings(path, source="Avito", listing_type="machinery")[0]

    assert (listing["name"], listing["operating_hours"], listing["price_rub"]) == ("Экскаватор", 6_200, 7_500_000)
    analogs = [
        {**listing, "adjustments": [{"name": "Состояние", "direction": "up"}]},
        {**listing, "price_rub": 9_000_000, "adjustments": [{"name": "Наработка", "direction": "down"}]},
    ]
    assert rf.qualitative_adjustments(analogs)["weighted_value"] == 8_250_000


def test_unknown_listing_type():
    with pytest.raises(ValueError, match="listing_type"):
        rf.normalize_listing({"price": 1}, "S", listing_type="art")


# Codex review of 0.6.0.


def test_income_listings_differing_only_in_income_are_kept(tmp_path):
    path = _csv(tmp_path, "Цена;ЧОД\n100 000 000;10 000 000\n100 000 000;20 000 000\n")
    listings = rf.load_listings(path, source="S", listing_type="income")

    assert [item["noi"] for item in listings] == [10_000_000, 20_000_000]


def test_xlsx_formula_without_cached_value_is_an_error(tmp_path):
    path = _xlsx(tmp_path, [["Цена"], [100], ["=100*2"]])

    with pytest.raises(ValueError, match="row 3.*пересчитайте"):
        rf.load_listings(path, source="S", sheet="Аналоги")
