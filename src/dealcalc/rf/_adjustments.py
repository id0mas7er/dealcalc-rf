"""Step-by-step comparable adjustments and sample statistics shared by the
real-estate and vehicle comparative approaches."""

from __future__ import annotations

import datetime
import math
import statistics
from decimal import ROUND_HALF_UP, Decimal
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Sequence

LEGACY_ADJUSTMENT_NAME = "Общая корректировка"
HOMOGENEITY_THRESHOLD_PCT = 33.0


def money(value: float) -> float:
    """Round to kopecks half up (2.675 -> 2.68), as reports and 1С expect.

    Python's ``round`` works on the binary float and gives 2.67 here.
    """

    rounded = float(Decimal(repr(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return rounded + 0.0  # normalise -0.0


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def source_range(name: str, bounds: Any) -> Dict[str, Any]:
    """Bounds of a value given by its source (a reference-book table):
    ``{"low", "high"}`` with optional ``mean``, the extended interval
    ``extended_low`` / ``extended_high``, ``source``, ``date``, ``page`` and
    ``justification`` of a value chosen against the bounds or the rule."""

    if not isinstance(bounds, Mapping):
        raise ValueError(f"{name} must be an object with low and high")
    low = _finite(f"{name}.low", bounds.get("low"))
    high = _finite(f"{name}.high", bounds.get("high"))
    if low > high:
        raise ValueError(f"{name}.low must not exceed {name}.high")
    result: Dict[str, Any] = {"low": low, "high": high}
    if bounds.get("mean") not in (None, ""):
        mean = _finite(f"{name}.mean", bounds["mean"])
        if not low <= mean <= high:
            raise ValueError(f"{name}.mean must lie within low and high")
        result["mean"] = mean
    if any(bounds.get(key) not in (None, "") for key in ("extended_low", "extended_high")):
        extended_low = _finite(f"{name}.extended_low", bounds.get("extended_low", low))
        extended_high = _finite(f"{name}.extended_high", bounds.get("extended_high", high))
        if extended_low > low or extended_high < high:
            raise ValueError(f"{name}: the extended interval must contain low and high")
        result.update(extended_low=extended_low, extended_high=extended_high)
    for key in ("source", "date", "page", "justification"):
        text = "" if bounds.get(key) is None else str(bounds[key]).strip()
        if text:
            result[key] = text
    return result


# The value of a step compared with the bounds of its source.
_RANGE_VALUE = {"pct": "value", "pct_group": "value", "coef": "value", "abs": "value", "param": "exponent"}
_RANGE_NUMBERS = ("low", "high", "mean", "extended_low", "extended_high")

# Choice of the value within the interval of a reference book (the
# appraiser's practice): an adjustment up to this size at the mean takes the
# mean; a larger one takes the point of the interval (extended, if given)
# giving the smallest adjustment.
CHOICE_THRESHOLD_PCT = 30.0


def _step_size_pct(kind: str, value: float, price: float, step: Mapping[str, Any]) -> float:
    """Size of the adjustment of a step with this value, % of the price."""

    if kind == "coef":
        return abs(value - 1) * 100
    if kind == "abs":
        return abs(value) / price * 100
    if kind == "param":
        return abs((float(step["subject"]) / float(step["analog"])) ** value - 1) * 100
    return abs(value)


def _choice(kind: str, bounds: Mapping[str, Any], value: float, price: float, step: Mapping[str, Any]) -> Dict[str, Any]:
    at_mean = _step_size_pct(kind, bounds["mean"], price, step)
    if at_mean <= CHOICE_THRESHOLD_PCT:
        expected, rule = bounds["mean"], "mean"
    else:
        extended = "extended_low" in bounds
        low = bounds["extended_low"] if extended else bounds["low"]
        high = bounds["extended_high"] if extended else bounds["high"]
        # No adjustment: a coefficient of 1, a zero percent, amount or exponent.
        neutral = 1.0 if kind == "coef" else 0.0
        expected = min(max(neutral, low), high)
        rule = "minimal_extended" if extended else "minimal_interval"
    return {
        "expected": expected,
        "rule": rule,
        "adjustment_at_mean_pct": money(at_mean),
        "follows_rule": math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-12),
    }


def adjustment_steps(comparable: Mapping[str, Any], prefix: str) -> List[Dict[str, Any]]:
    """Return the comparable's adjustments as a list of raw steps.

    ``adjustments`` is a list of ``{"name", "type", "value"}`` objects applied
    in order. The legacy single ``adjustment_pct`` field becomes one step.
    """

    has_steps = "adjustments" in comparable
    has_legacy = comparable.get("adjustment_pct") not in (None, "")
    if has_steps and has_legacy:
        raise ValueError(f"{prefix}: use either adjustment_pct or adjustments")
    if has_legacy:
        value = _finite(f"{prefix}.adjustment_pct", comparable["adjustment_pct"])
        if value <= -100:
            raise ValueError(f"{prefix}.adjustment_pct must be greater than -100")
        return [{"name": LEGACY_ADJUSTMENT_NAME, "type": "pct", "value": value}]
    steps = comparable.get("adjustments") or []
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        raise ValueError(f"{prefix}.adjustments must be a list")
    return list(steps)


def _effective_count(applied: Sequence[Mapping[str, Any]]) -> int:
    """Adjustments that change the price; a run of ``pct_group`` steps is one
    adjustment, so the count does not depend on how a group is written."""

    count = 0
    group_changed = None
    for record in applied:
        if record["type"] == "pct_group":
            group_changed = bool(group_changed) or record["change"] != 0
            continue
        if group_changed is not None:
            count += group_changed
            group_changed = None
        count += record["change"] != 0
    if group_changed is not None:
        count += group_changed
    return count


def apply_adjustments(
    base_price: float, steps: Sequence[Any], prefix: str
) -> Dict[str, Any]:
    """Apply adjustments sequentially and keep every intermediate price.

    Step types:

    * ``pct`` multiplies the current price by ``1 + value / 100``;
    * ``abs`` adds ``value`` in price units (RUB per m² for real estate,
      RUB for vehicles);
    * ``param`` multiplies by ``(subject / analog) ** exponent``, where
      ``exponent`` is the braking coefficient of the parameter;
    * ``depreciation`` multiplies by ``(1 - subject_pct / 100) /
      (1 - analog_pct / 100)``; with ``subject_pct = 0`` this is the
      new-equivalent price of a used analog (formula 22);
    * ``pct_group`` — consecutive steps of this type form one group: their
      percents are summed and applied once to the price before the group
      (``price × (1 + Σ value / 100)``), as is usual for the second group of
      corrections on physical characteristics;
    * ``coef`` multiplies by ``value`` — a coefficient of a reference-book
      table (0.94 for a bargaining discount of 6 %);
    * ``ratio`` multiplies by ``subject / analog`` — coefficients of the
      subject and of the analog relative to one base (a floor, a class, a
      price index on the valuation date and on the price date).

    ``range`` (``{"low", "high"}``, optional ``mean`` and the extended
    interval ``extended_low`` / ``extended_high``) holds the bounds of the
    source for the value of ``pct``, ``pct_group``, ``coef``, ``abs`` and the
    exponent of ``param``; ``within_range`` tells whether the value lies
    within them (the extended interval, if given). With ``mean``, ``choice``
    applies the rule of choice: an adjustment up to 30 % at the mean takes
    the mean, a larger one the point of the interval giving the smallest
    adjustment.
    ``source``, ``date``, ``page`` and ``justification`` travel with the step.
    """

    price = base_price
    applied = []
    gross_change = 0.0
    group_base = None
    group_total = 0.0
    for number, step in enumerate(steps, start=1):
        name_prefix = f"{prefix}.adjustments[{number - 1}]"
        if not isinstance(step, Mapping):
            raise ValueError(f"{name_prefix} must be an object")
        name = step.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{name_prefix}.name must be a non-empty string")
        kind = step.get("type")
        record: Dict[str, Any] = {"step": number, "name": name.strip(), "type": kind}
        if kind != "pct_group":
            group_base = None
        if kind == "pct_group":
            value = _finite(f"{name_prefix}.value", step.get("value"))
            if group_base is None:
                group_base, group_total = price, 0.0
            group_total += value
            if group_total <= -100:
                raise ValueError(f"{name_prefix}: total of the group must be greater than -100")
            new_price = group_base * (1 + group_total / 100)
            record.update(value=money(value), group_base=money(group_base), group_total_pct=money(group_total))
        elif kind == "pct":
            value = _finite(f"{name_prefix}.value", step.get("value"))
            if value <= -100:
                raise ValueError(f"{name_prefix}.value must be greater than -100")
            new_price = price * (1 + value / 100)
            record["value"] = money(value)
        elif kind == "abs":
            value = _finite(f"{name_prefix}.value", step.get("value"))
            new_price = price + value
            record["value"] = money(value)
        elif kind == "param":
            subject = _finite(f"{name_prefix}.subject", step.get("subject"))
            analog = _finite(f"{name_prefix}.analog", step.get("analog"))
            exponent = _finite(f"{name_prefix}.exponent", step.get("exponent"))
            if subject <= 0:
                raise ValueError(f"{name_prefix}.subject must be greater than 0")
            if analog <= 0:
                raise ValueError(f"{name_prefix}.analog must be greater than 0")
            factor = (subject / analog) ** exponent
            new_price = price * factor
            record.update(
                subject=subject, analog=analog, exponent=exponent, factor=round(factor, 4)
            )
        elif kind == "coef":
            value = _finite(f"{name_prefix}.value", step.get("value"))
            if value <= 0:
                raise ValueError(f"{name_prefix}.value must be greater than 0")
            new_price = price * value
            record["value"] = value
        elif kind == "ratio":
            subject = _finite(f"{name_prefix}.subject", step.get("subject"))
            analog = _finite(f"{name_prefix}.analog", step.get("analog"))
            if subject <= 0:
                raise ValueError(f"{name_prefix}.subject must be greater than 0")
            if analog <= 0:
                raise ValueError(f"{name_prefix}.analog must be greater than 0")
            factor = subject / analog
            new_price = price * factor
            record.update(subject=subject, analog=analog, factor=round(factor, 4))
        elif kind == "depreciation":
            analog_pct = _finite(f"{name_prefix}.analog_pct", step.get("analog_pct"))
            subject_pct = _finite(
                f"{name_prefix}.subject_pct", step.get("subject_pct", 0)
            )
            if not 0 <= analog_pct < 100:
                raise ValueError(f"{name_prefix}.analog_pct must be in [0, 100)")
            if not 0 <= subject_pct <= 100:
                raise ValueError(f"{name_prefix}.subject_pct must be in [0, 100]")
            factor = (1 - subject_pct / 100) / (1 - analog_pct / 100)
            new_price = price * factor
            record.update(
                analog_pct=analog_pct, subject_pct=subject_pct, factor=round(factor, 4)
            )
        else:
            raise ValueError(
                f"{name_prefix}.type must be 'pct', 'pct_group', 'coef', 'ratio', 'abs', 'param' "
                "or 'depreciation'"
            )
        if new_price <= 0:
            raise ValueError(f"{name_prefix}: adjusted price must be greater than 0")
        change = new_price - price
        gross_change += abs(change)
        record.update(
            price_before=money(price),
            price_after=money(new_price),
            change=money(change),
        )
        if step.get("range") is not None:
            if kind not in _RANGE_VALUE:
                raise ValueError(f"{name_prefix}.range applies to pct, pct_group, coef, abs and param steps")
            bounds = source_range(f"{name_prefix}.range", step["range"])
            checked = _finite(f"{name_prefix}.{_RANGE_VALUE[kind]}", step.get(_RANGE_VALUE[kind]))
            record["range"] = {key: bounds[key] for key in _RANGE_NUMBERS if key in bounds}
            low = bounds.get("extended_low", bounds["low"])
            high = bounds.get("extended_high", bounds["high"])
            record["within_range"] = low <= checked <= high
            if "mean" in bounds:
                record["choice"] = _choice(kind, bounds, checked, price, step)
        # The evidence of the step travels with it into the result.
        for key in ("source", "date", "page", "justification"):
            text = "" if step.get(key) is None else str(step[key]).strip()
            if text:
                record[key] = text
        applied.append(record)
        price = new_price

    return {
        "adjusted_price": price,
        "adjustments": applied,
        "adjustments_count": _effective_count(applied),
        "net_adjustment_pct": _share_pct(price - base_price, base_price),
        "gross_adjustment_pct": _share_pct(gross_change, base_price),
        # Unrounded, for weights computed over the whole sample.
        "gross_adjustment_raw_pct": None if base_price == 0 else gross_change / base_price * 100,
    }


WEIGHTING_FORMULAS = {
    "manual": "веса задаёт оценщик (поле weight, по умолчанию 1)",
    "inverse_gross": "w_i ∝ 1 / (1 + G_i / 100), G_i — валовая корректировка аналога, %",
    "inverse_count": "w_i ∝ 1 / (1 + n_i), n_i — число корректировок аналога",
    "count_share": (
        "K_i = (S − M_i) / ((N − 1) × S), M_i — число корректировок аналога, S = Σ M_i, "
        "N — число аналогов; при S = 0 веса равные"
    ),
    "gross_share": (
        "K_i = (1 − S_i / Σ(S_j + 1)) / Σ_k (1 − S_k / Σ(S_j + 1)), S_i — сумма модулей "
        "корректировок аналога, %"
    ),
}
# Rules that need the whole sample: the weight of an analog depends on the others.
SAMPLE_WEIGHTINGS = ("count_share", "gross_share")


def analog_weight(
    comparable: Mapping[str, Any], adjusted: Mapping[str, Any], weighting: str, prefix: str
) -> float:
    """Raw weight of an analog under the selected weighting rule."""

    if weighting not in WEIGHTING_FORMULAS:
        raise ValueError(f"weighting must be one of {', '.join(WEIGHTING_FORMULAS)}")
    if weighting == "manual":
        weight = _finite(f"{prefix}.weight", comparable.get("weight", 1))
        if weight <= 0:
            raise ValueError(f"{prefix}.weight must be greater than 0")
        return weight
    if comparable.get("weight") not in (None, ""):
        raise ValueError(f"{prefix}.weight is set manually: use weighting='manual'")
    if weighting in SAMPLE_WEIGHTINGS:
        return 1.0  # replaced by sample_weights once the sample is adjusted
    if weighting == "inverse_gross":
        return 1 / (1 + (adjusted["gross_adjustment_pct"] or 0) / 100)
    return 1 / (1 + adjusted["adjustments_count"])


def sample_weights(adjusted: Sequence[Mapping[str, Any]], weighting: str) -> Optional[List[float]]:
    """Weights of the rules computed over the whole sample, else ``None``.

    ``count_share``: ``K_i = (S − M_i) / ((N − 1) S)`` by the number of
    adjustments; ``gross_share``: ``K_i ∝ 1 − S_i / Σ(S_j + 1)`` by the sum
    of absolute adjustments, %. Both sum to 1.
    """

    if weighting not in SAMPLE_WEIGHTINGS:
        return None
    count = len(adjusted)
    if count == 1:
        return [1.0]
    if weighting == "count_share":
        numbers = [item["adjustments_count"] for item in adjusted]
        total = sum(numbers)
        if total == 0:
            return [1 / count] * count
        return [(total - number) / ((count - 1) * total) for number in numbers]
    gross = [item["gross_adjustment_raw_pct"] or 0 for item in adjusted]
    denominator = sum(value + 1 for value in gross)
    raw = [1 - value / denominator for value in gross]
    return [value / sum(raw) for value in raw]


def scaled_weights(weights: Sequence[float]) -> List[float]:
    """Weights divided by the largest one: shares and weighted averages stay
    the same, and very large weights cannot overflow their sum."""

    largest = max(weights)
    return [weight / largest for weight in weights]


def weight_shares(weights: Sequence[float]) -> List[float]:
    """Shares of unrounded positive weights, rounded for the output only."""

    scaled = scaled_weights(weights)
    total = sum(scaled)
    return [round(weight / total, 4) for weight in scaled]


def _share_pct(amount: float, base: float) -> Optional[float]:
    return None if base == 0 else money(amount / base * 100)


def variation(prices: Sequence[float]) -> Dict[str, Any]:
    """Sample coefficient of variation of adjusted prices with the 33% check."""

    if len(prices) < 2 or statistics.mean(prices) == 0:
        coefficient = None
    else:
        coefficient = statistics.stdev(prices) / statistics.mean(prices) * 100
    # The threshold is compared with the unrounded coefficient.
    # A descriptive statistic: a low coefficient does not prove comparability.
    return {
        "coefficient_pct": None if coefficient is None else money(coefficient),
        "threshold_pct": HOMOGENEITY_THRESHOLD_PCT,
        "within_threshold": None
        if coefficient is None
        else coefficient <= HOMOGENEITY_THRESHOLD_PCT,
    }


def json_value(value: Any) -> Any:
    """Make a pass-through field JSON-serializable."""

    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
