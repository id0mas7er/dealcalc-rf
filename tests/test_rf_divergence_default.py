"""Material divergence of approaches: more than 30% by default (user decision)."""

from dealcalc.rf import reconcile_approaches
from dealcalc.rf._meta import STATUS_NOT_RECONCILED


def test_default_threshold_is_30_pct():
    result = reconcile_approaches({"a": 100, "b": 130}, {"a": 0.5, "b": 0.5})

    assert result["max_divergence_pct"] == 30
    assert result["divergence_pct"] == 30
    assert result["status"] != STATUS_NOT_RECONCILED
    assert any("30" in note and "max_divergence_pct" in note for note in result["guardrails"])


def test_divergence_above_30_pct_is_material():
    result = reconcile_approaches({"a": 100, "b": 130.01}, {"a": 0.5, "b": 0.5})

    assert result["status"] == STATUS_NOT_RECONCILED


def test_appraiser_threshold_overrides_default():
    result = reconcile_approaches({"a": 100, "b": 125}, {"a": 0.5, "b": 0.5}, 20)

    assert result["status"] == STATUS_NOT_RECONCILED
    assert not any("max_divergence_pct" in note for note in result["guardrails"])
