# DealCalc Core

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

A pure-Python real estate investment **calculation engine** plus a local
(stdio) **MCP server** that exposes every calculator as a tool an AI agent can
call. No hosting, no external data APIs, no accounts — just the math.

This is **Phase 1** of [dealcalcpro.com](https://dealcalcpro.com): the engine and
local MCP only.

## What it is

- **18 calculators** covering offer/acquisition logic, investment metrics,
  composite deal analyzers, and cost estimators.
- **Pure functions.** Deterministic, no network, no file I/O, no globals. Every
  function validates its inputs and returns a JSON-serializable `dict`.
- **Provably correct.** `mortgage` and `irr` are cross-checked against
  `numpy-financial` directly in the test suite.

## Install

```bash
pip install -e .            # engine only
pip install -e ".[mcp]"     # engine + MCP server
pip install -e ".[dev]"     # engine + pytest
```

## Usage

```python
from dealcalc import calculators as calc

calc.cap_rate(24000, 400000)
# {'cap_rate_pct': 6.0}

calc.rental_property_analysis(
    300000, 25, 7, 30, 2200, 700, vacancy_pct=5, closing_costs=9000
)
# {'loan_amount': 225000.0, 'total_cash_invested': 84000.0,
#  'monthly_payment': 1496.93, 'monthly_cash_flow': -106.93,
#  'cap_rate_pct': 5.56, 'cash_on_cash_pct': -1.53, 'dscr': 0.93, ...}

calc.irr([-250000, 100000, 150000, 200000, 250000, 300000])
# {'irr_pct': 56.72}
```

### Conventions

- **Currency** is plain USD numbers (e.g. `300000`).
- **Rates and percentages** are *percent numbers*, not decimals: `6.5` means
  6.5%, `70` means 70%, `5` means 5% vacancy.
- **Outputs** are dicts with currency rounded to 2 decimals and rates/ratios to
  2 decimals.
- Invalid inputs (negative price, term ≤ 0, …) raise `ValueError`. Where a
  denominator can be 0, the field comes back as `None` with an explanatory
  `note`.

## Calculators

### Offer / acquisition
- `arv` — after-repair value from comp $/sqft
- `seventy_percent_rule` — classic 70% rule max offer
- `mao` — maximum allowable offer with explicit deductions
- `wholesale` — buyer max, assignment fee, max offer to seller

### Metric helpers
- `cap_rate` — capitalization rate
- `noi` — net operating income (with EGI breakout)
- `cash_on_cash` — cash-on-cash return
- `dscr` — debt-service coverage ratio
- `gross_rent_multiplier` — GRM

### Composite analyzers
- `mortgage` — payment, PITI, lifetime totals
- `rental_cash_flow` — monthly/annual cash flow
- `fix_and_flip` — profit, ROI, annualized ROI
- `brrrr` — buy/rehab/rent/refinance/repeat
- `rental_property_analysis` — flagship rental aggregate
- `multifamily_analysis` — GPR/EGI/NOI/cap rate/valuation
- `irr` — internal rate of return (+ `build_cash_flows` helper)

### Cost estimators
- `closing_costs` — closing costs incl. points
- `construction_cost` — construction/rehab budget with contingency

## MCP server

The engine is exposed to AI agents over a local MCP (stdio) server. See
[`mcp_server/README.md`](mcp_server/README.md) for setup, or in short:

```bash
pip install -e ".[mcp]"
python mcp_server/server.py
```

Register it with Claude Desktop or Claude Code and all 18 calculators become
callable tools.

## Russian Federation profile

The repository now includes a separate `dealcalc.rf` package with deterministic
calculation aids for Russian real-estate valuation:

- `comparative_approach` — adjusted comparable unit prices and an indicated
  value range;
- `income_capitalization` — direct capitalization of annual NOI;
- `dcf_valuation` — discounted cash flow with an explicit terminal value;
- `cost_approach` — replacement cost, land, and explicit depreciation inputs;
- `reconcile_approaches` — transparent weighted reconciliation of indicated
  values.

The module does not select market evidence or prescribe correction factors.
Those inputs must be supported by the appraiser's analysis. It is a calculation
layer, not a claim that a generated result is a signed valuation report.

The Russian profile is documented in [`docs/russia.md`](docs/russia.md). Its
normative starting points are Federal Law No. 135-FZ, FSO I–VI under Order
No. 200, FSO No. 7 for real estate, and FSO No. 10 for machinery and vehicles.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE) — open source. Built for [dealcalcpro.com](https://dealcalcpro.com).
