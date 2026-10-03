"""Codex review of 0.6.1 (03.10.2026): R1–R4."""

import pytest

from dealcalc import rf
from dealcalc.rf._meta import STATUS_NOT_RECONCILED
from test_rf_report import CONTEXT, _report


# R1: can_issue must not allow a report with unresolved checks.


def test_unresolved_reconciliation_blocks_issue():
    report = _report()
    report["approaches"]["calculations"] = [
        rf.reconcile_approaches({"a": 10_000_000, "b": 100_000_000}, {"a": 0.5, "b": 0.5}, context=CONTEXT)
    ]
    result = rf.check_report(report)

    assert result["missing"] == []
    assert result["checks"]
    assert result["can_issue"] is False


def test_final_value_outside_interval_blocks_issue():
    result = rf.check_report(_report(final_value=20_000_000))

    assert result["can_issue"] is False


# R2: a section of the wrong type is missing, not silently skipped.


@pytest.mark.parametrize("field", ["assignment", "approaches", "object", "customer", "sources"])
def test_section_of_wrong_type_is_missing(field):
    result = rf.check_report(_report(**{field: "x"}))

    assert result["can_issue"] is False
    assert any(field in item for item in result["missing"])


def test_calculations_must_be_a_list_of_results():
    report = _report()
    report["approaches"]["calculations"] = "x"
    result = rf.check_report(report)

    assert any("approaches.calculations" in item for item in result["missing"])


def test_calculation_that_is_not_an_object_is_missing():
    report = _report()
    report["approaches"]["calculations"] = report["approaches"]["calculations"] + ["x"]
    result = rf.check_report(report)

    assert any("approaches.calculations[1]" in item for item in result["missing"])


# R3: the VAT basis of analogs survives the import.


def _rows():
    return [
        dict(source="S", listing_id=str(i), date="2026-10-01", price_type="сделка", price=p, area_sqm=50, vat=vat)
        for i, p, vat in [(1, 12_000_000, "included"), (2, 10_000_000, "excluded")]
    ]


def test_vat_survives_normalization_and_is_checked():
    listings = [rf.normalize_listing(row) for row in _rows()]

    assert [item["vat"] for item in listings] == ["included", "excluded"]
    assert any("НДС" in check for check in rf.comparative_approach(50, listings, context=CONTEXT)["checks"])


def test_vat_in_russian_from_csv(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("Цена;Площадь;НДС\n12 000 000;50;с НДС\n10 000 000;50;без НДС\n9 000 000;50;НДС не применяется\n", encoding="utf-8")
    listings = rf.load_listings(str(path), source="S")

    assert [item["vat"] for item in listings] == ["included", "excluded", "not_applicable"]


def test_unknown_vat_is_left_empty_with_a_warning():
    listing = rf.normalize_listing({"price": 1_000_000, "vat": "может быть"}, "S")

    assert listing["vat"] == ""
    assert any("НДС" in warning for warning in listing["import_warnings"])


# R4: a zero approach value makes the divergence unbounded, not unknown.


def test_zero_value_blocks_reconciliation_without_justification():
    result = rf.reconcile_approaches({"a": 0, "b": 10_000_000}, {"a": 0.5, "b": 0.5})

    assert result["status"] == STATUS_NOT_RECONCILED
    assert result["reconciled_value"] is None
    assert result["weighted_value_diagnostic"] == 5_000_000


def test_zero_value_with_justification_is_reconciled_for_review():
    result = rf.reconcile_approaches(
        {"a": 0, "b": 10_000_000}, {"a": 0, "b": 1}, justification="затратный подход не применим"
    )

    assert result["reconciled_value"] == 10_000_000
    assert result["status"] != STATUS_NOT_RECONCILED


@pytest.mark.parametrize("base", ["min", "mean", "max"])
def test_all_zero_values_do_not_diverge(base):
    result = rf.reconcile_approaches({"a": 0, "b": 0}, {"a": 0.5, "b": 0.5}, divergence_base=base)

    assert result["divergence_pct"] == 0
    assert result["reconciled_value"] == 0
