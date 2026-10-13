"""Износ ТС, метод срока жизни, износ шин (разбор отчётов 13.10.2026: 147/25-ю, БМК — R2, R30, R4)."""

from __future__ import annotations

import math

import pytest

from dealcalc import rf


def test_rd37_reproduces_report_147():
    result = rf.vehicle_wear_rd37(11.25, 291.827, 5.2, 0.25, 20, region_coef=1.1)

    assert result["wear_pct"] == 82.73 and not result["capped"]


def test_rd37_is_limited_to_100():
    result = rf.vehicle_wear_rd37(30, 900, 5.2, 0.25, 20, region_coef=1.1)

    assert result["wear_pct"] == 100 and result["capped"] and result["checks"]


def test_exponential_wear():
    result = rf.vehicle_wear_exponential(10, 150, 0.07, 0.003)

    assert result["wear_pct"] == round(100 * (1 - math.exp(-(0.7 + 0.45))), 2)


def test_effective_life_reproduces_bmk():
    assert rf.wear_effective_life(20, 2)["wear_pct"] == 90.91
    assert rf.wear_effective_life(20, 5)["wear_pct"] == 80
    with pytest.raises(ValueError):
        rf.wear_effective_life(0, 0)


def test_tire_wear_reproduces_report_147():
    assert rf.tire_wear(9.5, 7, 4)["wear_pct"] == 45.4545
    with pytest.raises(ValueError, match="min_tread_mm"):
        rf.tire_wear(4, 3, 4)
