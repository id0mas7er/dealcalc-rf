"""Offline import and normalization for Russian marketplace listings.

The importer reads user-provided CSV/JSON/JSONL files only. It deliberately
does not make network requests. This makes it suitable for cached exports and
keeps collection policy separate from valuation formulas.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


LISTING_TYPES = {"property", "vehicle"}

_ALIASES = {
    "source": ("source", "источник", "площадка", "сайт"),
    "listing_id": ("listing_id", "id", "идентификатор", "номер объявления"),
    "url": ("url", "link", "ссылка", "ссылка на объявление"),
    "address": ("address", "адрес", "местоположение"),
    "cadastral_number": ("cadastral_number", "кадастровый номер", "кадастровый"),
    "vin": ("vin", "вин", "vin-номер"),
    "date": (
        "date",
        "дата публикации",
        "дата объявления",
        "дата размещения",
        "размещено",
    ),
    "price_type": ("price_type", "тип цены"),
    "collected_at": ("collected_at", "дата сбора", "дата_сбора"),
    "region": ("region", "регион", "область", "край"),
    "city": ("city", "город", "населенный пункт", "населённый пункт"),
    "price_rub": ("price_rub", "price", "цена", "стоимость", "цена руб"),
    "area_sqm": ("area_sqm", "area", "площадь", "площадь м2", "площадь м²"),
    "rooms": ("rooms", "комнаты", "комнат"),
    "floor": ("floor", "этаж"),
    "total_floors": ("total_floors", "этажей", "всего этажей"),
    "year": ("year", "год", "год выпуска", "год постройки"),
    "condition": ("condition", "состояние"),
    "brand": ("brand", "марка", "make"),
    "model": ("model", "модель"),
    "mileage_km": ("mileage_km", "mileage", "пробег", "пробег км"),
    "engine_power_hp": ("engine_power_hp", "мощность", "мощность лс", "мощность л.с."),
    "transmission": ("transmission", "коробка", "коробка передач"),
    "drive": ("drive", "привод"),
    "adjustment_pct": ("adjustment_pct", "корректировка", "корректировка %"),
    "weight": ("weight", "вес"),
    "adjustments": ("adjustments", "корректировки"),
}

_TEXT_FIELDS = {
    "listing_id",
    "url",
    "address",
    "cadastral_number",
    "vin",
    "date",
    "collected_at",
    "region",
    "city",
    "condition",
    "brand",
    "model",
    "transmission",
    "drive",
}
_NUMBER_FIELDS = {
    "price_rub",
    "area_sqm",
    "rooms",
    "floor",
    "total_floors",
    "year",
    "mileage_km",
    "engine_power_hp",
}


def _lookup(row: Mapping[str, Any], field: str) -> Any:
    """Find a field using canonical and common Russian aliases."""

    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in _ALIASES[field]:
        if alias.lower() in lowered:
            return lowered[alias.lower()]
    return None


def parse_number(value: Any, field: str) -> Optional[float]:
    """Parse a number from a CSV/JSON value, including Russian price strings."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace("\u00a0", " ")
        if not text:
            return None
        text = re.sub(r"[^0-9,.-]", "", text)
        if "," in text and "." in text:
            # The last separator is the decimal one: 1.200.000,50 or 1,200,000.50.
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif text.count(",") == 1:
            text = text.replace(",", ".")
        elif text.count(",") > 1:
            text = text.replace(",", "")
        elif text.count(".") > 1:
            text = text.replace(".", "")
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _parse_adjustments(value: Any) -> Optional[List[Dict[str, Any]]]:
    """Read step adjustments: a list, or a JSON list in a CSV cell."""

    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("adjustments must be a JSON list of objects") from exc
    if not isinstance(value, list) or not all(isinstance(step, Mapping) for step in value):
        raise ValueError("adjustments must be a JSON list of objects")
    return [dict(step) for step in value]


_PRICE_TYPES = {
    "сделка": "сделка",
    "transaction": "сделка",
    "цена сделки": "сделка",
    "предложение": "предложение",
    "offer": "предложение",
    "цена предложения": "предложение",
}


def _price_type(value: Any) -> Tuple[str, Optional[str]]:
    """Marketplace exports are offers unless the file says otherwise.

    An unknown value ("Продажа", "Аренда" — often the deal type) is left
    empty with a warning instead of stopping the import.
    """

    text = _text(value).lower()
    if not text:
        return "предложение", None
    if text not in _PRICE_TYPES:
        return "", (
            f"Тип цены «{_text(value)}» не распознан (ожидается «сделка» или "
            "«предложение»): поле оставлено пустым."
        )
    return _PRICE_TYPES[text], None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _default_collected_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_listing(
    row: Mapping[str, Any],
    source: Optional[str] = None,
    listing_type: str = "property",
    collected_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize one marketplace row into the shared listing schema.

    ``date`` is the publication date of the offer (the price date);
    ``collected_at`` is when the file was collected and is not a price date.
    ``price_type`` defaults to "предложение": marketplace listings are offers.
    """

    if not isinstance(row, Mapping):
        raise ValueError("row must be an object")
    listing_kind = _text(listing_type).lower()
    if listing_kind not in LISTING_TYPES:
        raise ValueError("listing_type must be 'property' or 'vehicle'")

    source_name = _text(source or _lookup(row, "source"))
    if source:
        source_name = _text(source)
    if not source_name:
        raise ValueError("source must be provided")

    values: Dict[str, Any] = {
        "listing_type": listing_kind,
        "source": source_name,
    }
    for field in _TEXT_FIELDS:
        values[field] = _text(_lookup(row, field))
    for field in _NUMBER_FIELDS:
        values[field] = parse_number(_lookup(row, field), field)
    for field in ("adjustment_pct", "weight"):
        number = parse_number(_lookup(row, field), field)
        if number is not None:
            values[field] = number
    values["price_type"], price_type_warning = _price_type(_lookup(row, "price_type"))
    if price_type_warning:
        values["import_warnings"] = [price_type_warning]
    adjustments = _parse_adjustments(_lookup(row, "adjustments"))
    if adjustments is not None:
        values["adjustments"] = adjustments

    if collected_at is not None:
        values["collected_at"] = _text(collected_at)
    elif not values["collected_at"]:
        values["collected_at"] = _default_collected_at()

    if values["price_rub"] is None or values["price_rub"] <= 0:
        raise ValueError("price_rub must be a number greater than 0")
    if values["area_sqm"] is not None and values["area_sqm"] <= 0:
        raise ValueError("area_sqm must be greater than 0 when provided")
    if values["mileage_km"] is not None and values["mileage_km"] < 0:
        raise ValueError("mileage_km must be non-negative")

    if not values["listing_id"]:
        stable_fields = (
            values["source"],
            values["url"],
            values["listing_type"],
            values["price_rub"],
            values["area_sqm"],
            values["year"],
            values["brand"],
            values["model"],
            values["mileage_km"],
        )
        # The address is not an identifier: different flats share it.
        if values["url"]:
            stable_fields = (values["source"], values["url"])
        elif values["vin"]:
            stable_fields = (values["source"], "vin", values["vin"].upper())
        elif values["cadastral_number"]:
            stable_fields = (values["source"], "cadastral", values["cadastral_number"])
        seed = "|".join("" if item is None else str(item) for item in stable_fields)
        values["listing_id"] = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    return values


def deduplicate_listings(listings: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the first row for each source/listing_id pair."""

    result: List[Dict[str, Any]] = []
    seen = set()
    for listing in listings:
        key = (listing.get("source"), listing.get("listing_id"))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(listing))
    return result


def _json_rows(path: Path) -> Iterable[Tuple[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if isinstance(payload, Mapping):
        for key in ("items", "listings", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                payload = candidate
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON root must be an object or an array")
    for number, row in enumerate(payload, start=1):
        yield f"item {number}", row


def _jsonl_rows(path: Path) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}") from exc
            if not isinstance(row, Mapping):
                raise ValueError(f"JSONL line {line_number} must contain an object")
            yield f"line {line_number}", row


def _csv_rows(path: Path) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        # Sniff the delimiter from the header only: data cells may hold JSON
        # with commas. Quoting follows standard CSV ("" inside quoted cells).
        sample = handle.readline()
        handle.seek(0)
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            delimiter = ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        for row in reader:
            yield f"line {reader.line_num}", row


def load_listings(
    path: str,
    source: str,
    listing_type: str = "property",
    collected_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load and normalize a local CSV, JSON, or JSONL export.

    No network request is made. Duplicate source/listing_id rows are removed
    while preserving the first occurrence. An invalid row stops the import
    with its line (CSV, JSONL) or item (JSON) number in the error.
    """

    input_path = Path(path)
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        rows = _csv_rows(input_path)
    elif suffix == ".json":
        rows = _json_rows(input_path)
    elif suffix == ".jsonl":
        rows = _jsonl_rows(input_path)
    else:
        raise ValueError("supported input formats are .csv, .json, and .jsonl")

    normalized = []
    for label, row in rows:
        try:
            normalized.append(normalize_listing(row, source, listing_type, collected_at))
        except ValueError as exc:
            raise ValueError(f"{label}: {exc}") from exc
    return deduplicate_listings(normalized)
