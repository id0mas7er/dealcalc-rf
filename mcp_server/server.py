"""Локальный (stdio) MCP-сервер расчётов DealCalc RF.

Каждая функция :mod:`dealcalc.rf` доступна как инструмент FastMCP с той же
сигнатурой; описание инструмента — то, что видит ИИ-агент. Запуск::

    python mcp_server/server.py
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from mcp.server.fastmcp import FastMCP

from dealcalc import rf

# Sent to the agent when it connects; the full guide is docs/agent-guide.md.
AGENT_INSTRUCTIONS = """\
DealCalc RF — расчёты для оценки в РФ (ФСО I–VI, №7, №8, №10, рекомендации «СРОО
Экспертный совет»). Результат любого инструмента — черновик для оценщика, не
итоговая стоимость и не отчёт.

Порядок работы:
1. rf_check_assignment: при can_proceed = false не считать, запросить
   missing_critical у оценщика.
2. Передавать context {valuation_date, value_type, vat, vat_rate_pct,
   assignment_id} в каждый расчёт стоимости.
3. Аналоги из файла — rf_load_listings; у аналогов указывать source, date (дату
   цены), price_type (сделка | предложение).
4. Скидки, корректировки, ставки, веса и ограничения отбора задаёт
   оценщик: не подставлять их самому; если их нет — спросить. Значение из
   справочника передавать с source, date, page и границами справочника
   (range у шага, source_ranges у ставок и сроков). Справочник — по
   категории объекта, последний выпуск; из интервала — среднее при поправке
   до 30 %, иначе минимальная поправка (range.mean, extended_low/high).
5. Согласование — rf_reconcile_approaches с весами оценщика; существенное
   расхождение подходов — более 30 % по умолчанию, другой порог — только по
   указанию оценщика. Если согласование не завершено, reconciled_value = null:
   не выдавать weighted_value_diagnostic за итог. Интервал стоимости
   (value_interval) задаёт только оценщик.
6. Докладывать стоимость, status дословно, все checks (дефекты данных) и все
   guardrails (что обосновать), стандарт и формулу из method_card. Числа не
   пересчитывать вручную.
7. В доходных расчётах описывать flow_rate_basis; у моделей СРО условия
   применения (confirmed_conditions) подтверждает только оценщик.
8. Перед подписанием отчёта — rf_check_report (ФСО VI) с расчётами в approaches.

Проценты задаются числами: 5 означает 5 %. Суммы в рублях, площадь в м².
Ошибка инструмента — неверный вход: прочитать текст и исправить данные.
Полная инструкция: docs/agent-guide.md в репозитории id0mas7er/dealcalc-rf.
"""

try:
    mcp = FastMCP("dealcalc-rf", instructions=AGENT_INSTRUCTIONS)
except TypeError:  # older SDK without server instructions
    mcp = FastMCP("dealcalc-rf")

CONTEXT_NOTE = (
    "\n\ncontext (необязательно): {valuation_date: 'ГГГГ-ММ-ДД', value_type: рыночная | "
    "инвестиционная | равновесная | ликвидационная, vat: included | excluded | "
    "not_applicable, vat_rate_pct, assignment_id} — возвращается в результате; без него "
    "результат нельзя переносить в отчёт.\n"
    "Результат всегда черновик для проверки оценщиком: status, method_card (стандарт, "
    "формула, статус формулы, ссылка), conditions, guardrails, checks."
)


FLOW_RATE_NOTE = (
    "\n\nflow_rate_basis (необязательно): {flow: {price_level: nominal | real, tax: pre_tax | "
    "post_tax, currency}, rate: {...}} — база потока и ставки; несовпадение — замечание, "
    "без описания — напоминание (ФСО V)."
)

SOURCE_RANGES_NOTE = (
    "\n\nsource_ranges (необязательно): {параметр: {low, high, source, date, page, "
    "justification}} — границы значения в источнике (справочнике); проценты — числами "
    "(ставка 0,07–0,13 из справочника → low 7, high 13). Значение вне границ — замечание, "
    "с justification — напоминание."
)

# Conditions of application of the Expert Council models, by tool.
TOOL_CONDITIONS = {
    "rf_market_rent_cost_plus": rf.special.MARKET_RENT_CONDITIONS,
    "rf_cellular_site_rent": rf.special.CELLULAR_SITE_CONDITIONS,
    "rf_external_obsolescence_cost_income": rf.special.COST_INCOME_CONDITIONS,
    "rf_external_obsolescence_paired_sales": rf.special.PAIRED_SALES_CONDITIONS,
    "rf_external_obsolescence_lost_income": rf.special.LOST_INCOME_CONDITIONS,
    "rf_fund_unit_value": rf.special.FUND_UNIT_CONDITIONS,
}


def tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Register a calculation tool; its description gets the context note,
    the flow–rate note of income models and the conditions of private models."""

    description = (func.__doc__ or "").strip() + CONTEXT_NOTE
    if func.__name__ in TOOL_CONDITIONS:
        items = "; ".join(f"{key} — {text}" for key, text in TOOL_CONDITIONS[func.__name__].items())
        description += (
            "\n\nconfirmed_conditions — id условий применения, подтверждённых оценщиком "
            f"(неподтверждённое условие — замечание): {items}."
        )
    if "flow_rate_basis" in func.__code__.co_varnames:
        description += FLOW_RATE_NOTE
    if "source_ranges" in func.__code__.co_varnames:
        description += SOURCE_RANGES_NOTE
    return mcp.tool(description=description)(func)


# ---------------------------------------------------------------------------
# Задание на оценку и данные
# ---------------------------------------------------------------------------


@mcp.tool()
def rf_check_assignment(assignment: dict) -> dict:
    """Проверка задания на оценку до любого расчёта (ФСО III, IV, II). Вызывайте первой.

    assignment: object_type (real_estate | business | machinery | vehicle),
    object_description, rights, purpose, value_type (рыночная, инвестиционная,
    равновесная, ликвидационная), value_premises, valuation_date (ГГГГ-ММ-ДД) и
    рекомендуемые сведения по типу объекта. Без критических сведений — статус
    «недостаточно данных» и перечень пробелов; также признаки применимости подходов
    и условия остановки расчёта."""
    return rf.check_assignment(assignment)


@mcp.tool()
def rf_check_report(report: dict) -> dict:
    """Проверка отчёта об оценке перед подписанием (ФСО VI, пп. 3–8): всё ли есть.

    report: report_number, report_date (ГГГГ-ММ-ДД), basis, assignment (как в
    rf_check_assignment), appraisers [{full_name, phone, postal_address, email,
    sro_registry_number, sro_name, sro_address}], customer ({full_name} или {name, ogrn,
    address}), employer {name, ogrn, address} или private_practice: true, independence,
    engaged_specialists (пустой список — их нет), standards, methodical_recommendations или
    recommendations_not_used_reason, object {description, rights}, assumptions,
    market_analysis, approaches {selection_justification, rejected, rejected_comment,
    calculations — результаты расчётов}, final_value (число), limits_of_use, value_interval
    {low, high, justification} — для недвижимости по ФСО №7, п. 30 (если задание не указывает
    иное: assignment.interval_not_required = true), documents,
    sources [{url или reference, date}], signing {form: paper | electronic, confirmed: [...]}:
    paper — pages_numbered, bound, signed, sealed; electronic — appraiser_qualified_signature,
    employer_signature. Раздел не того типа (строка вместо объекта или списка) — в missing.
    Результат: missing (с пунктами ФСО VI), checks (расчёты со статусом не «черновой расчёт»,
    расхождение контекста, источники без даты), can_issue — true, только если missing и
    checks пусты."""
    return rf.check_report(report)


@mcp.tool()
def rf_load_listings(
    path: str,
    source: str,
    listing_type: str = "property",
    collected_at: Optional[str] = None,
    sheet: Optional[str] = None,
    rent_period: Optional[str] = None,
) -> dict:
    """Импорт аналогов из локального файла CSV, JSON, JSONL или Excel (.xlsx) (без сети).

    listing_type: property (продажа недвижимости) | vehicle (автомобили) | rent (аренда:
    арендная плата или ставка за м² с площадью; период — колонка «период» или rent_period
    month | year, без умолчания; в price_rub — годовая аренда) | income (цена с ЧОД и/или
    валовым доходом — для rf_cap_rate_extraction и rf_gross_rent_multiplier) | business
    (компания, стоимость value, показатель metric — для rf_business_multiples) | machinery
    (наименование, марка, модель, год, цена, наработка). sheet — лист Excel (по умолчанию
    первый). Русские названия колонок, цены «12 500 000 ₽» и «5 млн руб.», дата публикации
    (date — дата цены), тип цены (по умолчанию «предложение»; нераспознанный оставляется
    пустым с import_warnings), НДС цены (vat: «с НДС» | «без НДС» | «НДС не применяется»),
    пошаговые корректировки; дубли удаляются. Ошибка называет
    номер строки. Аналоги передаются в расчёты как есть (price_rub читается как цена).
    Читается любой локальный путь, доступный процессу сервера. collected_at — дата сбора
    файла (не дата цены); без неё — текущее время."""
    listings = rf.load_listings(path, source, listing_type, collected_at, sheet, rent_period)
    return {"count": len(listings), "listings": listings}


# ---------------------------------------------------------------------------
# Недвижимость: сравнительный подход
# ---------------------------------------------------------------------------


@tool
def rf_comparative_approach(
    subject_area_sqm: float,
    comparables: List[dict],
    currency: str = "RUB",
    weighting: str = "manual",
    context: Optional[dict] = None,
) -> dict:
    """Сравнительный подход для недвижимости (ФСО V; ФСО №7, п. 22): стоимость по скорректированным ценам за м².

    Аналог: price, area_sqm, adjustments, weight и происхождение (source, date, url,
    price_type сделка|предложение, conditions, reliability). adjustments — шаги по
    порядку к цене за м²: {"name", "type", ...}: pct (процент), pct_group (подряд
    идущие суммируются и применяются один раз), coef (value — коэффициент таблицы
    справочника, 0,94), ratio (subject, analog — коэффициенты объекта и аналога к одной
    базе: этаж, класс, индекс цен на дату), abs (руб./м²), param (subject, analog,
    exponent — коэффициент торможения), staged (stages — этапы вариантов с label: среднее
    уравнение → уравнения границ → таблица; берётся первый этап с поправкой до 30 %,
    иначе наименьшая с justification), depreciation (analog_pct, subject_pct). У шага —
    source, date, page, justification и range {low, high, mean, extended_low,
    extended_high} — границы справочника (вне границ — замечание); с mean — правило
    выбора: поправка до 30 % — среднее, больше — минимальная поправка в интервале
    (отступление — замечание). Скидку на торг ставьте первой. weighting: manual | inverse_gross |
    inverse_count | count_share (K = (S − M)/((N − 1)·S) по числу корректировок) |
    gross_share (K ∝ 1 − S_i/Σ(S_j + 1), S_i — сумма модулей корректировок как записаны, %:
    |−10 %| + |+20 %| = 30) | gross_share_fraction (то же, S_i в долях: 0,30).
    Показываются все шаги, валовая и итоговая корректировки, коэффициент вариации (33%)."""
    return rf.comparative_approach(subject_area_sqm, comparables, currency, weighting, context=context)


# ---------------------------------------------------------------------------
# Доходный подход
# ---------------------------------------------------------------------------


@tool
def rf_net_operating_income(
    potential_gross_income: Optional[float] = None,
    rentable_area_sqm: Optional[float] = None,
    rent_rate_sqm_year: Optional[float] = None,
    vacancy_pct: float = 0,
    collection_loss_pct: float = 0,
    other_income_annual: float = 0,
    operating_expenses: Optional[List[dict]] = None,
    currency: str = "RUB",
    context: Optional[dict] = None,
    *,
    source_ranges: Optional[dict] = None,
) -> dict:
    """Годовой ЧОД по шагам: ПВД → ДВД → ЧОД (ФСО V; ФСО №7, п. 23).

    ПВД — готовой суммой или площадь × ставка аренды (руб./м² в год).
    ДВД = ПВД × (1 − недозагрузка) × (1 − недосбор) + прочие доходы.
    operating_expenses: {"name", "type": "abs" (руб./год) | "pct" (% ДВД), "value"}."""
    return rf.net_operating_income(
        potential_gross_income,
        rentable_area_sqm,
        rent_rate_sqm_year,
        vacancy_pct,
        collection_loss_pct,
        other_income_annual,
        operating_expenses,
        currency,
        source_ranges=source_ranges,
        context=context,
    )


@tool
def rf_cap_rate_extraction(comparables: List[dict], context: Optional[dict] = None) -> dict:
    """Ставка капитализации по рынку (ФСО №7, п. 23): ЧОД / цена продажи по каждому аналогу.

    Аналог: price, noi, происхождение. Среднее, медиана, диапазон, коэффициент
    вариации; выбор ставки — за оценщиком."""
    return rf.cap_rate_extraction(comparables, context=context)


@tool
def rf_income_capitalization(
    noi_annual: float, cap_rate_pct: float, currency: str = "RUB", flow_rate_basis: Optional[dict] = None,
    context: Optional[dict] = None, *, source_ranges: Optional[dict] = None
) -> dict:
    """Прямая капитализация (ФСО V, п. 14): стоимость = годовой ЧОД / ставка капитализации."""
    return rf.income_capitalization(
        noi_annual,
        cap_rate_pct,
        currency,
        flow_rate_basis=flow_rate_basis,
        source_ranges=source_ranges,
        context=context,
    )


@tool
def rf_gross_rent_multiplier(
    comparables: List[dict],
    subject_gross_income: Optional[float] = None,
    statistic: str = "mean",
    currency: str = "RUB",
    context: Optional[dict] = None,
) -> dict:
    """Валовой рентный мультипликатор: ВРМ = цена / годовой валовой доход аналога.

    Аналог: price, gross_income, происхождение. При subject_gross_income — стоимость =
    ВРМ (mean | median) × доход объекта. Одна база дохода (ПВД или ДВД) для всех."""
    return rf.gross_rent_multiplier(comparables, subject_gross_income, statistic, currency, context=context)


@tool
def rf_dcf_valuation(
    cash_flows: List[float],
    discount_rate_pct: float,
    terminal_value: float = 0,
    currency: str = "RUB",
    mid_year: bool = False,
    terminal_timing: str = "end",
    first_cash_flow_period: int = 1,
    flow_rate_basis: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """Дисконтирование денежных потоков (ФСО V, п. 15).

    cash_flows[0] — поток ПЕРВОГО ГОДА (first_cash_flow_period = 1, по умолчанию) или
    ПЕРИОДА 0 без дисконтирования, как в rf_npv (first_cash_flow_period = 0).
    mid_year — дисконтирование на середину года (только при периоде 1).
    terminal_timing: end (конец последнего периода) | mid (на полпериода раньше — для
    стоимости по Гордону из потока середины следующего года)."""
    return rf.dcf_valuation(
        cash_flows,
        discount_rate_pct,
        terminal_value,
        currency,
        mid_year,
        terminal_timing,
        first_cash_flow_period,
        flow_rate_basis=flow_rate_basis, context=context,
    )


@tool
def rf_gordon_terminal_value(
    cash_flow_next: float,
    discount_rate_pct: float,
    growth_rate_pct: float,
    flow_rate_basis: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """Постпрогнозная стоимость по модели Гордона (ФСО V, п. 21): TV = CF(n+1) / (r − g).

    Требует r > g, устойчивый поток и длительный или неограниченный срок использования."""
    return rf.gordon_terminal_value(
        cash_flow_next,
        discount_rate_pct,
        growth_rate_pct,
        flow_rate_basis=flow_rate_basis,
        context=context,
    )


@tool
def rf_reversion_value(
    noi_next_year: float,
    terminal_cap_rate_pct: float,
    selling_costs_pct: float = 0,
    flow_rate_basis: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """Стоимость реверсии: ЧОД года n + 1 / терминальная ставка капитализации × (1 − расходы на продажу).

    Результат используется как terminal_value в rf_dcf_valuation."""
    return rf.reversion_value(
        noi_next_year,
        terminal_cap_rate_pct,
        selling_costs_pct,
        flow_rate_basis=flow_rate_basis,
        context=context,
    )


@tool
def rf_discount_rate_build_up(
    risk_free_rate_pct: float,
    premiums: List[dict],
    risk_free_source: str = "",
    context: Optional[dict] = None,
) -> dict:
    """Ставка дисконтирования методом кумулятивного построения: безрисковая ставка + Σ премий.

    premiums: {"name", "value", "source"} — риск вложения, низкая ликвидность (срок
    экспозиции), инвестиционный менеджмент и др. Источник безрисковой ставки (ОФЗ на
    дату оценки) и премий обязателен — иначе замечание."""
    return rf.discount_rate_build_up(risk_free_rate_pct, premiums, risk_free_source, context=context)


@tool
def rf_capital_recovery_rate(
    discount_rate_pct: float,
    remaining_life_years: float,
    method: str,
    safe_rate_pct: Optional[float] = None,
    value_change_pct: Optional[float] = None,
    context: Optional[dict] = None,
) -> dict:
    """Ставка капитализации = ставка дохода + Δ × норма возврата капитала (ФСО №7, п. 23 (д)).

    method: ring (1/n) | inwood (фонд возмещения по ставке дохода) | hoskold (фонд
    возмещения по безрисковой ставке safe_rate_pct). remaining_life_years — оставшийся
    срок экономической жизни. value_change_pct (Δ) — доля потери стоимости за срок, %:
    без неё принимается 100 % (завышает ставку при большой доле земли); при росте
    стоимости — отрицательная. Выбор модели — за оценщиком."""
    return rf.capital_recovery_rate(
        discount_rate_pct, remaining_life_years, method, safe_rate_pct, value_change_pct, context=context
    )


@tool
def rf_npv(
    cash_flows: List[float],
    discount_rate_pct: float,
    flow_rate_basis: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """Чистая приведённая стоимость. cash_flows[0] — поток ПЕРИОДА 0 (обычно вложения, не дисконтируется).

    Показываются коэффициент дисконтирования и приведённая стоимость каждого периода."""
    return rf.npv(cash_flows, discount_rate_pct, flow_rate_basis=flow_rate_basis, context=context)


@tool
def rf_irr(cash_flows: List[float], context: Optional[dict] = None) -> dict:
    """Внутренняя норма доходности, %. cash_flows[0] — период 0; нужна смена знака потоков."""
    return rf.irr(cash_flows, context=context)


# ---------------------------------------------------------------------------
# Затратный подход, согласование, ликвидационная стоимость
# ---------------------------------------------------------------------------


@tool
def rf_cost_approach(
    replacement_cost: float,
    land_value: float = 0,
    physical_depreciation_pct: float = 0,
    functional_depreciation_pct: float = 0,
    external_depreciation_pct: float = 0,
    entrepreneurial_profit_pct: float = 0,
    currency: str = "RUB",
    profit_base: str = "improvements",
    total_depreciation_pct: Optional[float] = None,
    external_obsolescence_amount: Optional[float] = None,
    context: Optional[dict] = None,
) -> dict:
    """Затратный подход для недвижимости (ФСО №7, п. 24 (г); ФСО V, пп. 24, 31, 33).

    V = земля + (затраты + прибыль предпринимателя) × (1 − Иф)(1 − Ифу)(1 − Иэ).
    profit_base: improvements (ПП от затрат) | land_and_improvements (ПП от затрат и земли).
    Перемножение износов — одна из моделей. Иначе: total_depreciation_pct — совокупный
    износ по модели оценщика (вместо видов износа) или external_obsolescence_amount —
    внешнее обесценение в рублях (вместо процента; вычитается из улучшений)."""
    return rf.cost_approach(
        replacement_cost,
        land_value,
        physical_depreciation_pct,
        functional_depreciation_pct,
        external_depreciation_pct,
        entrepreneurial_profit_pct,
        currency,
        profit_base,
        total_depreciation_pct,
        external_obsolescence_amount,
        context=context,
    )


@tool
def rf_indexed_replacement_cost(
    base_cost: float,
    indices: List[dict],
    regional_coefficient: float = 1,
    vat_pct: float = 0,
    base_label: str = "",
    currency: str = "RUB",
    context: Optional[dict] = None,
) -> dict:
    """Затраты на замещение на дату оценки по цепочке индексов (ФСО №7, п. 24 (г)).

    base_cost — затраты в базисных ценах (УПВС 1969, цены 1984, КО-ИНВЕСТ);
    indices — {"name", "value", "source"} по порядку; затем региональный коэффициент и
    НДС (ставка — входной параметр). Каждый шаг показывается отдельно."""
    return rf.indexed_replacement_cost(
        base_cost, indices, regional_coefficient, vat_pct, base_label, currency, context=context
    )


@tool
def rf_reconcile_approaches(
    approach_values: dict,
    weights: dict,
    max_divergence_pct: Optional[float] = None,
    justification: Optional[str] = None,
    currency: str = "RUB",
    divergence_base: str = "min",
    value_interval: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """Согласование результатов подходов (ФСО V, п. 3). Механическое усреднение не допускается.

    weights — веса оценщика с суммой 1, вес 0 исключает подход. max_divergence_pct —
    порог существенного расхождения: по умолчанию 30 % (существенно — более 30 %),
    другой — по указанию оценщика; расхождение = (max − min) / база × 100,
    divergence_base: min | mean | max. Расхождение считается по ВСЕМ подходам, включая
    исключённые весом 0; исключение подхода требует justification. Выше порога без
    justification — статус «согласование не автоматизировано», reconciled_value = null,
    взвешенное число — только weighted_value_diagnostic. approaches_spread — разброс
    подходов, не интервал стоимости. value_interval {low, high, justification} — суждение
    оценщика о границах интервала стоимости (ФСО №7, п. 30); задаёт только оценщик."""
    return rf.reconcile_approaches(
        approach_values,
        weights,
        max_divergence_pct,
        justification,
        currency,
        divergence_base,
        value_interval,
        context=context,
    )


@tool
def rf_asset_liquidation_value(
    market_value: float,
    discount_rate_pct: float,
    typical_exposure_months: float,
    liquidation_exposure_months: float,
    additional_costs: float = 0,
    forced_sale_discount_pct: Optional[float] = None,
    forced_sale_justification: Optional[str] = None,
    context: Optional[dict] = None,
    *,
    source_ranges: Optional[dict] = None,
) -> dict:
    """Ликвидационная стоимость отдельного объекта (ФСО II): недвижимость, машина, автомобиль.

    V_л = V_р × (1 + r)^(−(T_типичный − T_вынужденный)/12) × (1 − d_вын) − доп. затраты;
    сроки в месяцах, ставка годовая. Множитель по срокам учитывает только стоимость
    времени. Скидка на вынужденность продажи (эластичность спроса) — forced_sale_discount_pct
    с обязательным forced_sale_justification; без неё в guardrails напоминание.
    Для бизнеса при ликвидации — rf_business_liquidation_value."""
    return rf.asset_liquidation_value(
        market_value,
        discount_rate_pct,
        typical_exposure_months,
        liquidation_exposure_months,
        additional_costs,
        forced_sale_discount_pct,
        forced_sale_justification,
        source_ranges=source_ranges,
        context=context,
    )


# ---------------------------------------------------------------------------
# Автомобили, машины и оборудование (ФСО №10)
# ---------------------------------------------------------------------------


@tool
def rf_vehicle_comparative_approach(
    subject: dict,
    comparables: List[dict],
    currency: str = "RUB",
    max_year_diff: Optional[float] = None,
    max_mileage_diff: Optional[float] = None,
    weighting: str = "manual",
    match: str = "exact",
    synonyms: Optional[dict] = None,
    synonyms_file: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict:
    """Сравнительный подход для автомобиля (ФСО V; ФСО №10, п. 13): итог — взвешенная медиана.

    Подбор по марке и модели по словарю пакета (ВАЗ/Lada/Лада, Солярис/Solaris,
    X-Trail/X Trail) и транслитерации; match: exact | contains (Vesta → Vesta SW Cross);
    synonyms: {каноническое имя: [написания]} — для марок и моделей; synonyms_file —
    локальный JSON {"brands": {...}, "models": {...}}. Ограничения по году и пробегу задаёт оценщик
    (умолчаний нет). adjustments — как в rf_comparative_approach, abs — в рублях;
    weighting: manual | inverse_gross | inverse_count | count_share | gross_share |
    gross_share_fraction."""
    return rf.vehicle_comparative_approach(
        subject,
        comparables,
        currency,
        max_year_diff,
        max_mileage_diff,
        weighting,
        match,
        synonyms,
        synonyms_file,
        context=context,
    )


@tool
def rf_braking_coefficient(
    price_1: float, param_1: float, price_2: float, param_2: float, context: Optional[dict] = None
) -> dict:
    """Коэффициент торможения b = ln(Ц2/Ц1) / ln(X2/X1) по двум аналогам, различающимся одним параметром.

    Используется как exponent в шаге корректировки param."""
    return rf.braking_coefficient(price_1, param_1, price_2, param_2, context=context)


@tool
def rf_parameter_unit_price(
    price_1: float, param_1: float, price_2: float, param_2: float, context: Optional[dict] = None
) -> dict:
    """«Цена» единицы параметра g = (Ц1 − Ц2) / (X1 − X2); поправка g × (Xобъекта − Xаналога) — шаг abs."""
    return rf.parameter_unit_price(price_1, param_1, price_2, param_2, context=context)


@tool
def rf_new_equivalent_price(price: float, total_depreciation_pct: float, context: Optional[dict] = None) -> dict:
    """Цена подержанного аналога как нового: Цус = Цан / (1 − Кизн) (Козлов, Фролов, формула 22)."""
    return rf.new_equivalent_price(price, total_depreciation_pct, context=context)


@tool
def rf_chain_index(price_start: float, price_end: float, periods: float, context: Optional[dict] = None) -> dict:
    """Средний цепной индекс цен h = (Цn / Ц0)^(1/n)."""
    return rf.chain_index(price_start, price_end, periods, context=context)


@tool
def rf_index_price(base_price: float, chain_index: float, periods: float, context: Optional[dict] = None) -> dict:
    """Индексный метод: цена на дату оценки = базовая цена × h^n."""
    return rf.index_price(base_price, chain_index, periods, context=context)


@tool
def rf_physical_depreciation(
    age_years: float,
    economic_life_years: float,
    replacement_cost: Optional[float] = None,
    annual_repair_cost: float = 0,
    salvage_value: float = 0,
    actual_load: float = 1,
    normative_load: float = 1,
    context: Optional[dict] = None,
) -> dict:
    """Физический износ машин по линейной модели (Козлов, Фролов, табл. 5, стр. 15).

    Устранимый = Р × n / ПВС; неустранимый = (Кз факт / Кз норм) × n / (Nэж × ПВС) ×
    (ПВС − Сут − Р × Nэж), где Р — годовые затраты на ремонты в текущих ценах. Без Р и
    Сут — (Кз факт / Кз норм) × n / Nэж. Отрицательная база износа принимается 0,
    итог ограничен 100% — оба случая отмечаются."""
    return rf.physical_depreciation(
        age_years,
        economic_life_years,
        replacement_cost,
        annual_repair_cost,
        salvage_value,
        actual_load,
        normative_load,
        context=context,
    )


@tool
def rf_scrap_value(
    mass_kg: float, scrap_price_per_kg: float, disposal_cost: float = 0, context: Optional[dict] = None
) -> dict:
    """Стоимость утилизации: масса × цена лома − затраты на утилизацию."""
    return rf.scrap_value(mass_kg, scrap_price_per_kg, disposal_cost, context=context)


@tool
def rf_residual_value(
    replacement_cost: float,
    total_depreciation_pct: float,
    salvage_value: float = 0,
    context: Optional[dict] = None,
) -> dict:
    """Остаточная стоимость машины (ФСО №10, п. 14; формула (10) Козлова–Фролова).

    V = ПВС × (1 − СО), но не ниже стоимости утилизации; при СО = 100 % V = ±утилизация
    (отрицательная — затраты на неё). Утилизация не прибавляется: модель физического
    износа (rf_physical_depreciation) уже оставляет её остатком в конце срока."""
    return rf.residual_value(replacement_cost, total_depreciation_pct, salvage_value, context=context)


@tool
def rf_cost_from_price(
    price: float,
    profitability_pct: float,
    vat_pct: float = 0,
    profit_tax_pct: Optional[float] = None,
    context: Optional[dict] = None,
) -> dict:
    """Полная себестоимость из цены изготовителя: Сп = (1 − Кр) × Ц / (1 + НДС).

    При profit_tax_pct рентабельность считается чистой: Сп = (1 − Нпр − Кчр) × Ц /
    ((1 + НДС)(1 − Нпр)). Ставка НДС — входной параметр."""
    return rf.cost_from_price(price, profitability_pct, vat_pct, profit_tax_pct, context=context)


@tool
def rf_price_from_cost(
    cost: float,
    profitability_pct: float,
    vat_pct: float = 0,
    profit_tax_pct: Optional[float] = None,
    context: Optional[dict] = None,
) -> dict:
    """Цена изготовителя из полной себестоимости — обратный расчёт к rf_cost_from_price."""
    return rf.price_from_cost(cost, profitability_pct, vat_pct, profit_tax_pct, context=context)


@tool
def rf_qualitative_adjustments(analogs: List[dict], context: Optional[dict] = None) -> dict:
    """Метод направленных качественных корректировок (Козлов, Фролов, формулы 26–27).

    Аналог: price и adjustments [{"name", "direction": "up" | "down", "weight"}] (вес 1
    по умолчанию). Нижние и верхние аналоги, стоимость каждой пары
    (Цн × N−в + Цв × N+н) / (N−в + N+н), средневзвешенный итог и итог по паре."""
    return rf.qualitative_adjustments(analogs, context=context)


# ---------------------------------------------------------------------------
# Бизнес (ФСО №8)
# ---------------------------------------------------------------------------


@tool
def rf_business_income_approach(
    cash_flows: List[float],
    discount_rate_pct: float,
    basis: str,
    terminal_value: float = 0,
    mid_year: bool = False,
    obligations_not_in_flows: Optional[float] = None,
    non_operating_assets: float = 0,
    non_operating_liabilities: float = 0,
    currency: str = "RUB",
    terminal_timing: str = "end",
    flow_rate_basis: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """Доходный подход к бизнесу (ФСО №8, п. 9): 100% собственного капитала.

    basis equity: FCFE по ставке на собственный капитал (обязательства не вычитаются —
    долг уже в потоке). basis invested_capital: FCFF по WACC → инвестированный капитал,
    затем вычитаются только обязательства, не учтённые в потоке (не весь балансовый
    долг). obligations_not_in_flows: не указано — неизвестно (замечание), 0 —
    подтверждённое отсутствие. Неоперационные активы и обязательства учитываются один раз.
    cash_flows[0] — первый год. terminal_timing: end | mid."""
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
        terminal_timing,
        flow_rate_basis=flow_rate_basis, context=context,
    )


@tool
def rf_business_multiples(
    analogs: List[dict],
    subject_metric: float,
    multiple_name: str,
    basis: str,
    statistic: str = "median",
    currency: str = "RUB",
    context: Optional[dict] = None,
) -> dict:
    """Сравнительный подход к бизнесу (ФСО №8, пп. 10, 10.2): 100% базы мультипликатора.

    basis — числитель мультипликатора, задаётся явно: equity (P/E, P/BV…) |
    invested_capital (EV/EBITDA, EV/S…). Аналог: value, metric, name, происхождение.
    Медиана или среднее мультипликаторов × показатель объекта."""
    return rf.business_multiples(analogs, subject_metric, multiple_name, basis, statistic, currency, context=context)


@tool
def rf_net_assets(
    assets: List[dict],
    liabilities: List[dict],
    adjustments: Optional[List[dict]] = None,
    currency: str = "RUB",
    context: Optional[dict] = None,
) -> dict:
    """Метод чистых активов (ФСО №8, п. 11).

    Активы и обязательства: {"name", "value", "basis": "market" | "book"} — балансовые
    отмечаются. adjustments: {"name", "value"} со знаком, каждую обосновать."""
    return rf.net_assets(assets, liabilities, adjustments, currency, context=context)


@tool
def rf_business_liquidation_value(
    events: List[dict], discount_rate_pct: float, currency: str = "RUB", context: Optional[dict] = None
) -> dict:
    """Бизнес при обоснованной предпосылке ликвидации (ФСО №8, п. 11.2; МРз–1/23).

    events: {"period" (лет от даты оценки), "sale_proceeds", "debt_payments",
    "disposal_costs", "closure_costs"}; чистые поступления дисконтируются по ставке
    риска их получения. Для отдельного объекта — rf_asset_liquidation_value."""
    return rf.business_liquidation_value(events, discount_rate_pct, currency, context=context)


@tool
def rf_actual_share_value(
    share_pct: float,
    accepted_assets: float,
    accepted_liabilities: float,
    paid_share_pct: float = 100,
    currency: str = "RUB",
    context: Optional[dict] = None,
) -> dict:
    """Действительная стоимость доли участника ООО при выходе (14-ФЗ: п. 2 ст. 14, п. 6.1 ст. 23, ст. 26).

    ДСД = доля × оплаченная часть × (принятые активы − принятые обязательства).
    Правовая величина, не рыночная стоимость доли; скидки и премии не применяются."""
    return rf.actual_share_value(
        share_pct, accepted_assets, accepted_liabilities, paid_share_pct, currency, context=context
    )


@tool
def rf_deferred_tax_effect(
    tax_without_effect: List[float],
    tax_with_effect: List[float],
    discount_rate_pct: float,
    currency: str = "RUB",
    context: Optional[dict] = None,
) -> dict:
    """Приведённый эффект отложенных налогов ОНА/ОНО (МР–2/22) по годам 1..n.

    Учитывайте эффект один раз: в прогнозе потоков или отдельной корректировкой."""
    return rf.deferred_tax_effect(tax_without_effect, tax_with_effect, discount_rate_pct, currency, context=context)


@tool
def rf_business_interest_value(
    value_100pct: float,
    share_pct: float,
    adjustments: Optional[List[dict]] = None,
    currency: str = "RUB",
    value_basis: Optional[str] = None,
    net_debt: Optional[float] = None,
    context: Optional[dict] = None,
) -> dict:
    """Стоимость конкретной доли: 100% × доля, затем скидки и премии по шагам (pct | abs).

    value_basis — что такое value_100pct: equity (собственный капитал) | invested_capital
    (EV; тогда обязателен net_debt и собственный капитал = EV − net_debt). Без value_basis —
    замечание. Ни одна скидка не применяется автоматически; каждую обосновать."""
    return rf.business_interest_value(
        value_100pct, share_pct, adjustments, currency, value_basis, net_debt, context=context
    )


# ---------------------------------------------------------------------------
# Частные рекомендации «СРОО Экспертный совет»
# ---------------------------------------------------------------------------


@tool
def rf_market_rent_cost_plus(
    property_value: float,
    cap_rate_pct: float,
    owner_expenses: Optional[List[dict]] = None,
    vacancy_pct: float = 0,
    collection_loss_pct: float = 0,
    rentable_area_sqm: Optional[float] = None,
    currency: str = "RUB",
    confirmed_conditions: Optional[List[str]] = None,
    context: Optional[dict] = None,
) -> dict:
    """Рыночная арендная плата методом компенсации затрат (МРз–1/26).

    Требуемый ЧОД = стоимость × ставка капитализации; плюс расходы собственника
    {"name", "type": "abs" руб./год | "pct" % ДВД, "value"} и потери → валовая аренда
    в год, месяц и за м². Сначала проверьте сравнительный подход."""
    return rf.market_rent_cost_plus(
        property_value,
        cap_rate_pct,
        owner_expenses,
        vacancy_pct,
        collection_loss_pct,
        rentable_area_sqm,
        currency,
        confirmed_conditions=confirmed_conditions, context=context,
    )


@tool
def rf_cellular_site_rent(
    comparable_asset_value: float,
    kit_share_pct: float,
    cap_rate_pct: float,
    owner_costs_annual: float = 0,
    collection_loss_pct: float = 0,
    currency: str = "RUB",
    confirmed_conditions: Optional[List[str]] = None,
    context: Optional[dict] = None,
) -> dict:
    """Аренда места под стандартный комплект оборудования сотовой связи (МР–3/26 (2), § 9.4).

    Обратная капитализация: стоимость объекта сопоставимой полезности × доля комплекта
    × ставка, плюс расходы собственника и недосбор. Только если данных сравнения нет."""
    return rf.cellular_site_rent(
        comparable_asset_value,
        kit_share_pct,
        cap_rate_pct,
        owner_costs_annual,
        collection_loss_pct,
        currency,
        confirmed_conditions=confirmed_conditions, context=context,
    )


@tool
def rf_external_obsolescence_cost_income(
    cost_value_without_external: float,
    income_value_with_external: float,
    currency: str = "RUB",
    land_value: float = 0,
    confirmed_conditions: Optional[List[str]] = None,
    context: Optional[dict] = None,
) -> dict:
    """Внешнее обесценение (МРз–8/23-2, § 4.1): затратная стоимость без фактора − доходная с ним.

    Обе стоимости должны отличаться только внешним фактором — иначе двойной учёт износа.
    Отрицательный результат показывается, а не превращается в скидку. Процент — от всей
    затратной стоимости; при land_value возвращается и процент от улучшений
    (external_obsolescence_pct_of_improvements) — его, или рубли, передавайте в rf_cost_approach."""
    return rf.external_obsolescence_cost_income(
        cost_value_without_external,
        income_value_with_external,
        currency,
        land_value,
        confirmed_conditions=confirmed_conditions,
        context=context,
    )


@tool
def rf_external_obsolescence_paired_sales(
    value_without_impact: float,
    value_with_impact: float,
    base_value: float,
    currency: str = "RUB",
    confirmed_conditions: Optional[List[str]] = None,
    context: Optional[dict] = None,
) -> dict:
    """Внешнее обесценение по паре продаж (МРз–8/23-2, § 4.2): доля = 1 − с фактором / без фактора, × база."""
    return rf.external_obsolescence_paired_sales(
        value_without_impact,
        value_with_impact,
        base_value,
        currency,
        confirmed_conditions=confirmed_conditions,
        context=context,
    )


@tool
def rf_external_obsolescence_lost_income(
    cash_flows_without: List[float],
    cash_flows_with: List[float],
    discount_rate_pct: float,
    cost_value: Optional[float] = None,
    currency: str = "RUB",
    flow_rate_basis: Optional[dict] = None,
    confirmed_conditions: Optional[List[str]] = None,
    context: Optional[dict] = None,
) -> dict:
    """Внешнее обесценение по приведённым потерям дохода (МРз–8/23-2, § 4.3), годы 1..n.

    При cost_value — также в процентах от затратной стоимости."""
    return rf.external_obsolescence_lost_income(
        cash_flows_without,
        cash_flows_with,
        discount_rate_pct,
        cost_value,
        currency,
        flow_rate_basis=flow_rate_basis,
        confirmed_conditions=confirmed_conditions,
        context=context,
    )


@tool
def rf_fund_unit_value(
    distributions: List[float],
    final_compensation: float,
    discount_rate_pct: float,
    termination_costs: float = 0,
    final_period: Optional[float] = None,
    currency: str = "RUB",
    flow_rate_basis: Optional[dict] = None,
    confirmed_conditions: Optional[List[str]] = None,
    context: Optional[dict] = None,
) -> dict:
    """Доходная модель инвестиционного пая ПИФ (МРз–5/23).

    Приведённые чистые выплаты на пай (годы 1..n) плюс приведённая финальная
    компенсация за вычетом расходов прекращения; отдельной терминальной стоимости нет."""
    return rf.fund_unit_value(
        distributions,
        final_compensation,
        discount_rate_pct,
        termination_costs,
        final_period,
        currency,
        flow_rate_basis=flow_rate_basis,
        confirmed_conditions=confirmed_conditions,
        context=context,
    )


if __name__ == "__main__":
    mcp.run()  # stdio transport
