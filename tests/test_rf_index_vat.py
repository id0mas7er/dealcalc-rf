"""Индекс на дату, здание из частей, НДС (разбор отчётов 13.10.2026: «Лагерь», 147/25-ю — R18, R19, R5)."""

from __future__ import annotations

import pytest

from dealcalc import rf

CONTEXT = {"valuation_date": "2026-08-31", "value_type": "рыночная", "vat": "excluded"}


def _index():
    return rf.interpolate_index("2026-08-31", {"date": "2026-06-30", "value": 224.228},
                                {"date": "2026-09-30", "value": 230.266}, base_value=138.351, source="КО-ИНВЕСТ 133")


def test_index_interpolation_reproduces_lager():
    result = _index()

    assert result["days"] == "62 / 92" and result["ratio_to_base"] == 1.65013 and not result["checks"]
    outside = rf.interpolate_index("2026-12-31", {"date": "2026-06-30", "value": 1}, {"date": "2026-09-30", "value": 2})
    assert outside["checks"] and outside["guardrails"]
    with pytest.raises(ValueError, match="earlier"):
        rf.interpolate_index("2026-08-31", {"date": "2026-09-30", "value": 1}, {"date": "2026-06-30", "value": 2})


def test_building_with_a_veranda_reproduces_lager():
    common = [{"name": "01.10.2021→31.08.2026", "value": _index()["ratio_to_base"], "source": "КО-ИНВЕСТ 133"}]
    chain = lambda ks: [{"name": "1969→1984", "value": 1.16, "source": "Пост. Госстроя № 94"},
                        {"name": "1984→01.10.2021", "value": ks, "source": "КО-ИНВЕСТ 106, 117"}]
    result = rf.composite_replacement_cost([
        {"name": "спальный корпус", "volume": 650.974, "unit_cost": 23.70, "indices": chain(156.070 * 1.143)},
        {"name": "веранда", "volume": 24.55, "unit_cost": 60, "indices": chain(164.765 * 1.147)},
    ], common_indices=common, context=CONTEXT)

    assert len(result["parts"]) == 2 and result["guardrails"]
    # С прибылью предпринимателя 7 %: пересчёт 6 207 015, отчёт 6 206 454 (индекс 1,650).
    assert result["replacement_cost"] * 1.07 == pytest.approx(6_206_454, rel=1e-4)


def test_vat_breakdown_reproduces_lager_and_nissan():
    lager = rf.vat_breakdown(214_273_905, 22, vat_included=False, land_value=157_586_000)
    nissan = rf.vat_breakdown(1_021_000, 20)

    assert lager["value_with_vat"] == 226_745_244.10
    assert nissan["vat"] == 170_166.67 and nissan["value_without_vat"] == 850_833.33
    with pytest.raises(ValueError, match="land_value"):
        rf.vat_breakdown(100, 20, land_value=200)
