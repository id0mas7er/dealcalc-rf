"""Земля в составе ЕОН (разбор отчётов 13.10.2026: 108/25-ю, 120/25-ю, 41): поправка, обеспеченность, разнесение."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2025-02-14", "value_type": "рыночная", "vat": "included", "vat_rate_pct": 20}

# Отчёт 108/25-ю: ЕОН 1040,3 м², земля объекта 15 238 000; земля аналогов — по цене земли объекта.
S_EON, LAND = 1040.3, 15_238_000
EON = [  # цена, площадь, отопление, назначение, ГПМ/ж-д, земля аналога
    (31_059_000, 1827.0, 11.69, -2.83, -11, 0),
    (110_000_000, 4758.8, 10.56, 0, (1 / 1.11 - 1) * 100, 10_083_503),
    (35_000_000, 1650.0, -3.61, 0, 0, 6_930_076),
]


def _eon(basis):
    comparables = []
    for (price, area, heat, purpose, extra, land), weight in zip(EON, (0.303, 0.333, 0.364)):
        steps = [
            {"name": "торг", "type": "pct", "value": -17.5},
            {"name": "площадь", "type": "param", "subject": S_EON, "analog": area, "exponent": -0.122},
            {"name": "отопление", "type": "pct", "value": heat},
        ]
        steps += [{"name": "назначение", "type": "pct", "value": purpose}] if purpose else []
        steps += [{"name": "ГПМ / ж-д ветка", "type": "pct", "value": extra}] if extra else []
        steps.append({"name": "земля в составе ЕОН", "type": "land", "subject_land_value": LAND,
                      "subject_area": S_EON, "analog_land_value": land, "analog_area": area, "basis": basis})
        comparables.append({"price": price, "area_sqm": area, "weight": weight, "adjustments": steps})
    return rf.comparative_approach(S_EON, comparables, context=CONTEXT)


def test_land_step_as_in_report_108_with_reminder():
    result = _eon("analog_area")

    assert result["indicated_value"] == pytest.approx(24_164_047, rel=1e-4)
    assert [item["adjustments"][-1]["value"] for item in result["comparables"]] == [8340.45, 1083.15, 5035.11]
    assert any("площадь аналога" in item for item in result["guardrails"])


def test_land_step_subject_on_subject_area():
    result = _eon("subject_area")

    land = [item["adjustments"][-1] for item in result["comparables"]]
    assert [step["value"] for step in land] == [14647.7, 12528.78, 10447.65]
    assert [step["price_without_land"] for step in land] == [14510.36, 20746.84, 13644.67]
    assert round(result["indicated_value"], -3) == 32_166_000
    assert not any("площадь аналога" in item for item in result["guardrails"])


def test_land_step_needs_areas():
    comparables = [{"price": 100, "area_sqm": 1, "adjustments": [
        {"name": "земля", "type": "land", "subject_land_value": 10, "subject_area": 0, "analog_area": 1}]}]
    with pytest.raises(ValueError, match="subject_area"):
        rf.comparative_approach(1, comparables, context=CONTEXT)


def test_land_deficit_reproduces_report_41():
    """Отчёт 41: плотность застройки 1,55 (ЗУ 0,645 на м² здания), факт 380 м², цена земли 156 485,84."""

    result = rf.land_sufficiency(380, 156_485.84, building_area_sqm=1049.3, building_density=1.55, context=CONTEXT)

    assert result["required_land_sqm"] == 676.97
    assert result["kind"] == "недостаток"
    assert round(result["adjustment"]) == -46_471_247
    assert result["guardrails"]


def test_land_taken_differently_in_approaches_is_a_check():
    """Отчёт 41: недостаток земли вычтен только в сравнительном (итог 329 млн вместо 306 млн)."""

    values = {"comparative": 314_000_000, "income": 344_000_000}
    weights = {"comparative": 0.5, "income": 0.5}
    differ = rf.reconcile_approaches(values, weights, land_adjustments={"comparative": -46_471_247, "income": 0},
                                     context=CONTEXT)
    same = rf.reconcile_approaches(values, weights, land_adjustments={"comparative": -46_471_247,
                                                                      "income": -46_471_247}, context=CONTEXT)

    assert any("по-разному" in item for item in differ["checks"])
    assert not any("по-разному" in item for item in same["checks"])
    with pytest.raises(ValueError, match="land_adjustments"):
        rf.reconcile_approaches(values, weights, land_adjustments={"comparative": 0}, context=CONTEXT)


def test_allocation_reproduces_report_108():
    result = rf.allocate_value(
        24_603_000,
        [{"name": "здание 213", "components": [{"area_sqm": 139, "coef": 0.73}, {"area_sqm": 485.7}]},
         {"name": "здание 214", "area_sqm": 415.6}],
        land_value=15_238_000, round_to=1000, context=CONTEXT,
    )

    assert [part["value"] for part in result["parts"]] == [5_484_000, 3_881_000]
    assert result["rounding_difference"] == 0 and not result["checks"]


def test_allocation_reproduces_report_120():
    result = rf.allocate_value(
        60_188_000,
        [{"name": "здание 27", "components": [{"area_sqm": 269}, {"area_sqm": 495, "coef": 0.96},
                                              {"area_sqm": 232.9, "coef": 0.78}]},
         {"name": "здание 72", "components": [{"area_sqm": 267.5}, {"area_sqm": 822.3, "coef": 0.96},
                                              {"area_sqm": 544.6, "coef": 0.78}]}],
        land_value=4_427_000, round_to=1000, context=CONTEXT,
    )

    assert [part["value"] for part in result["parts"]] == [21_444_000, 34_317_000]


def test_allocation_by_land_share_reproduces_report_41():
    result = rf.allocate_value(329_000_000, [{"name": "здание", "area_sqm": 1049.3}],
                               land_share_pct=32 * 380 / 676.97, round_to=1_000_000, context=CONTEXT)

    assert result["land_value"] == 59_000_000 and result["parts"][0]["value"] == 270_000_000


def test_allocation_reports_a_rounding_difference():
    result = rf.allocate_value(1000, [{"name": "a", "area_sqm": 1}, {"name": "b", "area_sqm": 1},
                                      {"name": "c", "area_sqm": 1}], round_to=10, context=CONTEXT)

    assert result["rounding_difference"] == 10 and result["checks"]


def test_allocation_takes_one_land_input():
    with pytest.raises(ValueError, match="not both"):
        rf.allocate_value(100, [{"name": "a", "area_sqm": 1}], land_value=10, land_share_pct=10, context=CONTEXT)
