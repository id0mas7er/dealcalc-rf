"""Agent rules from the methodology base: result envelope, data quality,
no default selection limits, Gordon model and the assignment check."""

import pytest

from dealcalc.rf import (
    check_assignment,
    comparative_approach,
    gordon_terminal_value,
    income_capitalization,
    irr,
    physical_depreciation,
    vehicle_comparative_approach,
)

FULL = {"source": "ЦИАН", "date": "2026-09-20", "price_type": "сделка"}


CONTEXT = {"valuation_date": "2026-10-01", "value_type": "рыночная", "vat": "excluded"}


def test_result_envelope_with_normative_formula():
    result = income_capitalization(1_200_000, 12, context=CONTEXT)

    assert result["status"] == "черновой расчёт"
    assert result["method_card"] == {
        "id": "DIRECT_CAPITALIZATION",
        "standard": "ФСО V, п. 14; ФСО №7, п. 23 (в)",
        "formula": "V = I_1 / R",
        "formula_status": "норма ФСО",
        "source_url": "https://srosovet.ru/activities/npa/fso-v/",
    }
    assert result["context"]["vat_label"] == "без НДС"
    assert result["checks"] == []


def test_comparables_with_full_provenance_are_a_draft():
    result = comparative_approach(
        50,
        [
            {"price": 10_000_000, "area_sqm": 50, **FULL},
            {"price": 10_500_000, "area_sqm": 50, **FULL, "reliability": "договор"},
        ],
    )

    assert result["status"] == "черновой расчёт"
    assert result["checks"] == []
    assert result["comparables"][1]["reliability"] == "договор"


def test_missing_provenance_requires_review():
    result = comparative_approach(
        50, [{"price": 10_000_000, "area_sqm": 50}, {"price": 10_200_000, "area_sqm": 50}]
    )

    assert result["status"] == "нужна проверка оценщика"
    assert any("источник" in check for check in result["checks"])
    assert any("дата" in check for check in result["checks"])
    assert any("тип цены" in check for check in result["checks"])


def test_offer_prices_are_flagged_and_normalized():
    result = comparative_approach(
        50,
        [
            {"price": 10_000_000, "area_sqm": 50, **FULL, "price_type": "offer"},
            {"price": 10_200_000, "area_sqm": 50, **FULL},
        ],
    )

    assert result["comparables"][0]["price_type"] == "предложение"
    assert any("цены предложения" in note for note in result["guardrails"])
    assert result["status"] == "черновой расчёт"


def test_invalid_price_type_is_rejected():
    with pytest.raises(ValueError, match="price_type"):
        comparative_approach(50, [{"price": 1, "area_sqm": 1, "price_type": "аукцион"}])


def test_heterogeneous_sample_is_flagged():
    result = comparative_approach(
        1, [{"price": 100, "area_sqm": 1, **FULL}, {"price": 300, "area_sqm": 1, **FULL}]
    )

    assert any("неоднородна" in check for check in result["checks"])


def test_vehicle_without_selection_limits_is_flagged():
    comparables = [
        {"price_rub": 1_000_000, "year": 2020, "mileage_km": 60_000, **FULL},
        {"price_rub": 1_050_000, "year": 2021, "mileage_km": 40_000, **FULL},
    ]
    subject = {"year": 2020, "mileage_km": 50_000}

    without = vehicle_comparative_approach(subject, comparables)
    limited = vehicle_comparative_approach(
        subject, comparables, max_year_diff=3, max_mileage_diff=50_000
    )

    assert without["selection"]["max_year_diff"] is None
    assert any("ограничения отбора" in check for check in without["checks"])
    assert limited["checks"] == []


def test_capped_physical_depreciation_is_flagged():
    result = physical_depreciation(30, 10)

    assert result["status"] == "нужна проверка оценщика"
    assert "превышает 100%" in result["checks"][0]


def test_irr_with_several_sign_changes_is_flagged():
    result = irr([-100, 230, -132])

    assert "несколько значений IRR" in result["checks"][0]


def test_gordon_terminal_value():
    result = gordon_terminal_value(1_100_000, 14, 4)

    assert result["terminal_value"] == 11_000_000.0
    assert result["method_card"]["standard"] == "ФСО V, п. 21"


@pytest.mark.parametrize("rate, growth", [(5, 5), (4, 6)])
def test_gordon_requires_rate_above_growth(rate, growth):
    with pytest.raises(ValueError, match="r > g"):
        gordon_terminal_value(1_000, rate, growth)


COMPLETE_ASSIGNMENT = {
    "object_type": "real_estate",
    "object_description": "Нежилое помещение 120 м²",
    "rights": "право собственности, без обременений",
    "purpose": "залог",
    "value_type": "рыночная",
    "value_premises": "текущее использование, добровольная продажа",
    "valuation_date": "2026-10-01",
    "inspection_status": "проведён 30.09.2026",
}


def test_complete_assignment_can_proceed():
    result = check_assignment(COMPLETE_ASSIGNMENT)

    assert result["can_proceed"] is True
    assert result["missing_critical"] == []
    assert result["profile_standard"] == "ФСО №7"
    assert "сравнительный" in result["approach_diagnostics"]


def test_missing_critical_items_stop_the_calculation():
    result = check_assignment({"object_type": "business", "purpose": "сделка"})

    assert result["status"] == "недостаточно данных"
    assert result["can_proceed"] is False
    assert any(item.startswith("value_type") for item in result["missing_critical"])
    assert "share_fraction" in result["missing_recommended"]


def test_assignment_warnings():
    result = check_assignment(
        {
            **COMPLETE_ASSIGNMENT,
            "value_type": "справедливая",
            "valuation_date": "01.10.2026",
            "inspection_status": "не проводился",
        }
    )

    assert any("ФСО II" in check for check in result["checks"])
    assert any("ГГГГ-ММ-ДД" in check for check in result["checks"])
    assert any("Осмотр не проводился" in check for check in result["checks"])


def test_assignment_rejects_unknown_object_type():
    with pytest.raises(ValueError, match="object_type"):
        check_assignment({"object_type": "art"})


def test_every_result_has_uniform_keys():
    result = income_capitalization(1_200_000, 12, context=CONTEXT)

    assert result["conditions"] == []
    assert result["guardrails"] == []
    assert result["checks"] == []


@pytest.mark.parametrize(
    "call",
    [
        lambda: comparative_approach(10, [{"price": 0, "area_sqm": 1}, {"price": 100, "area_sqm": 1}]),
        lambda: vehicle_comparative_approach({}, [{"price_rub": 0}, {"price_rub": 100}]),
    ],
)
def test_zero_comparable_price_is_rejected(call):
    with pytest.raises(ValueError, match="greater than 0"):
        call()


def test_negative_incurable_depreciation_is_floored_and_flagged():
    result = physical_depreciation(5, 10, replacement_cost=1_000_000, annual_repair_cost=120_000)

    assert result["incurable_pct"] == 0.0
    assert result["curable_pct"] == 60.0
    assert any("неустранимый износ принят равным 0" in check for check in result["checks"])


def test_collection_date_is_not_a_price_date():
    comparables = [
        {"price_rub": 1_000_000, "source": "avito", "price_type": "предложение", "collected_at": "2026-10-01"},
        {"price_rub": 1_050_000, "source": "avito", "price_type": "предложение", "collected_at": "2026-10-01"},
    ]

    result = vehicle_comparative_approach({}, comparables, max_year_diff=3, max_mileage_diff=50_000)

    assert any("дата цены" in check for check in result["checks"])


@pytest.mark.parametrize("value, expected", [(2.675, 2.68), (0.125, 0.13), (-2.675, -2.68), (-0.001, 0.0)])
def test_money_rounds_half_up(value, expected):
    from dealcalc.rf._adjustments import money

    assert money(value) == expected
    assert str(money(-0.001)) == "0.0"


def test_missing_context_is_a_reminder_not_a_defect():
    result = income_capitalization(1_200_000, 12)

    assert result["status"] == "черновой расчёт"
    assert result["context"]["valuation_date"] is None
    assert "дата оценки" in result["guardrails"][0]


@pytest.mark.parametrize(
    "context, message",
    [
        ({"valuation_date": "01.10.2026"}, "valuation_date"),
        ({"value_type": "справедливая"}, "value_type"),
        ({"vat": "yes"}, "vat"),
        ({"vat_rate_pct": -1}, "vat_rate_pct"),
        ({"unknown": 1}, "unknown fields"),
    ],
)
def test_invalid_context_is_rejected(context, message):
    with pytest.raises(ValueError, match=message):
        income_capitalization(1_200_000, 12, context=context)


def test_period_conventions_are_explicit():
    from dealcalc.rf import dcf_valuation, npv

    assert npv([-100, 110], 10)["first_cash_flow_period"] == 0
    assert dcf_valuation([110], 10)["first_cash_flow_period"] == 1


def test_terminal_value_mid_year_timing():
    from dealcalc.rf import business_income_approach, dcf_valuation

    end = dcf_valuation([100, 100], 10, terminal_value=1_000, mid_year=True)
    mid = dcf_valuation([100, 100], 10, terminal_value=1_000, mid_year=True, terminal_timing="mid")

    assert end["terminal_discount_period"] == 2
    assert mid["terminal_discount_period"] == 1.5
    assert mid["terminal_present_value"] == pytest.approx(1_000 / 1.1 ** 1.5, abs=0.01)
    assert business_income_approach([100], 10, "equity", 1_000, terminal_timing="mid")[
        "terminal_discount_period"
    ] == 0.5
    with pytest.raises(ValueError, match="terminal_timing"):
        dcf_valuation([100], 10, terminal_timing="start")


def test_asset_liquidation_value():
    from dealcalc.rf import asset_liquidation_value

    result = asset_liquidation_value(1_000_000, 20, typical_exposure_months=6, liquidation_exposure_months=2)

    assert result["liquidation_value"] == pytest.approx(941_036.03, abs=0.01)
    assert result["liquidation_discount_pct"] == pytest.approx(5.9, abs=0.01)
    assert result["value_kind"] == "ликвидационная стоимость"


def test_asset_liquidation_value_rejects_longer_forced_exposure():
    from dealcalc.rf import asset_liquidation_value

    with pytest.raises(ValueError, match="must not exceed"):
        asset_liquidation_value(1_000_000, 20, 6, 8)
