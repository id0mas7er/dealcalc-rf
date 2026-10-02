"""Fixes from the Codex audit of 0.3.3 (review-dealcalc-rf-codex.md)."""

import json
import math

import pytest

from dealcalc import rf
from dealcalc.rf._adjustments import variation
from dealcalc.rf.data import parse_number

C = {"valuation_date": "2026-10-01", "value_type": "рыночная", "vat": "excluded"}
M = {"source": "S", "date": "2026-10-01", "price_type": "сделка"}


# 1. Round only the output, not intermediate values.


def test_grm_value_uses_unrounded_multiplier():
    result = rf.gross_rent_multiplier([{"price": 1_000_000, "gross_income": 300_000}], 300_000)

    assert result["indicated_value"] == 1_000_000


def test_build_up_sums_unrounded_premiums():
    result = rf.discount_rate_build_up(
        5,
        [{"name": "A", "value": 0.004, "source": "S"}, {"name": "B", "value": 0.004, "source": "S"}],
        "S",
    )

    assert result["discount_rate_pct"] == 5.01


def test_market_rent_expense_items_add_up_to_total():
    result = rf.market_rent_cost_plus(100_000_000, 10, [{"name": "x", "type": "pct", "value": 0.004}])

    assert result["owner_expenses"][0]["amount"] == result["total_owner_expenses"] == 400.02


# 2. Deduplication without an explicit identifier.


def test_dedup_keeps_different_flats_with_same_price_and_area():
    rows = [
        rf.normalize_listing({"price": 5_000_000, "area": 50, "address": "A", "rooms": 1, "floor": 2}, "S"),
        rf.normalize_listing({"price": 5_000_000, "area": 50, "address": "B", "rooms": 2, "floor": 7}, "S"),
    ]

    assert len(rf.deduplicate_listings(rows)) == 2
    assert rows[0]["listing_id_basis"] == "characteristics"
    assert "import_warnings" not in rows[0]


def test_dedup_still_merges_the_same_flat():
    row = {"price": 5_000_000, "area": 50, "address": "A", "rooms": 1, "floor": 2}

    assert len(rf.deduplicate_listings([rf.normalize_listing(row, "S"), rf.normalize_listing(row, "S")])) == 1


@pytest.mark.parametrize(
    "row,basis",
    [
        ({"price": 1, "url": "https://x/1"}, "url"),
        ({"price": 1, "vin": "XTA123"}, "vin"),
        ({"price": 1, "cadastral_number": "77:01:1"}, "cadastral"),
        ({"price": 1, "id": "42"}, "listing_id"),
    ],
)
def test_listing_id_basis(row, basis):
    assert rf.normalize_listing(row, "S")["listing_id_basis"] == basis


# 3. Numbers with letters.


@pytest.mark.parametrize(
    "text,expected",
    [
        ("5 млн руб.", 5_000_000.0),
        ("1,5 млн", 1_500_000.0),
        ("850 тыс. руб.", 850_000.0),
        ("12 500 000 ₽", 12_500_000.0),
        ("45 м2", 45.0),
        ("45,5 м²", 45.5),
        ("120 000 км", 120_000.0),
        ("150 л.с.", 150.0),
    ],
)
def test_parse_number_units_and_multipliers(text, expected):
    assert parse_number(text, "price_rub") == expected


@pytest.mark.parametrize("text", ["1e6", "от 5 000 000", "5 000 000 USD", "2 комнаты"])
def test_parse_number_rejects_unknown_letters(text):
    with pytest.raises(ValueError, match="price_rub"):
        parse_number(text, "price_rub")


# 4. IRR with zero flows.


def test_irr_sign_changes_skip_zero_flows():
    result = rf.irr([-100, 0, 230, 0, -132])

    assert result["sign_changes"] == 2
    assert result["checks"]


# 5. Reconciliation weights within tolerance are normalized.


def test_reconcile_normalizes_weights_within_tolerance():
    result = rf.reconcile_approaches({"A": 1_000_000_000}, {"A": 0.99995}, 10)

    assert result["reconciled_value"] == 1_000_000_000


# 6. False in the assignment.


def _assignment(**fields):
    base = {
        "object_type": "real_estate",
        "object_description": "квартира",
        "rights": "собственность",
        "purpose": "залог",
        "value_type": "рыночная",
        "value_premises": "текущее использование",
        "valuation_date": "2026-10-01",
    }
    return {**base, **fields}


def test_false_in_critical_fields_is_missing():
    result = rf.check_assignment(
        _assignment(object_description=False, rights=False, purpose=False, value_premises=False)
    )

    assert result["can_proceed"] is False
    assert len(result["missing_critical"]) == 4


def test_inspection_status_false_warns():
    result = rf.check_assignment(_assignment(inspection_status=False))

    assert any("Осмотр не проводился" in check for check in result["checks"])
    assert "inspection_status" not in result["missing_recommended"]


# 7. Qualitative adjustments.


def _qual(low_price, high_price, **low_fields):
    return [
        {"price": low_price, "adjustments": [{"name": "x", "direction": "up"}], **low_fields},
        {"price": high_price, "adjustments": [{"name": "x", "direction": "down"}]},
    ]


def test_qualitative_rejects_zero_price():
    with pytest.raises(ValueError, match="greater than 0"):
        rf.qualitative_adjustments(_qual(0, 100))


def test_qualitative_checks_provenance_and_import_warnings():
    result = rf.qualitative_adjustments(_qual(100, 200, import_warnings=["warning"]), context=C)

    assert any("warning" in check for check in result["checks"])
    assert any("источник" in check for check in result["checks"])


def test_qualitative_flags_contradictory_pair():
    analogs = [{**item, **M} for item in _qual(200, 100)]
    result = rf.qualitative_adjustments(analogs, context=C)

    assert any("дороже" in check for check in result["checks"])


def test_qualitative_consistent_pair_with_provenance_is_clean():
    analogs = [{**item, **M} for item in _qual(100, 200)]

    assert rf.qualitative_adjustments(analogs, context=C)["checks"] == []


# 8. Year and mileage filters that could not be checked.


def test_vehicle_filters_without_data_are_reported():
    result = rf.vehicle_comparative_approach(
        {"year": 2026, "mileage_km": 10},
        [{**M, "price_rub": 100}, {**M, "price_rub": 110}],
        max_year_diff=0,
        max_mileage_diff=0,
        context=C,
    )

    assert any("года выпуска" in check for check in result["checks"])
    assert any("пробега" in check for check in result["checks"])


# 9. Validation of types and formats.


def test_string_instead_of_list_is_rejected():
    with pytest.raises(ValueError, match="cash_flows"):
        rf.dcf_valuation("100", 10)
    with pytest.raises(ValueError, match="distributions"):
        rf.fund_unit_value("100", 100, 10)


def test_mid_year_must_be_boolean():
    with pytest.raises(ValueError, match="mid_year"):
        rf.dcf_valuation([100], 10, mid_year="false")
    with pytest.raises(ValueError, match="mid_year"):
        rf.business_income_approach([100], 10, "equity", mid_year="false")


@pytest.mark.parametrize("limit", [float("nan"), float("inf"), True])
def test_vehicle_limits_reject_nan_inf_bool(limit):
    with pytest.raises(ValueError, match="max_year_diff"):
        rf.vehicle_comparative_approach({}, [{"price_rub": 100}], max_year_diff=limit)


def test_context_vat_rate_must_be_finite():
    with pytest.raises(ValueError, match="vat_rate_pct"):
        rf.income_capitalization(100, 10, context={**C, "vat_rate_pct": float("nan")})


def test_fund_rejects_distributions_after_final_period():
    with pytest.raises(ValueError, match="final_period"):
        rf.fund_unit_value([100, 100], 1000, 10, final_period=1)


def test_import_keeps_conditions_and_reliability():
    listing = rf.normalize_listing(
        {"price": 1000, "Условия сделки": "без НДС", "Надёжность": "договор"}, "S"
    )

    assert listing["conditions"] == "без НДС"
    assert listing["reliability"] == "договор"
    result = rf.comparative_approach(1, [{**listing, "price": 1000, "area_sqm": 1}])
    assert result["comparables"][0]["conditions"] == "без НДС"


@pytest.mark.parametrize("bad", ["31.02.2026", "yesterday", "сентябрь 2026"])
def test_unrecognized_price_date_is_reported(bad):
    result = rf.comparative_approach(
        1, [{**M, "date": bad, "price": 100, "area_sqm": 1}, {**M, "price": 110, "area_sqm": 1}], context=C
    )

    assert any("дата цены не распознана" in check.lower() for check in result["checks"])


@pytest.mark.parametrize("good", ["2026-09-20", "20.09.2026", "2026-09-20T10:15:00"])
def test_valid_price_dates_pass(good):
    result = rf.comparative_approach(
        1, [{**M, "date": good, "price": 100, "area_sqm": 1}, {**M, "price": 110, "area_sqm": 1}], context=C
    )

    assert result["checks"] == []


def test_homogeneity_compares_unrounded_coefficient():
    result = variation([100, 160.88])

    assert result["homogeneous"] is False


def test_docs_offer_prices_are_guardrails():
    with open("docs/russia.md", encoding="utf-8") as handle:
        text = handle.read()

    assert "использование цен предложения и неоднородная выборка отмечаются в\n`checks`" not in text


# 10. Numeric robustness.


def test_small_manual_weight_does_not_divide_by_zero():
    result = rf.comparative_approach(1, [{"price": 100, "area_sqm": 1, "weight": 1e-8}])

    assert result["indicated_value"] == 100
    assert result["comparables"][0]["weight_share"] == 1.0


def test_huge_weights_keep_median_and_mean():
    result = rf.vehicle_comparative_approach(
        {}, [{"price_rub": 100, "weight": 1e308}, {"price_rub": 110, "weight": 1e308}]
    )

    assert result["weighted_median_price"] == 100
    assert result["weighted_mean_price"] == 105
    assert [item["weight_share"] for item in result["comparables"]] == [0.5, 0.5]


def test_braking_coefficient_and_chain_index_extreme_ratios():
    assert rf.braking_coefficient(1e-200, 1e-200, 1e200, 1e200)["braking_coefficient"] == 1.0
    assert math.isclose(rf.chain_index(1e-200, 1e200, 2)["chain_index"], 1.0, rel_tol=1e-9) is False
    assert math.isclose(rf.chain_index(1e-200, 1e200, 2)["chain_index"], 1e200, rel_tol=1e-9)


def test_inwood_near_zero_rate():
    assert rf.capital_recovery_rate(1e-14, 10, "inwood")["capitalization_rate_pct"] == pytest.approx(10, abs=1e-4)


def test_result_is_json_compliant():
    result = rf.vehicle_comparative_approach(
        {}, [{"price_rub": 100, "weight": 1e308}, {"price_rub": 110, "weight": 1e308}]
    )

    json.dumps(result, allow_nan=False)
