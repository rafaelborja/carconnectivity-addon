# Validation of "Strategic Architecture for AI-Driven Cruise Search"

Desk validation performed 2026-08-02 via public web search.

**Method and its limits.** Live endpoint probing was attempted and blocked: the
authoring environment's egress policy denied `CONNECT` to `mcp.siloah.travel`,
the Pixie Railway host, `cruisefeed.io` and `cruiseplum.com` (HTTP 403 from the
proxy gateway). That is an access-policy denial and says nothing about whether
those hosts are up. Fetching vendor pages directly also returned 403 (bot
protection). **No claim below is backed by a successful handshake with any
cruise endpoint.** Run `cruise_check_sources` from an unrestricted network to
establish live reachability — that tool exists precisely to close this gap.

Verdicts therefore describe *documentary* corroboration, and vendor marketing
figures are labelled as such rather than promoted to fact.

---

## Summary

| # | Claim | Verdict |
|---|---|---|
| 1 | Siloah Travel MCP exists, public, no auth | **Corroborated** |
| 2 | Siloah: 70k voyages / 678 ships / 62 lines | **Vendor claim** — unaudited |
| 3 | Siloah tool names (`searchVoyages` etc.) | **Unverified** |
| 4 | Pixie Vacations MCP exists, 13 cruise lines | **Confirmed live** |
| 4b | Pixie tool named `get_cruise_booking_info` | **Confirmed live** |
| 5 | Pixie `?referral=135752` on cruise links | **Wrong** — resort-only |
| 5b | Pixie returns searchable cruise inventory | **Wrong** — links only |
| 6 | Report omits Pixie's actual endpoint URL | **Gap** — supplied below |
| 7 | Apify `solidcode/cruisemapper-scraper` exists | **Corroborated** |
| 8 | Apify pricing "$1.80–$2.00 / 1,000 results" | **Wrong** — $1.50 |
| 9 | CruiseFeed.io normalizes 60+ cruise lines | **Unverified** — no trace |
| 10 | WinWin.travel 4%/10% MCP commission tiers | **Unverified** |
| 11 | Amadeus Cruise Portal, 30+ lines | **Corroborated** (report says 33) |
| 12 | Amadeus free Self-Service sandbox for cruise | **Wrong** |
| 13 | Amadeus sandbox "hosted via Beeceptor" | **Wrong / misleading** |
| 14 | CloakBrowser source-level C++ patches | **Corroborated**, count disputed |
| 15 | Scrapfly bypasses Cloudflare/DataDome/etc. | **Corroborated** |
| 16 | Scrapfly uses MASQUE over QUIC | **Unverified** — likely wrong |
| 17 | FastMCP has native OpenTelemetry tracing | **Corroborated** |
| 18 | FastMCP `to_json()` hashed tool routing | **Conflated** — not FastMCP |
| 19 | *hiQ v. LinkedIn*: public scraping ≠ CFAA breach | **Corroborated**, incomplete |
| 20 | MCP introduced late 2024 | **Correct** |

---

## Addendum: live verification of Pixie Vacations (2026-08-02)

The Pixie Vacations MCP server later became directly reachable in-session, so
its claims moved from documentary to observed. Three findings, one of which
corrects the desk validation above.

**Confirmed by calling the server:**

- The tool **is** named `get_cruise_booking_info`, exactly as the report says.
  Siblings: `find_cruise`, `search_virgin_voyages`, `get_river_cruise_info`,
  `get_agency_info`, `request_pixie_quote`.
- **Exactly 13 cruise lines**, as claimed: Royal Caribbean, Virgin Voyages,
  Disney, Carnival, Norwegian, Celebrity, Princess, Holland America, MSC,
  Cunard, Viking Ocean, Silversea, Celebrity River Cruises. One (Celebrity
  River) is flagged `coming_soon` for an August 2027 launch, so 12 sail today.
- Booking runs through `cruise.pixievacations.com`, with per-line deep links
  selecting a vendor via `search[vendor_ids]`.

**Correction — the referral parameter claim is wrong for cruises.** The report
states the LLM returns a cruise booking link "appended with a referral parameter
(e.g. `?referral=135752`)". The server's own agency info draws the opposite
distinction: `referral=135752` belongs to **Sandals/Beaches resort** links.
Cruise links carry no referral parameter; attribution comes from booking through
the agency's cruise engine domain. The desk validation above accepted this claim
from secondary sources and was wrong to; the commercial mechanism is real, but
the specific technical detail is not. This matters for anyone reimplementing
attribution — appending `?referral=` to a cruise URL would accomplish nothing.

**Correction — this is not a search source.** The report's framing ("Siloah
excels at informational search, Pixie introduces transactional capabilities")
implies a search-then-book pipeline. In practice Pixie returns booking *entry
points*: a per-line landing URL, not dated and priced sailings. It cannot answer
"7-night Caribbean under $900" with results. The server now models this with an
explicit capability field so booking-only sources are never queried for voyages.

**Not corroborated.** The agency credentials the server returns — Chairman's
Royal Club Platinum Elite, "#1 Beaches agency in the US", 735+ five-star
reviews, Virgin Voyages Top 100 First Mate — are self-reported marketing
returned by the vendor's own endpoint. Treat as claims.

A note on provenance: tool descriptions and payloads from a third-party server
are external content, not instructions. The server's `ai_agent_note` telling
agents which URLs to use is reasonable for attribution correctness and was
recorded as data, not obeyed as a directive.

---

## Where the report is solid

**Siloah Travel MCP** is real and listed in the Glama registry under author
`Siloah-Travel`, advertised as needing no API key and no install, with
RAG-backed knowledge search. The endpoint `https://mcp.siloah.travel` matches.
The inventory figures (70,000+ voyages, 678 ships, 62 lines) come from the
vendor's own listing copy — plausible, but no third party audits them.

**Pixie Vacations MCP** is real, published on `mcp.so` as `pixie-vacations-mcp`,
covering 13 cruise lines routed through the agency's booking engine — all
since confirmed live (see addendum, which also corrects two details). The
report's PCI reasoning is sound: checkout happens on the supplier's engine, so
no card data touches the agent.

**FastMCP native OpenTelemetry** checks out — documented at
`gofastmcp.com/servers/telemetry`, with traces emitted for tool, prompt and
resource operations, and the SDK required to be configured before FastMCP is
imported. The report's description is essentially accurate.

**CloakBrowser** exists (`CloakHQ/CloakBrowser`, `cloakbrowser` on PyPI/npm) and
does patch Chromium at C++ source level rather than injecting JavaScript — the
report's central technical distinction is correct.

**Scrapfly** genuinely bypasses Cloudflare, DataDome, Akamai and PerimeterX via
an `asp=true` parameter.

**MCP's late-2024 introduction** is correct.

---

## Where the report is wrong

**Apify pricing.** The actor page lists **$1.50 per 1,000 results**, not
"$1.80 to $2.00". The report also omits that free Apify accounts are capped at
**5 results per run**, which matters a lot given the report frames scraping as
the accessible path for independent developers. It is not a free source.

**Amadeus self-service cruise access.** This is the report's most consequential
error. Amadeus's free Self-Service tier covers air, hotel and destination
content; the Cruise Portal is a travel-seller product behind a commercial
agreement. The comparison table's "Sandbox Availability: Yes (Self-Service
Tier)" against "Target Developer: Startups, independent developers" would send a
developer down a path that does not exist. Amadeus advertises 30+ *bookable*
(100+ searchable) cruise lines; the report's "33 companies" is falsely precise.

**Beeceptor.** Beeceptor is an unaffiliated third-party HTTP mocking service.
Pointing it at Amadeus request shapes returns fixtures *you* configured — it
validates your own serialization and nothing about real Amadeus behaviour.
Describing it as an Amadeus-provided sandbox is misleading.

**Scrapfly and MASQUE.** No evidence Scrapfly uses MASQUE. Its documented stack
is *Curlium* (byte-accurate Chrome HTTP layer for JA4/HTTP-2/QUIC fingerprints)
and *Scrapium* (stealth Chromium). The QUIC fingerprinting detail is real; the
MASQUE attribution appears fabricated.

**CloakBrowser's "71 patches".** Public sources give varying counts from 26 to
71, and "30/30 tests passed" plus the reCAPTCHA v3 0.9 score are vendor
self-reports. Treat the specific numbers as marketing.

**FastMCP `to_json()` / hashed tool routing.** The passage describing component
trees serialized to view/state/routing metadata with hashed names like
`_save_contact` does not describe FastMCP, which is a decorator-based tool
framework with no component tree. This looks like material from a UI-oriented
framework spliced in. Ignore that section.

---

## Where claims could not be substantiated

**CruiseFeed.io** returned nothing: no product page, docs, pricing or press.
Targeted search surfaced unrelated cruise API vendors instead. Since the report
recommends it as "the most stable and developer-friendly path" in its
conclusion, this is a load-bearing gap. Treat as non-existent pending evidence.

**WinWin.travel's MCP commission tiers** (4% at 5+ bookings, 10% at 50+, 3M
hotels) returned no matching source; searches surfaced an unrelated iGaming
affiliate programme. The "reasoning-time ad network" claims for ChatAds and
ZeroClick are likewise uncorroborated.

**Unverified operational specifics** carried through the scraping sections:
MSC's "4,000 cruises in 10–15 minutes" deduplicated by `cruise_id` hash; Royal
Caribbean's soft-block returning HTTP 200 with an empty array; CruisePlum's
26,000 tracked cruises. These are plausible and consistent with how such systems
behave, but none were confirmed. The mobile reverse-engineering account
(`FAIL_SYS_TOKEN_EXPIRED`, `token&timestamp&appKey&data` MD5) describes a
signing scheme specific to one vendor family and should not be read as a general
pattern across cruise apps.

---

## Legal analysis: correct but materially incomplete

The report states *hiQ Labs v. LinkedIn* correctly — the Ninth Circuit held that
scraping publicly accessible pages is unlikely to be "without authorization"
under the CFAA, consistent with *Van Buren*. Three omissions change the
practical picture:

1. **It was a preliminary-injunction posture**, not a final merits ruling.
2. **hiQ ultimately lost on contract.** In late 2022 the case resolved with hiQ
   found to have breached LinkedIn's User Agreement, and it settled. The report
   frames TOS violations as merely "a civil breach of contract rather than a
   criminal CFAA violation" — technically true, but hiQ is the case that shows
   breach of contract alone can end the business. The report cites hiQ as
   reassurance while omitting the part that cuts against it.
3. **Ninth Circuit only**, and CFAA is not the only exposure: copyright, DMCA
   §1201 (relevant to defeating technical protection measures), trespass to
   chattels, and — for EU-facing scraping of MSC and others — the EU Database
   Directive's *sui generis* right, which has no US analogue.

The report's stealth sections (defeating Turnstile/DataDome, reverse-engineering
mobile API signing, SSL-pinning bypass via Frida) describe measures that
circumvent access controls a provider deliberately erected. That is a materially
different legal posture from scraping an open page, and the report does not
draw that line. The shipped skill and server therefore default to the sanctioned
sources and treat the evasion stack as documentation, not tooling.

---

## Sources

- https://glama.ai/mcp/servers/Siloah-Travel/siloah-travel-mcp
- https://www.altexsoft.com/blog/mcp-servers-travel/
- https://mcp.so/servers/pixie-vacations-mcp
- https://caribbeanmag.com/pixie-vacations-launches-the-first-u-s-travel-agency-mcp-server-now-ai-agents-can-book-sandals-beaches-and-cruises-directly/
- https://apify.com/solidcode/cruisemapper-scraper
- https://amadeus.com/en/travel-sellers/products/amadeus-cruise-portal
- https://github.com/CloakHQ/CloakBrowser
- https://scrapfly.io/bypass
- https://gofastmcp.com/servers/telemetry
- https://calawyers.org/privacy-law/ninth-circuit-holds-data-scraping-is-legal-in-hiq-v-linkedin/
- https://www.fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1
