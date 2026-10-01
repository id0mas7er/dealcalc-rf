"""Local (stdio) MCP server exposing the DealCalc RF engine.

Each function in :mod:`dealcalc.rf` is surfaced as a FastMCP tool with the
same signature, units, and a clear docstring (the docstring is the
description the AI agent sees). Run locally with::

    python mcp_server/server.py

which serves over stdio for use with Claude Desktop / Claude Code.
"""

from __future__ import annotations

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from dealcalc import rf

mcp = FastMCP("dealcalc-rf")


# ---------------------------------------------------------------------------
# Russian Federation valuation aids
# ---------------------------------------------------------------------------


@mcp.tool()
def rf_comparative_approach(
    subject_area_sqm: float, comparables: List[dict], currency: str = "RUB"
) -> dict:
    """Calculate an indicated value from adjusted comparable unit prices.

    Each comparable contains price and area_sqm, with optional adjustments,
    weight, source, and date. adjustments is a list of {"name", "type",
    "value"} steps applied in order to the price per m²: type "pct" is a
    percent, "abs" is RUB per m². Put the bargaining discount first. The
    result shows every step, net and gross adjustment, and the coefficient of
    variation against the 33% threshold. Adjustments and weights are supplied
    by the appraiser; the tool does not impose universal market coefficients.
    Other step types: {"type": "param", "subject", "analog", "exponent"}
    multiplies by (subject / analog) ** exponent (braking coefficient);
    {"type": "depreciation", "analog_pct", "subject_pct"} multiplies by
    (1 - subject_pct/100) / (1 - analog_pct/100) to compare wear.
    """
    return rf.comparative_approach(subject_area_sqm, comparables, currency)


@mcp.tool()
def rf_income_capitalization(
    noi_annual: float, cap_rate_pct: float, currency: str = "RUB"
) -> dict:
    """Calculate value by direct capitalization of annual NOI."""
    return rf.income_capitalization(noi_annual, cap_rate_pct, currency)


@mcp.tool()
def rf_net_operating_income(
    potential_gross_income: Optional[float] = None,
    rentable_area_sqm: Optional[float] = None,
    rent_rate_sqm_year: Optional[float] = None,
    vacancy_pct: float = 0,
    collection_loss_pct: float = 0,
    other_income_annual: float = 0,
    operating_expenses: Optional[List[dict]] = None,
    currency: str = "RUB",
) -> dict:
    """Build annual NOI: potential gross income (ПВД) -> effective gross
    income (ДВД) -> net operating income (ЧОД).

    Pass potential_gross_income, or rentable_area_sqm and rent_rate_sqm_year
    (RUB per m² per year). ДВД = ПВД × (1 - vacancy) × (1 - collection loss)
    + other income. operating_expenses is a list of {"name", "type", "value"}
    items: "abs" is RUB per year, "pct" is a percent of ДВД."""
    return rf.net_operating_income(
        potential_gross_income,
        rentable_area_sqm,
        rent_rate_sqm_year,
        vacancy_pct,
        collection_loss_pct,
        other_income_annual,
        operating_expenses,
        currency,
    )


@mcp.tool()
def rf_cap_rate_extraction(comparables: List[dict]) -> dict:
    """Extract a market capitalization rate from comparable sales.

    Each comparable contains price and annual noi, with optional source and
    date. Returns each rate, mean, median, range and the coefficient of
    variation against the 33% threshold; the appraiser chooses the rate."""
    return rf.cap_rate_extraction(comparables)


@mcp.tool()
def rf_gross_rent_multiplier(
    comparables: List[dict],
    subject_gross_income: Optional[float] = None,
    statistic: str = "mean",
    currency: str = "RUB",
) -> dict:
    """Value by the gross rent multiplier (price / annual gross income).

    Each comparable contains price and gross_income, with optional source and
    date. Use the same income basis (potential or effective gross income) for
    comparables and subject. With subject_gross_income the indicated value is
    the "mean" or "median" multiplier times that income."""
    return rf.gross_rent_multiplier(comparables, subject_gross_income, statistic, currency)


@mcp.tool()
def rf_npv(cash_flows: List[float], discount_rate_pct: float) -> dict:
    """Net present value; cash_flows[0] is period 0 (usually the investment).
    Returns the discount factor and present value of every period."""
    return rf.npv(cash_flows, discount_rate_pct)


@mcp.tool()
def rf_irr(cash_flows: List[float]) -> dict:
    """Internal rate of return in percent; cash_flows[0] is period 0 and the
    flows must contain both negative and positive values."""
    return rf.irr(cash_flows)


@mcp.tool()
def rf_dcf_valuation(
    cash_flows: List[float],
    discount_rate_pct: float,
    terminal_value: float = 0,
    currency: str = "RUB",
    mid_year: bool = False,
) -> dict:
    """Calculate the present value of annual cash flows and terminal value.

    Cash flows are discounted at the end of each year, or at its middle when
    mid_year is true; the terminal value at the end of the last year."""
    return rf.dcf_valuation(
        cash_flows, discount_rate_pct, terminal_value, currency, mid_year
    )


@mcp.tool()
def rf_cost_approach(
    replacement_cost: float,
    land_value: float = 0,
    physical_depreciation_pct: float = 0,
    functional_depreciation_pct: float = 0,
    external_depreciation_pct: float = 0,
    entrepreneurial_profit_pct: float = 0,
    currency: str = "RUB",
) -> dict:
    """Calculate land plus improvements: replacement cost with entrepreneurial
    profit, reduced by physical, functional and external depreciation combined
    multiplicatively: 1 - (1-phys)(1-func)(1-ext)."""
    return rf.cost_approach(
        replacement_cost,
        land_value,
        physical_depreciation_pct,
        functional_depreciation_pct,
        external_depreciation_pct,
        entrepreneurial_profit_pct,
        currency,
    )


@mcp.tool()
def rf_reconcile_approaches(
    approach_values: dict,
    weights: Optional[dict] = None,
    currency: str = "RUB",
) -> dict:
    """Reconcile indicated values using analyst-supplied positive weights.

    Weights must sum to 1; without weights all approaches get equal weight."""
    return rf.reconcile_approaches(approach_values, weights, currency)


@mcp.tool()
def rf_vehicle_comparative_approach(
    subject: dict,
    comparables: List[dict],
    currency: str = "RUB",
    max_year_diff: Optional[float] = 3,
    max_mileage_diff: Optional[float] = 100_000,
) -> dict:
    """Estimate a vehicle from matched and explicitly adjusted comparables.

    The subject and comparables use normalized fields such as brand, model,
    year, mileage_km, and price_rub. Optional adjustments is a list of
    {"name", "type", "value"} steps applied in order: type "pct" is a percent,
    "abs" is RUB. Put the bargaining discount first. The result shows every
    step, net and gross adjustment, and the coefficient of variation against
    the 33% threshold. No automatic depreciation coefficient is imposed.
    Other step types: {"type": "param", "subject", "analog", "exponent"}
    multiplies by (subject / analog) ** exponent (braking coefficient);
    {"type": "depreciation", "analog_pct", "subject_pct"} multiplies by
    (1 - subject_pct/100) / (1 - analog_pct/100) to compare wear.
    """
    return rf.vehicle_comparative_approach(
        subject,
        comparables,
        currency,
        max_year_diff,
        max_mileage_diff,
    )


@mcp.tool()
def rf_braking_coefficient(
    price_1: float, param_1: float, price_2: float, param_2: float
) -> dict:
    """Braking coefficient b = ln(price_2/price_1) / ln(param_2/param_1) of a
    parameter from two analogs that differ only in this parameter. Use it as
    the exponent of a "param" adjustment step."""
    return rf.braking_coefficient(price_1, param_1, price_2, param_2)


@mcp.tool()
def rf_new_equivalent_price(price: float, total_depreciation_pct: float) -> dict:
    """Price a used analog would have as new:
    price / (1 - total_depreciation_pct / 100)."""
    return rf.new_equivalent_price(price, total_depreciation_pct)


if __name__ == "__main__":
    mcp.run()  # stdio transport
