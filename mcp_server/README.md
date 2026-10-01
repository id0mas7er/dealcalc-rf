# MCP-сервер DealCalc RF

Локальный сервер [Model Context Protocol](https://modelcontextprotocol.io):
расчёты `dealcalc.rf` доступны ИИ-агенту (например, Claude) как инструменты.
Работает по stdio на вашем компьютере — без хостинга, сети и внешних данных.
Описания инструментов на русском; у каждого расчётного инструмента есть
необязательный параметр `context` (дата оценки, вид стоимости, НДС).

## Установка

```bash
pip install -e ".[mcp]"
```

Сервер использует API `FastMCP` из MCP SDK 1.x; зависимость ограничена
`mcp>=1.0.0,<2`, потому что в SDK 2.x этот API переименован.

## Запуск

```bash
python mcp_server/server.py
```

## Подключение к Claude

Claude Desktop — в `claude_desktop_config.json`
(`%APPDATA%\Claude\claude_desktop_config.json` в Windows):

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

Claude Code — файл `.mcp.json` в корне проекта с тем же содержимым или команда:

```bash
claude mcp add dealcalc-rf -- python /absolute/path/to/dealcalc-rf/mcp_server/server.py
```

## Инструменты — 43

- Задание и данные: `rf_check_assignment`, `rf_load_listings`.
- Недвижимость, сравнительный подход: `rf_comparative_approach`.
- Доходный подход: `rf_net_operating_income`, `rf_cap_rate_extraction`,
  `rf_income_capitalization`, `rf_gross_rent_multiplier`, `rf_dcf_valuation`,
  `rf_gordon_terminal_value`, `rf_reversion_value`, `rf_discount_rate_build_up`,
  `rf_capital_recovery_rate`, `rf_npv`, `rf_irr`.
- Затратный подход и согласование: `rf_cost_approach`,
  `rf_indexed_replacement_cost`, `rf_reconcile_approaches`,
  `rf_asset_liquidation_value`.
- Автомобили, машины и оборудование: `rf_vehicle_comparative_approach`,
  `rf_braking_coefficient`, `rf_parameter_unit_price`, `rf_new_equivalent_price`,
  `rf_chain_index`, `rf_index_price`, `rf_physical_depreciation`,
  `rf_scrap_value`, `rf_residual_value`, `rf_cost_from_price`,
  `rf_price_from_cost`, `rf_qualitative_adjustments`.
- Бизнес (ФСО №8): `rf_business_income_approach`, `rf_business_multiples`,
  `rf_net_assets`, `rf_business_liquidation_value`, `rf_actual_share_value`,
  `rf_deferred_tax_effect`, `rf_business_interest_value`.
- Рекомендации «СРОО Экспертный совет»: `rf_market_rent_cost_plus`,
  `rf_cellular_site_rent`, `rf_external_obsolescence_cost_income`,
  `rf_external_obsolescence_paired_sales`, `rf_external_obsolescence_lost_income`,
  `rf_fund_unit_value`.

`rf_load_listings` и параметр `synonyms_file` у `rf_vehicle_comparative_approach`
читают любой локальный путь, который назовёт агент и к которому есть доступ у
процесса сервера. Для локального stdio-сервера это допустимо: сервер работает
с правами пользователя. Не подключайте его к агентам, которым не доверяете
чтение ваших файлов.

Каждый результат — черновик для проверки оценщиком: `status`, `context`,
`method_card` (стандарт, формула, статус формулы, ссылка на документ),
`conditions`, `guardrails`, `checks`.

## Единицы

Суммы — числа с пометкой `RUB` по умолчанию. Ставки и проценты — в процентах:
`12` означает 12 %.
