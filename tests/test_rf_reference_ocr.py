"""Reference books after OCR (0.11.0): domain of an equation, operating expenses of ПВД."""

import pytest

from dealcalc import rf
from test_rf_report import CONTEXT

META = {"source": "S", "date": "2026-10-01", "price_type": "transaction"}
AREA = {"name": "Площадь", "type": "param", "subject": 2000, "analog": 10000, "exponent": -0.06}


def _first_step(step):
    result = rf.comparative_approach(1, [
        dict(META, price=100, area_sqm=1, adjustments=[step]),
        dict(META, price=100, area_sqm=1),
    ], context=CONTEXT)
    return result, result["comparables"][0]["adjustments"][0]


# 1. Domain of an equation: the range of x on which it was built.


def test_param_within_domain():
    result, step = _first_step(dict(AREA, domain={"high": 30000}))

    assert step["domain"] == {"low": None, "high": 30000.0}
    assert step["within_domain"] is True
    assert result["checks"] == []


@pytest.mark.parametrize("domain", [{"high": 5000}, {"low": 3000, "high": 30000}])
def test_param_outside_domain_is_a_check(domain):
    result, step = _first_step(dict(AREA, domain=domain))

    assert step["within_domain"] is False
    assert any("«Площадь»" in check and "области применимости" in check for check in result["checks"])


def test_param_outside_domain_with_justification_is_a_guardrail():
    result, _ = _first_step(dict(AREA, domain={"high": 5000}, justification="других данных нет"))

    assert result["checks"] == []
    assert any("области применимости" in item and "обоснование" in item for item in result["guardrails"])


def test_domain_does_not_change_the_price():
    _, plain = _first_step(AREA)
    _, bounded = _first_step(dict(AREA, domain={"high": 5000}))

    assert bounded["price_after"] == plain["price_after"]


@pytest.mark.parametrize("domain, message", [
    ({}, "low or high"),
    ({"low": None, "high": None}, "low or high"),
    ({"low": 10, "high": 5}, "must not exceed"),
    ({"low": "x"}, "domain.low"),
    ("30000", "must be an object"),
])
def test_invalid_domain(domain, message):
    with pytest.raises(ValueError, match=message):
        _first_step(dict(AREA, domain=domain))


def test_domain_only_for_param():
    with pytest.raises(ValueError, match="domain applies to param"):
        _first_step({"name": "Торг", "type": "pct", "value": -5, "domain": {"high": 1}})


def test_staged_chosen_variant_outside_domain_is_a_check():
    result, step = _first_step({"name": "Площадь", "type": "staged", "stages": [
        [dict(AREA, label="среднее уравнение", domain={"high": 5000})],
    ]})

    assert step["chosen"]["within_domain"] is False
    assert step["chosen"]["domain"] == {"low": None, "high": 5000.0}
    assert any("«среднее уравнение»" in check and "области применимости" in check for check in result["checks"])


def test_staged_variant_not_chosen_outside_domain_is_not_a_check():
    result, step = _first_step({"name": "Площадь", "type": "staged", "stages": [
        [dict(AREA, label="среднее уравнение")],
        [dict(AREA, label="граница", domain={"high": 5000})],
    ]})

    assert step["chosen"]["label"] == "среднее уравнение"
    assert result["checks"] == []


# 2. Operating expenses as a share of ПВД (Leifer) and their bounds.


def _noi(*expenses):
    return rf.net_operating_income(1_000_000, vacancy_pct=10, operating_expenses=list(expenses))


def test_expense_pct_of_pgi():
    result = _noi({"name": "Электричество", "type": "pct", "value": 5.3, "base": "pgi"})
    item = result["operating_expenses"][0]

    assert item["base"] == "pgi"
    assert item["amount"] == 53_000.0


def test_expense_pct_of_egi_by_default():
    item = _noi({"name": "Электричество", "type": "pct", "value": 5.3})["operating_expenses"][0]

    assert item["base"] == "egi"
    assert item["amount"] == 47_700.0


@pytest.mark.parametrize("expense, message", [
    ({"name": "X", "type": "pct", "value": 1, "base": "gross"}, "base must be 'egi', 'pgi' or 'occupied'"),
    ({"name": "X", "type": "abs", "value": 1, "base": "pgi"}, "base applies to pct"),
])
def test_invalid_expense_base(expense, message):
    with pytest.raises(ValueError, match=message):
        _noi(expense)


def test_expense_within_range_keeps_evidence():
    result = _noi({"name": "Отопление", "type": "pct", "value": 5.9, "base": "pgi",
                   "range": {"low": 5.2, "high": 6.5, "mean": 5.9},
                   "source": "Лейфер, операционные расходы 2026", "page": "табл. 8"})
    item = result["operating_expenses"][0]

    assert item["within_range"] is True
    assert {key: item["range"][key] for key in ("low", "high", "mean")} == {"low": 5.2, "high": 6.5, "mean": 5.9}
    assert item["source"] == "Лейфер, операционные расходы 2026" and item["page"] == "табл. 8"
    assert result["checks"] == []


def test_expense_outside_range_is_a_check():
    result = _noi({"name": "Отопление", "type": "pct", "value": 9, "base": "pgi",
                   "range": {"low": 5.2, "high": 6.5}})

    assert result["operating_expenses"][0]["within_range"] is False
    assert any("«Отопление»" in check and "вне границ" in check for check in result["checks"])


def test_expense_outside_range_with_justification_is_a_guardrail():
    result = _noi({"name": "Отопление", "type": "pct", "value": 9, "base": "pgi",
                   "range": {"low": 5.2, "high": 6.5}, "justification": "старая котельная"})

    assert result["checks"] == []
    assert any("«Отопление»" in item for item in result["guardrails"])
