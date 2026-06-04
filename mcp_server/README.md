# DealCalc MCP Server

A local [Model Context Protocol](https://modelcontextprotocol.io) server that
exposes the DealCalc engine as tools an AI agent (e.g. Claude) can call. It runs
over **stdio** for local use — no hosting, no network, no external data.

Every calculator in `dealcalc.calculators` is surfaced as one tool with the same
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
    "dealcalcpro": {
      "command": "python",
      "args": ["/absolute/path/to/dealcalc-core/mcp_server/server.py"]
    }
  }
}
```

Restart Claude Desktop; the DealCalc tools appear in the tools menu.

### Claude Code (CLI)

```bash
claude mcp add dealcalcpro -- python /absolute/path/to/dealcalc-core/mcp_server/server.py
```

Then run `claude` and the tools are available.

## Tools

`arv`, `seventy_percent_rule`, `mao`, `wholesale`, `cap_rate`, `noi`,
`cash_on_cash`, `dscr`, `gross_rent_multiplier`, `mortgage`, `rental_cash_flow`,
`fix_and_flip`, `brrrr`, `rental_property_analysis`, `multifamily_analysis`,
`irr`, `closing_costs`, `construction_cost` — 18 in total.

## Units

Currency is plain USD numbers (e.g. `300000`). Rates and percentages are
**percent numbers**, not decimals: `6.5` means 6.5%, `70` means 70%, `5` means
5% vacancy.
