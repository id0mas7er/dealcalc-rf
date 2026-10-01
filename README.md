# DealCalc RF

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

Deterministic calculation aids for **Russian real-estate valuation** plus a
local (stdio) **MCP server** that exposes every calculation as a tool an AI
agent can call. No hosting, no external data APIs, no accounts — just the math.

Forked from [dealcalc-core](https://github.com/dealcalcpro2026/dealcalc-core);
the original US investment calculators have been removed.

## What it is

- **Pure functions.** Deterministic, no network, no file I/O, no globals. Every
  function validates its inputs and returns a JSON-serializable `dict`.
- **Calculation layer only.** The module does not select market evidence or
  prescribe correction factors. Those inputs must be supported by the
  appraiser's analysis. It is not a claim that a generated result is a signed
  valuation report.

## Install

```bash
pip install -e .            # engine only
pip install -e ".[mcp]"     # engine + MCP server
pip install -e ".[dev]"     # engine + pytest
```

## Calculations

The `dealcalc.rf` package provides:

- `comparative_approach` — adjusted comparable unit prices and an indicated
  value range;
- `income_capitalization` — direct capitalization of annual NOI;
- `dcf_valuation` — discounted cash flow with an explicit terminal value;
- `cost_approach` — replacement cost with entrepreneurial profit, land, and
  multiplicative physical/functional/external depreciation;
- `reconcile_approaches` — weighted reconciliation of indicated values with
  weights that must sum to 1.

```python
from dealcalc.rf import income_capitalization

income_capitalization(1_200_000, 12)
# {'approach': 'income', 'method': 'direct_capitalization', 'currency': 'RUB',
#  'noi_annual': 1200000.0, 'cap_rate_pct': 12.0, 'indicated_value': 10000000.0}
```

### Conventions

- **Amounts** are plain numbers labelled `RUB` by default; no currency
  conversion is performed.
- **Rates and percentages** are *percent numbers*, not decimals: `12` means 12%.
- **Outputs** are dicts with amounts rounded to 2 decimals.
- Invalid inputs raise `ValueError`.

The Russian profile is documented in [`docs/russia.md`](docs/russia.md). Its
normative starting points are Federal Law No. 135-FZ, FSO I–VI under Order
No. 200, FSO No. 7 for real estate, FSO No. 8 for business, and FSO No. 10 for
machinery and vehicles.

## MCP server

The engine is exposed to AI agents over a local MCP (stdio) server. See
[`mcp_server/README.md`](mcp_server/README.md) for setup, or in short:

```bash
pip install -e ".[mcp]"
python mcp_server/server.py
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE). Based on dealcalc-core by dealcalcpro2026.
