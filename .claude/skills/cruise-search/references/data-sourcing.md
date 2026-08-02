# Extending cruise data coverage

How to add a source to `cruise-search-mcp`, and where the legal lines fall.
Read `source-validation.md` first — several widely-cited sources do not exist.

## Adding a source

1. **Verify it exists before writing code.** Independent evidence: a registry
   listing, docs, press that is not the vendor's own. If you cannot find any,
   add it with `status=UNVERIFIED` and no endpoint. That is a real outcome, not
   a failure — `cruisefeed` and `winwin` are in the registry for this reason.

2. **Add a `Source` entry** in `src/cruise_search_mcp/sources.py`, splitting
   claims honestly across `verified`, `corrections` and `unverified_claims`.
   Put evidence URLs in `evidence`. Only `CORROBORATED` and
   `CORROBORATED_WITH_CORRECTIONS` sources with an endpoint are ever called.

3. **MCP sources need no new code.** `McpSourceProvider` discovers tools via
   `tools/list` and matches them by intent keyword, so a new MCP endpoint works
   as soon as it is in the registry. Extend `INTENT_KEYWORDS` in `providers.py`
   only if the server names tools unusually.

4. **REST sources need a provider.** Follow `ApifyProvider`: constructor takes
   the `Source`, credentials come from the environment, and a missing credential
   raises `ProviderError` with instructions rather than failing obscurely.

5. **Map fields, do not rewrite them.** Add upstream key names to
   `FIELD_ALIASES` in `normalize.py`. Unmapped keys survive under `raw`, so
   partial mapping degrades gracefully.

6. **Test offline.** Extend the fake upstream in `tests/test_server.py`. Never
   add a test that requires network.

## Verifying tool names

Documented tool names are unreliable. Use `cruise_check_sources`, which reports
what a server actually exposes. If a name is stable and you want to pin it, pass
`override` to `call_intent` rather than editing the keyword table.

## Legal posture

The server deliberately uses sanctioned interfaces only. The distinction that
matters:

**Generally defensible** — reading public pages and calling public endpoints.
*hiQ v. LinkedIn* (9th Cir.) held that scraping publicly accessible pages is
unlikely to be "without authorization" under the CFAA, consistent with *Van
Buren*.

**Not the same thing** — defeating Cloudflare Turnstile or DataDome,
reverse-engineering a mobile app's request signing, bypassing SSL pinning with
Frida. These circumvent access controls a provider deliberately erected. Whatever
the CFAA outcome, they implicate other exposure and are outside this server's
scope.

Three caveats the enthusiastic write-ups omit:

- hiQ was a **preliminary injunction**, not a final merits ruling.
- **hiQ still lost.** The case resolved in late 2022 with hiQ found to have
  breached LinkedIn's User Agreement. CFAA safety did not save the business —
  breach of contract ended it. Nearly every cruise operator's TOS prohibits
  automated collection.
- CFAA is not the only theory: copyright, DMCA §1201, trespass to chattels, and
  for EU-facing data the **EU Database Directive** *sui generis* right, which
  has no US equivalent. MSC, Costa and TUI are EU-facing.

**Practical rule:** if acquiring the data requires defeating a protection
someone built on purpose, it does not belong in this server. Add the operator's
official affiliate or agency feed instead, or ask the user to obtain access.

## Cost awareness

Not every source is free. Apify's CruiseMapper actor bills **$1.50 per 1,000
results**, with free accounts capped at 5 results per run. Record real costs in
the `Source.auth` and `summary` fields so an agent can weigh them before
fanning out a query.
