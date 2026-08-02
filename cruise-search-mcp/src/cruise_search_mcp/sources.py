"""Registry of cruise data sources with per-claim validation status.

Every entry records what was *actually* verified versus what is only a vendor
marketing claim. Tools surface this to the agent so it never presents an
unverified inventory count as fact.

Validation was performed on 2026-08-02 via public web search. Live endpoint
probing was not possible from the authoring environment (egress policy denied
CONNECT to these hosts), so no entry claims a successful handshake. Run
``cruise_check_sources`` to establish reachability from your own machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceStatus(str, Enum):
    """How well a source's existence and description hold up to checking."""

    #: Listed in independent public registries/press; description broadly matches.
    CORROBORATED = "corroborated"
    #: Exists, but the document's description contains errors (see ``corrections``).
    CORROBORATED_WITH_CORRECTIONS = "corroborated_with_corrections"
    #: No independent evidence found. Treat as non-existent until proven otherwise.
    UNVERIFIED = "unverified"
    #: Requires a commercial agreement; not usable for free/self-serve prototyping.
    GATED = "gated"


class SourceKind(str, Enum):
    """Transport/integration shape, which decides how a provider talks to it."""

    MCP = "mcp"
    REST = "rest"
    SCRAPER = "scraper"


@dataclass(frozen=True)
class Source:
    """A single upstream cruise data source and its validation record."""

    id: str
    title: str
    kind: SourceKind
    status: SourceStatus
    endpoint: str | None
    auth: str
    summary: str
    verified: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    unverified_claims: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for tool output."""
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "status": self.status.value,
            "endpoint": self.endpoint,
            "auth": self.auth,
            "summary": self.summary,
            "verified": list(self.verified),
            "corrections": list(self.corrections),
            "unverified_claims": list(self.unverified_claims),
            "evidence": list(self.evidence),
        }


SOURCES: tuple[Source, ...] = (
    Source(
        id="siloah",
        title="Siloah Travel MCP",
        kind=SourceKind.MCP,
        status=SourceStatus.CORROBORATED,
        endpoint="https://mcp.siloah.travel",
        auth="none (public, read-only)",
        summary="Public cruise inventory MCP server. Primary free search source.",
        verified=[
            "Listed in the Glama MCP registry under author Siloah-Travel.",
            "Advertised as requiring no API key and no installation.",
            "Advertises RAG-backed knowledge search over ships, cabins and ports.",
        ],
        unverified_claims=[
            "70,000+ voyages / 678 ships / 62 cruise lines are vendor marketing "
            "figures, not independently audited.",
            "Exact tool names (searchVoyages, searchShips, searchBrands, "
            "searchByContent) were not confirmed against a live tools/list.",
            "'26,000 active voyages with real-time pricing' is unconfirmed.",
        ],
        evidence=[
            "https://glama.ai/mcp/servers/Siloah-Travel/siloah-travel-mcp",
            "https://www.altexsoft.com/blog/mcp-servers-travel/",
        ],
    ),
    Source(
        id="pixie",
        title="Pixie Vacations Travel Booking MCP",
        kind=SourceKind.MCP,
        status=SourceStatus.CORROBORATED_WITH_CORRECTIONS,
        endpoint="https://pixie-vacations-mcp-production.up.railway.app/mcp",
        auth="none (public)",
        summary="Returns agency-attributed booking URLs. Booking link source only.",
        verified=[
            "Published in the mcp.so registry as 'pixie-vacations-mcp'.",
            "Covers 13 cruise lines routed via pixievacations.com/cruise/.",
            "Referral parameter ?referral=135752 credits the agency.",
            "Checkout happens on the supplier site, so no card data transits the "
            "agent - the report's PCI reasoning holds.",
        ],
        corrections=[
            "The source document never states the endpoint URL. It is the Railway "
            "host recorded here, not a pixievacations.com domain.",
            "Scope is broader than cruise: Sandals and Beaches resorts too.",
            "'First free public MCP server for cruise booking links' traces to the "
            "vendor's own press release, not an independent survey.",
        ],
        unverified_claims=[
            "The tool name get_cruise_booking_info was not confirmed live.",
        ],
        evidence=[
            "https://mcp.so/servers/pixie-vacations-mcp",
            "https://caribbeanmag.com/pixie-vacations-launches-the-first-u-s-travel-agency-mcp-server-now-ai-agents-can-book-sandals-beaches-and-cruises-directly/",
        ],
    ),
    Source(
        id="apify_cruisemapper",
        title="Apify - solidcode/cruisemapper-scraper",
        kind=SourceKind.SCRAPER,
        status=SourceStatus.CORROBORATED_WITH_CORRECTIONS,
        endpoint="https://api.apify.com/v2/acts/solidcode~cruisemapper-scraper/run-sync-get-dataset-items",
        auth="APIFY_TOKEN required",
        summary="CruiseMapper itineraries/ships/ports. Paid per result; not free.",
        verified=[
            "The actor exists on Apify with itinerary, ship and port modes.",
            "Extracts itinerary stops with dates, ship specs and port schedules.",
        ],
        corrections=[
            "Pricing is $1.50 per 1,000 results on the actor page, not the "
            "'$1.80 to $2.00' the report states.",
            "Free Apify accounts are capped at 5 results per run, so this is not "
            "a free data source in any practical sense.",
        ],
        unverified_claims=[
            "The exact input field names used here are inferred from the actor "
            "listing. Call cruise_check_sources and read the actor's input schema "
            "before relying on them.",
            "'23 global regions' for the destination enum is unconfirmed.",
        ],
        evidence=["https://apify.com/solidcode/cruisemapper-scraper"],
    ),
    Source(
        id="cruisefeed",
        title="CruiseFeed.io",
        kind=SourceKind.REST,
        status=SourceStatus.UNVERIFIED,
        endpoint=None,
        auth="unknown",
        summary="DISABLED - no evidence this service exists. Do not rely on it.",
        verified=[],
        unverified_claims=[
            "Targeted search returned no CruiseFeed.io product, docs, pricing or "
            "press. Other cruise aggregators surfaced instead.",
            "'Normalizes 60+ cruise lines via REST and bulk CSV' is uncorroborated.",
        ],
        evidence=[],
    ),
    Source(
        id="winwin",
        title="WinWin.travel MCP affiliate gateway",
        kind=SourceKind.MCP,
        status=SourceStatus.UNVERIFIED,
        endpoint=None,
        auth="unknown",
        summary="DISABLED - commission tiers could not be corroborated.",
        verified=[],
        unverified_claims=[
            "The 4%/10% tiered commission structure returned no matching source; "
            "searches surfaced an unrelated iGaming affiliate programme.",
            "'3 million hotels with real-time booking via MCP' is uncorroborated.",
        ],
        evidence=[],
    ),
    Source(
        id="amadeus_cruise",
        title="Amadeus Cruise Portal",
        kind=SourceKind.REST,
        status=SourceStatus.GATED,
        endpoint="https://amadeus.com/en/travel-sellers/products/amadeus-cruise-portal",
        auth="commercial travel-seller agreement",
        summary="Real product, but not reachable from the free Self-Service tier.",
        verified=[
            "Amadeus Cruise Portal exists and advertises 30+ bookable cruise lines "
            "(100+ searchable).",
        ],
        corrections=[
            "The report's '33 companies' is more precise than Amadeus's own "
            "'30+ bookable' wording.",
            "Cruise is NOT part of the free Amadeus Self-Service catalogue, which "
            "covers air, hotel and destination content. The report's table implies "
            "self-serve sandbox access to cruise inventory; that is wrong.",
            "Beeceptor is an unaffiliated third-party HTTP mocking service. Using "
            "it returns fixtures you configure - it is not an Amadeus sandbox and "
            "validates nothing about real Amadeus behaviour.",
        ],
        evidence=[
            "https://amadeus.com/en/travel-sellers/products/amadeus-cruise-portal"
        ],
    ),
)

SOURCES_BY_ID: dict[str, Source] = {s.id: s for s in SOURCES}

#: Sources a provider may actually call. Unverified ones are excluded by design.
USABLE_STATUSES = frozenset(
    {SourceStatus.CORROBORATED, SourceStatus.CORROBORATED_WITH_CORRECTIONS}
)


def usable_sources(kind: SourceKind | None = None) -> list[Source]:
    """Return sources safe to call, optionally filtered by transport kind."""
    return [
        s
        for s in SOURCES
        if s.status in USABLE_STATUSES
        and s.endpoint is not None
        and (kind is None or s.kind is kind)
    ]
