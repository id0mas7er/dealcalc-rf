"""Test suite for the DealCalc engine.

Exact asserts where the formula is exact; ``pytest.approx(..., abs=0.10)``
for mortgage / IRR / composites. Composite analyzers (BRRRR,
rental_property_analysis) use frozen first-run snapshots as regression
baselines. ``mortgage`` and ``irr`` are cross-checked against
``numpy_financial`` directly so the engine is provably correct.
"""

import numpy_financial as npf
import pytest

from dealcalc import calculators as calc
from dealcalc import primitives as prim


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def test_monthly_mortgage_payment_matches_npf():
    got = prim.monthly_mortgage_payment(300000, 6.5, 30)
    expected = -npf.pmt(6.5 / 100 / 12, 360, 300000)
    assert got == pytest.approx(expected, abs=0.10)
    assert got == pytest.approx(1896.20, abs=0.10)


def test_monthly_mortgage_payment_zero_rate():
    assert prim.monthly_mortgage_payment(120000, 0, 10) == 1000.0


def test_effective_gross_income():
    assert prim.effective_gross_income(36000, 0, 5) == 34200.0


def test_net_operating_income():
    assert prim.net_operating_income(34200, 12000) == 22200.0


def test_amortization_summary():
    summary = prim.amortization_summary(300000, 6.5, 30)
    assert summary["monthly_payment"] == pytest.approx(1896.20, abs=0.10)
    assert summary["total_paid"] == pytest.approx(1896.20 * 360, abs=0.10 * 360)
    assert summary["total_interest"] == pytest.approx(
        summary["total_paid"] - 300000, abs=0.01
    )


# ---------------------------------------------------------------------------
# Group A — Offer / acquisition logic
# ---------------------------------------------------------------------------


def test_arv():
    assert calc.arv(200, 1500) == {"arv": 300000.0}


def test_seventy_percent_rule():
    assert calc.seventy_percent_rule(300000, 40000) == {"max_allowable_offer": 170000.0}


def test_mao():
    assert calc.mao(300000, 40000, wholesale_fee=10000) == {
        "max_allowable_offer": 160000.0
    }


def test_wholesale():
    assert calc.wholesale(300000, 40000, 10000) == {
        "buyer_max_offer": 170000.0,
        "assignment_fee": 10000.0,
        "max_offer_to_seller": 160000.0,
    }


# ---------------------------------------------------------------------------
# Group B — Metric helpers
# ---------------------------------------------------------------------------


def test_cap_rate():
    assert calc.cap_rate(24000, 400000) == {"cap_rate_pct": 6.0}


def test_cap_rate_zero_value():
    result = calc.cap_rate(24000, 0)
    assert result["cap_rate_pct"] is None
    assert "note" in result


def test_noi():
    assert calc.noi(36000, 12000, vacancy_pct=5) == {
        "effective_gross_income": 34200.0,
        "noi": 22200.0,
    }


def test_cash_on_cash():
    assert calc.cash_on_cash(6000, 60000) == {"coc_pct": 10.0}


def test_cash_on_cash_zero_invested():
    result = calc.cash_on_cash(6000, 0)
    assert result["coc_pct"] is None
    assert "note" in result


def test_dscr():
    assert calc.dscr(24000, 20000) == {"dscr": 1.20}


def test_gross_rent_multiplier():
    assert calc.gross_rent_multiplier(300000, 30000) == {"grm": 10.0}


# ---------------------------------------------------------------------------
# Group C — Composite analyzers
# ---------------------------------------------------------------------------


def test_mortgage():
    result = calc.mortgage(300000, 6.5, 30, annual_taxes=3600, annual_insurance=1200)
    assert result["monthly_pi"] == pytest.approx(1896.20, abs=0.10)
    assert result["monthly_piti"] == pytest.approx(2296.20, abs=0.10)


def test_mortgage_totals_match_npf():
    result = calc.mortgage(300000, 6.5, 30)
    expected_pi = -npf.pmt(6.5 / 100 / 12, 360, 300000)
    assert result["monthly_pi"] == pytest.approx(expected_pi, abs=0.10)
    assert result["total_paid"] == pytest.approx(result["monthly_pi"] * 360, abs=0.01)


def test_rental_cash_flow():
    assert calc.rental_cash_flow(2000, 600, 1000, vacancy_pct=5) == {
        "effective_monthly_income": 1900.0,
        "monthly_cash_flow": 300.0,
        "annual_cash_flow": 3600.0,
    }


def test_fix_and_flip():
    result = calc.fix_and_flip(
        150000,
        40000,
        280000,
        holding_costs=5000,
        closing_costs_buy=3000,
        financing_costs=7000,
        selling_costs_pct=8,
    )
    assert result["total_invested"] == 205000.0
    assert result["selling_costs"] == 22400.0
    assert result["net_profit"] == 52600.0
    assert result["roi_pct"] == pytest.approx(25.66, abs=0.10)


def test_fix_and_flip_annualized():
    result = calc.fix_and_flip(150000, 40000, 280000, project_months=6)
    assert result["annualized_roi_pct"] == pytest.approx(result["roi_pct"] * 2, abs=0.01)


def test_brrrr_snapshot():
    # Frozen first-run regression baseline.
    result = calc.brrrr(
        100000,
        30000,
        180000,
        75,
        7,
        30,
        1600,
        400,
        vacancy_pct=5,
        closing_costs=5000,
        holding_costs=3000,
    )
    assert result == {
        "total_cash_invested": 138000.0,
        "refinance_loan_amount": 135000.0,
        "cash_left_in_deal": 3000.0,
        "new_monthly_payment": 898.16,
        "monthly_cash_flow": 221.84,
        "post_refi_coc_pct": 88.74,
    }


def test_brrrr_all_capital_recovered():
    result = calc.brrrr(
        100000, 30000, 300000, 90, 7, 30, 1600, 400, closing_costs=0, holding_costs=0
    )
    assert result["post_refi_coc_pct"] is None
    assert "note" in result


def test_rental_property_analysis_snapshot():
    # Frozen first-run regression baseline.
    result = calc.rental_property_analysis(
        300000, 25, 7, 30, 2200, 700, vacancy_pct=5, closing_costs=9000
    )
    assert result == {
        "loan_amount": 225000.0,
        "total_cash_invested": 84000.0,
        "monthly_payment": 1496.93,
        "effective_monthly_income": 2090.0,
        "monthly_cash_flow": -106.93,
        "annual_cash_flow": -1283.16,
        "noi_annual": 16680.0,
        "cap_rate_pct": 5.56,
        "cash_on_cash_pct": -1.53,
        "dscr": 0.93,
        "grm": 11.36,
    }


def test_multifamily_analysis():
    result = calc.multifamily_analysis(
        8, 1200, 38000, 1200000, vacancy_pct=5, market_cap_rate_pct=6
    )
    assert result["gross_potential_rent"] == 115200.0
    assert result["effective_gross_income"] == 109440.0
    assert result["noi_annual"] == 71440.0
    assert result["cap_rate_pct"] == pytest.approx(5.95, abs=0.01)
    assert result["price_per_unit"] == 150000.0
    assert result["value_by_market_cap"] == pytest.approx(1190666.67, abs=0.01)


def test_irr():
    assert calc.irr([-250000, 100000, 150000, 200000, 250000, 300000])[
        "irr_pct"
    ] == pytest.approx(56.72, abs=0.10)


def test_irr_matches_npf():
    flows = [-250000, 100000, 150000, 200000, 250000, 300000]
    got = calc.irr(flows)["irr_pct"]
    assert got == pytest.approx(npf.irr(flows) * 100, abs=0.01)


def test_irr_no_solution():
    result = calc.irr([100, 200, 300])  # all positive — no sign change
    assert result["irr_pct"] is None
    assert "note" in result


def test_build_cash_flows():
    series = calc.build_cash_flows(250000, [100000, 150000, 200000], sale_proceeds=50000)
    assert series == [-250000, 100000, 150000, 250000]


# ---------------------------------------------------------------------------
# Group D — Cost estimators
# ---------------------------------------------------------------------------


def test_closing_costs():
    result = calc.closing_costs(
        title_fees=1500, lender_fees=1200, points_pct=1, loan_amount=240000, prepaids=2000
    )
    assert result["points_cost"] == 2400.0
    assert result["total_closing_costs"] == 7100.0


def test_construction_cost():
    result = calc.construction_cost(2000, 150, contingency_pct=10)
    assert result["base_cost"] == 300000.0
    assert result["contingency"] == 30000.0
    assert result["total_cost"] == 330000.0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_negative_price_raises():
    with pytest.raises(ValueError):
        calc.seventy_percent_rule(-300000, 40000)


def test_negative_purchase_price_raises():
    with pytest.raises(ValueError):
        calc.rental_property_analysis(-300000, 25, 7, 30, 2200, 700)


def test_zero_term_raises():
    with pytest.raises(ValueError):
        prim.monthly_mortgage_payment(300000, 6.5, 0)
