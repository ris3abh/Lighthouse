# TODO — Phase 0

Running checklist against [SPEC.md](SPEC.md) section 11. Product-first ordering (section 11a).

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
- [x] Demo generator: `scripts/make_demo.py` (real connectors, recorded fixtures, in-memory keychain)
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
- [ ] 5. Missions
- [ ] 6. Overview briefing

## Later in Phase 1

- Website + scholarly connectors, scheduler, notifications, calendar, pipeline kanban, agent adapters,
  knowledge vault
