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
    ``justification`` of a value chosen against the bounds or the rule.

    ``kind`` tells what ``low`` / ``high`` are: ``values`` (default) — the
    range of the value itself; ``confidence`` — the confidence interval of
    the mean, which does not bound an individual value (Leifer). The
    extended interval always bounds the value."""

    if not isinstance(bounds, Mapping):
        raise ValueError(f"{name} must be an object with low and high")
    low = _finite(f"{name}.low", bounds.get("low"))
    high = _finite(f"{name}.high", bounds.get("high"))
    if low > high:
        raise ValueError(f"{name}.low must not exceed {name}.high")
    kind = "values" if bounds.get("kind") in (None, "") else bounds["kind"]
    if kind not in RANGE_KINDS:
        raise ValueError(f"{name}.kind must be 'values' or 'confidence'")
    result: Dict[str, Any] = {"low": low, "high": high, "kind": kind}
    if bounds.get("mean") not in (None, ""):
        mean = _finite(f"{name}.mean", bounds["mean"])
        if not low <= mean <= high:
            raise ValueError(f"{name}.mean must lie within low and high")
        result["mean"] = mean
    if any(bounds.get(key) not in (None, "") for key in ("extended_low", "extended_high")):
        # An omitted or null endpoint keeps the bound of the interval.
        given_low, given_high = bounds.get("extended_low"), bounds.get("extended_high")
        extended_low = low if given_low in (None, "") else _finite(f"{name}.extended_low", given_low)
        extended_high = high if given_high in (None, "") else _finite(f"{name}.extended_high", given_high)
        if extended_low > low or extended_high < high:
            raise ValueError(f"{name}: the extended interval must contain low and high")
        result.update(extended_low=extended_low, extended_high=extended_high)
    for key in ("source", "date", "page", "justification"):
        text = "" if bounds.get(key) is None else str(bounds[key]).strip()
        if text:
            result[key] = text
    return result


def equation_domain(name: str, bounds: Any) -> Dict[str, Any]:
    """Range of x on which a regression equation of a reference book was
    built: ``{"low", "high"}``, either may be omitted (``null``)."""

    if not isinstance(bounds, Mapping):
        raise ValueError(f"{name} must be an object with low or high")
    given = {key: bounds.get(key) for key in ("low", "high")}
    if all(value in (None, "") for value in given.values()):
        raise ValueError(f"{name} needs low or high")
    result = {key: None if value in (None, "") else _finite(f"{name}.{key}", value) for key, value in given.items()}
    if None not in result.values() and result["low"] > result["high"]:
        raise ValueError(f"{name}.low must not exceed {name}.high")
    return result


def within_domain(domain: Mapping[str, Any], *values: float) -> bool:
    return all(
        (domain["low"] is None or domain["low"] <= value) and (domain["high"] is None or value <= domain["high"])
        for value in values
    )


def range_position(bounds: Mapping[str, Any], value: float) -> Dict[str, Any]:
    """Where a value lies against the bounds of its source: ``within_range``
    — within the bounds of the value (the extended interval, else ``low`` /
    ``high`` of the kind ``values``; ``None`` when only the interval of the
    mean is given); ``within_confidence`` — within the interval of the mean."""

    position: Dict[str, Any] = {}
    if "extended_low" in bounds:
        position["within_range"] = bounds["extended_low"] <= value <= bounds["extended_high"]
    elif bounds["kind"] == "values":
        position["within_range"] = bounds["low"] <= value <= bounds["high"]
    else:
        position["within_range"] = None
    if bounds["kind"] == "confidence":
        position["within_confidence"] = bounds["low"] <= value <= bounds["high"]
    return position


# The value of a step compared with the bounds of its source.
_RANGE_VALUE = {"pct": "value", "pct_group": "value", "coef": "value", "abs": "value", "param": "exponent"}
RANGE_KINDS = ("values", "confidence")
# Rules of choice of a value within the interval: the mean (default, the
# reference books) or the appraiser's practice of the smallest adjustment.
CHOICE_RULES = ("mean", "minimal")

# An adjustment larger than this is a sign of a substantial difference
# between the subject and the analog (Leifer). Under the appraiser's rule
# ``choice_rule: "minimal"`` an adjustment up to it at the mean takes the
# mean, a larger one the point of the interval giving the smallest one.
CHOICE_THRESHOLD_PCT = 30.0


def _within_threshold(size_pct: float) -> bool:
    """An adjustment of exactly 30 % is within the threshold: 1.3 - 1 is not
    exactly 0.3 in floating point."""

    return size_pct <= CHOICE_THRESHOLD_PCT or math.isclose(size_pct, CHOICE_THRESHOLD_PCT, abs_tol=1e-9)


def _step_size_pct(kind: str, value: float, price: float, step: Mapping[str, Any]) -> float:
    """Size of the adjustment of a step with this value, % of the price."""

    if kind == "coef":
        return abs(value - 1) * 100
    if kind == "abs":
        return abs(value) / price * 100
    if kind == "param":
        return abs((float(step["subject"]) / float(step["analog"])) ** value - 1) * 100
    return abs(value)


def _choice(
    kind: str, bounds: Mapping[str, Any], value: float, price: float, step: Mapping[str, Any], policy: str
) -> Dict[str, Any]:
    at_mean = _step_size_pct(kind, bounds["mean"], price, step)
    size = _step_size_pct(kind, value, price, step)
    if policy == "mean" or _within_threshold(at_mean):
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
        "policy": policy,
        "adjustment_at_mean_pct": money(at_mean),
        "adjustment_pct": money(size),
        "within_threshold": _within_threshold(size),
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
    """Adjustments that change the price. In a run of ``pct_group`` steps
    each factor counts once: steps of one ``factor`` (by default — of one
    name) are one adjustment, steps of different factors are different
    ones, however the group is written."""

    count = 0
    group = None
    for record in applied:
        if record["type"] == "pct_group":
            group = set() if group is None else group
            if record["change"] != 0:
                group.add(record.get("factor", record["name"]))
            continue
        if group is not None:
            count += len(group)
            group = None
        count += record["change"] != 0
    if group is not None:
        count += len(group)
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
      price index on the valuation date and on the price date);
    * ``staged`` — a cascade of variants of one adjustment: ``stages`` is a
      list of stages, each a list of variants (``pct``, ``coef``, ``ratio``,
      ``param`` or ``abs`` steps with a ``label``) — for instance the mean
      regression equation, then the equations of the bounds, then the table
      of the reference book. Within a stage the variant with the smallest
      adjustment is taken; the first stage where it is within 30 % wins,
      otherwise the smallest of all evaluated variants (``selection``
      ``smallest_of_all``, which needs the appraiser's ``justification``).

    ``range`` (``{"low", "high"}``, optional ``mean`` and the extended
    interval ``extended_low`` / ``extended_high``) holds the bounds of the
    source for the value of ``pct``, ``pct_group``, ``coef``, ``abs`` and the
    exponent of ``param``; ``within_range`` tells whether the value lies
    within them (the extended interval, if given). ``domain`` (``{"low",
    "high"}``) of a ``param`` step is the range of x on which the equation was
    built; ``within_domain`` tells whether the subject and the analog lie in
    it. With ``mean``, ``choice`` applies the rule of choice of the step,
    ``choice_rule``: ``mean`` (default, as the reference books) expects the
    mean; ``minimal`` (the appraiser's practice) expects the mean for an
    adjustment up to 30 % at the mean and otherwise the point of the
    interval giving the smallest adjustment. An adjustment over 30 % at the
    value taken is flagged (``within_threshold``).
    ``source``, ``date``, ``page`` and ``justification`` travel with the step.
    """

    price = base_price
    applied = []
    gross_change = 0.0
    # Adjustments as written: a percent step by its percent, any other step
    # by its own change relative to the price before it.
    written_total = 0.0
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
        factor = "" if step.get("factor") is None else str(step["factor"]).strip()
        if factor:
            record["factor"] = factor
        policy = step.get("choice_rule")
        if policy is not None and policy not in CHOICE_RULES:
            raise ValueError(f"{name_prefix}.choice_rule must be 'mean' or 'minimal'")
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
        elif kind == "staged":
            evaluated, chosen, selection = _staged_choice(price, step.get("stages"), name_prefix)
            new_price = price * chosen["factor"]
            record.update(
                variants=[_public_variant(item) for item in evaluated],
                chosen=_public_variant(chosen),
                selection=selection,
                threshold_pct=CHOICE_THRESHOLD_PCT,
                factor=round(chosen["factor"], 4),
            )
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
                f"{name_prefix}.type must be 'pct', 'pct_group', 'coef', 'ratio', 'abs', 'param', "
                "'staged' or 'depreciation'"
            )
        if new_price <= 0:
            raise ValueError(f"{name_prefix}: adjusted price must be greater than 0")
        change = new_price - price
        gross_change += abs(change)
        written_total += abs(value) if kind in ("pct", "pct_group") else abs(new_price / price - 1) * 100
        record.update(
            price_before=money(price),
            price_after=money(new_price),
            change=money(change),
        )
        if step.get("domain") is not None:
            if kind != "param":
                raise ValueError(f"{name_prefix}.domain applies to param steps")
            domain = equation_domain(f"{name_prefix}.domain", step["domain"])
            record["domain"] = domain
            record["within_domain"] = within_domain(domain, record["subject"], record["analog"])
        if step.get("range") is not None:
            if kind not in _RANGE_VALUE:
                raise ValueError(f"{name_prefix}.range applies to pct, pct_group, coef, abs and param steps")
            bounds = source_range(f"{name_prefix}.range", step["range"])
            checked = _finite(f"{name_prefix}.{_RANGE_VALUE[kind]}", step.get(_RANGE_VALUE[kind]))
            record["range"] = dict(bounds)
            record.update(range_position(bounds, checked))
            if "mean" in bounds:
                record["choice"] = _choice(kind, bounds, checked, price, step, policy or "mean")
        if policy is not None and "choice" not in record:
            raise ValueError(f"{name_prefix}: choice_rule needs range.mean")
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
        "adjustments_sum_abs_raw_pct": written_total,
        "adjustments_sum_abs_pct": money(written_total),
    }


_STAGED_TYPES = ("pct", "coef", "ratio", "param", "abs")


def _staged_choice(price: float, stages: Any, prefix: str) -> tuple:
    """Evaluate the stages of a cascade in order; see ``apply_adjustments``."""

    if not isinstance(stages, Sequence) or isinstance(stages, (str, bytes)) or not stages:
        raise ValueError(f"{prefix}.stages must be a non-empty list of stages (lists of variants)")
    evaluated: List[Dict[str, Any]] = []
    for stage_number, stage in enumerate(stages, start=1):
        stage_prefix = f"{prefix}.stages[{stage_number - 1}]"
        if not isinstance(stage, Sequence) or isinstance(stage, (str, bytes)) or not stage:
            raise ValueError(f"{stage_prefix} must be a non-empty list of variants")
        current = []
        for number, variant in enumerate(stage):
            variant_prefix = f"{stage_prefix}[{number}]"
            if not isinstance(variant, Mapping) or variant.get("type") not in _STAGED_TYPES:
                raise ValueError(f"{variant_prefix}: variant type must be one of {', '.join(_STAGED_TYPES)}")
            if "range" in variant:
                raise ValueError(f"{variant_prefix}: range is not supported inside staged variants")
            label = variant.get("label")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"{variant_prefix}.label must be a non-empty string")
            adjusted = apply_adjustments(price, [{**variant, "name": label}], variant_prefix)
            factor = adjusted["adjusted_price"] / price
            current.append(
                {"stage": stage_number, "label": label.strip(), "record": adjusted["adjustments"][0],
                 "factor": factor, "size": abs(factor - 1) * 100}
            )
        evaluated += current
        # An equation outside its domain is not a candidate.
        applicable = [item for item in current if item["record"].get("within_domain") is not False]
        if applicable:
            best = min(applicable, key=lambda item: item["size"])
            if _within_threshold(best["size"]):
                return evaluated, best, "within_threshold"
    applicable = [item for item in evaluated if item["record"].get("within_domain") is not False]
    if not applicable:
        return evaluated, min(evaluated, key=lambda item: item["size"]), "outside_domain"
    return evaluated, min(applicable, key=lambda item: item["size"]), "smallest_of_all"


# Prices of a variant evaluated alone; the step of the cascade holds the prices.
_VARIANT_OMITTED = ("step", "name", "price_before", "price_after", "change")


def _public_variant(item: Mapping[str, Any]) -> Dict[str, Any]:
    """A variant with its inputs and evidence, so the choice can be verified."""

    inputs = {key: value for key, value in item["record"].items() if key not in _VARIANT_OMITTED}
    return {
        "stage": item["stage"],
        "label": item["label"],
        **inputs,
        "factor": round(item["factor"], 4),
        "adjustment_pct": money(item["size"]),
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
        "корректировок аналога как записаны, % (|−10 %| + |+20 %| = 30)"
    ),
    "gross_share_fraction": (
        "K_i = (1 − S_i / Σ(S_j + 1)) / Σ_k (1 − S_k / Σ(S_j + 1)), S_i — сумма модулей "
        "корректировок аналога как записаны, в долях (|−10 %| + |+20 %| = 0,30)"
    ),
}
# Rules that need the whole sample: the weight of an analog depends on the others.
SAMPLE_WEIGHTINGS = ("count_share", "gross_share", "gross_share_fraction")


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
    of absolute adjustments, % (``gross_share_fraction`` — the same sum in
    fractions; the "+ 1" makes the units matter). All sum to 1.
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
    scale = 1 if weighting == "gross_share" else 1 / 100
    gross = [item["adjustments_sum_abs_raw_pct"] * scale for item in adjusted]
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
