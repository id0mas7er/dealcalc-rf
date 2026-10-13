"""НМА и права требования (разбор отчётов 13.10.2026: ГНТТП, НИЦЭМ, РСХБ — R23, R26)."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2026-04-20", "value_type": "рыночная", "vat": "not_applicable"}


def test_intangible_cost_method_reproduces_gnttp_item_1():
    result = rf.intangible_cost_method(
        [{"name": "НМА 1", "costs": [{"amount": 8_875_112.58, "source": "платёжные документы", "date": "2025-07-01"}],
          "used_years": 294 / 365.2, "useful_life_years": 3652 / 365.2, "protection_years_left": 15}],
        entrepreneurial_profit_pct=13.4, context=CONTEXT,
    )
    item = result["items"][0]

    assert item["reproduction_cost"] == 10_064_377.67
    assert round(item["value"]) == 9_254_157
    assert result["guardrails"]


def test_intangible_life_is_checked_against_protection_and_fx_is_flagged():
    result = rf.intangible_cost_method(
        [{"name": "ноу-хау", "costs": [{"amount": 1700, "steps": [
            {"name": "курс евро на дату оценки / на дату затрат", "type": "ratio", "subject": 89.63, "analog": 60.05}]}],
          "used_years": 1, "protection_years_left": 2},
         {"name": "программа", "costs": [{"amount": 100}], "used_years": 1}],
        useful_life_years=10, context=CONTEXT,
    )

    assert result["items"][0]["costs"][0]["value"] == pytest.approx(2537.4, abs=0.2)
    assert any("правовой охраны" in item for item in result["checks"])
    assert any("одинаков у всех НМА" in item for item in result["guardrails"])
    assert any("не индекс цен" in item for item in result["guardrails"])


def test_relief_from_royalty():
    result = rf.relief_from_royalty([1000, 2000], 5, 20, periods=[0.5, 1.5], tax_rate_pct=20, lump_sum=10,
                                    royalty_source="договоры", context=CONTEXT)

    expected = 10 + 40 / 1.2 ** 0.5 + 80 / 1.2 ** 1.5
    assert result["value"] == pytest.approx(expected, abs=0.01)
    with pytest.raises(ValueError, match="periods"):
        rf.relief_from_royalty([1, 2], 5, 20, periods=[1], context=CONTEXT)


def test_bankruptcy_claim_reproduces_rshb():
    as_report = rf.bankruptcy_claim_value(32_385_962, 100_000_000, 24.34, 11, context=CONTEXT)
    with_priority = rf.bankruptcy_claim_value(32_385_962, 100_000_000, 24.34, 11, priority_claims=1_608_627,
                                             context=CONTEXT)

    assert as_report["to_secured_creditor"] == pytest.approx(30_766_664, abs=1)
    assert as_report["value"] == pytest.approx(25_197_287, abs=60)
    assert any("1–2 очереди не заданы" in item for item in as_report["guardrails"])
    assert with_priority["to_secured_creditor"] == pytest.approx(29_158_037, abs=1)
    assert round(with_priority["value"], -4) == 23_880_000


def test_bankruptcy_claim_caps_and_shares():
    capped = rf.bankruptcy_claim_value(1000, 500, 0, 0, context=CONTEXT)
    other = rf.bankruptcy_claim_value(1000, 10_000, 0, 0, pledge_type="other", priority_claims=500, context=CONTEXT)

    assert capped["to_secured_creditor"] == 500 and capped["capped_by_claim"]
    assert other["to_priority_claims"] == 200 and other["to_secured_creditor"] == 700


def test_assignment_knows_new_object_types():
    result = rf.check_assignment({"object_type": "intangible", "object_description": "программа для ЭВМ",
                                  "rights": "исключительное право", "purpose": "учёт", "value_type": "рыночная",
                                  "value_premises": "текущее использование", "valuation_date": "2026-04-20"})

    assert result["can_proceed"]
    assert any("legal_protection" in item for item in result["checks"])


# Ревью Codex 13.10.2026.


def test_sale_costs_come_before_the_distribution():
    result = rf.bankruptcy_claim_value(1000, 10_000, 0, 0, sale_costs=200, context=CONTEXT)

    assert result["net_proceeds"] == 800 and result["to_secured_creditor"] == 760
    assert result["reserve_for_costs"] == 40
    assert not any("сохранность" in item for item in result["guardrails"])
    with pytest.raises(ValueError, match="sale_costs"):
        rf.bankruptcy_claim_value(1000, 10_000, 0, 0, sale_costs=2000, context=CONTEXT)


def test_claim_amount_is_required():
    with pytest.raises(TypeError):
        rf.bankruptcy_claim_value(1000, 0, 0, context=CONTEXT)  # type: ignore[call-arg]


def test_intangible_methods_cite_fso_xi():
    cost = rf.intangible_cost_method([{"name": "a", "costs": [{"amount": 1}], "used_years": 0}],
                                     useful_life_years=1, context=CONTEXT)
    royalty = rf.relief_from_royalty([1], 1, 10, royalty_source="x", context=CONTEXT)

    assert "ФСО XI, п. 18" in cost["method_card"]["standard"]
    assert "ФСО XI" in royalty["method_card"]["standard"]
