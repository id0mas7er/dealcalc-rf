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
def rf_check_assignment(assignment: dict) -> dict:
    """Check the valuation assignment before any calculation (ФСО III, IV).

    assignment: object_type (real_estate | business | machinery | vehicle),
    object_description, rights, purpose, value_type (рыночная,
    инвестиционная, равновесная, ликвидационная), value_premises,
    valuation_date (YYYY-MM-DD) and recommended fields for the object type.
    Missing critical items give the status "недостаточно данных". Call it
    first; do not start with a formula."""
    return rf.check_assignment(assignment)


@mcp.tool()
def rf_gordon_terminal_value(
    cash_flow_next: float, discount_rate_pct: float, growth_rate_pct: float
) -> dict:
    """Terminal value by the constant-growth model TV = CF(n+1) / (r - g);
    requires r > g, a stable flow and a long or unlimited useful life."""
    return rf.gordon_terminal_value(cash_flow_next, discount_rate_pct, growth_rate_pct)


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
    weights: dict,
    max_divergence_pct: float,
    justification: Optional[str] = None,
    currency: str = "RUB",
) -> dict:
    """Reconcile indicated values with appraiser-supplied weights (sum 1).

    No default weights: mechanical averaging is not allowed. A weight of 0
    excludes an approach. max_divergence_pct is the appraiser's threshold of
    material divergence ((max - min) / min); above it the result is "not
    reconciled automatically" unless a justification is given."""
    return rf.reconcile_approaches(
        approach_values, weights, max_divergence_pct, justification, currency
    )


@mcp.tool()
def rf_vehicle_comparative_approach(
    subject: dict,
    comparables: List[dict],
    currency: str = "RUB",
    max_year_diff: Optional[float] = None,
    max_mileage_diff: Optional[float] = None,
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


@mcp.tool()
def rf_parameter_unit_price(
    price_1: float, param_1: float, price_2: float, param_2: float
) -> dict:
    """"Price" of one unit of a parameter g = (price_1 - price_2) /
    (param_1 - param_2) from two analogs that differ only in this parameter.
    Use g * (subject_param - analog_param) as an "abs" adjustment step."""
    return rf.parameter_unit_price(price_1, param_1, price_2, param_2)


@mcp.tool()
def rf_chain_index(price_start: float, price_end: float, periods: float) -> dict:
    """Average chain price index h = (price_end / price_start) ** (1 / periods)."""
    return rf.chain_index(price_start, price_end, periods)


@mcp.tool()
def rf_index_price(base_price: float, chain_index: float, periods: float) -> dict:
    """Index a past price to the valuation date: base_price * chain_index ** periods."""
    return rf.index_price(base_price, chain_index, periods)


@mcp.tool()
def rf_physical_depreciation(
    age_years: float,
    economic_life_years: float,
    replacement_cost: Optional[float] = None,
    annual_repair_cost: float = 0,
    salvage_value: float = 0,
    actual_load: float = 1,
    normative_load: float = 1,
) -> dict:
    """Physical depreciation of machinery under the linear model: curable part
    annual_repair_cost * age / replacement_cost plus incurable part
    (actual_load / normative_load) * age / (life * cost) *
    (cost - salvage_value - annual_repair_cost * life). Without repair costs
    and salvage value it is (load ratio) * age / life. Capped at 100%."""
    return rf.physical_depreciation(
        age_years,
        economic_life_years,
        replacement_cost,
        annual_repair_cost,
        salvage_value,
        actual_load,
        normative_load,
    )


@mcp.tool()
def rf_scrap_value(
    mass_kg: float, scrap_price_per_kg: float, disposal_cost: float = 0
) -> dict:
    """Salvage value by scrap metal: mass_kg * scrap_price_per_kg - disposal_cost."""
    return rf.scrap_value(mass_kg, scrap_price_per_kg, disposal_cost)


@mcp.tool()
def rf_residual_value(
    replacement_cost: float, total_depreciation_pct: float, salvage_value: float = 0
) -> dict:
    """Residual value: replacement_cost * (1 - depreciation) + salvage_value;
    a negative salvage_value is a disposal cost."""
    return rf.residual_value(replacement_cost, total_depreciation_pct, salvage_value)


@mcp.tool()
def rf_cost_from_price(
    price: float,
    profitability_pct: float,
    vat_pct: float = 0,
    profit_tax_pct: Optional[float] = None,
) -> dict:
    """Full production cost from the manufacturer's price:
    (1 - profitability) * price / (1 + VAT). With profit_tax_pct the
    profitability is net: (1 - tax - profitability) * price / ((1 + VAT) *
    (1 - tax)). The VAT rate is an input."""
    return rf.cost_from_price(price, profitability_pct, vat_pct, profit_tax_pct)


@mcp.tool()
def rf_price_from_cost(
    cost: float,
    profitability_pct: float,
    vat_pct: float = 0,
    profit_tax_pct: Optional[float] = None,
) -> dict:
    """Manufacturer's price from full production cost; the inverse of
    rf_cost_from_price with the same parameters."""
    return rf.price_from_cost(cost, profitability_pct, vat_pct, profit_tax_pct)


@mcp.tool()
def rf_qualitative_adjustments(analogs: List[dict]) -> dict:
    """Method of directed qualitative adjustments. Each analog has price and
    adjustments: [{"name", "direction": "up" | "down", "weight"}] (weight 1
    by default). Returns lower/upper analogs, the value of every pair
    (Цн*N−в + Цв*N+н) / (N−в + N+н), the weighted value and the range value."""
    return rf.qualitative_adjustments(analogs)


if __name__ == "__main__":
    mcp.run()  # stdio transport
