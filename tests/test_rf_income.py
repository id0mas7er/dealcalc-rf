import pytest

from dealcalc.rf import cap_rate_extraction, net_operating_income

EXPENSES = [
    {"name": "Налог на имущество", "type": "abs", "value": 500_000},
    {"name": "Управление", "type": "pct", "value": 3},
    {"name": "Страхование", "type": "abs", "value": 50_000},
]


def test_net_operating_income_from_area_and_rent_rate():
    result = net_operating_income(
        rentable_area_sqm=1_000,
        rent_rate_sqm_year=12_000,
        vacancy_pct=10,
        collection_loss_pct=2,
        other_income_annual=100_000,
        operating_expenses=EXPENSES,
    )

    assert result["potential_gross_income"] == 12_000_000.0
    assert result["vacancy_loss"] == 1_200_000.0
    assert result["collection_loss"] == 216_000.0
    assert result["effective_gross_income"] == 10_684_000.0
    assert [item["amount"] for item in result["operating_expenses"]] == [
        500_000.0,
        320_520.0,
        50_000.0,
    ]
    assert result["operating_expenses"][1]["name"] == "Управление"
    assert result["total_operating_expenses"] == 870_520.0
    assert result["operating_expense_ratio_pct"] == 8.15
    assert result["net_operating_income"] == 9_813_480.0


def test_net_operating_income_from_given_potential_gross_income():
    result = net_operating_income(potential_gross_income=1_000_000, vacancy_pct=5)

    assert result["effective_gross_income"] == 950_000.0
    assert result["net_operating_income"] == 950_000.0
    assert result["operating_expenses"] == []


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "potential_gross_income"),
        ({"potential_gross_income": 1, "rentable_area_sqm": 1, "rent_rate_sqm_year": 1}, "either"),
        ({"rentable_area_sqm": 0, "rent_rate_sqm_year": 1}, "rentable_area_sqm"),
        ({"potential_gross_income": 1, "vacancy_pct": 100}, "vacancy_pct"),
        ({"potential_gross_income": 1, "collection_loss_pct": -1}, "collection_loss_pct"),
        (
            {"potential_gross_income": 1, "operating_expenses": [{"type": "abs", "value": 1}]},
            "name",
        ),
        (
            {
                "potential_gross_income": 1,
                "operating_expenses": [{"name": "x", "type": "abs", "value": -1}],
            },
            "value",
        ),
        (
            {
                "potential_gross_income": 1,
                "operating_expenses": [{"name": "x", "type": "rub", "value": 1}],
            },
            "type",
        ),
    ],
)
def test_net_operating_income_rejects_invalid_input(kwargs, message):
    with pytest.raises(ValueError, match=message):
        net_operating_income(**kwargs)


def test_cap_rate_extraction():
    result = cap_rate_extraction(
        [
            {"price": 10_000_000, "noi": 1_100_000, "source": "ЦИАН"},
            {"price": 20_000_000, "noi": 2_000_000},
            {"price": 15_000_000, "noi": 1_800_000},
        ]
    )

    assert [item["cap_rate_pct"] for item in result["comparables"]] == [11.0, 10.0, 12.0]
    assert result["comparables"][0]["source"] == "ЦИАН"
    assert result["sample_size"] == 3
    assert result["mean_cap_rate_pct"] == 11.0
    assert result["median_cap_rate_pct"] == 11.0
    assert result["min_cap_rate_pct"] == 10.0
    assert result["max_cap_rate_pct"] == 12.0
    assert result["variation"]["coefficient_pct"] == 9.09
    assert result["variation"]["homogeneous"] is True


@pytest.mark.parametrize(
    "comparables, message",
    [
        ([], "at least one"),
        ([{"price": 0, "noi": 1}], "price"),
        ([{"price": 1, "noi": 0}], "noi"),
    ],
)
def test_cap_rate_extraction_rejects_invalid_input(comparables, message):
    with pytest.raises(ValueError, match=message):
        cap_rate_extraction(comparables)
