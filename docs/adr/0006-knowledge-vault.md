# 0006. Knowledge vault: tiered sources, content-addressed snapshots, local hybrid search

- Status: accepted
- Date: 2026-10-06
- Phase: 1d item 1 (SPEC 5a)

## Context

Every statement Lighthouse makes about the rules (criteria wording, fees, forms, timelines, standards of
proof) must cite a source fetched within its freshness window. Item 2 (rule-check) needs a corpus it can match
claims against, with exact text and dates; item 3 needs the agent to search it first.

## Decision

1. **Manifest in the app repo** (`vault/sources.yaml`, shipped in the wheel): URLs, tiers (1 primary law and
   agency, 2 adjudication, 3 secondary), a fact kind per source, and the freshness registry `ttl_days`
   (fees, form editions and processing times 7 days, the Visa Bulletin monthly, regulations 30, case law
   365). A workspace can add or override sources in its own `vault/sources.yaml`. Long sections are cut to the
   paragraph that matters with start / end regexes (8 CFR 214.2 → paragraph (o)). eCFR is read through its
   versioner API (`{ecfr_date}` resolves to the latest issue date); the HTML site answers automated clients
   with a "Request Access" page.
2. **Fetch through the shared public-web guard** (`lighthouse_gc/web.py`, now also used by the agent's
   `read_page` and, next, the website connector): public http(s) hosts only, re-checked on every redirect,
   size-capped. Bot checks and maintenance pages are recognized even when served with HTTP 200 and recorded as
   *unreadable*, never stored as content. We don't disguise the client to get past bot protection. For sites
   that block it (in our tests: USCIS pages, travel.state.gov, the processing-times app), the person saves the
   page in their browser and runs `lighthouse-gc vault import <source> <file>`; the log marks it `manual`.
3. **Content-addressed snapshots in the cache** (`.lighthouse/cache/vault/snapshots/<sha>.txt.gz`, sha256 of the
   extracted text). Old snapshots are kept. Fetched content is not committed to the case repo; the small
   append-only `vault/log.jsonl` is (new, changed, unreadable, error; unchanged re-checks only bump the
   check time).
4. **Index**: the current snapshot of each source is chunked so that every chunk is an exact slice of the text
   with offsets (item 2 checks quotes character for character), and indexed in SQLite with FTS5 (bm25) and
   local embeddings, fused by reciprocal rank. The default embedder is feature hashing of unigrams and bigrams:
   offline, deterministic, no model download. It is weaker than a neural embedder at paraphrase; full-text
   search carries exact terms, and the `Embedder` interface takes a dense model later (sqlite-vec or LanceDB
   when the corpus outgrows brute force; it is ~20 sources today).
5. **Freshness** = last successful check + the kind's window. A failed or blocked fetch never refreshes a
   source, so it goes stale and item 2 will mark claims that rely on it.
6. **vault-watch** (daily 06:00): re-checks every Tier 1 source (and anything stale) and notifies (`vault`
   event) when a Tier 1 source changed, with the first changed lines. Tier 2 / 3 changes are logged, not
   notified. `vault.enabled: false` turns all vault fetching off.

## Consequences

- Outbound requests now include the public sources in the manifest (documented in the README).
- Many official pages can't be read by an automated client; they show as unreadable until imported by hand.
  That is visible on purpose: the vault guarantees every rule claim is cited and dated, not that every page
  is reachable.
- `pypdf` is a new dependency (court opinions, AAO decisions and the fee schedule are PDFs).
