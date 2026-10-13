"""Сравнительный подход «за объект» (разбор отчётов 13.10.2026, R7: отчёт 46/25-ю — печь и тестоделитель)."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2025-01-24", "value_type": "рыночная", "vat": "included", "vat_rate_pct": 20}


def _comparables(rows, weights):
    result = []
    for (price, rate, weight_param, condition), weight in zip(rows, weights):
        steps = [{"name": "дата (курс евро)", "type": "coef", "value": 103.6612 / rate}] if rate else []
        steps.append({"name": "торг", "type": "pct", "value": -13.2})
        if weight_param:
            steps.append({"name": "вес печи", "type": "param", "subject": 1840, "analog": 1665, "exponent": 0.68})
        if condition:
            steps.append({"name": "состояние", "type": "depreciation", "subject_pct": 60, "analog_pct": 35})
        result.append({"price": price, "adjustments": steps, "weight": weight, "source": "Avito",
                       "date": "2025-01-24", "price_type": "предложение"})
    return result


def test_oven_report_46_and_weights_not_summing_to_one():
    oven = [(645_000, None, 1, 1), (740_000, None, 0, 1), (599_000, None, 0, 0)]
    result = rf.item_comparative_approach(_comparables(oven, [0.364, 0.273, 0.364]), context=CONTEXT)

    assert [item["adjusted_price"] for item in result["comparables"]] == [368_757.2, 395_273.85, 519_932.0]
    assert result["indicated_value"] == 430_961.67  # в отчёте 431 393: веса в сумме 1,001
    assert any("1.001" in item for item in result["checks"])


def test_divider_report_46():
    divider = [(500_000, 102.4719, 0, 1), (300_000, None, 0, 0), (490_000, 99.45, 0, 1)]
    result = rf.item_comparative_approach(_comparables(divider, [0.25, 0.5, 0.25]), context=CONTEXT)

    assert result["indicated_value"] == 265_948.8
    assert not any("в сумме" in item for item in result["checks"])


def test_quantity_and_no_area():
    result = rf.item_comparative_approach([{"price": 100}, {"price": 200}], quantity=3, context=CONTEXT)

    assert result["weighted_price"] == 150 and result["indicated_value"] == 450
    with pytest.raises(ValueError, match="per object"):
        rf.item_comparative_approach([{"price": 100, "area_sqm": 5}], context=CONTEXT)
