"""Methods from Kozlov V.V., Frolov I.S. "Оценка машин и оборудования"
(srosovet.ru): braking coefficient and secondary-market analogs."""

import pytest

from dealcalc.rf import braking_coefficient, new_equivalent_price, vehicle_comparative_approach


def test_braking_coefficient_from_two_analogs():
    # Book: drills 59 000 RUB at 32 mm and 74 400 RUB at 50 mm
    result = braking_coefficient(59_000, 32, 74_400, 50)

    assert result["braking_coefficient"] == pytest.approx(0.5197, abs=0.0001)


@pytest.mark.parametrize(
    "args, message",
    [
        ((0, 32, 74_400, 50), "price_1"),
        ((59_000, 32, 74_400, 32), "different"),
        ((59_000, -1, 74_400, 50), "param_1"),
    ],
)
def test_braking_coefficient_rejects_invalid_input(args, message):
    with pytest.raises(ValueError, match=message):
        braking_coefficient(*args)


def test_new_equivalent_price_formula_22():
    result = new_equivalent_price(630_000, 37)

    assert result["new_equivalent_price"] == 1_000_000.0


@pytest.mark.parametrize("depreciation", [-1, 100])
def test_new_equivalent_price_rejects_invalid_depreciation(depreciation):
    with pytest.raises(ValueError, match="total_depreciation_pct"):
        new_equivalent_price(1, depreciation)


def test_param_adjustment_step():
    result = vehicle_comparative_approach(
        {},
        [
            {
                "price_rub": 124_871,
                "adjustments": [
                    {
                        "name": "Наибольший диаметр сверления",
                        "type": "param",
                        "subject": 20,
                        "analog": 25,
                        "exponent": 1.2311,
                    }
                ],
            }
        ],
    )
    step = result["comparables"][0]["adjustments"][0]

    assert step["type"] == "param"
    assert step["subject"] == 20
    assert step["analog"] == 25
    assert step["exponent"] == 1.2311
    assert step["factor"] == pytest.approx(0.7598, abs=0.0001)
    # the book rounds the factor to 0.7598 and gets 94 877
    assert step["price_after"] == pytest.approx(94_875.85, abs=0.01)


def test_depreciation_adjustment_step_compares_wear():
    result = vehicle_comparative_approach(
        {},
        [
            {
                "price_rub": 630_000,
                "adjustments": [
                    {
                        "name": "Разница в износе",
                        "type": "depreciation",
                        "analog_pct": 37,
                        "subject_pct": 20,
                    }
                ],
            }
        ],
    )
    step = result["comparables"][0]["adjustments"][0]

    assert step["factor"] == pytest.approx(0.8 / 0.63, abs=0.0001)
    assert step["price_after"] == 800_000.0


@pytest.mark.parametrize(
    "step, message",
    [
        ({"name": "x", "type": "param", "subject": 0, "analog": 25, "exponent": 1}, "subject"),
        ({"name": "x", "type": "param", "subject": 20, "analog": 25}, "exponent"),
        ({"name": "x", "type": "depreciation", "analog_pct": 100}, "analog_pct"),
        ({"name": "x", "type": "depreciation", "analog_pct": 10, "subject_pct": 101}, "subject_pct"),
    ],
)
def test_invalid_new_adjustment_steps_are_rejected(step, message):
    with pytest.raises(ValueError, match=message):
        vehicle_comparative_approach({}, [{"price_rub": 100_000, "adjustments": [step]}])


def test_book_example_full_chain():
    # Book example: drill 2С125 -> subject, June 2008; result 50 660 RUB
    result = vehicle_comparative_approach(
        {},
        [
            {
                "price_rub": 109_774,
                "adjustments": [
                    {"name": "Индексация на дату оценки", "type": "pct", "value": 3.03},
                    {"name": "Вылет шпинделя", "type": "abs", "value": 80 * 147.14},
                    {
                        "name": "Наибольший диаметр сверления",
                        "type": "param",
                        "subject": 20,
                        "analog": 25,
                        "exponent": 1.2311,
                    },
                    {"name": "Без НДС 18%", "type": "pct", "value": (1 / 1.18 - 1) * 100},
                    {
                        "name": "Физический износ",
                        "type": "depreciation",
                        "analog_pct": 0,
                        "subject_pct": 37,
                    },
                ],
            }
        ],
    )

    # The book rounds intermediate coefficients (0.7598, 0.8475) and the
    # result, giving 50 660; the exact chain is 50 654.20.
    assert result["indicated_value"] == pytest.approx(50_660, abs=10)
