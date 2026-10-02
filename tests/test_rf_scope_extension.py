"""Scope extension after the Codex methodology review: D11 (flow and rate),
D13 (conditions of private models)."""

import pytest

from dealcalc import rf

NOMINAL_POST_TAX = {"price_level": "nominal", "tax": "post_tax", "currency": "RUB"}


# D11. The basis of the flow and of the rate.


def test_income_model_without_basis_is_reminded():
    result = rf.income_capitalization(1_000_000, 10)

    assert result["flow_rate_basis"] is None
    assert any("flow_rate_basis" in note for note in result["guardrails"])


def test_matching_basis_is_clean():
    result = rf.dcf_valuation(
        [100, 110], 12, flow_rate_basis={"flow": NOMINAL_POST_TAX, "rate": NOMINAL_POST_TAX}
    )

    assert result["checks"] == []
    assert not any("flow_rate_basis" in note for note in result["guardrails"])
    assert result["flow_rate_basis"]["rate"]["price_level"] == "nominal"


def test_real_flow_with_nominal_rate_is_checked():
    result = rf.business_income_approach(
        [100], 15, "equity",
        flow_rate_basis={"flow": {**NOMINAL_POST_TAX, "price_level": "real"}, "rate": NOMINAL_POST_TAX},
    )

    assert any("уровню цен" in check for check in result["checks"])


def test_currency_mismatch_is_checked():
    result = rf.npv(
        [-100, 60, 60], 10,
        flow_rate_basis={"flow": {**NOMINAL_POST_TAX, "currency": "usd"}, "rate": NOMINAL_POST_TAX},
    )

    assert any("валюте" in check for check in result["checks"])


def test_flow_rate_basis_is_validated():
    with pytest.raises(ValueError, match="price_level"):
        rf.income_capitalization(100, 10, flow_rate_basis={"flow": {"price_level": "nominal-ish"}, "rate": {}})
    with pytest.raises(ValueError, match="income models"):
        rf.comparative_approach(1, [{"price": 1, "area_sqm": 1}], flow_rate_basis={})


# D13. Conditions of private models of the Expert Council.


def test_market_rent_conditions_unconfirmed_are_checked():
    result = rf.market_rent_cost_plus(10_000_000, 10)

    ids = [item["id"] for item in result["required_conditions"]]
    assert "result_form_defined" in ids
    assert any("confirmed_conditions" in check for check in result["checks"])


def test_market_rent_conditions_confirmed():
    result = rf.market_rent_cost_plus(
        10_000_000, 10,
        confirmed_conditions=["no_comparable_rents", "owner_costs_complete", "result_form_defined"],
    )

    assert not any("confirmed_conditions" in check for check in result["checks"])
    assert all(item["confirmed"] for item in result["required_conditions"])


def test_unknown_condition_id_is_rejected():
    with pytest.raises(ValueError, match="unknown"):
        rf.fund_unit_value([10], 100, 10, confirmed_conditions=["whatever"])


def test_conditions_only_for_models_that_have_them():
    with pytest.raises(ValueError, match="no conditions"):
        rf.income_capitalization(100, 10, confirmed_conditions=["x"])


@pytest.mark.parametrize(
    "call",
    [
        lambda **kw: rf.cellular_site_rent(1_000_000, 10, 12, **kw),
        lambda **kw: rf.external_obsolescence_cost_income(100, 80, **kw),
        lambda **kw: rf.external_obsolescence_paired_sales(100, 80, 50, **kw),
        lambda **kw: rf.external_obsolescence_lost_income([10], [8], 10, **kw),
        lambda **kw: rf.fund_unit_value([10], 100, 10, **kw),
    ],
)
def test_every_private_model_has_conditions(call):
    result = call()

    assert result["required_conditions"]
    assert any("confirmed_conditions" in check for check in result["checks"])


def test_lost_income_horizon_condition():
    result = rf.external_obsolescence_lost_income([10], [8], 10)

    assert "full_horizon" in [item["id"] for item in result["required_conditions"]]


def test_liquidation_shows_price_and_net_proceeds():
    result = rf.asset_liquidation_value(1_000_000, 15, 6, 2, additional_costs=50_000)

    assert result["liquidation_price"] == pytest.approx(954_481.22, abs=0.01)
    assert result["liquidation_value"] == pytest.approx(result["liquidation_price"] - 50_000, abs=0.01)
