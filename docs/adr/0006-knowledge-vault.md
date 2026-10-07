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

### 7. rule-check gate (Phase 1d item 2)

- **What is checked:** every final agent answer, every published briefing, and the agent-written text bound
  for petition-facing records (evidence title and summary, a letter writer's credentials, letter
  credentials / asks updates).
- **Finding candidates:** sentences that may state a rule are found with the manifest's `rule_hints`
  (no model call when none match).
- **Backup:** sentences that mention a CFR section, USCIS, a fee, a form number, a day count or a criteria
  count are always checked. These patterns are in code and can't be configured.
  - If the judge skips such a sentence or calls it "not a rule", one retry asks it to treat those sentences as
    rule claims.
  - If the judge still gives no verdict, the sentence is unverified and says why.
  - This means some case facts ("3 of 8 criteria banked") are badged unverified. We accept that noise; the
    judge's extraction is not trusted to wave a regulated fact through.
- **Judging:** each candidate is matched against the vault (Tier 1–2, at most two excerpts per source). One
  judge call (`agent.models.check`, the same locked-down engine with no tools, one turn, no web search)
  decides which candidates are rules, and which excerpts entail or contradict them, quoting the excerpt.
- **Deciding the status:** code, not the judge, decides it:
  - the quote must be found in the excerpt (exact, or the same words with different whitespace);
  - the excerpt must be the source's current snapshot and inside its freshness window;
  - Tier 3 never verifies.
- **Statuses:**
  - verified: a fresh Tier 1 or 2 source entails it, and no fresh Tier 1 source contradicts it;
  - conflict: Tier 1 sources disagree, which also sends a notification;
  - stale: the only support is stale;
  - unverified: anything else, including when the judge or the vault is unavailable.
- **Re-evaluation:** statuses are recomputed whenever a check is read or used, so a claim goes stale when
  its source changes.
- **The gate:**
  - the agent's write tools refuse text with a non-verified rule;
  - accepting an Inbox item re-checks freshness and refuses if a rule is no longer verified;
  - when the person rewrites the text, the words are theirs and the check is cleared.
- **Cost:** the judge's tokens and cost are added to the run, so budgets cover them.
- **Exports:** the attorney export (Phase 2) will use the same gate.

### 8. Vault first, then Tier 1, then Tier 2 (Phase 1d item 3)

The agent has a `search_vault` tool; stale sources in its results are re-fetched before they're returned.
Its web search is guarded in code (`EngineRequest.guard`, a `PreToolUse` hook on the Claude adapter's
`WebSearch`): a query that looks like a rule question (`rule_hints`) is refused unless the agent searched the
vault earlier in the run, and unless it passes `allowed_domains` within the manifest's Tier 1 domains (Tier 2
only after a Tier 1 search). Other searches (opportunities, events, people) stay open, so the opportunity
scout still works. Official pages the agent reads with `read_page` on Tier 1/2 domains are kept in the vault
as **findings** (`vault/findings.jsonl` + a snapshot): searchable and labelled, but observations rather than
reviewed sources, so rule-check never cites them and vault-watch doesn't re-fetch them. Promoting a finding
to a source is a person's decision (Knowledge page). Autopilot's "Tier 1 deadline" check now uses the same
manifest domains.

### 9. Primary and secondary sources; manual-import reminders

- **Fees come from the regulation.** 8 CFR 106.2 (fees by form) and 106.4 (premium processing), read through
  the eCFR API, are the primary Tier 1 fee sources. The USCIS fee page (G-1055) is `secondary_to:
  ecfr-8cfr-106-2`.
- **The primary governs.** A secondary copy never outvotes its primary. When the two disagree, the primary
  decides and the claim says so. While the primary is fresh in the vault, a secondary page can't verify a
  claim on its own. Independent Tier 1 primaries that disagree are still a conflict.
- **Exact figures are retrieved by value.** For a sentence with a dollar amount, rule-check also offers the
  best paragraph containing that amount, and always offers the primary whenever a secondary copy is offered.
  Vault search ranks each exact identifier (amounts, form numbers, section numbers) as its own list.
- **Manual-import sources.** `manual: true` marks sites that refuse automated clients (uscis.gov,
  travel.state.gov). Automatic fetches are still tried. Once an imported copy passes its freshness window and
  the automatic attempt fails, vault-watch sends one reminder per lapse, with the page link. Sources never
  imported don't send reminders; the Knowledge page shows them as never fetched.

## Consequences

- Outbound requests now include the public sources in the manifest (documented in the README).
- Many official pages can't be read by an automated client; they show as unreadable until imported by hand.
  That is visible on purpose: the vault guarantees every rule claim is cited and dated, not that every page
  is reachable.
- `pypdf` is a new dependency (court opinions, AAO decisions and the fee schedule are PDFs).
