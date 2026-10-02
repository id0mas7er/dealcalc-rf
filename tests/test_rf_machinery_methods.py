"""Remaining methods from Kozlov V.V., Frolov I.S. "Оценка машин и оборудования"."""

import pytest

from dealcalc.rf import (
    chain_index,
    cost_from_price,
    index_price,
    parameter_unit_price,
    physical_depreciation,
    price_from_cost,
    qualitative_adjustments,
    residual_value,
    scrap_value,
)


def test_parameter_unit_price_book_example():
    # Book: drills 21 000 RUB at 180 mm and 24 500 RUB at 250 mm -> 50 RUB/mm
    assert parameter_unit_price(21_000, 180, 24_500, 250)["unit_price"] == 50.0


def test_parameter_unit_price_rejects_equal_parameters():
    with pytest.raises(ValueError, match="different"):
        parameter_unit_price(1, 5, 2, 5)


def test_index_price_book_example():
    # Book: 109 774 RUB, chain index 1.01 for 3 months -> 1.0303, 113 100 RUB
    result = index_price(109_774, 1.01, 3)

    assert result["total_index"] == pytest.approx(1.0303, abs=0.0001)
    assert result["indexed_price"] == pytest.approx(113_100.26, abs=0.01)


def test_chain_index_from_two_prices():
    result = chain_index(100_000, 121_000, 2)

    assert result["chain_index"] == pytest.approx(1.1)


@pytest.mark.parametrize(
    "call, message",
    [
        (lambda: index_price(1, 0, 3), "chain_index"),
        (lambda: index_price(1, 1.01, -1), "periods"),
        (lambda: chain_index(0, 1, 1), "price_start"),
        (lambda: chain_index(1, 2, 0), "periods"),
    ],
)
def test_index_methods_reject_invalid_input(call, message):
    with pytest.raises(ValueError, match=message):
        call()


def test_physical_depreciation_age_life_book_example():
    # Book: 7.4 years of 20 years of service -> 37%
    assert physical_depreciation(7.4, 20)["total_pct"] == 37.0


def test_physical_depreciation_with_load():
    result = physical_depreciation(5, 10, actual_load=0.8, normative_load=0.5)

    assert result["load_ratio"] == 1.6
    assert result["total_pct"] == 80.0


def test_physical_depreciation_curable_and_incurable():
    # ФИУ = 20 000 * 5 / 1 000 000 = 10%
    # ФИН = 5 / (10 * 1 000 000) * (1 000 000 - 50 000 - 20 000 * 10) = 37.5%
    result = physical_depreciation(
        5,
        10,
        replacement_cost=1_000_000,
        annual_repair_cost=20_000,
        salvage_value=50_000,
    )

    assert result["curable_pct"] == 10.0
    assert result["incurable_pct"] == 37.5
    assert result["total_pct"] == 47.5
    assert result["capped"] is False


def test_physical_depreciation_is_capped_at_100():
    result = physical_depreciation(30, 10)

    assert result["total_pct"] == 100.0
    assert result["capped"] is True


@pytest.mark.parametrize(
    "args, kwargs, message",
    [
        ((-1, 10), {}, "age_years"),
        ((1, 0), {}, "economic_life_years"),
        ((1, 10), {"annual_repair_cost": 1}, "replacement_cost"),
        ((1, 10), {"actual_load": 0}, "actual_load"),
    ],
)
def test_physical_depreciation_rejects_invalid_input(args, kwargs, message):
    with pytest.raises(ValueError, match=message):
        physical_depreciation(*args, **kwargs)


def test_scrap_value():
    result = scrap_value(mass_kg=2_000, scrap_price_per_kg=20, disposal_cost=10_000)

    assert result["scrap_value"] == 30_000.0


def test_residual_value_with_salvage():
    result = residual_value(1_000_000, 37, salvage_value=30_000)

    assert result["depreciated_value"] == 630_000.0
    assert result["residual_value"] == 630_000.0


def test_residual_value_with_disposal_cost():
    assert residual_value(1_000_000, 90, salvage_value=-20_000)["residual_value"] == 100_000.0
    assert residual_value(1_000_000, 100, salvage_value=-20_000)["residual_value"] == -20_000.0


def test_cost_from_price_with_vat():
    # Сп = (1 - 0.10) * 1 200 000 / 1.20
    result = cost_from_price(1_200_000, profitability_pct=10, vat_pct=20)

    assert result["full_cost"] == 900_000.0
    assert result["profit"] == 100_000.0
    assert result["vat"] == 200_000.0


def test_cost_from_price_with_net_profitability_and_profit_tax():
    # Сп = (1 - 0.20 - 0.08) * 1 200 000 / (1.20 * (1 - 0.20))
    result = cost_from_price(1_200_000, profitability_pct=8, vat_pct=20, profit_tax_pct=20)

    assert result["full_cost"] == 900_000.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"profitability_pct": 10, "vat_pct": 20},
        {"profitability_pct": 8, "vat_pct": 20, "profit_tax_pct": 20},
        {"profitability_pct": 0, "vat_pct": 0},
    ],
)
def test_price_from_cost_is_inverse(kwargs):
    cost = cost_from_price(1_200_000, **kwargs)["full_cost"]

    assert price_from_cost(cost, **kwargs)["price"] == pytest.approx(1_200_000, abs=0.01)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"profitability_pct": 100}, "profitability_pct"),
        ({"profitability_pct": 10, "vat_pct": -1}, "vat_pct"),
        ({"profitability_pct": 85, "profit_tax_pct": 20}, "profit_tax_pct"),
    ],
)
def test_price_cost_conversion_rejects_invalid_input(kwargs, message):
    with pytest.raises(ValueError, match=message):
        cost_from_price(1_000, **kwargs)


def _steps(up, down):
    return [{"name": f"up {i}", "direction": "up"} for i in range(up)] + [
        {"name": f"down {i}", "direction": "down"} for i in range(down)
    ]


def test_qualitative_adjustments_single_pair_formula_27():
    # Book figure 9: upper analog has 2 effective down, lower has 4 effective up
    result = qualitative_adjustments(
        [
            {"price": 100, "adjustments": _steps(4, 0)},
            {"price": 160, "adjustments": _steps(0, 2)},
        ]
    )

    assert result["pairs"][0]["value"] == 140.0
    assert result["weighted_value"] == 140.0
    assert result["range_value"] == 140.0


def test_qualitative_adjustments_several_pairs():
    result = qualitative_adjustments(
        [
            {"price": 100, "adjustments": _steps(2, 0), "source": "A"},
            {"price": 110, "adjustments": _steps(2, 1), "source": "B"},
            {"price": 150, "adjustments": _steps(0, 1), "source": "C"},
        ]
    )

    assert [analog["role"] for analog in result["analogs"]] == ["lower", "lower", "upper"]
    assert [pair["value"] for pair in result["pairs"]] == [133.33, 130.0]
    assert [pair["weight"] for pair in result["pairs"]] == pytest.approx([4 / 7, 3 / 7], abs=1e-4)
    assert result["weighted_value"] == pytest.approx(131.9, abs=0.01)
    # range method: upper with fewest effective adjustments, lower with fewest
    # effective adjustments and the highest price
    assert result["range_value"] == 130.0


def test_qualitative_adjustments_weighted_directions():
    result = qualitative_adjustments(
        [
            {"price": 100, "adjustments": [{"name": "Состояние", "direction": "up", "weight": 3}]},
            {"price": 200, "adjustments": [{"name": "Комплектация", "direction": "down", "weight": 1}]},
        ]
    )

    # (100 * 1 + 200 * 3) / (1 + 3)
    assert result["weighted_value"] == 175.0


def test_qualitative_adjustments_reports_neutral_analogs():
    result = qualitative_adjustments(
        [
            {"price": 100, "adjustments": _steps(1, 0)},
            {"price": 120, "adjustments": _steps(1, 1)},
            {"price": 150, "adjustments": _steps(0, 1)},
        ]
    )

    assert result["analogs"][1]["role"] == "neutral"
    assert len(result["pairs"]) == 1


@pytest.mark.parametrize(
    "analogs, message",
    [
        ([{"price": 100, "adjustments": _steps(1, 0)}], "lower and one upper"),
        ([{"price": 100, "adjustments": [{"name": "x", "direction": "left"}]}], "direction"),
        ([{"price": 100, "adjustments": [{"name": "x", "direction": "up", "weight": 0}]}], "weight"),
    ],
)
def test_qualitative_adjustments_rejects_invalid_input(analogs, message):
    with pytest.raises(ValueError, match=message):
        qualitative_adjustments(analogs)
