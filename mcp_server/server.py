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


if __name__ == "__main__":
    mcp.run()  # stdio transport
