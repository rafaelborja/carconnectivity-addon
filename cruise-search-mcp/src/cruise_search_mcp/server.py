#!/usr/bin/env python3
"""MCP server aggregating public cruise search sources.

Fans a single search out across the upstream sources that survived validation,
normalizes their differing payloads into one voyage shape, and refuses to call
sources whose existence could not be corroborated.

Every result carries provenance, and inventory figures quoted by vendors are
reported as claims rather than facts.
"""

from __future__ import annotations

import asyncio
import json
from enum import Enum
from typing import Any, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .normalize import merge_voyages, sort_voyages
from .providers import ApifyProvider, McpSourceProvider, ProviderError
from .sources import (
    SOURCES,
    SOURCES_BY_ID,
    Source,
    SourceKind,
    SourceStatus,
    usable_sources,
)

mcp = FastMCP("cruise_search_mcp")

PER_SOURCE_TIMEOUT_SECONDS = 45.0
HEALTH_TIMEOUT_SECONDS = 20.0


class SortBy(str, Enum):
    """Ordering applied to merged voyage results."""

    PRICE = "price"
    NIGHTS = "nights"
    DEPARTURE_DATE = "departure_date"
    RELEVANCE = "relevance"


class SearchVoyagesInput(BaseModel):
    """Filters for a cross-source voyage search."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    destination: Optional[str] = Field(
        default=None,
        description="Region or destination, e.g. 'Caribbean', 'Mediterranean', 'Alaska'",
        max_length=100,
    )
    departure_port: Optional[str] = Field(
        default=None, description="Embarkation port, e.g. 'Miami'", max_length=100
    )
    cruise_line: Optional[str] = Field(
        default=None, description="Cruise line or brand, e.g. 'Royal Caribbean'", max_length=100
    )
    ship: Optional[str] = Field(
        default=None, description="Ship name, e.g. 'Wonder of the Seas'", max_length=100
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Earliest departure date, ISO YYYY-MM-DD",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Latest departure date, ISO YYYY-MM-DD",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    min_nights: Optional[int] = Field(default=None, description="Minimum nights", ge=1, le=200)
    max_nights: Optional[int] = Field(default=None, description="Maximum nights", ge=1, le=200)
    max_price: Optional[float] = Field(
        default=None, description="Maximum lead-in price per person", ge=0
    )
    sources: Optional[list[str]] = Field(
        default=None,
        description=(
            "Source ids to query. Defaults to every corroborated MCP source. "
            "Call cruise_list_sources to see ids and their validation status."
        ),
        max_length=10,
    )
    limit: int = Field(default=25, description="Maximum voyages to return", ge=1, le=200)
    sort_by: SortBy = Field(default=SortBy.PRICE, description="Result ordering")

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        """Reject unknown or non-callable source ids early with a useful message."""
        if value is None:
            return None
        for source_id in value:
            source = SOURCES_BY_ID.get(source_id)
            if source is None:
                raise ValueError(
                    f"Unknown source {source_id!r}. Known ids: {sorted(SOURCES_BY_ID)}"
                )
            if source.status is SourceStatus.UNVERIFIED:
                raise ValueError(
                    f"Source {source_id!r} is unverified and intentionally disabled: "
                    f"{source.summary}"
                )
            if source.status is SourceStatus.GATED:
                raise ValueError(
                    f"Source {source_id!r} needs a commercial agreement and has no "
                    "free programmatic endpoint."
                )
        return value


class ListSourcesInput(BaseModel):
    """Filter for the source registry listing."""

    model_config = ConfigDict(extra="forbid")

    include_disabled: bool = Field(
        default=True,
        description="Include unverified and commercially gated sources in the listing",
    )


class CheckSourcesInput(BaseModel):
    """Options for the live source health preflight."""

    model_config = ConfigDict(extra="forbid")

    sources: Optional[list[str]] = Field(
        default=None,
        description="Source ids to probe. Defaults to all callable MCP sources.",
        max_length=10,
    )


class BookingLinkInput(BaseModel):
    """Inputs for resolving an agency-attributed booking URL."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    cruise_line: str = Field(
        ..., description="Cruise line to book, e.g. 'Carnival'", min_length=2, max_length=100
    )
    ship: Optional[str] = Field(default=None, description="Ship name", max_length=100)
    departure_date: Optional[str] = Field(
        default=None, description="Departure date, ISO YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"
    )


def _json(payload: Any) -> str:
    """Serialize tool output consistently."""
    return json.dumps(payload, indent=2, default=str)


def _describe_error(source_id: str, exc: BaseException) -> dict[str, Any]:
    """Turn a provider failure into an actionable, non-fatal report entry."""
    if isinstance(exc, asyncio.TimeoutError):
        message = f"Timed out after {PER_SOURCE_TIMEOUT_SECONDS:.0f}s"
    elif isinstance(exc, ProviderError):
        message = str(exc)
    else:
        message = f"{type(exc).__name__}: {exc}"
    return {"source": source_id, "ok": False, "error": message}


def _resolve_targets(requested: Optional[list[str]]) -> list[Source]:
    """Resolve requested source ids to callable MCP sources."""
    if requested is None:
        return usable_sources(SourceKind.MCP)
    resolved = [SOURCES_BY_ID[s] for s in requested]
    return [s for s in resolved if s.kind is SourceKind.MCP and s.endpoint]


@mcp.tool(
    name="cruise_list_sources",
    annotations={
        "title": "List Cruise Data Sources And Validation Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def cruise_list_sources(params: ListSourcesInput) -> str:
    """List every known cruise data source with what was and was not verified.

    Read this before quoting any inventory figure to a user. Entries separate
    corroborated facts from vendor marketing claims, and record corrections
    where widely circulated write-ups are wrong.

    Args:
        params (ListSourcesInput): Validated input containing:
            - include_disabled (bool): Include unverified/gated sources.

    Returns:
        str: JSON with schema:
        {
          "count": int,
          "sources": [
            {
              "id": str,                    # e.g. "siloah"
              "title": str,
              "kind": str,                  # "mcp" | "rest" | "scraper"
              "status": str,                # corroborated | corroborated_with_corrections
                                            # | unverified | gated
              "endpoint": str | null,
              "auth": str,
              "summary": str,
              "verified": [str],            # independently corroborated facts
              "corrections": [str],         # where common write-ups are wrong
              "unverified_claims": [str],   # treat as unproven
              "evidence": [str]             # source URLs
            }
          ],
          "note": str
        }

    Examples:
        - Use when: "Which cruise sources can you actually search?"
        - Use when: verifying a claim before repeating it to the user.
        - Don't use when: you want live reachability - use cruise_check_sources.
    """
    selected = [
        s
        for s in SOURCES
        if params.include_disabled
        or s.status in {SourceStatus.CORROBORATED, SourceStatus.CORROBORATED_WITH_CORRECTIONS}
    ]
    return _json(
        {
            "count": len(selected),
            "sources": [s.to_dict() for s in selected],
            "note": (
                "Status reflects desk validation on 2026-08-02, not a live "
                "handshake. Run cruise_check_sources for current reachability. "
                "Figures under 'unverified_claims' are vendor marketing and must "
                "not be repeated as fact."
            ),
        }
    )


@mcp.tool(
    name="cruise_check_sources",
    annotations={
        "title": "Probe Cruise Sources For Live Reachability",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def cruise_check_sources(params: CheckSourcesInput) -> str:
    """Probe each MCP source with a real handshake and report what it exposes.

    This is the ground truth the static registry cannot provide: it connects,
    lists tools, and reports the actual tool names. Run it before trusting any
    documented tool name, and after any search failure.

    Args:
        params (CheckSourcesInput): Validated input containing:
            - sources (Optional[list[str]]): Source ids to probe.

    Returns:
        str: JSON with schema:
        {
          "checked": int,
          "healthy": int,
          "results": [
            {
              "source": str,
              "ok": bool,
              "endpoint": str,            # present when ok
              "tool_count": int,          # present when ok
              "tools": [str],             # actual upstream tool names
              "error": str                # present when ok is false
            }
          ]
        }

    Examples:
        - Use when: a search returned nothing and you need to know why.
        - Use when: confirming which tools a server really exposes.
    """
    targets = _resolve_targets(params.sources)

    async def probe(source: Source) -> dict[str, Any]:
        try:
            provider = McpSourceProvider(source, timeout=HEALTH_TIMEOUT_SECONDS)
            tools = await asyncio.wait_for(
                provider.list_tools(), timeout=HEALTH_TIMEOUT_SECONDS
            )
            return {
                "source": source.id,
                "ok": True,
                "endpoint": source.endpoint,
                "tool_count": len(tools),
                "tools": sorted(getattr(t, "name", "") for t in tools),
            }
        except Exception as exc:  # noqa: BLE001 - report, never abort the sweep
            return _describe_error(source.id, exc)

    results = await asyncio.gather(*(probe(s) for s in targets))
    return _json(
        {
            "checked": len(results),
            "healthy": sum(1 for r in results if r["ok"]),
            "results": list(results),
        }
    )


@mcp.tool(
    name="cruise_search_voyages",
    annotations={
        "title": "Search Cruise Voyages Across Sources",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def cruise_search_voyages(params: SearchVoyagesInput) -> str:
    """Search cruise voyages across every corroborated source and merge results.

    Queries sources concurrently, normalizes their differing field names into one
    shape, collapses duplicate sailings, and applies price/night filters locally
    because upstream filter support varies. A failing source degrades the result
    rather than failing the call.

    Args:
        params (SearchVoyagesInput): Validated input containing:
            - destination, departure_port, cruise_line, ship (Optional[str])
            - start_date, end_date (Optional[str]): ISO YYYY-MM-DD
            - min_nights, max_nights (Optional[int])
            - max_price (Optional[float]): per-person lead-in ceiling
            - sources (Optional[list[str]]): source ids to query
            - limit (int): max voyages, 1-200 (default 25)
            - sort_by (SortBy): price | nights | departure_date | relevance

    Returns:
        str: JSON with schema:
        {
          "count": int,
          "sources_queried": [str],
          "source_errors": [{"source": str, "ok": false, "error": str}],
          "voyages": [
            {
              "source": str,              # provenance
              "also_seen_in": [str],      # other sources with the same sailing
              "voyage_id": str | null,
              "title": str | null,
              "cruise_line": str | null,
              "ship": str | null,
              "departure_date": str | null,
              "return_date": str | null,
              "nights": int | null,
              "departure_port": str | null,
              "arrival_port": str | null,
              "destination": str | null,
              "price": float | null,      # null means upstream gave no price
              "currency": str | null,
              "booking_url": str | null,
              "raw": {}                   # unmapped upstream fields
            }
          ],
          "caveats": [str]
        }

    Examples:
        - Use when: "Find 7-night Caribbean cruises from Miami under $900."
        - Don't use when: you need a booking URL - use cruise_get_booking_link.

    Error Handling:
        - Unknown/disabled source ids are rejected by validation with the reason.
        - Per-source failures appear in "source_errors"; the call still succeeds.
        - If every source fails, "voyages" is empty and each error is listed.
    """
    targets = _resolve_targets(params.sources)
    if not targets:
        return _json(
            {
                "count": 0,
                "sources_queried": [],
                "source_errors": [],
                "voyages": [],
                "caveats": ["No callable MCP sources are configured."],
            }
        )

    upstream_args = {
        "destination": params.destination,
        "departurePort": params.departure_port,
        "departure_port": params.departure_port,
        "cruiseLine": params.cruise_line,
        "cruise_line": params.cruise_line,
        "brand": params.cruise_line,
        "shipName": params.ship,
        "ship": params.ship,
        "startDate": params.start_date,
        "start_date": params.start_date,
        "endDate": params.end_date,
        "end_date": params.end_date,
        "priceMax": params.max_price,
        "max_price": params.max_price,
        "limit": params.limit,
    }

    async def query(source: Source) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        try:
            provider = McpSourceProvider(source, timeout=PER_SOURCE_TIMEOUT_SECONDS)
            voyages = await asyncio.wait_for(
                provider.search_voyages(upstream_args), timeout=PER_SOURCE_TIMEOUT_SECONDS
            )
            return source.id, voyages, None
        except Exception as exc:  # noqa: BLE001 - degrade, do not abort
            return source.id, [], _describe_error(source.id, exc)

    outcomes = await asyncio.gather(*(query(s) for s in targets))

    merged = merge_voyages([voyages for _, voyages, _ in outcomes])

    if params.min_nights is not None:
        merged = [v for v in merged if v.get("nights") is None or v["nights"] >= params.min_nights]
    if params.max_nights is not None:
        merged = [v for v in merged if v.get("nights") is None or v["nights"] <= params.max_nights]
    if params.max_price is not None:
        merged = [v for v in merged if v.get("price") is None or v["price"] <= params.max_price]

    merged = sort_voyages(merged, params.sort_by.value)[: params.limit]
    errors = [err for _, _, err in outcomes if err]

    caveats = [
        "Prices are lead-in fares as published upstream and usually exclude taxes, "
        "fees and gratuities. Confirm on the operator's site before booking.",
        "Records with a null price were returned without pricing; they are not free.",
    ]
    if errors:
        caveats.append(
            f"{len(errors)} of {len(targets)} sources failed; results are partial."
        )

    return _json(
        {
            "count": len(merged),
            "sources_queried": [s.id for s in targets],
            "source_errors": errors,
            "voyages": merged,
            "caveats": caveats,
        }
    )


@mcp.tool(
    name="cruise_get_booking_link",
    annotations={
        "title": "Get An Agency-Attributed Cruise Booking Link",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def cruise_get_booking_link(params: BookingLinkInput) -> str:
    """Resolve a booking URL for a cruise line via the Pixie Vacations MCP source.

    Returns a link only. It does not book anything, take payment, or hold
    inventory: the user completes checkout on the supplier's own site. The URL
    carries the agency's referral parameter, which credits that agency as agent
    of record - disclose this when presenting the link.

    Args:
        params (BookingLinkInput): Validated input containing:
            - cruise_line (str): Cruise line to book, required
            - ship (Optional[str]): Ship name
            - departure_date (Optional[str]): ISO YYYY-MM-DD

    Returns:
        str: JSON with schema:
        {
          "source": "pixie",
          "tool_called": str,          # actual upstream tool name used
          "results": [ {...} ],        # upstream payload, may contain booking urls
          "booking_urls": [str],       # urls discovered in the payload
          "disclosure": str            # affiliate attribution notice
        }

        Error response: {"error": str, "hint": str}

    Examples:
        - Use when: the user picked a sailing and wants to book it.
        - Don't use when: still comparing options - use cruise_search_voyages.

    Error Handling:
        - Returns an error object if the source is unreachable or exposes no
          booking-capable tool; run cruise_check_sources to see its real tools.
    """
    source = SOURCES_BY_ID["pixie"]
    try:
        provider = McpSourceProvider(source, timeout=PER_SOURCE_TIMEOUT_SECONDS)
        tool_name, records = await asyncio.wait_for(
            provider.call_intent(
                "booking",
                {
                    "cruise_line": params.cruise_line,
                    "cruiseLine": params.cruise_line,
                    "ship": params.ship,
                    "departure_date": params.departure_date,
                    "departureDate": params.departure_date,
                },
            ),
            timeout=PER_SOURCE_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        return _json(
            {
                "error": _describe_error(source.id, exc)["error"],
                "hint": (
                    "Run cruise_check_sources to see whether the endpoint is up and "
                    "which tools it exposes."
                ),
            }
        )

    urls: list[str] = []
    for record in records:
        for value in record.values():
            if isinstance(value, str) and value.startswith("http") and value not in urls:
                urls.append(value)

    return _json(
        {
            "source": source.id,
            "tool_called": tool_name,
            "results": records,
            "booking_urls": urls,
            "disclosure": (
                "Links are attributed to Pixie Vacations via a referral parameter; "
                "the agency earns a commission. Supplier pricing is unchanged. "
                "Tell the user this before they click."
            ),
        }
    )


def main() -> None:
    """Run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
