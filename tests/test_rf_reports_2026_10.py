"""Разбор 14 отчётов оценщиков 13.10.2026: числа отчётов, которые библиотека должна воспроизводить."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2025-05-13", "value_type": "рыночная", "vat": "not_applicable"}


def _shares(result):
    return [round(item["weight_share"], 4) for item in result["comparables"]]


# --- R1: автомобиль — взвешенное среднее или медиана (отчёт 147/25-ю, Nissan Teana) ---

def _nissan_default():
    return _nissan(None)


def _nissan(statistic):
    comparables = [
        {"brand": "Nissan", "model": "Teana", "year": 2013, "price_rub": price, "source": "Drom",
         "date": "2025-02-28", "price_type": "предложение",
         "adjustments": [{"name": "торг", "type": "pct", "value": -9.6}]}
        for price in (1_125_000, 1_250_000, 1_200_000, 1_033_000)
    ]
    extra = {} if statistic is None else {"statistic": statistic}
    return rf.vehicle_comparative_approach({"brand": "Nissan", "model": "Teana", "year": 2013}, comparables, **extra)


def test_vehicle_weighted_mean_reproduces_report():
    result = _nissan("weighted_mean")

    assert result["statistic"] == "weighted_mean"
    assert result["indicated_value"] == 1_041_408
    assert result["weighted_median_price"] == 1_017_000


def test_vehicle_weighted_mean_is_the_default():
    """Решение оценщика 15.10.2026: как в отчётах — взвешенное среднее."""

    result = _nissan_default()

    assert result["statistic"] == "weighted_mean" and result["indicated_value"] == 1_041_408


def test_vehicle_weighted_median_on_request():
    result = _nissan("weighted_median")

    assert result["statistic"] == "weighted_median"
    assert result["indicated_value"] == 1_017_000
    assert result["weighted_mean_price"] == 1_041_408


def test_vehicle_unknown_statistic_is_rejected():
    with pytest.raises(ValueError, match="statistic"):
        _nissan("mean")


# --- R16: веса по сумме модулей поправок -----------------------------------------

def test_sum_share_reproduces_report_5605():
    """Отчёт 5605-25 (ЗУ 18 900 м²): Козлов–Фролов по сумме поправок без торга."""

    subject = 18_900
    comm_1 = (1.13 * 1.02 * 1.02 * 1.12) / (1.08 * 1.02 * 1.02 * 1.12)
    comm_3 = (1.13 * 1.02 * 1.02 * 1.12) / (1.08 * 1.02 * 1.02 * 1.00)
    rows = [
        (99_900_000, 11_190, [("ценовая зона", 13), ("благоустройство", 4.5)], comm_1),
        (75_000_000, 8_420, [("ценовая зона", 13), ("автодорога", 8), ("благоустройство", -4.13)], None),
        (95_000_000, 14_508, [("автодорога", 8), ("благоустройство", 4.5)], comm_3),
    ]
    comparables = []
    for price, area, steps, comm in rows:
        adjustments = [{"name": "торг", "type": "pct", "value": -16.42, "exclude_from_weights": True}]
        adjustments += [{"name": name, "type": "pct", "value": value} for name, value in steps]
        adjustments.append({"name": "площадь", "type": "param", "subject": subject, "analog": area, "exponent": -0.125})
        if comm:
            adjustments.append({"name": "коммуникации", "type": "coef", "value": comm})
        comparables.append({"price": price, "area_sqm": area, "adjustments": adjustments})

    result = rf.comparative_approach(subject, comparables, weighting="sum_share", context=CONTEXT)

    assert _shares(result) == [0.3519, 0.3193, 0.3287]
    assert [round(item["sum_abs_adjustments_pct"], 2) for item in result["comparables"]] == [28.47, 34.74, 32.94]
    assert result["comparables"][0]["adjustments"][0]["exclude_from_weights"] is True
    assert round(result["weighted_unit_price"]) == 7_855


def _by_sums(sums, weighting):
    comparables = [
        {"price": 1_000_000, "area_sqm": 10, "adjustments": [{"name": "местоположение", "type": "pct", "value": value}]}
        for value in sums
    ]
    return rf.comparative_approach(10, comparables, weighting=weighting, context=CONTEXT)


def test_sum_share_100_reproduces_report_120():
    """Отчёт 120/25-ю (ЕОН, Оренбург): K ∝ 1 − M/(ΣM + 100)."""

    assert _shares(_by_sums([35.10, -34.63, 56.05], "sum_share_100")) == [0.3457, 0.3466, 0.3077]


def test_inverse_sum_reproduces_report_41():
    """Отчёт 41 (особняк, Москва): w ∝ 1/M; последний вес в отчёте 0,1130 — округлён до суммы 1."""

    assert _shares(_by_sums([16.02, 22.25, -9.58, 37.05], "inverse_sum")) == [0.2615, 0.1883, 0.4372, 0.1131]


def test_inverse_sum_without_adjustments_is_an_error():
    with pytest.raises(ValueError, match="inverse_sum"):
        _by_sums([10, 0], "inverse_sum")


def test_sum_share_without_adjustments_gives_equal_weights():
    assert _shares(_by_sums([0, 0], "sum_share")) == [0.5, 0.5]


def test_exclude_from_weights_must_be_boolean():
    comparables = [{"price": 100, "area_sqm": 1, "adjustments": [
        {"name": "торг", "type": "pct", "value": -10, "exclude_from_weights": "да"}]}]
    with pytest.raises(ValueError, match="exclude_from_weights"):
        rf.comparative_approach(1, comparables, context=CONTEXT)


# --- R14, R21, R27: напоминания ---------------------------------------------------

def test_land_vat_reminder():
    """Отчёт 108/25-ю: НДС «в т.ч.» выделен со стоимости, включая землю."""

    context = dict(CONTEXT, vat="included", vat_rate_pct=20)
    result = rf.cost_approach(10_000_000, land_value=3_000_000, context=context)

    assert any("ст. 146" in item for item in result["guardrails"])
    no_land = rf.cost_approach(10_000_000, context=context)
    assert not any("ст. 146" in item for item in no_land["guardrails"])


def test_share_without_discounts_reminder():
    """Отчёт ТПЭ2024: 51 % доли ООО без скидок и премий."""

    result = rf.business_interest_value(100_000_000, 51, context=CONTEXT)

    assert any("ФСО №8" in item for item in result["guardrails"])
    full = rf.business_interest_value(100_000_000, 100, context=CONTEXT)
    assert not any("ФСО №8" in item for item in full["guardrails"])


def test_currency_rate_step_reminder():
    """Отчёты 58/25-ю, ГНТТП, БМК: отношение курсов валюты как индекс цен."""

    comparables = [{"price": 100, "area_sqm": 1, "adjustments": [
        {"name": "Курс евро на дату оценки", "type": "ratio", "subject": 95.2, "analog": 90.1}]}]
    result = rf.comparative_approach(1, comparables, context=CONTEXT)

    assert any("не индекс цен" in item for item in result["guardrails"])
    plain = rf.comparative_approach(1, [{"price": 100, "area_sqm": 1}], context=CONTEXT)
    assert not any("не индекс цен" in item for item in plain["guardrails"])


# Анализ отчётов Codex 14.10.2026: даты относительно даты оценки.


def test_vehicle_year_after_the_valuation_date_is_a_check():
    comparables = [{"brand": "Nissan", "model": "Teana", "year": year, "price_rub": 1_000_000, "source": "Drom",
                    "date": "2025-02-28", "price_type": "предложение"} for year in (2027, 2024)]
    context = {"valuation_date": "2025-02-28", "value_type": "рыночная", "vat": "included", "vat_rate_pct": 20}
    result = rf.vehicle_comparative_approach({"brand": "Nissan", "model": "Teana", "year": 2027}, comparables,
                                             context=context)

    assert any("Год выпуска объекта 2027" in item for item in result["checks"])
    assert any("Аналоги [1]" in item for item in result["checks"])
    assert result["status"] == "нужна проверка оценщика"


def test_source_dated_by_a_later_year_is_a_check():
    """Справочник «2023» на дату оценки 31.12.2022 (год издания без дня и месяца)."""

    comparables = [{"price": 100, "area_sqm": 1, "adjustments": [
        {"name": "торг", "type": "pct", "value": -9.6, "date": "2023", "source": "Лейфер МиО, 2023"}]}]
    later = rf.comparative_approach(1, comparables, context=dict(CONTEXT, valuation_date="2022-12-31"))
    same = rf.comparative_approach(1, comparables, context=dict(CONTEXT, valuation_date="2023-06-30"))

    assert any("позже даты оценки" in item for item in later["checks"])
    assert not any("позже даты оценки" in item for item in same["checks"])



def test_vehicle_year_given_as_a_string_is_checked():
    comparables = [{"brand": "Kia", "model": "Rio", "year": "2026", "price_rub": 1_000_000}]
    context = {"valuation_date": "2025-02-28", "value_type": "рыночная", "vat": "included", "vat_rate_pct": 20}
    result = rf.vehicle_comparative_approach({"brand": "Kia", "model": "Rio"}, comparables, context=context)

    assert any("Аналоги [1]" in item and "год выпуска" in item for item in result["checks"])


# Седьмой прогон ревью Codex 15.10.2026.


def test_vat_breakdown_rate_against_the_context():
    context = dict(CONTEXT, vat="included", vat_rate_pct=22)

    assert any("не совпадает" in text for text in rf.vat_breakdown(1_220_000, 20, context=context)["checks"])
    assert not rf.vat_breakdown(1_220_000, 22, context=context)["checks"]


def test_mean_new_price_from_prices_as_given():
    assert rf.mean_new_price([{"price": 100.005}, {"price": 100.015}], context=CONTEXT)["mean_price"] == 100.01
    assert rf.mean_new_price([{"price": 0.004}], context=CONTEXT)["spread_pct"] == 0


def test_relief_from_royalty_is_an_income_model():
    basis = {"flow": {"price_level": "nominal", "tax": "post_tax"}, "rate": {"price_level": "nominal", "tax": "pre_tax"}}
    result = rf.relief_from_royalty([1000], 5, 20, context=CONTEXT, flow_rate_basis=basis)

    assert result["flow_rate_basis"] and result["checks"]
    with pytest.raises(ValueError, match="list of numbers"):
        rf.relief_from_royalty("1000", 5, 20, context=CONTEXT)


def test_currency_reminder_in_a_composite_replacement_cost():
    indices = [{"name": "USD currency ratio", "value": 1.1}]
    result = rf.composite_replacement_cost([{"name": "корпус", "base_cost": 1000, "indices": indices}], context=CONTEXT)

    assert any("не индекс цен" in text for text in result["guardrails"])


@pytest.mark.parametrize("name, result_of", [
    ("item", lambda: rf.item_comparative_approach([{"price": 100}], weighting="count_share", context=CONTEXT)),
    ("royalty", lambda: rf.relief_from_royalty([1000], 10, 20, context=CONTEXT)),
    ("bank", lambda: rf.bank_liquidation_value({"a": 1000}, 10, 1, 0, 0, context=CONTEXT)),
])
def test_report_accepts_the_value_of_new_methods(name, result_of):
    from dealcalc.rf.report import _VALUE_KEYS

    result = result_of()
    keys = _VALUE_KEYS[result["method_card"]["id"]]
    assert any(isinstance(result.get(key), (int, float)) for key in keys)


# Восьмой прогон ревью Codex 15.10.2026.


def test_machinery_vat_of_a_new_price_is_not_an_analog_basis():
    context = dict(CONTEXT, vat="included", vat_rate_pct=20)
    item = [{"name": "a", "new_price": 1000, "vat": "excluded", "physical_depreciation_pct": 0}]
    result = rf.machinery_cost_approach(item, vat_rate_pct=20, context=context)

    assert result["total_value"] == 1200 and not any("базе задания" in text for text in result["checks"])


def test_report_takes_the_rounded_machinery_total():
    from dealcalc.rf.report import _VALUE_KEYS

    assert _VALUE_KEYS["MACHINERY_COST_APPROACH"] == ("total_rounded",)


def test_justified_land_difference_is_a_reminder():
    values = {"comparative": 314_000_000, "income": 344_000_000}
    weights = {"comparative": 0.5, "income": 0.5}
    land = {"comparative": -46_471_247, "income": 0}
    result = rf.reconcile_approaches(values, weights, justification="аренда отражает землю", land_adjustments=land,
                                     context=CONTEXT)

    assert not any("по-разному" in item for item in result["checks"])
    assert any("по-разному" in item for item in result["guardrails"])
