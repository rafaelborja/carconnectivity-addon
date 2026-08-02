"""Normalization of heterogeneous upstream payloads into a common voyage record.

Upstream cruise sources are not schema-compatible with each other, and their
schemas are not contractually stable. Rather than hard-coding one vendor's field
names, map a set of aliases per output field and keep whatever else came back
under ``raw`` so nothing is silently lost.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

#: Output field -> candidate upstream keys, in priority order.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "voyage_id": ("voyage_id", "voyageId", "id", "cruise_id", "cruiseId", "code"),
    "title": ("title", "name", "cruise_title", "cruiseTitle", "voyage_name"),
    "cruise_line": (
        "cruise_line",
        "cruiseLine",
        "brand",
        "line",
        "operator",
        "brand_name",
    ),
    "ship": ("ship", "ship_name", "shipName", "vessel", "vessel_name"),
    "departure_date": (
        "departure_date",
        "departureDate",
        "sail_date",
        "sailDate",
        "start_date",
        "startDate",
        "cruise_date",
    ),
    "return_date": ("return_date", "returnDate", "end_date", "endDate", "arrival_date"),
    "nights": ("nights", "duration", "duration_nights", "length", "cruise_length"),
    "departure_port": (
        "departure_port",
        "departurePort",
        "embark_port",
        "embarkPort",
        "from_port",
        "origin",
    ),
    "arrival_port": ("arrival_port", "arrivalPort", "disembark_port", "to_port"),
    "destination": ("destination", "region", "area", "itinerary_region"),
    "price": ("price", "lead_price", "leadPrice", "from_price", "cruise_price", "fare"),
    "currency": ("currency", "currency_code", "currencyCode"),
    "booking_url": ("booking_url", "bookingUrl", "url", "link", "deep_link"),
}

_MONEY_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _first_present(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    """Return the first non-empty value among ``keys``."""
    for key in keys:
        if key in record:
            value = record[key]
            if value not in (None, "", [], {}):
                return value
    return None


def coerce_price(value: Any) -> float | None:
    """Best-effort numeric price from ints, floats or strings like '$1,299 pp'."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        match = _MONEY_RE.search(value.replace(",", ""))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


def coerce_nights(value: Any) -> int | None:
    """Best-effort night count from ints or strings like '7 nights' / '7-night'."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def normalize_voyage(record: Mapping[str, Any], source_id: str) -> dict[str, Any]:
    """Map one upstream record onto the common voyage shape.

    Unmapped keys are preserved under ``raw`` so that agents can still reason
    about vendor-specific fields the alias table does not know about.
    """
    out: dict[str, Any] = {"source": source_id}
    consumed: set[str] = set()

    for target, aliases in FIELD_ALIASES.items():
        value = _first_present(record, aliases)
        out[target] = value
        consumed.update(a for a in aliases if a in record)

    out["price"] = coerce_price(out["price"])
    out["nights"] = coerce_nights(out["nights"])
    out["raw"] = {k: v for k, v in record.items() if k not in consumed}
    return out


def dedupe_key(voyage: Mapping[str, Any]) -> tuple[str, str, str]:
    """Identity used to collapse the same sailing seen through several sources."""

    def norm(value: Any) -> str:
        return str(value).strip().lower() if value not in (None, "") else ""

    return (norm(voyage.get("ship")), norm(voyage.get("departure_date")), norm(voyage.get("nights")))


def merge_voyages(batches: Iterable[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Concatenate per-source results, collapsing duplicate sailings.

    When the same sailing appears twice, the first occurrence wins and the extra
    source is recorded in ``also_seen_in`` so provenance is not lost.
    """
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []

    for batch in batches:
        for voyage in batch:
            key = dedupe_key(voyage)
            if not any(key):
                unkeyed.append(voyage)
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = voyage
                continue
            also = existing.setdefault("also_seen_in", [])
            if voyage["source"] not in also and voyage["source"] != existing["source"]:
                also.append(voyage["source"])
            # Keep a price if the winning record lacked one.
            if existing.get("price") is None and voyage.get("price") is not None:
                existing["price"] = voyage["price"]
                existing["currency"] = voyage.get("currency")

    return [*merged.values(), *unkeyed]


def sort_voyages(voyages: list[dict[str, Any]], sort_by: str) -> list[dict[str, Any]]:
    """Sort results, always pushing records missing the sort key to the end."""
    if sort_by == "price":
        return sorted(
            voyages, key=lambda v: (v.get("price") is None, v.get("price") or 0.0)
        )
    if sort_by == "nights":
        return sorted(
            voyages, key=lambda v: (v.get("nights") is None, v.get("nights") or 0)
        )
    if sort_by == "departure_date":
        return sorted(
            voyages,
            key=lambda v: (
                v.get("departure_date") in (None, ""),
                str(v.get("departure_date") or ""),
            ),
        )
    return voyages
