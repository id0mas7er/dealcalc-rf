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
      corrections on physical characteristics.
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
                f"{name_prefix}.type must be 'pct', 'pct_group', 'abs', 'param' or 'depreciation'"
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
        # The evidence of the step travels with it into the result.
        for key in ("source", "date", "justification"):
            if step.get(key) not in (None, ""):
                record[key] = str(step[key])
        applied.append(record)
        price = new_price

    return {
        "adjusted_price": price,
        "adjustments": applied,
        # Steps that change the price; zero steps do not count.
        "adjustments_count": sum(1 for record in applied if record["change"] != 0),
        "net_adjustment_pct": _share_pct(price - base_price, base_price),
        "gross_adjustment_pct": _share_pct(gross_change, base_price),
    }


WEIGHTING_FORMULAS = {
    "manual": "веса задаёт оценщик (поле weight, по умолчанию 1)",
    "inverse_gross": "w_i ∝ 1 / (1 + G_i / 100), G_i — валовая корректировка аналога, %",
    "inverse_count": "w_i ∝ 1 / (1 + n_i), n_i — число корректировок аналога",
}


def analog_weight(
    comparable: Mapping[str, Any], adjusted: Mapping[str, Any], weighting: str, prefix: str
) -> float:
    """Raw weight of an analog under the selected weighting rule."""

    if weighting not in WEIGHTING_FORMULAS:
        raise ValueError("weighting must be 'manual', 'inverse_gross' or 'inverse_count'")
    if weighting == "manual":
        weight = _finite(f"{prefix}.weight", comparable.get("weight", 1))
        if weight <= 0:
            raise ValueError(f"{prefix}.weight must be greater than 0")
        return weight
    if comparable.get("weight") not in (None, ""):
        raise ValueError(f"{prefix}.weight is set manually: use weighting='manual'")
    if weighting == "inverse_gross":
        return 1 / (1 + (adjusted["gross_adjustment_pct"] or 0) / 100)
    return 1 / (1 + adjusted["adjustments_count"])


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
