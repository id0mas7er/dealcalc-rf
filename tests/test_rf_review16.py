"""Deep review of the books (04.10.2026): P01, P02, M04."""

import inspect

from dealcalc import rf
from dealcalc.rf import _adjustments


# P01: costs arising only while the premises are let — a share of the occupied ПВД.


def _noi(base):
    return rf.net_operating_income(
        1_000_000, vacancy_pct=20, collection_loss_pct=10, other_income_annual=100_000,
        operating_expenses=[{"name": "Уборка", "type": "pct", "value": 10, "base": base}],
    )


def test_expense_of_the_occupied_pgi():
    result = _noi("occupied")

    assert result["operating_expenses"][0]["base"] == "occupied"
    assert result["operating_expenses"][0]["amount"] == 80_000.0
    assert result["net_operating_income"] == 740_000.0


def test_occupied_differs_from_pgi_and_egi():
    amounts = {base: _noi(base)["operating_expenses"][0]["amount"] for base in ("pgi", "egi", "occupied")}

    assert amounts == {"pgi": 100_000.0, "egi": 82_000.0, "occupied": 80_000.0}


# P02: the docstring describes the default rule of choice.


def test_docstring_names_the_default_rule():
    doc = inspect.getdoc(_adjustments.apply_adjustments)

    assert "choice_rule" in doc and "mean" in doc


# M04: the age reaching the economic life.


def test_age_reaching_the_life_is_a_reminder():
    result = rf.physical_depreciation(10, 10)

    assert result["total_pct"] == 100.0
    assert any("срок экономической жизни" in item for item in result["guardrails"])


def test_age_below_the_life_has_no_reminder():
    result = rf.physical_depreciation(5, 15)

    assert not any("срок экономической жизни" in item for item in result["guardrails"])
