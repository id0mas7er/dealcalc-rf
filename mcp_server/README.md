# DealCalc RF MCP Server

A local [Model Context Protocol](https://modelcontextprotocol.io) server that
exposes the DealCalc RF engine as tools an AI agent (e.g. Claude) can call. It runs
over **stdio** for local use — no hosting, no network, no external data.

Every function in `dealcalc.rf` is surfaced as one tool with the same
signature, units, and a clear docstring (the docstring is the description the
agent sees).

## Install

```bash
pip install -e ".[mcp]"   # installs the engine plus the MCP SDK
```

## Run standalone

```bash
python mcp_server/server.py
```

The server speaks the MCP stdio transport, so it waits for a client to connect.

## Register with Claude

### Claude Desktop

Add an entry to `claude_desktop_config.json`
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS,
`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "dealcalc-rf": {
      "command": "python",
      "args": ["/absolute/path/to/dealcalc-rf/mcp_server/server.py"]
    }
  }
}
```

Restart Claude Desktop; the DealCalc RF tools appear in the tools menu.

### Claude Code (CLI)

```bash
claude mcp add dealcalc-rf -- python /absolute/path/to/dealcalc-rf/mcp_server/server.py
```

Then run `claude` and the tools are available.

## Tools

`rf_comparative_approach`, `rf_income_capitalization`,
`rf_net_operating_income`, `rf_cap_rate_extraction`,
`rf_gross_rent_multiplier`, `rf_npv`, `rf_irr`, `rf_dcf_valuation`,
`rf_cost_approach`, `rf_reconcile_approaches`,
`rf_vehicle_comparative_approach`, `rf_braking_coefficient`,
`rf_new_equivalent_price` — 13 in total.

## Units

Amounts are plain numbers labelled `RUB` by default. Rates and percentages are
**percent numbers**, not decimals: `12` means 12%.
