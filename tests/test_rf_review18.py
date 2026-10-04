"""Code review of 04.10.2026: numbers with separators, the weighted median, small fixes."""

import inspect

import pytest

from dealcalc import rf
from dealcalc.rf import vehicle
from dealcalc.rf.data import parse_number


# 02: several separators of one kind are thousands only in groups of three digits.


@pytest.mark.parametrize("text", ["1,5,2", "1.2.3", "12,34,567", "1.23.456"])
def test_ambiguous_separators_are_rejected(text):
    with pytest.raises(ValueError, match="price"):
        parse_number(text, "price")


@pytest.mark.parametrize("text, number", [
    ("1,234,567", 1_234_567),
    ("1.234.567", 1_234_567),
    ("1.200.000,50", 1_200_000.5),
    ("1,200,000.50", 1_200_000.5),
    ("12 500 000", 12_500_000),
    ("4,5 млн", 4_500_000),
])
def test_thousand_separators_still_work(text, number):
    assert parse_number(text, "price") == number


# 03: the weighted median is the lower one; statistics come from unrounded prices.


def _vehicles(prices):
    return rf.vehicle_comparative_approach(
        {"brand": "Kia", "model": "Rio"},
        [{"brand": "Kia", "model": "Rio", "price_rub": price, "source": "S", "date": "2026-09-01",
          "price_type": "offer"} for price in prices],
    )


def test_two_equal_weights_take_the_lower_median():
    result = _vehicles([1_000_000, 1_200_000])

    assert result["weighted_median_price"] == result["indicated_value"] == 1_000_000.0


def test_the_median_convention_is_documented():
    doc = inspect.getdoc(rf.vehicle_comparative_approach)

    assert "lower" in doc and "median" in doc


def test_spread_and_variation_use_unrounded_prices(monkeypatch):
    calls = []
    original = vehicle.variation
    monkeypatch.setattr(vehicle, "variation", lambda values: calls.append(list(values)) or original(values))
    rf.vehicle_comparative_approach(
        {"brand": "Kia", "model": "Rio"},
        [{"brand": "Kia", "model": "Rio", "price_rub": 1_000_000, "source": "S", "date": "2026-09-01",
          "price_type": "offer", "adjustments": [{"name": "x", "type": "pct", "value": 1 / 3}]},
         {"brand": "Kia", "model": "Rio", "price_rub": 1_000_000, "source": "S", "date": "2026-09-01",
          "price_type": "offer"}],
    )

    assert calls[0][0] == pytest.approx(1_000_000 * (1 + 1 / 300), abs=1e-9)
    assert calls[0][0] != round(calls[0][0], 2)


# 07: messages and docstrings.


def test_message_of_the_exposure_periods():
    with pytest.raises(ValueError, match="typical_exposure_months must be greater than 0"):
        rf.asset_liquidation_value(1_000_000, 20, 0, 0)
    with pytest.raises(ValueError, match="liquidation_exposure_months must be non-negative"):
        rf.asset_liquidation_value(1_000_000, 20, 6, -1)


def test_check_report_docstring_has_no_doubled_number():
    server = pytest.importorskip("mcp_server.server", exc_type=ImportError)

    assert "final_value_justification) (число)" not in inspect.getdoc(server.rf_check_report)
