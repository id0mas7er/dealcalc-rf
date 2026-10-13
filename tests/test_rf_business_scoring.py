"""Статьи баланса, балльные методы, премия за ликвидность, внешний износ по зарплатам
(разбор отчётов 13.10.2026: ТПЭ2024, МПРГ2023, РСХБ2022 — R20, R22, R24, R25)."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2024-03-31", "value_type": "рыночная", "vat": "not_applicable"}


def test_balance_items_reproduce_report_tpe():
    result = rf.balance_items_present_value([
        {"name": "запасы", "side": "asset", "book_value": 311, "years": 0.0078, "rate_pct": 14.63, "rate_source": "ЦБ"},
        {"name": "дебиторская задолженность", "side": "asset", "book_value": 1605, "years": 0.266, "rate_pct": 16.19,
         "rate_source": "ЦБ"},
        {"name": "финансовые вложения", "side": "asset", "book_value": 2100, "years": 0.751, "rate_pct": 16,
         "rate_source": "ЦБ"},
        {"name": "займы", "side": "liability", "book_value": 550, "years": 0.249, "rate_pct": 17.97},
    ], context=CONTEXT)

    values = [item["value"] for item in result["items"]]
    assert values == pytest.approx([311, 1542, 1879, 528], abs=0.5)
    assert [item["factor"] for item in result["items"]] == pytest.approx([0.99894, 0.96092, 0.89457, 0.95964], abs=1e-4)
    assert result["net_value"] == pytest.approx(sum(values[:3]) - values[3], abs=0.02)
    assert any("займы" in item for item in result["checks"])


def test_scoring_discount_reproduces_report_mprg():
    result = rf.scoring_discount([{"name": f"фактор {n}", "score": s} for n, s in enumerate([20, 30, 20, 40, 20, 30, 10, 20])],
                                 context=CONTEXT)

    assert result["discount_pct"] == 23.75 and result["formula"] == "190.0 / 8"
    assert result["guardrails"]


def test_build_up_rate_reproduces_report_rshb():
    result = rf.discount_rate_build_up(10.09, [
        {"name": "риск вложения", "scores": [5, 2.5, 2.5, 0, 2.5], "source": "баллы оценщика"},
        {"name": "низкая ликвидность", "exposure_months": 11, "source": "срок экспозиции"},
        {"name": "инвестиционный менеджмент", "value": 2.5, "source": "оценщик"},
    ], risk_free_source="ОФЗ", context=CONTEXT)

    assert result["discount_rate_pct"] == 24.34
    assert result["premiums"][1]["formula"] == "10.09 × 11.0 / 12"
    with pytest.raises(ValueError, match="scores"):
        rf.discount_rate_build_up(10, [{"name": "риск", "scores": []}], context=CONTEXT)


def test_weights_from_scores_and_wage_obsolescence():
    assert rf.weights_from_scores({"сравнительный": 30, "затратный": 7.5})["weights"] == {
        "сравнительный": 0.8, "затратный": 0.2}
    wages = rf.external_obsolescence_wages(0.794, 1, 0.737, context=CONTEXT)
    assert wages["external_obsolescence_pct"] == 41.48 and len(wages["guardrails"]) == 2
