"""Затратный подход для машин и оборудования (разбор отчётов 13.10.2026: 46/25-ю, 58/25-ю): R8, R9, R10."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2025-02-25", "value_type": "рыночная", "vat": "not_applicable"}
USD = 88.2065
MOUNT = {"name": "монтаж в цене КП", "type": "coef", "value": 1 / 1.18}
COMMON = [{"name": "торг", "type": "coef", "value": 0.868}, {"name": "вторичный рынок", "type": "coef", "value": 0.887}]


def _fx(rate):
    return {"name": "курс USD на дату оценки", "type": "coef", "value": rate}


def _index(old_rate):
    return {"name": "индекс курса USD", "type": "ratio", "subject": USD, "analog": old_rate}


def test_report_58_reproduces_every_item():
    kit = rf.split_set_price(35_910, {"аппарат": 16_400, "модуль": 4_069, "монитор": 3_273},
                             base_source="договор 2021 г.", context=CONTEXT)
    price = {item["name"]: item["price"] for item in kit["items"]}
    sterilizer_1 = rf.mean_new_price([{"price": 403_650}, {"price": 450_000}], context=CONTEXT)["mean_price"]
    sterilizer_2 = rf.mean_new_price([{"price": 155_000}, {"price": 191_651}], context=CONTEXT)["mean_price"]
    items = [
        ("Наркозно-дыхательный аппарат 9100 NXT", price["аппарат"], [_fx(USD), MOUNT]),
        ("Монитор пациента B105", price["монитор"], [_fx(USD), MOUNT]),
        ("Модуль CARESCAPE E-sCAIO", price["модуль"], [_fx(USD), MOUNT]),
        ("MERCURY 1000 (1)", 285_000, []),
        ("MERCURY 1000 (2)", 285_000, []),
        ("ЛОР-комбайн UE-3000", 6_000, [_fx(USD)]),
        ("Кресло ЛОР", 2_373, [_fx(USD)]),
        ("ЭХВЧ-300-01", 943_000, []),
        ("Монитор EndoVue 32", 300_000, [_index(73.5453)]),
        ("Стерилизатор ВКа-75ПЗ", sterilizer_1, []),
        ("PIEZOTOM SOLO LED", 270_000, [_index(73.4453)]),
        ("Стол операционный СОМэп-01", 715_000, []),
        ("Стерилизатор Tanzo-C23", sterilizer_2, []),
        ("Стол операционный Armed", 369_000, []),
    ]
    result = rf.machinery_cost_approach(
        [{"name": name, "new_price": new, "steps": steps} for name, new, steps in items],
        common_steps=COMMON, physical_depreciation_pct=35, functional_depreciation_pct=5, round_to=1000,
        context=CONTEXT,
    )

    assert [item["value_rounded"] for item in result["items"]] == [
        882_000, 176_000, 219_000, 135_000, 135_000, 252_000, 100_000, 448_000, 171_000, 203_000, 154_000,
        340_000, 82_000, 175_000]
    assert result["total_rounded"] == 3_472_000
    assert result["items"][0]["total_depreciation_pct"] == 38.25
    assert any("одинаков у всех позиций" in item for item in result["guardrails"])
    assert any("не индекс цен" in item for item in result["guardrails"])


def test_report_46_mixer_with_vat():
    result = rf.machinery_cost_approach(
        [{"name": "Тестомес FIMAK SPM 250M", "new_price": 28_900, "steps": [
            {"name": "курс EUR на дату оценки", "type": "coef", "value": 103.6612}]}],
        common_steps=[{"name": "торг", "type": "coef", "value": 0.868},
                      {"name": "без НДС", "type": "coef", "value": 100 / 120},
                      {"name": "вторичный рынок", "type": "coef", "value": 0.887}],
        physical_depreciation_pct=60, functional_depreciation_pct=15, vat_rate_pct=20,
        context=dict(CONTEXT, vat="included", vat_rate_pct=20),
    )
    item = result["items"][0]

    assert item["steps"][2]["price_after"] == 2_166_968.28
    assert (item["value"], item["value_with_vat"]) == (653_514.29, 784_217.15)
    assert not any("одинаков" in text for text in result["guardrails"])


def test_item_depreciation_overrides_the_common_one():
    result = rf.machinery_cost_approach(
        [{"name": "a", "new_price": 100, "physical_depreciation_pct": 50}, {"name": "b", "new_price": 100}],
        physical_depreciation_pct=20, context=CONTEXT,
    )

    assert [item["value"] for item in result["items"]] == [50, 80]


def test_physical_depreciation_is_required():
    with pytest.raises(ValueError, match="physical_depreciation_pct"):
        rf.machinery_cost_approach([{"name": "a", "new_price": 100}], context=CONTEXT)


def test_split_and_mean_reminders():
    kit = rf.split_set_price(100, {"a": 1, "b": 3}, context=CONTEXT)
    quotes = rf.mean_new_price([{"price": 100}, {"price": 150}], context=CONTEXT)

    assert [item["price"] for item in kit["items"]] == [25, 75] and kit["guardrails"]
    assert quotes["mean_price"] == 125 and quotes["spread_pct"] == 50 and quotes["guardrails"]


def test_split_keeps_the_sum_and_no_negative_prices():
    """Копейки — по наибольшим остаткам (ревью Codex 14.10.2026: 0,02 на четыре давало −0,01)."""

    three = rf.split_set_price(100, {"a": 1, "b": 1, "c": 1}, base_source="договор", context=CONTEXT)
    tiny = rf.split_set_price(0.02, {"a": 1, "b": 1, "c": 1, "d": 1}, base_source="договор", context=CONTEXT)

    assert [item["price"] for item in three["items"]] == [33.34, 33.33, 33.33]
    assert [item["price"] for item in tiny["items"]] == [0.01, 0.01, 0, 0]
    assert three["rounding_difference"] == tiny["rounding_difference"] == 0


def test_later_price_of_a_machinery_item_is_a_check():
    """Анализ отчётов 14.10.2026: цена позиции 2026 г. на дату оценки 2025 г. проходила без замечаний."""

    result = rf.machinery_cost_approach(
        [{"name": "аппарат", "new_price": 1_609_556, "physical_depreciation_pct": 35, "date": "2026-01-01",
          "source": "КП", "price_type": "предложение",
          "steps": [{"name": "индекс", "type": "coef", "value": 1.1, "date": "2026-02-01"}]}],
        context=CONTEXT,
    )

    assert any("позже даты оценки" in item for item in result["checks"])
    assert any("Позиция 1, шаг" in item for item in result["checks"])
