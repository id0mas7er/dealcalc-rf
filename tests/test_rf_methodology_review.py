"""Fixes from the Codex methodology review (dealcalc-rf-methodology-review.md), group A."""

import pytest

from dealcalc import rf
from dealcalc.rf._meta import STATUS_NOT_RECONCILED, STATUS_REVIEW

C = {"valuation_date": "2026-10-02", "value_type": "рыночная", "vat": "excluded"}
M = {"source": "S", "date": "2026-10-01", "price_type": "сделка"}


# D01. Salvage value is already inside the physical depreciation model.


@pytest.mark.parametrize("age,expected", [(0, 1_000_000), (5, 550_000), (10, 100_000)])
def test_physical_depreciation_and_residual_value_agree(age, expected):
    depreciation = rf.physical_depreciation(age, 10, 1_000_000, salvage_value=100_000)
    result = rf.residual_value(1_000_000, depreciation["total_pct"], 100_000)

    assert result["residual_value"] == expected


def test_residual_value_salvage_is_a_floor():
    result = rf.residual_value(1_000_000, 95, 100_000)

    assert result["residual_value"] == 100_000
    assert result["salvage_floor_applied"] is True


def test_residual_value_full_depreciation_with_disposal_cost():
    assert rf.residual_value(1_000_000, 100, -20_000)["residual_value"] == -20_000


# D02. External obsolescence: the base of the percent.


def test_external_obsolescence_percent_of_improvements():
    obsolescence = rf.external_obsolescence_cost_income(100e6, 80e6, land_value=40e6)

    assert obsolescence["external_obsolescence_pct"] == 20
    assert obsolescence["external_obsolescence_pct_of_improvements"] == pytest.approx(33.33, abs=0.01)
    result = rf.cost_approach(
        60e6, 40e6, external_depreciation_pct=obsolescence["external_obsolescence_pct_of_improvements"]
    )
    assert result["indicated_value"] == pytest.approx(80e6, abs=1)


def test_cost_approach_absolute_external_obsolescence():
    result = rf.cost_approach(60e6, 40e6, external_obsolescence_amount=20e6)

    assert result["indicated_value"] == 80e6
    assert result["depreciation"]["external_amount"] == 20e6


# D03. An impossible valuation date stops the assignment.


def test_invalid_valuation_date_stops_assignment():
    result = rf.check_assignment({
        "object_type": "real_estate", "object_description": "x", "rights": "x", "purpose": "x",
        "value_type": "рыночная", "value_premises": "x", "valuation_date": "2026-02-31",
    })

    assert result["can_proceed"] is False
    assert any("valuation_date" in item for item in result["missing_critical"])


# D04. Prices dated after the valuation date.


def test_prices_after_valuation_date_are_checked():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "date": "2030-01-01"},
         {**M, "price": 10e6, "area_sqm": 100, "date": "02.01.2030"}],
        context=C,
    )

    assert any("позже даты оценки" in check and "[1, 2]" in check for check in result["checks"])


def test_prices_before_valuation_date_pass():
    result = rf.comparative_approach(
        100, [{**M, "price": 10e6, "area_sqm": 100}, {**M, "price": 10.5e6, "area_sqm": 100}], context=C
    )

    assert result["checks"] == []


def test_price_collected_after_valuation_date_is_checked():
    """date — дата размещения, но цену видели позже даты оценки (ретроспектива):
    price_collected_at важнее date."""

    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "date": "2026-07-01", "price_collected_at": "2026-10-05"},
         {**M, "price": 10.5e6, "area_sqm": 100}],
        context=C,
    )

    assert any("позже даты оценки" in check and "[1]" in check for check in result["checks"])


def test_price_collected_before_valuation_date_passes():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "price_collected_at": "2026-10-01"},
         {**M, "price": 10.5e6, "area_sqm": 100}],
        context=C,
    )

    assert result["checks"] == []


# D05. Basis of capital in business valuation.


def _multiples(name, basis):
    return rf.business_multiples(
        [{**M, "value": 100e6, "metric": 10e6}, {**M, "value": 120e6, "metric": 12e6}],
        20e6, name, basis, context=C,
    )


def test_multiple_name_contradicting_basis_is_checked():
    assert any("EV" in check for check in _multiples("EV/EBITDA", "equity")["checks"])
    assert any("P/E" in check for check in _multiples("P/E", "invested_capital")["checks"])
    assert _multiples("EV/EBITDA", "invested_capital")["checks"] == []


def test_interest_value_from_invested_capital_needs_net_debt():
    with pytest.raises(ValueError, match="net_debt"):
        rf.business_interest_value(200e6, 25, value_basis="invested_capital")
    result = rf.business_interest_value(200e6, 25, value_basis="invested_capital", net_debt=80e6)

    assert result["equity_value_100pct"] == 120e6
    assert result["interest_value"] == 30e6


def test_interest_value_without_basis_is_checked():
    result = rf.business_interest_value(200e6, 25)

    assert any("value_basis" in check for check in result["checks"])


def test_unknown_obligations_outside_fcff_are_checked():
    unknown = rf.business_income_approach([10e6], 10, "invested_capital", terminal_value=100e6)
    confirmed = rf.business_income_approach(
        [10e6], 10, "invested_capital", terminal_value=100e6, obligations_not_in_flows=0
    )

    assert any("obligations_not_in_flows" in check for check in unknown["checks"])
    assert not any("obligations_not_in_flows" in check for check in confirmed["checks"])


# D06. Kind of the result against the type of value in the assignment.


def test_liquidation_value_with_market_context_is_checked():
    result = rf.asset_liquidation_value(
        10e6, 10, 12, 1, forced_sale_discount_pct=20, forced_sale_justification="x", context=C
    )

    assert any("ликвидационн" in check for check in result["checks"])


def test_liquidation_value_with_liquidation_context_passes():
    result = rf.asset_liquidation_value(
        10e6, 10, 12, 1, forced_sale_discount_pct=20, forced_sale_justification="x",
        context={**C, "value_type": "ликвидационная"},
    )

    assert result["checks"] == []


def test_dsd_needs_its_own_value_type():
    market = rf.actual_share_value(25, 100e6, 20e6, context=C)
    dsd = rf.actual_share_value(25, 100e6, 20e6, context={**C, "value_type": "действительная стоимость доли"})

    assert any("ДСД" in check for check in market["checks"])
    assert dsd["checks"] == []


# D07. Evidence chain and VAT basis of analogs.


def test_adjustment_evidence_and_identification_are_kept():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "address": "Адрес А", "listing_id": "A",
          "adjustments": [{"name": "Состояние", "type": "pct", "value": 10,
                           "source": "парные продажи", "date": "2026-10-01", "justification": "обоснование"}]}],
        context=C,
    )
    item = result["comparables"][0]
    step = item["adjustments"][0]

    assert (item["address"], item["listing_id"]) == ("Адрес А", "A")
    assert (step["source"], step["date"], step["justification"]) == ("парные продажи", "2026-10-01", "обоснование")


def test_mixed_vat_basis_of_analogs_is_checked():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "conditions": "Цена с НДС"},
         {**M, "price": 10e6, "area_sqm": 100, "conditions": "Цена без НДС"}],
        context=C,
    )

    assert any("НДС" in check for check in result["checks"])


def test_analog_vat_against_context_is_checked():
    result = rf.comparative_approach(
        100,
        [{**M, "price": 10e6, "area_sqm": 100, "vat": "included"},
         {**M, "price": 10.5e6, "area_sqm": 100, "vat": "included"}],
        context=C,
    )

    assert any("НДС" in check for check in result["checks"])


# D08. Reconciliation: zero weight does not hide divergence; unresolved has no value.


def test_zero_weight_does_not_hide_divergence():
    result = rf.reconcile_approaches({"comparative": 10e6, "income": 100e6}, {"comparative": 1, "income": 0}, 10)

    assert result["divergence_pct"] == 900
    assert result["status"] == STATUS_NOT_RECONCILED


def test_excluded_approach_with_justification():
    result = rf.reconcile_approaches(
        {"comparative": 10e6, "income": 100e6}, {"comparative": 1, "income": 0}, 10,
        justification="доходный подход: поток не относится к объекту",
    )

    assert result["status"] == STATUS_REVIEW
    assert result["reconciled_value"] == 10e6


def test_unresolved_reconciliation_has_no_final_value():
    result = rf.reconcile_approaches({"comparative": 10e6, "income": 100e6}, {"comparative": 0.5, "income": 0.5}, 10)

    assert result["reconciled_value"] is None
    assert result["weighted_value_diagnostic"] == 55e6


def test_excluded_approach_without_justification_is_checked():
    result = rf.reconcile_approaches({"comparative": 10e6, "income": 10.5e6}, {"comparative": 1, "income": 0}, 10)

    assert any("исключ" in check for check in result["checks"])


# D09. Model of combined depreciation.


def test_cost_approach_accepts_combined_depreciation():
    result = rf.cost_approach(60e6, 40e6, total_depreciation_pct=25)

    assert result["indicated_value"] == 85e6
    assert result["depreciation"]["model"] == "total"
    with pytest.raises(ValueError, match="total_depreciation_pct"):
        rf.cost_approach(60e6, 40e6, physical_depreciation_pct=10, total_depreciation_pct=25)


def test_multiplicative_model_is_named():
    assert rf.cost_approach(60e6, 40e6, physical_depreciation_pct=10)["depreciation"]["model"] == "multiplicative"


# D10. Coefficient of variation and automatic weights are heuristics.


def test_variation_is_descriptive():
    result = rf.comparative_approach(1, [{**M, "price": 100, "area_sqm": 1}, {**M, "price": 300, "area_sqm": 1}])

    assert "within_threshold" in result["variation"]
    assert "homogeneous" not in result["variation"]


def test_inverse_count_ignores_zero_steps():
    with_zero = rf.comparative_approach(
        1,
        [{**M, "price": 100, "area_sqm": 1, "adjustments": [
            {"name": "a", "type": "pct", "value": 20}, {"name": "b", "type": "pct", "value": 0}]},
         {**M, "price": 100, "area_sqm": 1}],
        weighting="inverse_count",
    )
    without = rf.comparative_approach(
        1,
        [{**M, "price": 100, "area_sqm": 1, "adjustments": [{"name": "a", "type": "pct", "value": 20}]},
         {**M, "price": 100, "area_sqm": 1}],
        weighting="inverse_count",
    )

    assert with_zero["indicated_value"] == without["indicated_value"]


def test_automatic_weights_carry_a_reminder():
    result = rf.comparative_approach(
        1, [{**M, "price": 100, "area_sqm": 1}, {**M, "price": 110, "area_sqm": 1}], weighting="inverse_gross"
    )

    assert any("эвристик" in note for note in result["guardrails"])


# D12. Spread of analogs and approaches is not an interval of value.


def test_spreads_are_named_as_spreads():
    comparative = rf.comparative_approach(1, [{**M, "price": 100, "area_sqm": 1}, {**M, "price": 110, "area_sqm": 1}])
    reconciled = rf.reconcile_approaches({"a": 100, "b": 110}, {"a": 0.5, "b": 0.5})

    assert "analogs_spread" in comparative and "indicated_value_range" not in comparative
    assert "approaches_spread" in reconciled and "value_range" not in reconciled
