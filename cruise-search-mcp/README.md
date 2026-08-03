# cruise-search-mcp

An MCP server that searches cruise voyages across public sources, normalizes
their incompatible payloads into one shape, and — deliberately — refuses to call
sources whose existence could not be corroborated.

It was built from the claims in a research write-up on AI-driven cruise search.
Roughly a quarter of those claims did not survive checking; see
[VALIDATION.md](VALIDATION.md). The disproven sources are still present in the
registry, marked `unverified`, so an agent asking for them gets an explicit
refusal with the reason instead of silently inventing an answer.

## Why the design looks like this

Three findings from validation shaped the code:

- **Upstream tool names were never confirmed.** Nothing hard-codes
  `searchVoyages`. Providers call `tools/list` at request time and match tools by
  intent keywords, so a rename upstream does not break the server.
- **Reachability is a runtime question, not a documentation claim.** Answered
  by `cruise_check_sources`. This was not academic: the flagship "free, no-auth"
  source turned out to sit behind a Cloudflare challenge no MCP client can pass,
  and is now disabled.
- **Vendor inventory figures are unaudited.** They are returned as
  `unverified_claims`, never as facts.

## Install

```bash
cd cruise-search-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Register with Claude Code

```bash
claude mcp add cruise-search -- /absolute/path/to/.venv/bin/cruise-search-mcp
```

Or in `mcpServers` config:

```json
{
  "mcpServers": {
    "cruise-search": {
      "command": "/absolute/path/to/.venv/bin/cruise-search-mcp"
    }
  }
}
```

`APIFY_TOKEN` is effectively **required** for voyage search. Apify is the only
working voyage source: the free MCP alternative is unreachable (Cloudflare
challenge) and the remaining MCP source returns booking links only. The actor
bills **$1.50 per 1,000 results**, and free accounts are capped at 5 results per
run — so voyage search is not free. Without the token, searches return an empty
result set with an explicit error rather than failing silently.

## Tools

| Tool | Purpose |
|---|---|
| `cruise_list_sources` | Source registry with per-claim validation status |
| `cruise_check_sources` | Live handshake; reports the tool names each source *really* exposes |
| `cruise_search_voyages` | Concurrent multi-source search, normalized and deduplicated |
| `cruise_get_booking_link` | Agency-attributed booking URL, with affiliate disclosure |

Start with `cruise_check_sources`. It is the only thing here that reports
ground truth about the network.

## Behaviour worth knowing

- **Partial failure is normal.** A dead source lands in `source_errors`; the
  search still returns what the others found, with a caveat noting the result is
  partial.
- **`price: null` means unpriced, not free.** Nulls are never coerced to `0`,
  and they sort last rather than appearing as the cheapest option.
- **Duplicate sailings collapse** on (ship, departure date, nights), with the
  extra source recorded in `also_seen_in` so provenance survives.
- **Unmapped upstream fields survive** under `raw` rather than being dropped.
- **Booking links carry a referral parameter** that credits a travel agency.
  The tool returns a disclosure string; present it to the user.

## Tests

```bash
PYTHONPATH=src pytest tests -q     # 23 tests, no network required
```

A fake in-memory upstream stands in for the real servers, so the suite is
deterministic. Coverage includes alias normalization, price/night coercion,
dedup, tool-name discovery across naming conventions, schema-aware argument
filtering, graceful per-source degradation, and refusal of unverified sources.

## Scope

Read-only search and link resolution against sources that publish public
endpoints. It does not book, take payment, or hold inventory.

There is no scraping or anti-bot evasion here. The source write-up devoted
considerable space to defeating Cloudflare Turnstile, DataDome and mobile SSL
pinning; those techniques circumvent access controls a provider deliberately
erected, which is a different legal posture from reading an open page — see the
legal section of [VALIDATION.md](VALIDATION.md). This server uses the sanctioned
interfaces instead.
