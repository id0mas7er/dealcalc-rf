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


def test_result_envelope_with_normative_formula():
    result = income_capitalization(1_200_000, 12)

    assert result["status"] == "черновой расчёт"
    assert result["method_card"] == {
        "id": "DIRECT_CAPITALIZATION",
        "standard": "ФСО V, п. 14; ФСО №7",
        "formula": "V = I_1 / R",
        "formula_status": "норма ФСО",
    }
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
    assert any("цены предложения" in check for check in result["checks"])


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
        {"price_rub": 1_000_000, **FULL},
        {"price_rub": 1_050_000, **FULL},
    ]

    without = vehicle_comparative_approach({}, comparables)
    limited = vehicle_comparative_approach(
        {}, comparables, max_year_diff=3, max_mileage_diff=50_000
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
