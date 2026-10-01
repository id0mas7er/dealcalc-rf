"""Local (stdio) MCP server exposing the DealCalc engine.

Each calculator in :mod:`dealcalc.calculators` is surfaced as a FastMCP
tool with the same signature, units, and a clear docstring (the docstring
is the description the AI agent sees). Run locally with::

    python mcp_server/server.py

which serves over stdio for use with Claude Desktop / Claude Code.
"""

from __future__ import annotations

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from dealcalc import calculators as calc
from dealcalc import rf

mcp = FastMCP("dealcalc-rf")


# ---------------------------------------------------------------------------
# Group A — Offer / acquisition logic
# ---------------------------------------------------------------------------


@mcp.tool()
def arv(comp_price_per_sqft: float, subject_sqft: float) -> dict:
    """After-repair value from a comparable's price per square foot.

    arv = comp_price_per_sqft * subject_sqft. Returns {arv}.
    """
    return calc.arv(comp_price_per_sqft, subject_sqft)


@mcp.tool()
def seventy_percent_rule(arv: float, rehab_cost: float, rule_pct: float = 70) -> dict:
    """Classic 70% rule maximum offer = arv*(rule_pct/100) - rehab_cost.

    Returns {max_allowable_offer}.
    """
    return calc.seventy_percent_rule(arv, rehab_cost, rule_pct)


@mcp.tool()
def mao(
    arv: float,
    rehab_cost: float,
    rule_pct: float = 70,
    desired_profit: float = 0,
    holding_costs: float = 0,
    closing_costs: float = 0,
    wholesale_fee: float = 0,
) -> dict:
    """Maximum allowable offer with explicit cost/profit deductions.

    arv*(rule_pct/100) - rehab_cost - desired_profit - holding_costs
    - closing_costs - wholesale_fee. Returns {max_allowable_offer}.
    """
    return calc.mao(
        arv,
        rehab_cost,
        rule_pct,
        desired_profit,
        holding_costs,
        closing_costs,
        wholesale_fee,
    )


@mcp.tool()
def wholesale(
    arv: float, rehab_cost: float, assignment_fee: float, buyer_rule_pct: float = 70
) -> dict:
    """Wholesale offer math for the buyer's max, your fee, and seller offer.

    buyer_max = arv*(buyer_rule_pct/100) - rehab_cost;
    max_offer_to_seller = buyer_max - assignment_fee.
    Returns {buyer_max_offer, assignment_fee, max_offer_to_seller}.
    """
    return calc.wholesale(arv, rehab_cost, assignment_fee, buyer_rule_pct)


# ---------------------------------------------------------------------------
# Group B — Metric helpers
# ---------------------------------------------------------------------------


@mcp.tool()
def cap_rate(noi_annual: float, property_value: float) -> dict:
    """Capitalization rate = NOI / property value * 100. Returns {cap_rate_pct}."""
    return calc.cap_rate(noi_annual, property_value)


@mcp.tool()
def noi(
    gross_rent_annual: float,
    operating_expenses_annual: float,
    other_income_annual: float = 0,
    vacancy_pct: float = 0,
) -> dict:
    """Net operating income with effective gross income breakout.

    egi = (gross_rent_annual + other_income_annual)*(1 - vacancy_pct/100);
    noi = egi - operating_expenses_annual. Returns {effective_gross_income, noi}.
    """
    return calc.noi(
        gross_rent_annual, operating_expenses_annual, other_income_annual, vacancy_pct
    )


@mcp.tool()
def cash_on_cash(annual_pre_tax_cash_flow: float, total_cash_invested: float) -> dict:
    """Cash-on-cash return = annual cash flow / total cash invested * 100.

    Returns {coc_pct}; if total_cash_invested is 0, coc_pct is None with a note.
    """
    return calc.cash_on_cash(annual_pre_tax_cash_flow, total_cash_invested)


@mcp.tool()
def dscr(noi_annual: float, annual_debt_service: float) -> dict:
    """Debt-service coverage ratio = NOI / annual debt service. Returns {dscr}."""
    return calc.dscr(noi_annual, annual_debt_service)


@mcp.tool()
def gross_rent_multiplier(price: float, gross_annual_rent: float) -> dict:
    """Gross rent multiplier = price / gross annual rent. Returns {grm}."""
    return calc.gross_rent_multiplier(price, gross_annual_rent)


# ---------------------------------------------------------------------------
# Group C — Composite analyzers
# ---------------------------------------------------------------------------


@mcp.tool()
def mortgage(
    loan_amount: float,
    annual_rate_pct: float,
    term_years: float,
    annual_taxes: float = 0,
    annual_insurance: float = 0,
    monthly_hoa: float = 0,
) -> dict:
    """Mortgage payment with PITI and lifetime totals.

    monthly_piti = monthly_pi + annual_taxes/12 + annual_insurance/12 + monthly_hoa.
    Returns {monthly_pi, monthly_piti, total_interest, total_paid}.
    """
    return calc.mortgage(
        loan_amount,
        annual_rate_pct,
        term_years,
        annual_taxes,
        annual_insurance,
        monthly_hoa,
    )


@mcp.tool()
def rental_cash_flow(
    monthly_rent: float,
    monthly_operating_expenses: float,
    monthly_debt_service: float,
    vacancy_pct: float = 0,
    other_monthly_income: float = 0,
) -> dict:
    """Monthly and annual rental cash flow.

    effective = (monthly_rent + other_monthly_income)*(1 - vacancy_pct/100);
    monthly_cash_flow = effective - monthly_operating_expenses - monthly_debt_service.
    Returns {effective_monthly_income, monthly_cash_flow, annual_cash_flow}.
    """
    return calc.rental_cash_flow(
        monthly_rent,
        monthly_operating_expenses,
        monthly_debt_service,
        vacancy_pct,
        other_monthly_income,
    )


@mcp.tool()
def fix_and_flip(
    purchase_price: float,
    rehab_cost: float,
    arv: float,
    holding_costs: float = 0,
    closing_costs_buy: float = 0,
    financing_costs: float = 0,
    selling_costs_pct: float = 8,
    project_months: Optional[float] = None,
) -> dict:
    """Fix-and-flip profitability and ROI.

    total_invested = purchase+rehab+holding+closing_buy+financing;
    selling_costs = arv*selling_costs_pct/100;
    net_profit = arv - total_invested - selling_costs; roi_pct = net_profit/total_invested*100.
    Returns {total_invested, selling_costs, net_profit, roi_pct, annualized_roi_pct}.
    """
    return calc.fix_and_flip(
        purchase_price,
        rehab_cost,
        arv,
        holding_costs,
        closing_costs_buy,
        financing_costs,
        selling_costs_pct,
        project_months,
    )


@mcp.tool()
def brrrr(
    purchase_price: float,
    rehab_cost: float,
    arv: float,
    refinance_ltv_pct: float,
    loan_rate_pct: float,
    loan_term_years: float,
    monthly_rent: float,
    monthly_operating_expenses: float,
    vacancy_pct: float = 0,
    closing_costs: float = 0,
    holding_costs: float = 0,
) -> dict:
    """Buy, Rehab, Rent, Refinance, Repeat (BRRRR) analysis.

    Computes total cash invested, the cash-out refinance loan, capital left in the
    deal, the new payment, monthly cash flow, and post-refinance cash-on-cash.
    Returns {total_cash_invested, refinance_loan_amount, cash_left_in_deal,
    new_monthly_payment, monthly_cash_flow, post_refi_coc_pct}.
    """
    return calc.brrrr(
        purchase_price,
        rehab_cost,
        arv,
        refinance_ltv_pct,
        loan_rate_pct,
        loan_term_years,
        monthly_rent,
        monthly_operating_expenses,
        vacancy_pct,
        closing_costs,
        holding_costs,
    )


@mcp.tool()
def rental_property_analysis(
    purchase_price: float,
    down_payment_pct: float,
    annual_rate_pct: float,
    term_years: float,
    monthly_rent: float,
    monthly_operating_expenses: float,
    vacancy_pct: float = 0,
    closing_costs: float = 0,
    other_monthly_income: float = 0,
) -> dict:
    """Flagship rental aggregate: financing, cash flow, and key metrics.

    Returns {loan_amount, total_cash_invested, monthly_payment,
    effective_monthly_income, monthly_cash_flow, annual_cash_flow, noi_annual,
    cap_rate_pct, cash_on_cash_pct, dscr, grm}.
    """
    return calc.rental_property_analysis(
        purchase_price,
        down_payment_pct,
        annual_rate_pct,
        term_years,
        monthly_rent,
        monthly_operating_expenses,
        vacancy_pct,
        closing_costs,
        other_monthly_income,
    )


@mcp.tool()
def multifamily_analysis(
    num_units: int,
    avg_monthly_rent: float,
    annual_operating_expenses: float,
    purchase_price: float,
    vacancy_pct: float = 0,
    market_cap_rate_pct: Optional[float] = None,
) -> dict:
    """Multifamily underwriting: GPR, EGI, NOI, cap rate, and valuation.

    Returns {gross_potential_rent, effective_gross_income, noi_annual,
    cap_rate_pct, price_per_unit, value_by_market_cap}.
    """
    return calc.multifamily_analysis(
        num_units,
        avg_monthly_rent,
        annual_operating_expenses,
        purchase_price,
        vacancy_pct,
        market_cap_rate_pct,
    )


@mcp.tool()
def irr(cash_flows: List[float]) -> dict:
    """Internal rate of return for a series of periodic cash flows.

    Period 0 is the (negative) initial investment; later entries are net cash
    flows, with the final entry typically including sale proceeds.
    Returns {irr_pct} (None with a note if there is no real solution).
    """
    return calc.irr(cash_flows)


# ---------------------------------------------------------------------------
# Group D — Cost estimators
# ---------------------------------------------------------------------------


@mcp.tool()
def closing_costs(
    title_fees: float = 0,
    lender_fees: float = 0,
    points_pct: float = 0,
    loan_amount: float = 0,
    prepaids: float = 0,
    other: float = 0,
) -> dict:
    """Estimate buyer closing costs including discount/origination points.

    points_cost = loan_amount*points_pct/100;
    total = title_fees + lender_fees + points_cost + prepaids + other.
    Returns {points_cost, total_closing_costs, breakdown}.
    """
    return calc.closing_costs(
        title_fees, lender_fees, points_pct, loan_amount, prepaids, other
    )


@mcp.tool()
def construction_cost(
    square_feet: float, cost_per_sqft: float, contingency_pct: float = 0
) -> dict:
    """Construction/rehab budget with a contingency allowance.

    base = square_feet*cost_per_sqft; contingency = base*contingency_pct/100;
    total = base + contingency. Returns {base_cost, contingency, total_cost}.
    """
    return calc.construction_cost(square_feet, cost_per_sqft, contingency_pct)


# ---------------------------------------------------------------------------
# Russian Federation valuation aids
# ---------------------------------------------------------------------------


@mcp.tool()
def rf_comparative_approach(
    subject_area_sqm: float, comparables: List[dict], currency: str = "RUB"
) -> dict:
    """Calculate an indicated value from adjusted comparable unit prices.

    Each comparable contains price and area_sqm, with optional adjustment_pct,
    weight, source, and date. Adjustments and weights are supplied by the
    appraiser; the tool does not impose universal market coefficients.
    """
    return rf.comparative_approach(subject_area_sqm, comparables, currency)


@mcp.tool()
def rf_income_capitalization(
    noi_annual: float, cap_rate_pct: float, currency: str = "RUB"
) -> dict:
    """Calculate value by direct capitalization of annual NOI."""
    return rf.income_capitalization(noi_annual, cap_rate_pct, currency)


@mcp.tool()
def rf_dcf_valuation(
    cash_flows: List[float],
    discount_rate_pct: float,
    terminal_value: float = 0,
    currency: str = "RUB",
) -> dict:
    """Calculate the present value of annual cash flows and terminal value."""
    return rf.dcf_valuation(cash_flows, discount_rate_pct, terminal_value, currency)


@mcp.tool()
def rf_cost_approach(
    replacement_cost: float,
    land_value: float = 0,
    physical_depreciation_pct: float = 0,
    functional_depreciation_pct: float = 0,
    external_depreciation_pct: float = 0,
    currency: str = "RUB",
) -> dict:
    """Calculate residual improvements plus land under an explicit depreciation model."""
    return rf.cost_approach(
        replacement_cost,
        land_value,
        physical_depreciation_pct,
        functional_depreciation_pct,
        external_depreciation_pct,
        currency,
    )


@mcp.tool()
def rf_reconcile_approaches(
    approach_values: dict,
    weights: Optional[dict] = None,
    currency: str = "RUB",
) -> dict:
    """Reconcile indicated values using analyst-supplied positive weights."""
    return rf.reconcile_approaches(approach_values, weights, currency)


if __name__ == "__main__":
    mcp.run()  # stdio transport
