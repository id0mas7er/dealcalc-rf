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


# ---------------------------------------------------------------------------
# Business valuation (FSO No. 8)
# ---------------------------------------------------------------------------


@mcp.tool()
def rf_business_income_approach(
    cash_flows: List[float],
    discount_rate_pct: float,
    basis: str,
    terminal_value: float = 0,
    mid_year: bool = False,
    obligations_not_in_flows: float = 0,
    non_operating_assets: float = 0,
    non_operating_liabilities: float = 0,
    currency: str = "RUB",
) -> dict:
    """Equity value (100%) of a business from forecast cash flows (FSO No. 8).

    basis "equity": FCFE at the cost of equity (obligations_not_in_flows must
    be 0). basis "invested_capital": FCFF at WACC give invested capital, then
    obligations not reflected in the flows are subtracted. Non-operating
    assets/liabilities are added/subtracted once. cash_flows[0] is year 1."""
    return rf.business_income_approach(
        cash_flows,
        discount_rate_pct,
        basis,
        terminal_value,
        mid_year,
        obligations_not_in_flows,
        non_operating_assets,
        non_operating_liabilities,
        currency,
    )


@mcp.tool()
def rf_business_multiples(
    analogs: List[dict],
    subject_metric: float,
    multiple_name: str,
    basis: str,
    statistic: str = "median",
    currency: str = "RUB",
) -> dict:
    """Value of 100% of a capital base by a market multiple (FSO No. 8).

    Each analog: value (equity or invested capital matching basis), metric,
    optional name and provenance (source, date, price_type...). The median or
    mean multiple is applied to subject_metric; a basis/multiple mismatch
    (EV/... with equity, P/... with invested capital) is flagged."""
    return rf.business_multiples(analogs, subject_metric, multiple_name, basis, statistic, currency)


@mcp.tool()
def rf_net_assets(
    assets: List[dict],
    liabilities: List[dict],
    adjustments: Optional[List[dict]] = None,
    currency: str = "RUB",
) -> dict:
    """Equity by the net asset method (FSO No. 8): assets and liabilities as
    {"name", "value", "basis": "market" | "book"}; book values are flagged.
    adjustments: {"name", "value"} with a sign, each to be justified."""
    return rf.net_assets(assets, liabilities, adjustments, currency)


@mcp.tool()
def rf_liquidation_value(
    events: List[dict], discount_rate_pct: float, currency: str = "RUB"
) -> dict:
    """Business value under a justified liquidation premise (FSO No. 8 p. 11.2).

    events: {"period" (years from valuation date), "sale_proceeds",
    "debt_payments", "disposal_costs", "closure_costs"}; net proceeds are
    discounted at the rate for the risk of receiving liquidation proceeds."""
    return rf.liquidation_value(events, discount_rate_pct, currency)


@mcp.tool()
def rf_actual_share_value(
    share_pct: float,
    accepted_assets: float,
    accepted_liabilities: float,
    paid_share_pct: float = 100,
    currency: str = "RUB",
) -> dict:
    """Actual value of an LLC participant's share (ДСД) on exit:
    share × paid part × (accepted assets − accepted liabilities). A legal
    value, not the market value of the share; no discounts or premiums."""
    return rf.actual_share_value(
        share_pct, accepted_assets, accepted_liabilities, paid_share_pct, currency
    )


@mcp.tool()
def rf_deferred_tax_effect(
    tax_without_effect: List[float],
    tax_with_effect: List[float],
    discount_rate_pct: float,
    currency: str = "RUB",
) -> dict:
    """Present value of the change in tax payments from deferred tax assets /
    liabilities (years 1..n). Use the effect once: in the forecast or as a
    separate adjustment."""
    return rf.deferred_tax_effect(tax_without_effect, tax_with_effect, discount_rate_pct, currency)


@mcp.tool()
def rf_business_interest_value(
    value_100pct: float,
    share_pct: float,
    adjustments: Optional[List[dict]] = None,
    currency: str = "RUB",
) -> dict:
    """Value of a specific interest: 100% value × share, then optional step
    adjustments {"name", "type": "pct" | "abs", "value"} (control or
    liquidity discounts), each to be justified; none applied automatically."""
    return rf.business_interest_value(value_100pct, share_pct, adjustments, currency)


# ---------------------------------------------------------------------------
# Special methods from the Expert Council recommendations
# ---------------------------------------------------------------------------


@mcp.tool()
def rf_market_rent_cost_plus(
    property_value: float,
    cap_rate_pct: float,
    owner_expenses: Optional[List[dict]] = None,
    vacancy_pct: float = 0,
    collection_loss_pct: float = 0,
    rentable_area_sqm: Optional[float] = None,
    currency: str = "RUB",
) -> dict:
    """Market rent by the cost-plus model (МРз–1/26): required NOI = property
    value × cap rate, plus owner expenses ({"name", "type": "abs" RUB/year |
    "pct" % of effective gross income, "value"}) and losses -> gross rent per
    year, month and m². Check comparable rents first; market rent is not the
    value of the property or of the leasehold."""
    return rf.market_rent_cost_plus(
        property_value,
        cap_rate_pct,
        owner_expenses,
        vacancy_pct,
        collection_loss_pct,
        rentable_area_sqm,
        currency,
    )


@mcp.tool()
def rf_cellular_site_rent(
    comparable_asset_value: float,
    kit_share_pct: float,
    cap_rate_pct: float,
    owner_costs_annual: float = 0,
    collection_loss_pct: float = 0,
    currency: str = "RUB",
) -> dict:
    """Rent of a site for one standard cellular equipment kit (МР–3/26 (2)) by
    reverse capitalization: comparable-utility asset value × kit share × cap
    rate, plus owner costs and collection losses. Only when comparable rent
    data are missing or doubtful."""
    return rf.cellular_site_rent(
        comparable_asset_value, kit_share_pct, cap_rate_pct, owner_costs_annual, collection_loss_pct, currency
    )


@mcp.tool()
def rf_external_obsolescence_cost_income(
    cost_value_without_external: float,
    income_value_with_external: float,
    currency: str = "RUB",
) -> dict:
    """External obsolescence (МРз–8/23-2 §4.1): cost value without the external
    factor minus income value with it, in RUB and percent. A negative result
    is reported, not forced to a discount."""
    return rf.external_obsolescence_cost_income(
        cost_value_without_external, income_value_with_external, currency
    )


@mcp.tool()
def rf_external_obsolescence_paired_sales(
    value_without_impact: float,
    value_with_impact: float,
    base_value: float,
    currency: str = "RUB",
) -> dict:
    """External obsolescence (МРз–8/23-2 §4.2) from a pair of sales differing
    only in the external factor: ratio = 1 − with/without, applied to base_value."""
    return rf.external_obsolescence_paired_sales(
        value_without_impact, value_with_impact, base_value, currency
    )


@mcp.tool()
def rf_external_obsolescence_lost_income(
    cash_flows_without: List[float],
    cash_flows_with: List[float],
    discount_rate_pct: float,
    cost_value: Optional[float] = None,
    currency: str = "RUB",
) -> dict:
    """External obsolescence (МРз–8/23-2 §4.3) as the present value of lost
    cash flows (years 1..n); with cost_value also as a percent."""
    return rf.external_obsolescence_lost_income(
        cash_flows_without, cash_flows_with, discount_rate_pct, cost_value, currency
    )


@mcp.tool()
def rf_fund_unit_value(
    distributions: List[float],
    final_compensation: float,
    discount_rate_pct: float,
    termination_costs: float = 0,
    final_period: Optional[float] = None,
    currency: str = "RUB",
) -> dict:
    """Income value of a closed-end fund unit (МРз–5/23): PV of net payouts
    per unit (years 1..n) plus PV of the final compensation minus termination
    costs at final_period (default n). No separate terminal value."""
    return rf.fund_unit_value(
        distributions, final_compensation, discount_rate_pct, termination_costs, final_period, currency
    )


if __name__ == "__main__":
    mcp.run()  # stdio transport
