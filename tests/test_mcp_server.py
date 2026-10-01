"""MCP server smoke tests; skipped when the optional mcp package is missing."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server"))

import server  # noqa: E402

EXPECTED_TOOLS = {
    "rf_comparative_approach",
    "rf_income_capitalization",
    "rf_net_operating_income",
    "rf_cap_rate_extraction",
    "rf_gross_rent_multiplier",
    "rf_npv",
    "rf_irr",
    "rf_dcf_valuation",
    "rf_cost_approach",
    "rf_reconcile_approaches",
    "rf_vehicle_comparative_approach",
    "rf_braking_coefficient",
    "rf_new_equivalent_price",
    "rf_parameter_unit_price",
    "rf_chain_index",
    "rf_index_price",
    "rf_physical_depreciation",
    "rf_scrap_value",
    "rf_residual_value",
    "rf_cost_from_price",
    "rf_price_from_cost",
    "rf_qualitative_adjustments",
    "rf_check_assignment",
    "rf_gordon_terminal_value",
    "rf_business_income_approach",
    "rf_business_multiples",
    "rf_net_assets",
    "rf_liquidation_value",
    "rf_actual_share_value",
    "rf_deferred_tax_effect",
    "rf_business_interest_value",
    "rf_market_rent_cost_plus",
    "rf_cellular_site_rent",
    "rf_external_obsolescence_cost_income",
    "rf_external_obsolescence_paired_sales",
    "rf_external_obsolescence_lost_income",
    "rf_fund_unit_value",
}


def _call(name, arguments):
    result = asyncio.run(server.mcp.call_tool(name, arguments))
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


def test_server_exposes_all_tools():
    tools = asyncio.run(server.mcp.list_tools())

    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_tool_call_returns_calculation_with_visible_adjustments():
    result = _call(
        "rf_comparative_approach",
        {
            "subject_area_sqm": 50,
            "comparables": [
                {
                    "price": 10_000_000,
                    "area_sqm": 50,
                    "adjustments": [{"name": "Скидка на торг", "type": "pct", "value": -5}],
                }
            ],
        },
    )

    assert result["indicated_value"] == 9_500_000.0
    assert result["comparables"][0]["adjustments"][0]["name"] == "Скидка на торг"


def test_tool_call_reports_validation_error():
    with pytest.raises(Exception, match="noi_annual"):
        asyncio.run(
            server.mcp.call_tool("rf_income_capitalization", {"noi_annual": -1, "cap_rate_pct": 12})
        )
