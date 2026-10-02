import pytest

from dealcalc.rf import vehicle_comparative_approach


def test_small_weights_do_not_round_to_zero():
    result = vehicle_comparative_approach({}, [
        {"price_rub": 1_000_000, "weight": 0.001},
        {"price_rub": 2_000_000, "weight": 0.003},
    ])
    assert result["weighted_mean_price"] == 1_750_000
    assert result["indicated_value"] == 2_000_000


def test_vehicle_comparative_approach_filters_and_uses_weighted_median():
    result = vehicle_comparative_approach(
        {"brand": "Lada", "model": "Vesta", "year": 2021, "mileage_km": 60_000},
        [
            {
                "listing_id": "1",
                "source": "drom",
                "brand": "Lada",
                "model": "Vesta",
                "year": 2021,
                "mileage_km": 55_000,
                "price_rub": 1_100_000,
                "weight": 2,
            },
            {
                "listing_id": "2",
                "source": "avito",
                "brand": "Lada",
                "model": "Vesta",
                "year": 2020,
                "mileage_km": 80_000,
                "price_rub": 1_000_000,
            },
            {
                "listing_id": "3",
                "source": "drom",
                "brand": "Lada",
                "model": "Granta",
                "year": 2021,
                "mileage_km": 40_000,
                "price_rub": 900_000,
            },
        ],
    )

    assert result["sample_size"] == 2
    assert result["rejected_count"] == 1
    assert result["indicated_value"] == 1_100_000.0
    assert result["analogs_spread"] == {"low": 1_000_000.0, "high": 1_100_000.0}


def test_vehicle_comparative_approach_reports_no_matches():
    with pytest.raises(ValueError, match="no comparable vehicles"):
        vehicle_comparative_approach(
            {"brand": "Toyota", "model": "Camry"},
            [{"brand": "Lada", "model": "Vesta", "price_rub": 1_000_000}],
        )


def test_vehicle_comparative_approach_rejects_negative_adjustment_below_minus_100():
    with pytest.raises(ValueError, match="adjustment_pct"):
        vehicle_comparative_approach(
            {"brand": "Lada", "model": "Vesta"},
            [
                {
                    "brand": "Lada",
                    "model": "Vesta",
                    "price_rub": 1_000_000,
                    "adjustment_pct": -100,
                }
            ],
        )
