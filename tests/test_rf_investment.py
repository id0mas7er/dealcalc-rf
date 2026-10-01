import pytest

from dealcalc.rf import gross_rent_multiplier, irr, npv

GRM_COMPARABLES = [
    {"price": 10_000_000, "gross_income": 1_250_000, "source": "ЦИАН"},
    {"price": 12_000_000, "gross_income": 1_200_000},
    {"price": 9_000_000, "gross_income": 1_000_000},
]


def test_gross_rent_multiplier_with_subject_income():
    result = gross_rent_multiplier(GRM_COMPARABLES, subject_gross_income=1_100_000)

    assert [item["multiplier"] for item in result["comparables"]] == [8.0, 10.0, 9.0]
    assert result["comparables"][0]["source"] == "ЦИАН"
    assert result["mean_multiplier"] == 9.0
    assert result["median_multiplier"] == 9.0
    assert result["min_multiplier"] == 8.0
    assert result["max_multiplier"] == 10.0
    assert result["variation"]["coefficient_pct"] == 11.11
    assert result["statistic"] == "mean"
    assert result["indicated_value"] == 9_900_000.0


def test_gross_rent_multiplier_median_statistic():
    comparables = GRM_COMPARABLES + [{"price": 20_000_000, "gross_income": 1_000_000}]

    result = gross_rent_multiplier(comparables, 1_000_000, statistic="median")

    assert result["mean_multiplier"] == 11.75
    assert result["median_multiplier"] == 9.5
    assert result["indicated_value"] == 9_500_000.0


def test_gross_rent_multiplier_without_subject_income():
    result = gross_rent_multiplier(GRM_COMPARABLES)

    assert result["indicated_value"] is None


@pytest.mark.parametrize(
    "args, kwargs, message",
    [
        (([],), {}, "at least one"),
        (([{"price": 1, "gross_income": 0}],), {}, "gross_income"),
        (([{"price": 0, "gross_income": 1}],), {}, "price"),
        ((GRM_COMPARABLES, -1), {}, "subject_gross_income"),
        ((GRM_COMPARABLES, 1), {"statistic": "mode"}, "statistic"),
    ],
)
def test_gross_rent_multiplier_rejects_invalid_input(args, kwargs, message):
    with pytest.raises(ValueError, match=message):
        gross_rent_multiplier(*args, **kwargs)


def test_npv_shows_discounted_periods():
    result = npv([-1_000, 300, 400, 500], 10)

    assert result["npv"] == pytest.approx(-21.04, abs=0.01)
    assert [item["period"] for item in result["periods"]] == [0, 1, 2, 3]
    assert result["periods"][1]["present_value"] == pytest.approx(272.73, abs=0.01)
    assert result["periods"][0]["discount_factor"] == 1.0


@pytest.mark.parametrize(
    "args, message",
    [(([], 10), "cash_flows"), (([-1, 1], -100), "discount_rate_pct")],
)
def test_npv_rejects_invalid_input(args, message):
    with pytest.raises(ValueError, match=message):
        npv(*args)


def test_irr():
    assert irr([-1_000, 300, 400, 500])["irr_pct"] == 8.9
    assert irr([-250_000, 100_000, 150_000, 200_000, 250_000, 300_000])["irr_pct"] == 56.72


def test_irr_npv_at_irr_is_zero():
    flows = [-1_000, 300, 400, 500]
    rate = irr(flows)["irr_pct"]

    assert npv(flows, rate)["npv"] == pytest.approx(0, abs=0.5)


@pytest.mark.parametrize("flows", [[100, 200], [-100, -200], [-100]])
def test_irr_requires_sign_change(flows):
    with pytest.raises(ValueError, match="sign"):
        irr(flows)
