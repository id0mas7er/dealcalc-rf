"""Fixes from review 26 (dealcalc-rf 0.13.3 / collect 0.4.2), group E."""

from dealcalc import rf

C = {"valuation_date": "2026-09-29", "value_type": "рыночная", "vat": "excluded"}
M = {"source": "S", "price_type": "предложение"}


# E4. An analog with only price_collected_at (the «Дата цены» column) is not
# flagged as dateless.


def test_price_collected_at_counts_as_date_in_no_date_check():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "price_collected_at": "2026-09-29"},
         {**M, "price": 10.5e6, "area_sqm": 100, "price_collected_at": "2026-09-29"}],
        context=C,
    )
    assert not any("Не указана дата" in check for check in result["checks"])


def test_truly_dateless_analog_is_still_flagged():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100},
         {**M, "price": 10.5e6, "area_sqm": 100}],
        context=C,
    )
    assert any("Не указана дата" in check for check in result["checks"])
