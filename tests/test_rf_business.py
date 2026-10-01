"""Business valuation under FSO No. 8."""

import pytest

from dealcalc.rf import (
    actual_share_value,
    business_income_approach,
    business_interest_value,
    business_multiples,
    deferred_tax_effect,
    business_liquidation_value,
    net_assets,
)

FLOWS = [100, 110, 121]


def test_income_approach_equity_basis():
    # 100/1.1 + 110/1.21 + 121/1.331 = 272.73; 1331/1.331 = 1000
    result = business_income_approach(
        FLOWS, 10, "equity", terminal_value=1_331, non_operating_assets=50, non_operating_liabilities=20
    )

    assert result["flow_type"] == "FCFE"
    assert result["present_value_cash_flows"] == pytest.approx(272.73, abs=0.01)
    assert result["terminal_present_value"] == 1_000.0
    assert result["invested_capital_value"] is None
    assert result["equity_value_100pct"] == pytest.approx(1_302.73, abs=0.01)
    assert result["method_card"]["id"] == "BUSINESS_EQUITY_DCF"


def test_income_approach_invested_capital_bridge():
    result = business_income_approach(
        FLOWS,
        10,
        "invested_capital",
        terminal_value=1_331,
        obligations_not_in_flows=300,
        non_operating_assets=50,
        non_operating_liabilities=20,
    )

    assert result["flow_type"] == "FCFF"
    assert result["invested_capital_value"] == pytest.approx(1_272.73, abs=0.01)
    assert result["equity_value_100pct"] == pytest.approx(1_002.73, abs=0.01)


def test_income_approach_rejects_debt_deduction_for_fcfe():
    with pytest.raises(ValueError, match="FCFE already reflect debt"):
        business_income_approach(FLOWS, 10, "equity", obligations_not_in_flows=300)


def test_income_approach_rejects_unknown_basis():
    with pytest.raises(ValueError, match="basis"):
        business_income_approach(FLOWS, 10, "enterprise")


ANALOGS = [
    {"name": "А", "value": 1_000, "metric": 100, "source": "Мосбиржа", "date": "2026-09-30", "price_type": "сделка"},
    {"name": "Б", "value": 1_200, "metric": 100, "source": "Мосбиржа", "date": "2026-09-30", "price_type": "сделка"},
    {"name": "В", "value": 900, "metric": 100, "source": "Мосбиржа", "date": "2026-09-30", "price_type": "сделка"},
]


def test_business_multiples_median():
    result = business_multiples(ANALOGS, 50, "P/E", "equity")

    assert [item["multiple"] for item in result["analogs"]] == [10.0, 12.0, 9.0]
    assert result["selected_multiple"] == 10.0
    assert result["mean_multiple"] == pytest.approx(10.3333, abs=0.0001)
    assert result["value_100pct"] == 500.0
    assert result["status"] == "черновой расчёт"


def test_business_multiples_basis_is_explicit_not_parsed_from_name():
    result = business_multiples(ANALOGS, 50, "Цена/Прибыль", "equity")

    assert result["basis"] == "equity"
    assert result["checks"] == []


@pytest.mark.parametrize(
    "analogs, metric, message",
    [
        ([], 50, "at least one"),
        ([{"value": 100, "metric": -5}], 50, "metric"),
        (ANALOGS, 0, "subject_metric"),
    ],
)
def test_business_multiples_rejects_invalid_input(analogs, metric, message):
    with pytest.raises(ValueError, match=message):
        business_multiples(analogs, metric, "P/E", "equity")


def test_net_assets_flags_book_values():
    result = net_assets(
        assets=[{"name": "Здание", "value": 1_000, "basis": "market"}, {"name": "Запасы", "value": 500, "basis": "book"}],
        liabilities=[{"name": "Кредит", "value": 600, "basis": "market"}],
        adjustments=[{"name": "Сомнительная дебиторка", "value": -50}],
    )

    assert result["equity_value_100pct"] == 850.0
    assert any("Запасы" in check for check in result["checks"])
    assert result["status"] == "нужна проверка оценщика"


def test_net_assets_rejects_invalid_basis():
    with pytest.raises(ValueError, match="basis"):
        net_assets([{"name": "x", "value": 1, "basis": "fair"}], [])


def test_liquidation_value_discounts_dated_events():
    result = business_liquidation_value(
        [
            {"period": 0.5, "sale_proceeds": 1_000, "debt_payments": 300, "disposal_costs": 50},
            {"period": 1, "sale_proceeds": 500, "closure_costs": 100},
        ],
        20,
    )

    assert [row["net_proceeds"] for row in result["events"]] == [650.0, 400.0]
    assert result["business_liquidation_value"] == pytest.approx(926.70, abs=0.01)
    assert result["checks"] == []


def test_liquidation_value_flags_immediate_proceeds():
    result = business_liquidation_value([{"period": 0, "sale_proceeds": 1_000}], 20)

    assert "немедленными" in result["checks"][0]


def test_actual_share_value():
    result = actual_share_value(25, accepted_assets=10_000_000, accepted_liabilities=4_000_000)

    assert result["actual_share_value"] == 1_500_000.0
    assert "ДСД не равна рыночной стоимости доли." in result["guardrails"]
    assert result["status"] == "черновой расчёт"


def test_actual_share_value_partly_paid():
    result = actual_share_value(25, 10_000_000, 4_000_000, paid_share_pct=80)

    assert result["actual_share_value"] == 1_200_000.0
    assert result["status"] == "нужна проверка оценщика"


def test_deferred_tax_effect():
    result = deferred_tax_effect([100, 100], [80, 90], 10)

    assert [row["tax_change"] for row in result["periods"]] == [20.0, 10.0]
    assert result["present_value_effect"] == pytest.approx(26.45, abs=0.01)


def test_deferred_tax_effect_requires_equal_lengths():
    with pytest.raises(ValueError, match="same length"):
        deferred_tax_effect([100, 100], [80], 10)


def test_business_interest_value_with_discount():
    result = business_interest_value(
        1_000, 25, [{"name": "Скидка за недостаточную ликвидность", "type": "pct", "value": -15}]
    )

    assert result["pro_rata_value"] == 250.0
    assert result["adjustments"][0]["price_after"] == 212.5
    assert result["interest_value"] == 212.5
    assert result["status"] == "черновой расчёт"
    assert "обоснуйте" in result["guardrails"][0]


def test_business_interest_value_without_adjustments():
    result = business_interest_value(1_000, 25)

    assert result["interest_value"] == 250.0
    assert result["checks"] == []


def test_net_assets_adjustments_are_a_reminder_not_a_defect():
    result = net_assets(
        [{"name": "Здание", "value": 1_000, "basis": "market"}],
        [],
        [{"name": "Корректировка", "value": -50}],
    )

    assert result["status"] == "черновой расчёт"
    assert result["guardrails"]
