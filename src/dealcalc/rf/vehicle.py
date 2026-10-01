"""Comparable-vehicle valuation helpers for Russian marketplace data."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from ._adjustments import (
    WEIGHTING_FORMULAS,
    adjustment_steps,
    analog_weight,
    apply_adjustments,
    json_value,
    money,
    variation,
    weight_shares,
)
from ._meta import (
    FORMULA_TECHNICAL,
    method_card,
    observation_checks,
    observation_fields,
    variation_checks,
)


def _number(name: str, value: Any, *, allow_none: bool = False) -> Optional[float]:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError(f"{name} is required")
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
})

# Common spellings of brands on the Russian market; extend with ``synonyms``.
BRAND_SYNONYMS = {
    "lada": ["ваз", "vaz", "лада", "lada"],
    "uaz": ["уаз", "uaz"],
    "gaz": ["газ", "gaz"],
    "moskvich": ["москвич", "moskvich"],
    "haval": ["хавал", "хавейл", "haval"],
    "chery": ["чери", "chery"],
    "geely": ["джили", "geely"],
    "changan": ["чанган", "changan"],
    "exeed": ["эксид", "exeed"],
    "omoda": ["омода", "omoda"],
    "jetour": ["джетур", "jetour"],
    "tank": ["танк", "tank"],
    "kia": ["киа", "kia"],
    "hyundai": ["хендай", "хёндэ", "хундай", "hyundai"],
    "toyota": ["тойота", "toyota"],
    "volkswagen": ["фольксваген", "volkswagen", "vw"],
    "skoda": ["шкода", "skoda", "škoda"],
    "renault": ["рено", "renault"],
    "nissan": ["ниссан", "nissan"],
    "mitsubishi": ["мицубиси", "митсубиси", "mitsubishi"],
    "bmw": ["бмв", "bmw"],
    "mercedes-benz": ["мерседес", "мерседес-бенц", "mercedes", "mercedes-benz"],
    "chevrolet": ["шевроле", "chevrolet"],
    "ford": ["форд", "ford"],
    "mazda": ["мазда", "mazda"],
}


def _tokens(value: Any) -> List[str]:
    text = "" if value is None else str(value).casefold().replace("ё", "е")
    return [token for token in re.split(r"[^0-9a-zа-я-]+", text) if token]


def _latin(token: str) -> str:
    return token.translate(_TRANSLIT)


def _synonym_index(extra: Optional[Mapping[str, Sequence[str]]]) -> Dict[str, str]:
    groups = {key: list(values) for key, values in BRAND_SYNONYMS.items()}
    for key, values in (extra or {}).items():
        groups.setdefault(str(key).casefold(), []).extend(values)
        groups[str(key).casefold()].append(str(key))
    index = {}
    for key, values in groups.items():
        for value in values:
            for token in _tokens(value) or [str(value).casefold()]:
                index[token] = key
                index[_latin(token)] = key
            index[str(value).casefold()] = key
    return index


def _brand_keys(value: Any, index: Mapping[str, str]) -> set:
    """All canonical keys a brand string may denote: "ВАЗ (Lada)" -> {"lada"}."""

    text = "" if value is None else str(value).casefold().replace("ё", "е").strip()
    if not text:
        return set()
    keys = {index[text]} if text in index else set()
    for token in _tokens(text):
        keys.add(index.get(token) or index.get(_latin(token)) or _latin(token))
    return keys


def _model_tokens(value: Any, index: Mapping[str, str]) -> List[str]:
    """Model tokens in Latin; appraiser-supplied synonyms map spellings that
    letter-by-letter transliteration cannot (Солярис -> solaris)."""

    return [index.get(token) or index.get(_latin(token)) or _latin(token) for token in _tokens(value)]


def _models_match(subject: List[str], comparable: List[str], mode: str) -> bool:
    if mode == "exact":
        return subject == comparable
    return bool(subject) and set(subject) <= set(comparable)


def _weighted_median(items: Sequence[tuple[float, float]]) -> float:
    ordered = sorted(items, key=lambda item: item[0])
    total_weight = sum(weight for _, weight in ordered)
    threshold = total_weight / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


@method_card(
    "VEHICLE_COMPARATIVE",
    "ФСО V; ФСО №10, п. 13",
    "P_adj = P_0 с последовательными поправками; V = взвешенная медиана P_adj",
    FORMULA_TECHNICAL,
    source_url="https://srosovet.ru/activities/npa/fso-10/",
)
def vehicle_comparative_approach(
    subject: Mapping[str, Any],
    comparables: Sequence[Mapping[str, Any]],
    currency: str = "RUB",
    max_year_diff: Optional[float] = None,
    max_mileage_diff: Optional[float] = None,
    weighting: str = "manual",
    match: str = "exact",
    synonyms: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    """Estimate a vehicle from matched, adjusted comparable listings.

    The subject and each comparable should use the normalized fields from
    :func:`dealcalc.rf.data.normalize_listing`. Comparables are matched by
    brand/model when those fields are present, and optionally limited by year
    and mileage differences set by the appraiser (no default limits; an
    unset limit is reported in ``checks``). ``adjustments`` and ``weight``
    are optional analyst-supplied fields on each comparable; the
    provenance of the observation (``source``, ``date``, ``url``,
    ``price_type``, ``conditions``, ``reliability``) is kept.

    ``adjustments`` is a list of ``{"name", "type", "value"}`` steps applied in
    order to the price: ``pct`` multiplies by ``1 + value / 100``, ``abs`` adds
    ``value`` RUB. Put the bargaining discount first. Every intermediate price
    is kept in the result. The legacy ``adjustment_pct`` field is treated as
    one step. ``variation`` reports the coefficient of variation of adjusted
    prices against the 33% homogeneity threshold. No automatic depreciation
    coefficient is imposed.
    """

    if not isinstance(subject, Mapping):
        raise ValueError("subject must be an object")
    if not comparables:
        raise ValueError("comparables must contain at least one item")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency must be a non-empty string")
    currency_code = currency.strip().upper()

    subject_price = _number("subject.price_rub", subject.get("price_rub"), allow_none=True)
    subject_year = _number("subject.year", subject.get("year"), allow_none=True)
    subject_mileage = _number(
        "subject.mileage_km", subject.get("mileage_km"), allow_none=True
    )
    if match not in ("exact", "contains"):
        raise ValueError("match must be 'exact' or 'contains'")
    if synonyms is not None and not isinstance(synonyms, Mapping):
        raise ValueError("synonyms must be an object: {canonical name: [spellings]}")
    synonym_index = _synonym_index(synonyms)
    subject_brand = _brand_keys(subject.get("brand"), synonym_index)
    subject_model = _model_tokens(subject.get("model"), synonym_index)

    if max_year_diff is not None and max_year_diff < 0:
        raise ValueError("max_year_diff must be non-negative or None")
    if max_mileage_diff is not None and max_mileage_diff < 0:
        raise ValueError("max_mileage_diff must be non-negative or None")

    matched: List[Dict[str, Any]] = []
    weighted_items = []
    rejected = 0
    for index, comparable in enumerate(comparables, start=1):
        if not isinstance(comparable, Mapping):
            raise ValueError(f"comparables[{index - 1}] must be an object")
        price = _number(f"comparables[{index - 1}].price_rub", comparable.get("price_rub"))
        if price <= 0:
            raise ValueError(f"comparables[{index - 1}].price_rub must be greater than 0")
        comp_brand = _brand_keys(comparable.get("brand"), synonym_index)
        comp_model = _model_tokens(comparable.get("model"), synonym_index)
        if subject_brand and not subject_brand & comp_brand:
            rejected += 1
            continue
        if subject_model and not _models_match(subject_model, comp_model, match):
            rejected += 1
            continue

        comp_year = _number(
            f"comparables[{index - 1}].year", comparable.get("year"), allow_none=True
        )
        comp_mileage = _number(
            f"comparables[{index - 1}].mileage_km",
            comparable.get("mileage_km"),
            allow_none=True,
        )
        if (
            max_year_diff is not None
            and subject_year is not None
            and comp_year is not None
            and abs(subject_year - comp_year) > max_year_diff
        ):
            rejected += 1
            continue
        if (
            max_mileage_diff is not None
            and subject_mileage is not None
            and comp_mileage is not None
            and abs(subject_mileage - comp_mileage) > max_mileage_diff
        ):
            rejected += 1
            continue

        prefix = f"comparables[{index - 1}]"
        adjusted = apply_adjustments(price, adjustment_steps(comparable, prefix), prefix)
        adjusted_price = adjusted["adjusted_price"]
        weight = analog_weight(comparable, adjusted, weighting, prefix)
        weighted_items.append((adjusted_price, weight))
        item: Dict[str, Any] = {
            "index": index,
            "price_rub": money(price),
            "adjustments": adjusted["adjustments"],
            "net_adjustment_pct": adjusted["net_adjustment_pct"],
            "gross_adjustment_pct": adjusted["gross_adjustment_pct"],
            "adjusted_price_rub": money(adjusted_price),
            "weight": round(weight, 6),
        }
        for field in ("listing_id", "brand", "model", "year", "mileage_km", "collected_at"):
            if field in comparable and comparable[field] not in (None, ""):
                item[field] = json_value(comparable[field])
        item.update(observation_fields(comparable, prefix))
        matched.append(item)

    if not matched:
        raise ValueError("no comparable vehicles matched the subject filters")
    for item, share in zip(matched, weight_shares([weight for _, weight in weighted_items])):
        item["weight_share"] = share

    weight_sum = sum(weight for _, weight in weighted_items)
    weighted_mean = sum(value * weight for value, weight in weighted_items) / weight_sum
    adjusted_prices = [item["adjusted_price_rub"] for item in matched]
    price_variation = variation(adjusted_prices)
    checks = observation_checks(matched)
    checks += variation_checks(price_variation, len(matched))
    if max_year_diff is None or max_mileage_diff is None:
        checks.append(
            "Не заданы ограничения отбора по году и/или пробегу: "
            "сопоставимость аналогов обоснуйте отдельно."
        )
    return {
        "approach": "comparative",
        "asset_type": "vehicle",
        "currency": currency_code,
        "subject_price_rub": None if subject_price is None else money(subject_price),
        "sample_size": len(matched),
        "rejected_count": rejected,
        "weighting": weighting,
        "weighting_formula": WEIGHTING_FORMULAS[weighting],
        "weighted_median_price": money(_weighted_median(weighted_items)),
        "weighted_mean_price": money(weighted_mean),
        "indicated_value": money(_weighted_median(weighted_items)),
        "indicated_value_range": {
            "low": money(min(adjusted_prices)),
            "high": money(max(adjusted_prices)),
        },
        "variation": price_variation,
        "selection": {
            "match": match,
            "max_year_diff": max_year_diff,
            "max_mileage_diff": max_mileage_diff,
            "automatic_adjustments": False,
        },
        "comparables": matched,
        "checks": checks,
    }
