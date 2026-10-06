"""Fixes from the third external review (0.3.1)."""

import json

import pytest

from dealcalc.rf import (
    asset_liquidation_value,
    braking_coefficient,
    capital_recovery_rate,
    chain_index,
    cost_from_price,
    dcf_valuation,
    indexed_replacement_cost,
    load_listings,
    normalize_listing,
    npv,
    reconcile_approaches,
    vehicle_comparative_approach,
)

FULL_CONTEXT = {"valuation_date": "2026-10-01", "value_type": "рыночная"}


# 1. Capital recovery with the share of value change.


def test_capital_recovery_share_of_value_change():
    full = capital_recovery_rate(10, 5, "inwood")
    partial = capital_recovery_rate(10, 5, "inwood", value_change_pct=40)

    sff = 0.1 / (1.1 ** 5 - 1)
    assert full["capitalization_rate_pct"] == pytest.approx((0.1 + sff) * 100, abs=1e-4)
    assert partial["capitalization_rate_pct"] == pytest.approx((0.1 + 0.4 * sff) * 100, abs=1e-4)
    assert partial["value_change_pct"] == 40
    assert partial["recovery_rate_pct"] == pytest.approx(0.4 * sff * 100, abs=1e-4)


def test_capital_recovery_value_growth_lowers_rate():
    result = capital_recovery_rate(12, 10, "ring", value_change_pct=-20)

    assert result["capitalization_rate_pct"] == pytest.approx(12 - 20 / 10, abs=1e-4)


def test_capital_recovery_default_full_loss_is_reminded():
    result = capital_recovery_rate(12, 20, "ring")

    assert result["value_change_pct"] == 100
    assert any("value_change_pct" in note for note in result["guardrails"])
    assert not any("value_change_pct" in note for note in capital_recovery_rate(
        12, 20, "ring", value_change_pct=100)["guardrails"])


def test_capital_recovery_rejects_change_above_100():
    with pytest.raises(ValueError, match="value_change_pct"):
        capital_recovery_rate(12, 20, "ring", value_change_pct=120)


# 2. Liquidation value: discount for the forced nature of the sale.


def test_liquidation_without_forced_discount_warns_time_value_only():
    result = asset_liquidation_value(1_000_000, 15, 6, 2)

    assert result["liquidation_discount_pct"] == pytest.approx(4.55, abs=0.01)
    assert result["forced_sale_discount_pct"] is None
    assert any("вынужденност" in note for note in result["guardrails"])


def test_liquidation_with_forced_discount():
    result = asset_liquidation_value(
        1_000_000, 15, 6, 2,
        forced_sale_discount_pct=20,
        forced_sale_justification="эластичность спроса по данным банка",
    )

    factor = 1.15 ** (-4 / 12)
    assert result["liquidation_value"] == pytest.approx(1_000_000 * factor * 0.8, abs=0.01)
    assert result["total_discount_pct"] == pytest.approx((1 - factor * 0.8) * 100, abs=0.01)
    assert result["forced_sale_justification"] == "эластичность спроса по данным банка"
    assert not any("вынужденност" in note for note in result["guardrails"])


def test_liquidation_forced_discount_requires_justification():
    with pytest.raises(ValueError, match="forced_sale_justification"):
        asset_liquidation_value(1_000_000, 15, 6, 2, forced_sale_discount_pct=20)
    with pytest.raises(ValueError, match="forced_sale_discount_pct"):
        asset_liquidation_value(1_000_000, 15, 6, 2, forced_sale_discount_pct=100, forced_sale_justification="x")


# 3. Unknown price type and row numbers in import errors.


def test_unknown_price_type_is_left_empty_with_warning():
    listing = normalize_listing({"Цена": "1 000 000", "Тип цены": "Продажа"}, source="avito")

    assert listing["price_type"] == ""
    assert any("Продажа" in note for note in listing["import_warnings"])


def test_load_listings_reports_row_number(tmp_path):
    path = tmp_path / "listings.csv"
    path.write_text("Цена;Площадь\n1000000;40\n0;41\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 3"):
        load_listings(str(path), source="avito")


def test_load_listings_json_reports_item_number(tmp_path):
    path = tmp_path / "listings.json"
    path.write_text(json.dumps([{"price": 1}, {"price": "abc"}]), encoding="utf-8")

    with pytest.raises(ValueError, match="item 2"):
        load_listings(str(path), source="avito")


def test_plain_date_column_is_the_publication_date():
    # Решение оценщика 06.10.2026 (ревью 9) заменило решение 0.3.1: «Дата» —
    # дата размещения, а не дата сбора.
    listing = normalize_listing({"price": 1_000, "Дата": "2026-09-01"}, source="avito")

    assert listing["date"] == "2026-09-01"


# 4. VAT treatment in the context against the VAT rate of the calculation.


def test_vat_excluded_context_with_positive_rate_is_checked():
    result = indexed_replacement_cost(
        10_000, [{"name": "Индекс", "value": 1.2}], vat_pct=22,
        context={**FULL_CONTEXT, "vat": "excluded"},
    )

    assert any("НДС" in check for check in result["checks"])


def test_vat_included_context_with_zero_rate_is_checked():
    result = cost_from_price(
        1_000_000, profitability_pct=10, vat_pct=0, context={**FULL_CONTEXT, "vat": "included"}
    )

    assert any("НДС" in check for check in result["checks"])


def test_vat_rate_mismatch_with_context_is_checked():
    result = cost_from_price(
        1_000_000, profitability_pct=10, vat_pct=20,
        context={**FULL_CONTEXT, "vat": "included", "vat_rate_pct": 22},
    )

    assert any("22" in check and "20" in check for check in result["checks"])


def test_consistent_vat_has_no_vat_check():
    result = cost_from_price(
        1_000_000, profitability_pct=10, vat_pct=22,
        context={**FULL_CONTEXT, "vat": "included", "vat_rate_pct": 22},
    )

    assert not any("НДС" in check for check in result["checks"])


# 5. No context reminder for auxiliary calculations.


def test_auxiliary_calculations_have_no_context_reminder():
    for result in (braking_coefficient(100, 50, 200, 80), chain_index(100, 121, 2)):
        assert not any("context" in note for note in result["guardrails"])
    assert any("context" in note for note in npv([-100, 60, 60], 10)["guardrails"])


# 6. Period of the first cash flow in DCF.


def test_dcf_first_cash_flow_period_zero_matches_npv():
    flows = [-100, 60, 60]
    result = dcf_valuation(flows, 10, first_cash_flow_period=0)

    assert result["first_cash_flow_period"] == 0
    assert result["indicated_value"] == npv(flows, 10)["npv"]


def test_dcf_first_period_zero_terminal_at_last_flow():
    result = dcf_valuation([0, 0], 10, terminal_value=110, first_cash_flow_period=0)

    assert result["terminal_discount_period"] == 1
    assert result["terminal_present_value"] == 100.0


def test_dcf_rejects_bad_first_period():
    with pytest.raises(ValueError, match="first_cash_flow_period"):
        dcf_valuation([100], 10, first_cash_flow_period=2)
    with pytest.raises(ValueError, match="mid_year"):
        dcf_valuation([100], 10, first_cash_flow_period=0, mid_year=True)


# 7. Built-in model dictionary and synonyms from a file.


@pytest.mark.parametrize(
    "subject,comparable",
    [
        ({"brand": "Хендай", "model": "Солярис"}, {"brand": "Hyundai", "model": "Solaris"}),
        ({"brand": "Хендай", "model": "Крета"}, {"brand": "Hyundai", "model": "Creta"}),
        ({"brand": "Грейт Волл", "model": "Hover"}, {"brand": "Great Wall", "model": "Hover"}),
        ({"brand": "Nissan", "model": "X-Trail"}, {"brand": "Ниссан", "model": "X Trail"}),
        ({"brand": "Nissan", "model": "Х-Трейл"}, {"brand": "Nissan", "model": "X-Trail"}),
    ],
)
def test_builtin_model_dictionary(subject, comparable):
    result = vehicle_comparative_approach(subject, [{**comparable, "price_rub": 1_000_000}])

    assert result["sample_size"] == 1


def test_contains_match_with_dictionary_phrase():
    result = vehicle_comparative_approach(
        {"brand": "Nissan", "model": "Х-Трейл"},
        [{"brand": "Nissan", "model": "X-Trail T32", "price_rub": 1_000_000}],
        match="contains",
    )

    assert result["sample_size"] == 1


def test_synonyms_file(tmp_path):
    path = tmp_path / "synonyms.json"
    path.write_text(
        json.dumps({"brands": {"sollers": ["соллерс"]}, "models": {"ceed": ["сид"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    comparables = [{"brand": "Sollers", "model": "Ceed", "price_rub": 1_000_000}]

    with pytest.raises(ValueError, match="no comparable"):
        vehicle_comparative_approach({"brand": "Соллерс", "model": "Сид"}, comparables)
    result = vehicle_comparative_approach(
        {"brand": "Соллерс", "model": "Сид"}, comparables, synonyms_file=str(path)
    )

    assert result["sample_size"] == 1


# 8. Reconciliation weights are reported as given.


def test_reconcile_reports_weights_as_given():
    third = 1 / 3
    result = reconcile_approaches(
        {"a": 100, "b": 101, "c": 102}, {"a": third, "b": third, "c": third}, 10
    )

    assert sum(result["weights"].values()) == pytest.approx(1, abs=1e-12)
