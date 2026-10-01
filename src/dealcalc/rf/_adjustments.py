"""Step-by-step comparable adjustments and sample statistics shared by the
real-estate and vehicle comparative approaches."""

from __future__ import annotations

import datetime
import math
import statistics
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Sequence

LEGACY_ADJUSTMENT_NAME = "Общая корректировка"
HOMOGENEITY_THRESHOLD_PCT = 33.0


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

    ``pct`` multiplies the current price by ``1 + value / 100``; ``abs`` adds
    ``value`` in price units (RUB per m² for real estate, RUB for vehicles).
    """

    price = base_price
    applied = []
    gross_change = 0.0
    for number, step in enumerate(steps, start=1):
        name_prefix = f"{prefix}.adjustments[{number - 1}]"
        if not isinstance(step, Mapping):
            raise ValueError(f"{name_prefix} must be an object")
        name = step.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{name_prefix}.name must be a non-empty string")
        kind = step.get("type")
        if kind not in ("pct", "abs"):
            raise ValueError(f"{name_prefix}.type must be 'pct' or 'abs'")
        value = _finite(f"{name_prefix}.value", step.get("value"))
        if kind == "pct":
            if value <= -100:
                raise ValueError(f"{name_prefix}.value must be greater than -100")
            new_price = price * (1 + value / 100)
        else:
            new_price = price + value
            if new_price <= 0:
                raise ValueError(
                    f"{name_prefix}: adjusted price must be greater than 0"
                )
        change = new_price - price
        gross_change += abs(change)
        applied.append(
            {
                "step": number,
                "name": name.strip(),
                "type": kind,
                "value": round(value, 2),
                "price_before": round(price, 2),
                "price_after": round(new_price, 2),
                "change": round(change, 2),
            }
        )
        price = new_price

    return {
        "adjusted_price": price,
        "adjustments": applied,
        "net_adjustment_pct": _share_pct(price - base_price, base_price),
        "gross_adjustment_pct": _share_pct(gross_change, base_price),
    }


def _share_pct(amount: float, base: float) -> Optional[float]:
    return None if base == 0 else round(amount / base * 100, 2)


def variation(prices: Sequence[float]) -> Dict[str, Any]:
    """Sample coefficient of variation of adjusted prices with the 33% check."""

    if len(prices) < 2 or statistics.mean(prices) == 0:
        coefficient = None
    else:
        coefficient = round(statistics.stdev(prices) / statistics.mean(prices) * 100, 2)
    return {
        "coefficient_pct": coefficient,
        "threshold_pct": HOMOGENEITY_THRESHOLD_PCT,
        "homogeneous": None
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
