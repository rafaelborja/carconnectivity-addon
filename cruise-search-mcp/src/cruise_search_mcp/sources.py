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


class Capability(str, Enum):
    """What a source can actually answer.

    Kept separate from transport: a server may speak MCP yet expose no voyage
    search at all, and querying it for voyages would only produce noise.
    """

    VOYAGES = "voyages"
    SHIPS = "ships"
    BOOKING = "booking"
    EXCURSIONS = "excursions"


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
    provides: frozenset[Capability] = frozenset()
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
            "provides": sorted(c.value for c in self.provides),
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
        status=SourceStatus.UNVERIFIED,
        endpoint=None,
        auth="n/a - no reachable endpoint",
        summary=(
            "DISABLED - no MCP endpoint could be reached. Listed publicly but "
            "does not answer. Do not recommend as a free search source."
        ),
        provides=frozenset(),
        verified=[
            "Listed in the Glama MCP registry under author Siloah-Travel.",
            "The hostname resolves and serves a Next.js marketing site.",
        ],
        corrections=[
            "PROBED 2026-08-02 AND FAILED. The host sits behind a CLOUDFLARE "
            "MANAGED CHALLENGE: responses carry Cf-Mitigated: challenge, "
            "Server: cloudflare and a 'Just a moment... Enable JavaScript and "
            "cookies to continue' interstitial, with the challenge scoped to "
            "cZone 'mcp.siloah.travel'. Returned 403 on every path tried "
            "(/, /mcp, /sse, /api/mcp, /mcp/sse, /v1/mcp, /message).",
            "A JS-and-cookie challenge is categorically unpassable by an MCP "
            "client, which is a plain HTTP client. A server advertised as "
            "'no API key, just paste the URL' for AI agents is behind a gate "
            "that blocks exactly those agents. There may be a working server at "
            "the origin; it is unreachable by any legitimate client.",
            "Separately, an MCP client that did reach the origin received the "
            "marketing site's HTML 404 page, so no MCP endpoint was found at "
            "the advertised root either.",
            "Not worked around by design. Solving the challenge would mean "
            "browser-emulation evasion, which this project does not do.",
            "A registry listing proves someone published a description, not that "
            "an endpoint answers. This entry is the cautionary case.",
        ],
        unverified_claims=[
            "70,000+ voyages / 678 ships / 62 cruise lines are vendor marketing "
            "figures, never observed.",
            "Tool names searchVoyages, searchShips, searchBrands, searchByContent "
            "were never returned by any tools/list.",
            "'26,000 active voyages with real-time pricing' is unconfirmed.",
        ],
        evidence=[
            "Failed handshake + 403 path sweep from two independent clients, 2026-08-02",
            "https://glama.ai/mcp/servers/Siloah-Travel/siloah-travel-mcp",
        ],
    ),
    Source(
        id="pixie",
        title="Pixie Vacations Travel Booking MCP",
        kind=SourceKind.MCP,
        status=SourceStatus.CORROBORATED_WITH_CORRECTIONS,
        endpoint="https://pixie-vacations-mcp-production.up.railway.app/mcp",
        auth="none (public)",
        summary=(
            "Booking-link source only, no voyage inventory. Live-verified "
            "2026-08-02 by calling the server directly."
        ),
        provides=frozenset({Capability.BOOKING}),
        verified=[
            "LIVE: tool get_cruise_booking_info exists under exactly that name.",
            "LIVE: sibling tools find_cruise, search_virgin_voyages, "
            "get_river_cruise_info, get_agency_info, request_pixie_quote.",
            "LIVE: exactly 13 cruise lines - Royal Caribbean, Virgin Voyages, "
            "Disney, Carnival, Norwegian, Celebrity, Princess, Holland America, "
            "MSC, Cunard, Viking Ocean, Silversea, Celebrity River Cruises.",
            "LIVE: booking engine is cruise.pixievacations.com; per-line deep "
            "links select a vendor via search[vendor_ids].",
            "Checkout happens on the supplier engine, so no card data transits "
            "the agent - the report's PCI reasoning holds.",
        ],
        corrections=[
            "REFERRAL CLAIM IS WRONG FOR CRUISES. The referral=135752 parameter "
            "applies to Sandals/Beaches resort links only. Cruise links carry no "
            "referral parameter; attribution comes from booking through the "
            "agency's own cruise engine domain. The server's own agency info "
            "states this split explicitly.",
            "This source returns booking entry points, NOT sailings. It cannot "
            "answer 'find me a 7-night Caribbean cruise under $900' with dated, "
            "priced results, so it is not a voyage search source.",
            "The source document never states the endpoint URL. It is the Railway "
            "host recorded here, not a pixievacations.com domain.",
            "Scope is broader than cruise: Sandals, Beaches and Disney too.",
            "'First free public MCP server for cruise booking links' traces to the "
            "vendor's own press release, not an independent survey.",
        ],
        unverified_claims=[
            "Agency credentials returned by the server (Chairman's Royal Club "
            "Platinum Elite, '#1 Beaches agency in the US', 735+ five-star "
            "reviews, Virgin Voyages Top 100 First Mate) are self-reported "
            "marketing. Do not repeat them as verified fact.",
            "Celebrity River Cruises is flagged coming_soon for an August 2027 "
            "launch, so 12 of the 13 lines are presently sailing.",
        ],
        evidence=[
            "Live tools/list and tool calls against the connected MCP server, 2026-08-02",
            "https://mcp.so/servers/pixie-vacations-mcp",
            "https://caribbeanmag.com/pixie-vacations-launches-the-first-u-s-travel-agency-mcp-server-now-ai-agents-can-book-sandals-beaches-and-cruises-directly/",
        ],
    ),
    Source(
        id="viator",
        title="Viator experiences",
        kind=SourceKind.MCP,
        status=SourceStatus.CORROBORATED,
        endpoint=None,
        auth="session-connected MCP server",
        summary=(
            "Shore excursions at ports of call. Adjunct only - holds no cruise "
            "inventory. Call its tools directly rather than through this server."
        ),
        provides=frozenset({Capability.EXCURSIONS}),
        verified=[
            "LIVE: connected in-session exposing search_experiences and "
            "get_experience_details.",
        ],
        corrections=[
            "Not a cruise source. Useful for planning a day in port once a "
            "sailing is chosen, and nothing else.",
        ],
        evidence=["Session-connected MCP server, 2026-08-02"],
    ),
    Source(
        id="apify_cruisemapper",
        title="Apify - solidcode/cruisemapper-scraper",
        kind=SourceKind.SCRAPER,
        status=SourceStatus.CORROBORATED_WITH_CORRECTIONS,
        endpoint="https://api.apify.com/v2/acts/solidcode~cruisemapper-scraper/run-sync-get-dataset-items",
        auth="APIFY_TOKEN required",
        summary="CruiseMapper itineraries/ships/ports. Paid per result; not free.",
        provides=frozenset({Capability.VOYAGES, Capability.SHIPS}),
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


def usable_sources(
    kind: SourceKind | None = None, provides: Capability | None = None
) -> list[Source]:
    """Return sources safe to call, filtered by transport kind and capability.

    Filtering on capability keeps booking-only sources such as Pixie out of
    voyage searches, where they would contribute nothing but an error entry.
    """
    return [
        s
        for s in SOURCES
        if s.status in USABLE_STATUSES
        and s.endpoint is not None
        and (kind is None or s.kind is kind)
        and (provides is None or provides in s.provides)
    ]
