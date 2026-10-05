"""Fix from review 27 (dealcalc-rf 0.13.4 / collect 0.4.3), group F."""

from dealcalc import rf
from dealcalc.rf import normalize_listing

C = {"valuation_date": "2026-09-29", "value_type": "рыночная", "vat": "excluded"}
M = {"source": "S", "date": "2026-07-01", "price_type": "предложение"}


# F1. date_check (collect marks listings whose marketplace has no publication
# date) survives normalization and reaches the calculation output.


def test_date_check_survives_normalization():
    row = normalize_listing(
        {"price": "10 000 000", "date": "2026-07-01", "date_check": "not_applied"},
        source="S",
    )
    assert row["date_check"] == "not_applied"


def test_date_check_reaches_comparables():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "date_check": "not_applied"},
         {**M, "price": 10.5e6, "area_sqm": 100}],
        context=C,
    )
    assert result["comparables"][0]["date_check"] == "not_applied"
