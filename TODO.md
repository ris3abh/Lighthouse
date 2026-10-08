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
- [x] C10. Failed lookups (owner's run): root cause reported (double https:// on fixed links; paper titles with
      venue tails / arXiv links never parsed, "0 found" shown as done; LinkedIn's wrapped sidebar lines split
      into separate awards; web-search outcomes lost when moving on). Fixed with regression tests; every lookup
      shows searching / found / nothing found / couldn't reach / blocked with the reason and Retry
- [x] C11. Back and forth: Back on every onboarding step and question, clickable step bar, answers kept and
      lookups re-offered; a URL per step and question; browser back / forward across pages and dialogs
- [x] C12. Chip input for lists in onboarding (one shared, keyboard-accessible component)
- [x] C13. Chat as a centered modal over a blurred dashboard; changed panels un-blur and highlight; pin to
      dock; Cmd/Ctrl+K, Esc; full-screen sheet on phones
- [~] C14. Chat-history import for real exports: format-agnostic intake with adapters, local relevance filter,
      picker step, extraction on picked items (mundane tier), longest-range advice. Shipped on synthetic
      fixtures; the adapter for the owner's Claude export (manifest + dated files) and a ChatGPT sample fixture
      wait for the redacted samples
- [x] C15. Onboarding as one conversation (ADR 0008 amendment): a window like Ask's over the blurred dashboard,
      every step a message in one thread that scrolls up as it grows, widgets inside their messages, reply
      controls in the composer, new messages type in, typing dots while working; a chat drop with no chats says
      what arrived and what happened to each file
- [x] CHECKPOINT 2c: chip input, picker with real match reasons, modal with a highlighted change, both themes
      Reported 2026-10-07 (d4d9ab1, d0d067a, b5a6dfa, 715deb5, 84a179b, 7af2ff3), plus C15 (41eb04b); approved
      2026-10-07. C14's real-export adapter still waits for the redacted samples

### Part S: the front door (ADR 0013), added 2026-10-07 at the owner's request
- [x] S1. `areao1` with no arguments: creates ~/AreaO1 on first run, remembers it, serves it and
      opens onboarding; later runs reopen it
- [x] S2. The wheel is the product: release workflow builds the UI, attaches the wheel to the GitHub release
      (PyPI via trusted publishing once configured); CI installs the wheel in a clean venv and smoke-tests it
      (release.yml on v* tags; PyPI waits for the PYPI_PUBLISH variable; scripts/smoke_wheel.py; the sdist
      now keeps the built UI, which `python -m build` used to drop)
- [x] S3. "Connect your AI" in onboarding and Settings: existing Claude login, or an Anthropic key in the
      keychain checked with a free request; cost note; bundled CLI counts as available; skippable. A new
      onboarding step ("Your AI") between the questions and the lookups, asked once; the key goes to the CLI
      process only. Area O1 never reads the Claude Code login itself
- [x] S4. One-line installers (install.sh, install.ps1): uv if missing, install, run; CI runs them
      (latest release wheel by default; AREAO1_SPEC / AREAO1_NO_RUN for CI; ubuntu, macOS, Windows)
- [x] S5. Landing page (docs/site, GitHub Pages) and a README that opens with the one line
      (reported with Checkpoint 3: a clean-machine install walkthrough)
      (static page with self-hosted fonts and a first-run screenshot; pages.yml deploys once Pages is enabled)

### Part D: agent upgrade + model routing (ADR 0009)
- [x] D1. Every UI write action is a chat tool through the service layer with the same rules (calendar /
      tracker auto-apply with undo; criterion-affecting -> Inbox; outreach needs approval); coverage test.
      agent/actions.py maps each page action to a tool or gives the reason it's yours; direct tools only in runs
      you started (missions keep the Inbox); Undo in the chat reply; deletes, letter writers and to-dos undoable
- [x] D2. Three tiers from .env (then hard = claude-opus-5-5, mid = claude-sonnet-5-5, mundane = small OpenAI; now ADR 0015
      model), rule-based router by task type, redaction + guardrails on every provider, .env.example.
      agent/routing.py (a areao1.yaml model that differs from the default still wins); OpenAI only for
      tool-less mundane reading, redacted, capped and costed (gpt-5-mini by default; prices in openai_chat.py);
      without an OpenAI key the mundane tier is Claude Haiku. Runs record task, tier and provider
- [x] D3. Long chats: older turns summarized (summary saved, original kept); "cheap mode" toggle (mid tier).
      Past ~6,000 replayed tokens, all but the last six messages fold into a summary on the mundane tier
      (guardrails applied, cost recorded, shown at the top of the chat); a failed summary never blocks the chat;
      cheap mode in the chat header and Settings
- [x] CHECKPOINT 3 (agent): chat actions, routing + cost per run on the Agent page, cheap mode
      Reported 2026-10-07 with Part S (clean-install walkthrough); one live run ($0.10); approved 2026-10-07

### Checkpoint 3 follow-ups (owner, 2026-10-07)
- [x] F1. Remove the "Claude Code login" option: an Anthropic API key is the only way to connect the AI
      (Agent SDK terms); the CLI runs with its own empty config folder and no OAuth token (ADR 0013 amendment)
- [x] F2. Chat footer token count (no "0 tokens" next to a nonzero cost): runs that only recorded a price
      (chat-history extraction) now record tokens too, and lib/usage.ts shows the cost alone when tokens are unknown
- [x] F3. The chat modal blurs the whole background evenly: the content area blurs as one, and a changed panel
      stays blurred with a crisp outline and label drawn on top (no more un-blurring; checked in Chrome)
- [x] F4. Test: no chat request can move a criterion claim from invited to completed (tests/test_no_stage_upgrades.py:
      five phrasings, every write tool aimed at the MLH invitation; only the pipeline item moves; negative control)
- [x] F5. Status of items 7-11: C10-C13 done; C14 done except the adapter for the owner's real export layout,
      which still waits for the redacted sample (manifests and dated files are already followed generically)
- [x] F6. Rename to Area O1 (ADR 0010): every name in areao1/core/names.json; Lighthouse-era workspaces, settings,
      keychain entries and variables migrated once with a notice; deprecated lighthouse-gc alias (baf7966);
      banter only where listed, rules enforced by tests/test_banter.py and checked in Chrome (d15c9df, d71bfc2)

### Part E: Google, CRM, outreach (ADR 0014)
- [x] E1. Google sign-in with the user's own OAuth client (built, then removed by the ADR 0014 amendment:
      Gmail connects with an app password instead; see E6)
- [x] E2. Gmail read: threads with case contacts linked to the CRM; nothing else stored (headers only,
      one redacted line per thread, last touch follows the newest thread; the google job every 15 minutes)
- [x] E3. Two-way sync with a dedicated "Area O1" Google calendar (built, then dropped by the ADR 0014
      amendment; the local Calendar page and calendar.ics stay)
- [x] E4. CRM page: people, relationship, threads, asks, last touch, next follow-up; linked to Letters/Pipeline
      (Contacts page; data/contacts.json via the service layer, undoable; letter writers appear until added;
      chat tools list/add/update/delete_contact)
- [x] E5. Outreach: agent drafts, user approves / edits / rejects, sends from Gmail; proactive follow-ups
      after 7 quiet days (same approval); daily send limits; case contacts only (draft_email tool; approval on
      the Contacts page; only the person can send, gmail.send; follow-ups are a short template to edit)
- [x] E6. Google is Gmail only, with an app password (ADR 0014 amendment): Settings > Gmail takes the address +
      16-letter app password (test login, keychain, plain errors); IMAP headers only / SMTP for approved sends;
      OAuth client flow and Google Calendar sync removed (an old sign-in leaves the keychain on start); optional
      Email step in onboarding; docs/gmail.md
- [x] E6 live check (2026-10-07): connected with an app password; one approved send to the owner's second
      address. The audit found it went out 4 times (clicks during a 6-second SMTP send); fixed: sends are
      serialized and re-read the draft, the button disables while sending (regression test). Refresh threads
      not yet tried live
- [x] E6b. Send log: every send attempt (time, recipient, Message-ID or error) in outreach.json; the daily limit
      counts sends Gmail accepted (pre-log sends counted from the change log); failures show on Contacts
- [x] E6c. Undo send: Approve & send waits 10 seconds (server-side) with Undo send; a refusal after the window
      returns it to draft; an approval left waiting when the app stops becomes a draft again
- [x] E7. Read-only Mail view on Contacts (ADR 0014, Mail view amendment): per-contact threads (sent and
      received) and all case mail in 7 categories with counts; rules first (taught senders, contacts, organizer
      domains, subject keywords), then the mundane tier on headers + first lines; moving teaches a sender rule;
      PEEK-only reads of a read-only mailbox; text fetched on open, never written; links to Inbox candidates
- [x] G0. OpenAI is the only engine (ADR 0015): Responses API engine with our tool loop, guarded web search,
      prompt caching, price table, dollar cap; tiers one line each (hard/mid gpt-6.1-sol, mundane gpt-6-luna);
      OpenAI key only (Anthropic key removed on start); the suite's FakeEngine runs the real engine against a
      scripted Responses API; Claude Code skill + AGENTS.md Codex section in every workspace
- [x] G0 live check (2026-10-07, owner's workspace, gpt-6.1-sol): chat $0.0077 (3 tool calls, no search);
      opportunity scout $0.2203 (20 tool calls, 4 searches = $0.1306 of it, 6 sources, 6 Inbox proposals)
- [x] E7 live check: rules-only refresh on the owner's Gmail ($0); found organizer mail in Promotions was never
      read (fixed, ab734a1). The HackMIT judging thread and DubHacks reply aren't in the connected account
- [x] E8. Emails from other accounts (ADR 0014 amendment): .eml drops on Evidence, Inbox and Mail go through the
      upload pipeline (original kept) with sender authentication from the original headers, the Mail view's
      rules, criterion mapping and an invited / completed stage from the text; Gmail messages forwarded as an
      attachment are sorted and verified by the attached original, which can be imported
- [ ] CHECKPOINT 4 (Gmail): connect with an app password, Refresh threads, one approved send
      Reported 2026-10-07 (built and tested with fake IMAP / SMTP); the live run waits for the owner's app password

### Part F: daily opportunity job
- [ ] F1. Off-by-default 24h job over Gmail (IMAP, app password) for judging / reviewer / call invites
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

- [x] `areao1 init` creates a workspace from a template, with schemas and .gitignore
      (+ git init, gitleaks pre-commit hook, AGENTS.md, empty `memory/`)
- [x] O-1A and EB-1A profiles load; criteria engine computes the scoreboard from exhibits.json
- [x] GitHub (public + PAT) and Hugging Face connectors: discover, snapshot, candidates (fixture tests)
- [x] `areao1 import <url>` auto-detects the connector
- [x] metrics-snapshot appends to metrics.csv (upsert per day; GitHub 14-day traffic kept)
- [x] `areao1 up` serves Overview, Sources, Metrics, Evidence and Inbox pages (checked in Chrome,
      light + dark)
- [x] DASHBOARD.md generated; demo workspace renders with no network (tested)
- [x] Memory store (5b): connectors attach raw responses → observations (content-addressed snapshots);
      claims, edges and decisions as append-only JSONL; rebuildable SQLite index in `.areao1/cache/`;
      Inbox accept/reject records approved/rejected decisions and CITES edges
- [x] Core/profile split: `areao1.core` imports nothing outside core and mentions no profile
      (`tests/test_layering.py`); profiles, scoring and views live in `areao1/criteria/`
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
- [x] `areao1 mcp`: read-only MCP server (get_scoreboard, list_gaps, query_claims, get_provenance,
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
  as unreadable; `areao1 vault import <source> <saved page>` fills them by hand. We don't disguise the
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
