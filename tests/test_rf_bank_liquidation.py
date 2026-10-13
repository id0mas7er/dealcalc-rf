"""Ликвидационная стоимость по модели банков (разбор отчётов 13.10.2026, R11: отчёт 108/25-ю)."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2025-02-14", "value_type": "ликвидационная", "vat": "not_applicable"}
VALUES = {"земля": 15_238_000, "здание 213": 5_484_000, "здание 214": 3_881_000}


def test_report_108_with_truncated_coefficient():
    result = rf.bank_liquidation_value(VALUES, 10, 0.85, 15.19, 6, coefficient_decimals=4,
                                       coefficient_rounding="down", round_to=1000, context=CONTEXT)

    assert result["coefficient"] == 0.7127 and result["coefficient_exact"] == 0.712778
    assert [part["liquidation_value"] for part in result["parts"].values()] == [10_860_000, 3_908_000, 2_766_000]
    assert result["liquidation_value"] == 17_534_000
    assert result["guardrails"]


def test_exact_coefficient_and_the_elasticity_from_the_text():
    exact = rf.bank_liquidation_value(VALUES, 10, 0.85, 15.19, 6, round_to=1000, context=CONTEXT)
    text = rf.bank_liquidation_value(VALUES, 10, 0.76, 15.19, 6, round_to=1000, context=CONTEXT)

    assert exact["liquidation_value"] == 17_536_000
    assert text["liquidation_value"] == 15_679_000  # Кэ 0,76 из текста отчёта: −10,6 %


def test_value_type_and_inputs_are_checked():
    market = rf.bank_liquidation_value(VALUES, 10, 0.85, 15.19, 6, context=dict(CONTEXT, value_type="рыночная"))

    assert any("ликвидационная" in item for item in market["checks"])
    with pytest.raises(ValueError, match="elasticity_coef"):
        rf.bank_liquidation_value(VALUES, 10, 1.2, 15.19, 6, context=CONTEXT)
    with pytest.raises(ValueError, match="coefficient_rounding"):
        rf.bank_liquidation_value(VALUES, 10, 0.85, 15.19, 6, coefficient_decimals=4, coefficient_rounding="up",
                                  context=CONTEXT)
