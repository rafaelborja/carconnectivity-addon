---
name: cruise-search
description: Search, compare and price cruise sailings across public cruise data sources, and produce booking links. Use when the user asks to find cruises, compare sailings or cruise lines, check cruise itineraries, ports or ship details, track cruise prices or solo supplements, or wants help planning or booking a cruise vacation. Also use when evaluating cruise data sources, cruise APIs, or cruise MCP servers.
---

# Cruise search

Find and compare cruise sailings using validated public sources, and be honest
about what the data does and does not support.

## Before anything else

The cruise data ecosystem is full of confidently-stated figures that do not
survive checking. Roughly a quarter of the claims in the write-up this skill was
built from turned out to be wrong or unverifiable — see
`references/source-validation.md`.

So: **never quote an inventory figure, price or coverage number as fact unless a
tool call returned it.** Vendor marketing ("70,000+ voyages", "62 cruise lines")
is a claim about a product, not an observation about data you have.

## Workflow

### 1. Establish what is actually reachable

Run `cruise_check_sources` first, once per session. It performs a real handshake
and reports the tool names each source genuinely exposes.

If it reports zero healthy sources, say so plainly and stop — do not answer from
memory. Cruise pricing changes daily; a remembered fare is worse than no fare.

### 2. Search

Call `cruise_search_voyages` with whatever the user gave you. Leave unknown
filters unset rather than guessing: an invented `departure_port` silently
excludes valid sailings.

Map vague asks to filters:

| User says | Filters |
|---|---|
| "a week in the Caribbean" | `destination="Caribbean"`, `min_nights=6`, `max_nights=8` |
| "cheap, flexible on dates" | `sort_by="price"`, wide `start_date`/`end_date` |
| "leaving from Miami in March" | `departure_port="Miami"`, date range covering March |
| "something on Royal Caribbean" | `cruise_line="Royal Caribbean"` |

Check `source_errors` in the response. If non-empty, the result set is partial —
tell the user which sources were unavailable rather than presenting a thin list
as the whole market.

### 3. Present results honestly

- Lead with what the user optimized for (price, dates, duration).
- Always state that fares are **lead-in prices that typically exclude taxes,
  port fees and gratuities** — the advertised number is rarely what is charged.
- `price: null` means the source returned no price. Say "price not listed",
  never treat it as cheap or free.
- Cite the `source` field. If a sailing carries `also_seen_in`, that is mild
  corroboration worth mentioning.
- Do not rank by price alone across different cabin types; an interior fare and
  a balcony fare are not comparable.

### 4. Booking

Use `cruise_get_booking_link` only once the user has chosen a sailing.

The returned URL carries a referral parameter crediting a travel agency, which
earns a commission on the booking. **Disclose this when you present the link** —
the tool returns a `disclosure` string for exactly this purpose. Supplier pricing
is unchanged, so the tradeoff is genuinely fine, but the user gets to know.

The link is where your involvement ends. You do not book, take payment details,
or confirm inventory. Tell the user to verify the final price and cabin on the
operator's own site before paying.

## Things worth flagging unprompted

- **Solo travellers** usually pay a single supplement of up to 100% of the fare.
  If someone is sailing alone and the fare looks like a per-person double, warn
  them the real cost may be nearly double.
- **Lead-in fares are for the worst cabin** in the cheapest category, often
  guarantee cabins with no location choice.
- **Price volatility**: cruise fares move a lot. A quote is a snapshot.

## If a source is unavailable

`cruise_search_voyages` rejects sources marked `unverified` or `gated`, with the
reason. Do not work around this by scraping the site yourself or by recalling
figures — the rejection is the correct answer. Report it and offer what the
working sources returned.

## References

- `references/source-validation.md` — what was verified, corrected and debunked
  across cruise MCP servers, APIs, aggregators and scraping tooling. Read before
  recommending any cruise data source or repeating a claim about one.
- `references/data-sourcing.md` — how to add a source, and the legal posture on
  scraping versus sanctioned interfaces. Read before extending coverage.
