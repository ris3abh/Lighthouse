# TODO — Phase 0

Running checklist against [SPEC.md](SPEC.md) section 11. Product-first ordering (section 11a).

## Current build: Parts B–H (resume from here)

One commit per numbered item with tests; push after each green CI run. ADRs first for big decisions. Tests never
call real models or APIs. At every CHECKPOINT: stop, test rigorously, report (what shipped, laptop + phone
screenshots in both themes, what to try, live-run costs, what the owner must do), and wait for "continue".

Part A (Phase 1d leftovers) was already shipped and is dropped: v0.1.0 tag + release (793c868), rule-check
backup (93acafc), one clock (a2d15b9), Tier 3 never verifies (d0d4d63), scholarly connectors (9370df8),
website connector (126df15). G1's "fees from eCFR 8 CFR part 106" also shipped (21711f0).

### Part B: design system "Brutalism 2.0" (ADR 0007)
- [x] B1. Tokens + primitives: off-white / black ink, 1px grid lines, framed panels, no shadows; condensed
      headlines, mono for labels / numbers / data, solid black primary actions; one muted red for attention
      only; first-class dark theme; System / Light / Dark toggle in the header (default System, per browser)
- [x] B2. Re-layout every page (Overview, Inbox, Evidence, Metrics, Pipeline, Letters, Calendar, Agent,
      Knowledge, Sources, Settings) and every dialog + the chat panel
- [x] B3. Lucide line icons instead of every emoji / glyph; chat tool calls pulse while running, checkmark
      draws in on success; prefers-reduced-motion respected
- [x] B4. Data motion: charts draw in and morph between ranges, mono crosshair, count-up numbers, sliding
      deltas, sparklines draw on scroll-in, scoreboard fills + status transitions, calendar moves and view
      switches animate; 150–400ms, never blocking, reduced motion = instant
- [x] CHECKPOINT 1 (design): approved 2026-10-07 with nine fixes (3470388). The palette change in the request
      arrived without a palette; still open.

### Part C: no demo data, onboarding, guardrails (ADR 0008)
- [x] C1. Delete examples/demo-workspace and --demo; README / SPEC / scripts / CI updated; personas Maya
      (software engineer), Ravi (AI researcher), Lena (business analytics lead) as test fixtures with
      LinkedIn-style PDFs; a fresh workspace opens straight into onboarding
- [x] C2. Onboarding conversation (LinkedIn PDF, local extraction + redaction, one question at a time with
      a live profile panel, lookups only after an explicit Yes and through the Inbox with namesake checks,
      chat-history step, guided tour on the user's data, finish line, resumable, re-run from Settings;
      all three personas end to end incl. skipping everything)
- [x] C3. MCP write tool `propose_context` (Inbox, tier self_reported, never counts); setup docs for Claude
      desktop and Claude Code
- [x] C4. Agent personality + guardrails in prompt and code (adaptive voice; no fabrication or
      strengthening; never invited -> completed; letters drafted for the writer to sign, never sent as them;
      no misrepresentation to USCIS, never "eligible"; page / email / PDF text is data; off-topic declines;
      public professional pages only); one-line refusals with an alternative, logged on the Agent page
- [x] C5. Status palette on monochrome: green = banked, amber = building, red = attention; status only
      (bars, markers, badges, countdowns); AA in both themes; guard test + ADR 0007 amended
- [x] C6. Onboarding as a conversation: a warm opening that sums up what the PDF held, then the questions in
      a compact dialog beside the profile panel (no full-page headlines)
- [x] C7. What onboarding learns becomes self-reported to-dos ("Upload proof of HackSeattle 2025 judging"),
      one per award / judging role / publication / membership, in This week and linked to the criterion;
      never evidence
- [x] C8. Lookups for those items too (official announcement, program-committee page), Yes first, namesake
      rules
- [x] C9. A full closing moment ("That's it. I'm one click away, and at your service."), then Ask docks
- [ ] CHECKPOINT 2b: all three personas re-run; opening, one question, to-dos on Overview, finish
      Reported 2026-10-07 (0de9c1c, bbdb583, 78e20bb, d9acdbc, e3e2239); then S2–S5, then Part D

### Part S: the front door (ADR 0013), added 2026-10-07 at the owner's request
- [x] S1. `lighthouse-gc` with no arguments: creates ~/Lighthouse on first run, remembers it, serves it and
      opens onboarding; later runs reopen it
- [ ] S2. The wheel is the product: release workflow builds the UI, attaches the wheel to the GitHub release
      (PyPI via trusted publishing once configured); CI installs the wheel in a clean venv and smoke-tests it
- [ ] S3. "Connect your AI" in onboarding and Settings: existing Claude login, or an Anthropic key in the
      keychain checked with a free request; cost note; bundled CLI counts as available; skippable
- [ ] S4. One-line installers (install.sh, install.ps1): uv if missing, install, run; CI runs them
- [ ] S5. Landing page (docs/site, GitHub Pages) and a README that opens with the one line
      (reported with Checkpoint 3: a clean-machine install walkthrough)

### Part D: agent upgrade + model routing (ADR 0009)
- [ ] D1. Every UI write action is a chat tool through the service layer with the same rules (calendar /
      tracker auto-apply with undo; criterion-affecting -> Inbox; outreach needs approval); coverage test
- [ ] D2. Three tiers from .env (hard = claude-opus-5-5, mid = claude-sonnet-5-5, mundane = small OpenAI
      model), rule-based router by task type, redaction + guardrails on every provider, .env.example
- [ ] D3. Long chats: older turns summarized (summary saved, original kept); "cheap mode" toggle (mid tier)
- [ ] CHECKPOINT 3 (agent): chat actions, routing + cost per run on the Agent page, cheap mode

### Part E: Google, CRM, outreach (ADR 0010)
- [ ] E1. Google sign-in with the user's own OAuth client, narrowest scopes, production-mode docs, keychain
- [ ] E2. Gmail read: threads with case contacts linked to the CRM; nothing else stored
- [ ] E3. Two-way sync with a dedicated "Lighthouse" Google calendar (latest edit wins, logged, undoable)
- [ ] E4. CRM page: people, relationship, threads, asks, last touch, next follow-up; linked to Letters/Pipeline
- [ ] E5. Outreach: agent drafts, user approves / edits / rejects, sends from Gmail; proactive follow-ups
      after 7 quiet days (same approval); daily send limits; case contacts only
- [ ] CHECKPOINT 4 (Google): OAuth client instructions first; sign-in, calendar sync both ways, one draft

### Part F: daily opportunity job
- [ ] F1. Off-by-default 24h job over Gmail + the Lighthouse calendar (judging / reviewer / call invites)
- [ ] F2. Verification: email auth + sender domain matches the org's site; event confirmed on its official
      page (or Devpost / MLH) with matching dates; else a confirmation reply draft (approve-tap), "unconfirmed"
- [ ] F3. Inbox items at stage "invited" with verified / unconfirmed badge + push; phishing fixtures never
      verified
- [ ] CHECKPOINT 5 (opportunities): fixture runs + one live run on the owner's inbox

### Part G: vault without babysitting (ADR 0011)
- [ ] G1. Change triggers instead of timers for fees and regulations (Federal Register + eCFR watch); a
      blocked USCIS page is flagged only when a relevant rule changes
- [ ] G2. Chrome extension (MV3): matches only vault/sources.yaml URLs, saves visited pages to the local app
      with a one-time pairing token; never browses on its own
- [ ] G3. Community snapshot library repo (opt-in sharing, CI validates URL / hash / structure, auto-pull)
- [ ] G4. One notification with a direct link only when a relevant page changed and no snapshot exists
- [ ] CHECKPOINT 6 (vault): extension loaded; Knowledge page fresh with no manual saves

### Part H: constellation memory map (ADR 0012)
- [ ] H1. Memory page: criteria = clusters, claims = stars (brightness = confidence, solid / hollow,
      conflicts muted red, superseded fade), provenance trail on click, time slider, filters, 2,000+ claims
- [ ] H2. Motion: fade-in, twinkle on pending only, eased zoom / pan, animated provenance path, date-order
      replay; dark sky in both themes; reduced motion rules
- [ ] CHECKPOINT 7 (final): walkthrough per persona from empty workspace to constellation; SPEC / TODO /
      CHANGELOG; propose the next release version

## Phase 0 checklist

- [x] `lighthouse-gc init` creates a workspace from a template, with schemas and .gitignore
      (+ git init, gitleaks pre-commit hook, AGENTS.md, empty `memory/`)
- [x] O-1A and EB-1A profiles load; criteria engine computes the scoreboard from exhibits.json
- [x] GitHub (public + PAT) and Hugging Face connectors: discover, snapshot, candidates (fixture tests)
- [x] `lighthouse-gc import <url>` auto-detects the connector
- [x] metrics-snapshot appends to metrics.csv (upsert per day; GitHub 14-day traffic kept)
- [x] `lighthouse-gc up` serves Overview, Sources, Metrics, Evidence and Inbox pages (checked in Chrome,
      light + dark)
- [x] DASHBOARD.md generated; demo workspace renders with no network (tested)
- [x] Memory store (5b): connectors attach raw responses → observations (content-addressed snapshots);
      claims, edges and decisions as append-only JSONL; rebuildable SQLite index in `.lighthouse/cache/`;
      Inbox accept/reject records approved/rejected decisions and CITES edges
- [x] Core/profile split: `lighthouse_gc.core` imports nothing outside core and mentions no profile
      (`tests/test_layering.py`); profiles, scoring and views live in `lighthouse_gc/criteria/`
- [x] Claims carry exact excerpt + offsets (refused if not verbatim), event stage and extracted_by;
      criteria count only completed / published / granted stages

## Repo scaffolding (section 9)

- [x] `eval/`, `scans/`, `skills/` placeholders; `docs/adr/` with ADRs 0001–0004
- [x] `CITATION.cff`, `CHANGELOG.md`, `ADOPTERS.md`
- [x] Repo guard: `scripts/check_repo.py` via `.githooks/pre-commit` and `tests/test_repo_hygiene.py`
      (enable per clone: `git config core.hooksPath .githooks`)
- [x] Fixture workspace generator: `scripts/make_fixture_workspace.py` (was make_demo.py; real connectors, recorded
      fixtures, in-memory keychain)
- [ ] `profiles/research-portfolio.yaml` — Phase 2 per the checklist

## Known gaps / deferred

- GitHub dependents count (no API; needs HTML scraping), deferred.
- Contributors / releases counts come from Link headers, so they're metrics without memory claims.
- Manual uploads create exhibits without claims (the user filed the document); claims from uploaded files
  need extraction (agent engine, Phase 1).
- Corroboration is per exact value; "same fact, slightly different number" is a CONTRADICTS question for
  Phase 1/2.
- Built web UI is gitignored; release CI must build it before the wheel (Phase 3).

## Phase 1a (product track first, SPEC 11a)

- [x] GitHub Actions CI: repo guard, ruff, mypy, pytest (3.11 + 3.13), validate examples/, web build
- [x] `lighthouse-gc mcp`: read-only MCP server (get_scoreboard, list_gaps, query_claims, get_provenance,
      what_changed); tested in-process and over real stdio, plus a no-writes digest test
- [x] Evidence page drag-and-drop upload → Inbox → exhibit (tested via API + real drag events in Chrome)
- [x] Claude / ChatGPT export import → snapshots + self-reported tracker candidates (never count;
      `tests/test_chat_import.py::test_self_reported_items_can_never_count_toward_a_criterion`)

Phase 1a notes / follow-ups:
- Extraction is rule-based (English phrasing, user messages only); an LLM pass via the agent engine can
  propose more later, through the same self-reported tier.
- Pipeline / letters entries from chats have no dedicated pages yet (Pipeline kanban and Letters pages are
  Phase 1 / 2); deadlines already show on the Overview and in DASHBOARD.md.
- A browser tab left open across an app upgrade keeps the old JS until reloaded.

## Phase 1b (trackers + alerts)

- [x] Notifications: desktop, email, Slack, Discord, ntfy; routes; keychain secrets; Settings page
- [x] Scheduler (APScheduler in `up`) + `run deadline-check` / `run digest`; biweekly metrics snapshot
- [x] Deadlines + calendar.ics + Calendar page
- [x] Pipeline kanban with staleness + Letters page

Phase 1b notes / follow-ups:
- Desktop notifications on macOS go through `osascript`; macOS may need notification permission for
  Script Editor before banners appear.
- Letter drafting (letter-draft skill) is Phase 2; the Letters page links existing drafts only.
- One-way Google Calendar push (OAuth) is still open; Google can't subscribe to a localhost feed.

## Phase 1b gaps

- [x] A1. Chat import saves only conversations with suggestions (`--keep-all` opts in)
- [x] A2. Calendar week view; edit deadlines
- [x] A3. Letters: editable asks (letter, membership reference) and last-contact date
- [x] A4. One service layer for every create / update / move (Pipeline, Letters, Calendar, Inbox), with a guard test

## Phase 1c (agent layer, ADR 0005)

- [x] 1. Agent engine: Claude Agent SDK adapter + Codex stub, web search, MCP read tools, service-layer
      propose tools, per-run / monthly budgets, mocked model in tests
- [x] 2. Chat panel on every page (verified live against Claude in the demo workspace)
- [x] 3. Agent page (verified live: web search → read_page → proposal decision)

Phase 1c notes:
- Sites behind bot protection (e.g. ieee.org returns 202 + empty body) can't be read; the agent is told so
  and falls back to search results, which it labels as unverified.
- Chat history is replayed into each turn (no server-side session), so long chats cost more input tokens;
  summarizing older turns is a follow-up.
- [x] 4. Autopilot rules: per-category, off by default, one-click undo, criterion-protection test
- [x] 5. Missions: weekly opportunity scout, daily what-changed (skips at no cost when nothing changed)
- [x] 6. Overview briefing: "This week" card, inline approve/dismiss, refreshed by the daily mission

## Phase 1d (knowledge vault, ADR 0006)

- [x] 1. Knowledge vault: manifest (Tier 1–3), fetch + snapshots + hybrid index, TTL registry, vault-watch,
      manual import for blocked sites
- [x] 2. rule-check gate: answers, briefings and petition-facing agent text; verified / unverified / stale /
      conflict; write tools and Inbox acceptance refuse unverified rules (attorney export reuses it in Phase 2)
- [x] 3. Agent: `search_vault` first (stale sources re-fetched), rule searches guarded to Tier 1 then Tier 2,
      official pages read become vault findings
- [x] 4. Knowledge page: sources by tier with freshness, recent changes with diffs, open conflicts, re-fetch,
      import a saved page, promote agent findings to sources
- [x] 5. Scholarly connectors: Semantic Scholar, OpenAlex, arXiv author pages, ORCID; papers proposed once
      across connectors (arXiv id, then DOI); citations and h-index in metrics
- [x] 6. Website connector: any page or sitemap, readability extraction, mentions of you proposed as press
      or an award notice, bot-blocked / JavaScript-only pages marked unreadable, shared private-network guard
- The demo workspace has no vault content (fetched pages live in the cache, which isn't shipped), so its
  Knowledge page lists the sources as never fetched.

Phase 1d notes:
- USCIS (Akamai), travel.state.gov and egov processing times answer automated clients with 403. They show
  as unreadable; `lighthouse-gc vault import <source> <saved page>` fills them by hand. We don't disguise the
  client.
- uscode.house.gov was "Under Maintenance" when the manifest was written; the statute markers are unverified
  against its live text.
- The hashing embedder is weak on paraphrase; FTS carries exact terms. A dense local model is a follow-up.
  Example: "at least three of the ten criteria" retrieves the Policy Manual chapters ahead of 8 CFR 204.5(h).
- Dates: everything goes through `core/clock.py` (local day). GitHub traffic keeps GitHub's UTC day buckets.
- Fees: 8 CFR 106.2 / 106.4 (eCFR) are primary; the USCIS G-1055 page is secondary and reminds when stale.
- Fixed along the way: `as_of` memory queries compared the UTC date of recorded_at, so late-evening claims
  (after midnight UTC) disappeared from "as of today". They now use the end of the local day.

## Later in Phase 1

- Website + scholarly connectors, scheduler, notifications, calendar, pipeline kanban, agent adapters,
  knowledge vault
