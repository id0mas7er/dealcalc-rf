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
    "rf_check_assignment",
    "rf_load_listings",
    "rf_comparative_approach",
    "rf_net_operating_income",
    "rf_cap_rate_extraction",
    "rf_income_capitalization",
    "rf_gross_rent_multiplier",
    "rf_dcf_valuation",
    "rf_gordon_terminal_value",
    "rf_reversion_value",
    "rf_discount_rate_build_up",
    "rf_capital_recovery_rate",
    "rf_npv",
    "rf_irr",
    "rf_cost_approach",
    "rf_indexed_replacement_cost",
    "rf_reconcile_approaches",
    "rf_asset_liquidation_value",
    "rf_vehicle_comparative_approach",
    "rf_braking_coefficient",
    "rf_parameter_unit_price",
    "rf_new_equivalent_price",
    "rf_chain_index",
    "rf_index_price",
    "rf_physical_depreciation",
    "rf_scrap_value",
    "rf_residual_value",
    "rf_cost_from_price",
    "rf_price_from_cost",
    "rf_qualitative_adjustments",
    "rf_business_income_approach",
    "rf_business_multiples",
    "rf_net_assets",
    "rf_business_liquidation_value",
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


def test_server_sends_agent_instructions():
    assert "rf_check_assignment" in (server.mcp.instructions or "")


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


def test_context_is_passed_through_the_tool():
    result = _call(
        "rf_income_capitalization",
        {"noi_annual": 1_200_000, "cap_rate_pct": 12, "context": {"valuation_date": "2026-10-01", "value_type": "рыночная", "vat": "excluded"}},
    )

    assert result["context"]["valuation_date"] == "2026-10-01"
    assert result["guardrails"] == []
