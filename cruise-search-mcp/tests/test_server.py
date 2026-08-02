"""Offline tests for the cruise search MCP server.

No network is used: a fake upstream MCP server stands in for the real sources,
so the suite is deterministic and runnable in CI.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from cruise_search_mcp import normalize, providers, server
from cruise_search_mcp.providers import ProviderError, extract_records, select_tool
from cruise_search_mcp.sources import SOURCES_BY_ID, SourceStatus


# --------------------------------------------------------------------------
# Fake upstream
# --------------------------------------------------------------------------

FAKE_VOYAGES = [
    {
        "id": "V1",
        "name": "7 Night Eastern Caribbean",
        "brand": "Royal Caribbean",
        "shipName": "Wonder of the Seas",
        "departureDate": "2026-11-07",
        "duration": "7 nights",
        "departurePort": "Miami",
        "region": "Caribbean",
        "price": "$1,299 pp",
        "currency": "USD",
        "promo": "kids sail free",
    },
    {
        "id": "V2",
        "name": "3 Night Bahamas",
        "brand": "Carnival",
        "shipName": "Carnival Conquest",
        "departureDate": "2026-10-02",
        "duration": 3,
        "departurePort": "Miami",
        "region": "Caribbean",
    },
]


def build_fake_upstream() -> FastMCP:
    """An upstream that mimics a vendor's camelCase tool and envelope."""
    upstream = FastMCP("fake_upstream")

    @upstream.tool(name="searchVoyages")
    async def search_voyages(  # noqa: ANN202
        destination: str | None = None, limit: int = 25
    ) -> dict[str, Any]:
        """Return voyages in a nested envelope."""
        return {"results": FAKE_VOYAGES[:limit]}

    @upstream.tool(name="getCruiseBookingInfo")
    async def get_booking(cruise_line: str) -> dict[str, Any]:  # noqa: ANN202
        """Return a referral-tagged booking URL."""
        return {
            "results": [
                {
                    "cruise_line": cruise_line,
                    "booking_url": "https://pixievacations.com/cruise/?referral=135752",
                }
            ]
        }

    return upstream


@pytest.fixture
def patched_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every McpSourceProvider at the in-memory fake upstream."""
    upstream = build_fake_upstream()
    monkeypatch.setattr(
        providers.McpSourceProvider, "_client", lambda self: Client(upstream)
    )


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------


def test_normalize_maps_aliases_and_coerces_types() -> None:
    voyage = normalize.normalize_voyage(FAKE_VOYAGES[0], "siloah")
    assert voyage["cruise_line"] == "Royal Caribbean"
    assert voyage["ship"] == "Wonder of the Seas"
    assert voyage["nights"] == 7
    assert voyage["price"] == 1299.0
    assert voyage["source"] == "siloah"
    # Unmapped vendor fields survive rather than being dropped.
    assert voyage["raw"]["promo"] == "kids sail free"


def test_missing_price_is_none_not_zero() -> None:
    """A missing price must never be coerced to 0, which would sort as cheapest."""
    voyage = normalize.normalize_voyage(FAKE_VOYAGES[1], "siloah")
    assert voyage["price"] is None
    assert voyage["nights"] == 3


def test_merge_dedupes_same_sailing_across_sources() -> None:
    a = normalize.normalize_voyage(FAKE_VOYAGES[0], "siloah")
    b = normalize.normalize_voyage(FAKE_VOYAGES[0], "pixie")
    merged = normalize.merge_voyages([[a], [b]])
    assert len(merged) == 1
    assert merged[0]["also_seen_in"] == ["pixie"]


def test_sort_pushes_missing_prices_last() -> None:
    voyages = [
        {"price": None, "ship": "A"},
        {"price": 500.0, "ship": "B"},
    ]
    assert [v["ship"] for v in normalize.sort_voyages(voyages, "price")] == ["B", "A"]


# --------------------------------------------------------------------------
# Provider internals
# --------------------------------------------------------------------------


class _FakeTool:
    def __init__(self, name: str, schema: dict[str, Any] | None = None):
        self.name = name
        self.inputSchema = schema or {}


def test_select_tool_matches_camel_and_snake_case() -> None:
    """Tool discovery must survive upstream renames, since names are unverified."""
    for name in ("searchVoyages", "search_voyages", "cruise_voyage_search"):
        match = select_tool([_FakeTool(name)], "voyages")
        assert match is not None and match.name == name


def test_select_tool_returns_none_when_no_match() -> None:
    assert select_tool([_FakeTool("listHotels")], "voyages") is None


def test_pinned_tool_override_errors_clearly_when_absent() -> None:
    with pytest.raises(ProviderError, match="not exposed upstream"):
        select_tool([_FakeTool("searchVoyages")], "voyages", override="nope")


def test_filter_to_schema_drops_undeclared_arguments() -> None:
    schema = {"properties": {"destination": {"type": "string"}}}
    out = providers.filter_to_schema({"destination": "Alaska", "brand": "X"}, schema)
    assert out == {"destination": "Alaska"}


def test_extract_records_parses_json_embedded_in_text() -> None:
    class _Block:
        text = json.dumps({"items": [{"id": "V9"}]})

    class _Result:
        content = [_Block()]

    assert extract_records(_Result()) == [{"id": "V9"}]


# --------------------------------------------------------------------------
# Tools, end to end via in-memory client
# --------------------------------------------------------------------------


async def call(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invoke a server tool in-memory and parse its JSON payload."""
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, {"params": args or {}})
        return json.loads(result.content[0].text)


async def test_tools_are_registered() -> None:
    async with Client(server.mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert {
        "cruise_list_sources",
        "cruise_check_sources",
        "cruise_search_voyages",
        "cruise_get_booking_link",
    } <= names


async def test_list_sources_reports_validation_status() -> None:
    payload = await call("cruise_list_sources", {"include_disabled": True})
    by_id = {s["id"]: s for s in payload["sources"]}
    assert by_id["cruisefeed"]["status"] == SourceStatus.UNVERIFIED.value
    assert by_id["amadeus_cruise"]["status"] == SourceStatus.GATED.value
    # The corrected Apify price must be recorded, not the figure from the report.
    assert any("$1.50" in c for c in by_id["apify_cruisemapper"]["corrections"])


async def test_list_sources_can_hide_disabled() -> None:
    payload = await call("cruise_list_sources", {"include_disabled": False})
    assert {s["id"] for s in payload["sources"]}.isdisjoint({"cruisefeed", "winwin"})


async def test_unverified_source_is_rejected() -> None:
    """Guard against an agent talking itself into using a fabricated source."""
    with pytest.raises(Exception, match="unverified"):
        await call("cruise_search_voyages", {"sources": ["cruisefeed"]})


async def test_gated_source_is_rejected() -> None:
    with pytest.raises(Exception, match="commercial agreement"):
        await call("cruise_search_voyages", {"sources": ["amadeus_cruise"]})


async def test_unknown_source_is_rejected() -> None:
    with pytest.raises(Exception, match="Unknown source"):
        await call("cruise_search_voyages", {"sources": ["made_up"]})


async def test_search_returns_normalized_merged_results(patched_upstream: None) -> None:
    payload = await call(
        "cruise_search_voyages", {"destination": "Caribbean", "sort_by": "price"}
    )
    assert payload["count"] == 2
    assert payload["source_errors"] == []
    first = payload["voyages"][0]
    assert first["cruise_line"] == "Royal Caribbean"
    assert first["price"] == 1299.0
    assert first["source"] in {"siloah", "pixie"}
    # Priced voyage sorts ahead of the unpriced one.
    assert payload["voyages"][1]["price"] is None


async def test_search_applies_local_night_filters(patched_upstream: None) -> None:
    payload = await call("cruise_search_voyages", {"min_nights": 5})
    assert [v["nights"] for v in payload["voyages"]] == [7]


async def test_search_degrades_when_a_source_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One dead source must not take down the whole search."""

    def boom(self: Any) -> Any:
        raise ConnectionError("upstream down")

    monkeypatch.setattr(providers.McpSourceProvider, "_client", boom)
    payload = await call("cruise_search_voyages", {})
    assert payload["voyages"] == []
    assert payload["source_errors"]
    assert all(not e["ok"] for e in payload["source_errors"])
    assert any("partial" in c for c in payload["caveats"])


async def test_check_sources_reports_real_tool_names(patched_upstream: None) -> None:
    payload = await call("cruise_check_sources", {})
    assert payload["healthy"] == payload["checked"] > 0
    assert "searchVoyages" in payload["results"][0]["tools"]


async def test_check_sources_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Any) -> Any:
        raise ConnectionError("dns failure")

    monkeypatch.setattr(providers.McpSourceProvider, "_client", boom)
    payload = await call("cruise_check_sources", {})
    assert payload["healthy"] == 0
    assert "dns failure" in payload["results"][0]["error"]


async def test_booking_link_includes_referral_disclosure(patched_upstream: None) -> None:
    payload = await call("cruise_get_booking_link", {"cruise_line": "Carnival"})
    assert payload["tool_called"] == "getCruiseBookingInfo"
    assert any("referral=135752" in u for u in payload["booking_urls"])
    assert "commission" in payload["disclosure"]


async def test_booking_link_error_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Any) -> Any:
        raise ConnectionError("refused")

    monkeypatch.setattr(providers.McpSourceProvider, "_client", boom)
    payload = await call("cruise_get_booking_link", {"cruise_line": "Carnival"})
    assert "error" in payload
    assert "cruise_check_sources" in payload["hint"]


def test_apify_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    provider = providers.ApifyProvider(SOURCES_BY_ID["apify_cruisemapper"], token=None)
    with pytest.raises(ProviderError, match="APIFY_TOKEN"):
        import asyncio

        asyncio.run(provider.run({}))
