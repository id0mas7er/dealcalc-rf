"""Comparable-vehicle valuation helpers for Russian marketplace data."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ._adjustments import (
    WEIGHTING_FORMULAS,
    adjustment_steps,
    analog_weight,
    sample_weights,
    apply_adjustments,
    json_value,
    money,
    scaled_weights,
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

# Spellings of brands and models on the Russian market, {canonical: [spellings]};
# extended with ``synonyms`` and ``synonyms_file``.
_SYNONYMS_PATH = Path(__file__).with_name("vehicle_synonyms.json")
with _SYNONYMS_PATH.open(encoding="utf-8") as _handle:
    _BUILTIN_SYNONYMS = json.load(_handle)
BRAND_SYNONYMS: Dict[str, List[str]] = _BUILTIN_SYNONYMS["brands"]
MODEL_SYNONYMS: Dict[str, List[str]] = _BUILTIN_SYNONYMS["models"]


def _tokens(value: Any) -> List[str]:
    text = "" if value is None else str(value).casefold().replace("ё", "е")
    return [token for token in re.split(r"[^0-9a-zа-я-]+", text) if token]


def _latin(token: str) -> str:
    return token.translate(_TRANSLIT)


def _merge_groups(
    base: Mapping[str, Sequence[str]], *extras: Optional[Mapping[str, Sequence[str]]]
) -> Dict[str, List[str]]:
    groups = {key: list(values) for key, values in base.items()}
    for extra in extras:
        for key, values in (extra or {}).items():
            groups.setdefault(str(key).casefold(), []).extend(values)
            groups[str(key).casefold()].append(str(key))
    return groups


def _load_synonyms_file(path: str) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Read appraiser synonyms: {"brands": {...}, "models": {...}}."""

    with Path(path).open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("synonyms_file must hold an object with 'brands' and/or 'models'")
    result = []
    for part in ("brands", "models"):
        groups = data.get(part) or {}
        if not isinstance(groups, Mapping) or not all(
            isinstance(values, list) for values in groups.values()
        ):
            raise ValueError(f"synonyms_file.{part} must be an object: {{canonical name: [spellings]}}")
        result.append(groups)
    return result[0], result[1]


def _synonym_index(groups: Mapping[str, Sequence[str]]) -> Dict[str, str]:
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


def _phrase(value: Any) -> str:
    """Lower-case words separated by single spaces: "X-Trail" -> "x trail"."""

    text = "" if value is None else str(value).casefold().replace("ё", "е")
    return " ".join(re.findall(r"[0-9a-zа-я]+", text))


def _model_replacements(groups: Mapping[str, Sequence[str]]) -> List[Tuple[str, str]]:
    pairs = {}
    for canonical, values in groups.items():
        for value in values:
            variant = _phrase(value)
            if variant:
                # Also the letter-by-letter Latin form: Крета -> kreta -> creta.
                pairs[variant] = pairs[_latin(variant)] = _phrase(canonical)
    return sorted(pairs.items(), key=lambda pair: -len(pair[0]))


def _model_tokens(value: Any, replacements: Sequence[Tuple[str, str]]) -> List[str]:
    """Model tokens in Latin. Dictionary phrases map spellings that
    letter-by-letter transliteration cannot (Солярис -> solaris,
    Х-Трейл -> x trail); hyphens count as spaces."""

    text = _phrase(value)
    for variant, canonical in replacements:
        text = re.sub(rf"(?<!\S){re.escape(variant)}(?!\S)", canonical, text)
    return [_latin(token) for token in text.split()]


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
    synonyms_file: Optional[str] = None,
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

    The indicated value is the weighted median of adjusted prices without
    interpolation: the first price, in ascending order, whose cumulative
    weight reaches half of the total. With an even split it is the lower
    median — of two analogs with equal weights, the cheaper one.

    Brands and models are matched through the package dictionary
    ``vehicle_synonyms.json`` and transliteration. ``synonyms``
    (``{canonical name: [spellings]}``, applied to brands and models) and
    ``synonyms_file`` (a local JSON ``{"brands": {...}, "models": {...}}``)
    extend it.
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
    file_brands, file_models = _load_synonyms_file(synonyms_file) if synonyms_file else ({}, {})
    synonym_index = _synonym_index(_merge_groups(BRAND_SYNONYMS, file_brands, synonyms))
    model_replacements = _model_replacements(_merge_groups(MODEL_SYNONYMS, file_models, synonyms))
    subject_brand = _brand_keys(subject.get("brand"), synonym_index)
    subject_model = _model_tokens(subject.get("model"), model_replacements)

    max_year_diff = _number("max_year_diff", max_year_diff, allow_none=True)
    max_mileage_diff = _number("max_mileage_diff", max_mileage_diff, allow_none=True)
    if max_year_diff is not None and max_year_diff < 0:
        raise ValueError("max_year_diff must be non-negative or None")
    if max_mileage_diff is not None and max_mileage_diff < 0:
        raise ValueError("max_mileage_diff must be non-negative or None")

    matched: List[Dict[str, Any]] = []
    weighted_items = []
    adjusted_all = []
    rejected = 0
    # Analogs a set limit could not be applied to for lack of data.
    no_year: List[int] = []
    no_mileage: List[int] = []
    for index, comparable in enumerate(comparables, start=1):
        if not isinstance(comparable, Mapping):
            raise ValueError(f"comparables[{index - 1}] must be an object")
        price = _number(f"comparables[{index - 1}].price_rub", comparable.get("price_rub"))
        if price <= 0:
            raise ValueError(f"comparables[{index - 1}].price_rub must be greater than 0")
        comp_brand = _brand_keys(comparable.get("brand"), synonym_index)
        comp_model = _model_tokens(comparable.get("model"), model_replacements)
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
        if max_year_diff is not None and subject_year is not None and comp_year is None:
            no_year.append(index)
        if max_mileage_diff is not None and subject_mileage is not None and comp_mileage is None:
            no_mileage.append(index)
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
        adjusted_all.append(adjusted)
        item: Dict[str, Any] = {
            "index": index,
            "price_rub": money(price),
            "adjustments": adjusted["adjustments"],
            "net_adjustment_pct": adjusted["net_adjustment_pct"],
            "gross_adjustment_pct": adjusted["gross_adjustment_pct"],
            "adjustments_count": adjusted["adjustments_count"],
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
    sample = sample_weights(adjusted_all, weighting)
    if sample is not None:
        weighted_items = [(price, weight) for (price, _), weight in zip(weighted_items, sample)]
        for item, weight in zip(matched, sample):
            item["weight"] = round(weight, 6)
    weighted_items = list(
        zip([price for price, _ in weighted_items], scaled_weights([weight for _, weight in weighted_items]))
    )
    for item, share in zip(matched, weight_shares([weight for _, weight in weighted_items])):
        item["weight_share"] = share

    weight_sum = sum(weight for _, weight in weighted_items)
    weighted_mean = sum(value * weight for value, weight in weighted_items) / weight_sum
    # Statistics of the sample come from unrounded prices, as the mean does.
    adjusted_prices = [price for price, _ in weighted_items]
    price_variation = variation(adjusted_prices)
    median = _weighted_median(weighted_items)
    checks = observation_checks(matched)
    checks += variation_checks(price_variation, len(matched))
    matched_indices = {item["index"] for item in matched}
    for limit, subject_value, missing, label in (
        (max_year_diff, subject_year, no_year, "года выпуска"),
        (max_mileage_diff, subject_mileage, no_mileage, "пробега"),
    ):
        if limit is None:
            continue
        if subject_value is None:
            checks.append(f"У объекта оценки нет {label}: ограничение отбора по нему не проверено.")
        missing = [index for index in missing if index in matched_indices]
        if missing:
            checks.append(f"У аналогов {missing} нет {label}: ограничение отбора по нему не проверено.")
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
        "weighted_median_price": money(median),
        "weighted_mean_price": money(weighted_mean),
        "indicated_value": money(median),
        # The spread of analogs, not an interval of value.
        "analogs_spread": {
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
