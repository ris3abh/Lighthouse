# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-08

### Highlights
- **OpenAI is the only engine** (ADR 0015): the Responses API with Area O1's own tool loop, nothing stored at
  OpenAI, three model tiers one line each (hard and mid `gpt-6.1-sol`, mundane `gpt-6-luna`), web search as a
  guarded tool on the mundane tier, capped per run (`agent.max_searches`, default 8), and every run's cost,
  including its searches. Connecting the AI takes an OpenAI API key.
- **Memory constellation** (ADR 0012): every claim a star in its criterion's cluster; brightness is confidence,
  solid approved, rings pending, red conflicts; click a star for its provenance trail; replay the case in date order.
- **Daily opportunity check** (ADR 0016): invitations in your mail become Inbox items, each **verified** (sender
  authentication and the event on its official page) or unconfirmed (a check-in drafted for your approval) or
  suspicious; phishing fixtures never verify.
- **A vault without babysitting** (ADR 0011): official pages stay fresh on real rule changes (Federal Register and
  eCFR), a Chrome extension saves the blocked pages you visit, and a public community snapshot library fills gaps.
- **Gmail with an app password** (ADR 0014): a read-only Mail view of case mail, `.eml` and forward-as-attachment
  import with sender checks, and approved sends with a 10-second undo.
- **Letters drafted from approved claims**, each sentence citing its claims, for the writer to rewrite and sign.

### Changed
- Renamed to **Area O1** (ADR 0010): package and command `areao1`, `AREAO1_*` variables, `areao1.yaml` and
  `.areao1/` in workspaces, keychain service `areao1`. Lighthouse-era workspaces, settings, keychain entries and
  variables are migrated on first run with a notice; `lighthouse-gc` remains as a deprecated alias.
- The agent engine is OpenAI's Responses API (ADR 0015); an Anthropic key saved before is removed from the keychain
  on start, and workspaces naming Claude models load with the OpenAI tier defaults.
- Google is Gmail only, with an app password (ADR 0014 amendment): the OAuth client flow and Google Calendar sync
  are removed; the Calendar page and `calendar.ics` stay (Google Calendar imports the file).
- Freshness of blocked official pages follows change signals instead of timers (ADR 0011); timers stay for sources
  with no change feed (processing times, the Visa Bulletin).

### Added
- Memory page (ADR 0012): the constellation, filters by criterion, entity, status and date, a time slider and
  Replay, a list view for screen readers, smooth at 2,000+ claims, phones; `/api/memory/constellation` and
  `/api/claims/{id}/provenance`.
- Daily opportunity job `daily-opportunities` (ADR 0016), off by default (Settings > Gmail > Daily opportunity
  check, or Check now): the Mail rules (Promotions / Social filtered), the sender check, the invited / completed
  stage rule, web confirmation on the organizer's domain or Devpost / MLH, de-duplication against the Inbox (scout
  leads included), the pipeline and exhibits, and an `opportunity` notification per new find.
- Vault change signals (Federal Register final rules in effect, eCFR amendment dates), the capture extension
  (`areao1 extension`, `docs/extension.md`; pairing in Knowledge > Browser extension), the community snapshot
  library (github.com/ris3abh/areao1-community-vault; pulled on vault-watch, hash-verified; opt-in local sharing),
  and one reminder only when a relevant page changed and no newer snapshot exists.
- Contacts > Mail (ADR 0014 amendments): case mail only, in seven categories, rules first, model sorting opt-in,
  sender-check badges, read-only (PEEK), bodies fetched on open and never stored; `.eml` drops on Evidence, Inbox
  and Mail; Gmail forwards-as-attachment sorted and verified by the attached original; a guide for bringing in mail
  from another account.
- Outreach: every send attempt logged (failures shown on Contacts), the daily limit counts sends Gmail accepted,
  Approve & send waits 10 seconds with Undo send, double approvals send once.
- Letter drafts (Letters > Draft from claims): approved claims only, every sentence cites its claims, verdicts
  dropped, a signature placeholder; Send to the writer goes through Approve & send.
- Claude Code skill (`.claude/skills/areao1/`) and an `AGENTS.md` Codex section in every workspace; the
  chat-import adapter hook (`docs/chat-import.md`); `NOTICE` in built packages; a dev-only filming workspace
  (`scripts/film_demo.py`, `docs/filming.md`).
- Design system "Brutalism 2.0" (ADR 0007): semantic light and dark tokens with one muted red for attention,
  condensed Archivo headlines with JetBrains Mono for data, framed panels, a System / Light / Dark switch,
  lucide line icons, and data motion (charts draw in and morph, count-ups, calendar drag-and-glide).
  Reduced motion is respected everywhere; text tokens meet WCAG AA.
- Onboarding (ADR 0008): a new workspace opens into a short conversation.
  - It starts from your LinkedIn PDF, which is read on this computer. Emails and phone numbers are removed
    first, and the PDF itself isn't kept.
  - It asks one question at a time (Yes / No, let me fix it / Skip), with your profile filling in beside it.
    Skipped fields stay blank.
  - Lookups (arXiv, GitHub, ORCID, your website) run only after you say Yes. Finds go to the Inbox, with a
    namesake check on papers.
  - Then come the chat-history import, a guided tour on your own data and a finish note by the Ask button.
  - Onboarding is resumable and can be run again from Settings.
- MCP `propose_context` (C3): Claude Code, Claude desktop and other MCP tools can send important context to your
  Inbox. It's self-reported: kept as a note when you accept it, and never counts toward a criterion. Setup guide in
  `docs/mcp.md`.
- Agent personality and guardrails (C4). The voice starts warm, then mirrors your tone and length. Code-level
  checks back the prompt:
  - An invitation can't be proposed as completed, published or granted.
  - The agent can't mark a letter sent or signed, and has no tool to send or sign anything.
  - Eligibility verdicts and guarantees are replaced in answers.
  - Web page text is wrapped as data, and pages that address an AI are flagged.
  - People-search and personal social sites are refused.
  - A `decline` tool covers off-topic requests.
  - Every refusal, including from the rule-check gate and the search policy, is listed under "Declined" on the
    Agent page.
- No demo data (ADR 0008): `--demo` and `examples/demo-workspace` are gone. The fictional Alex Rivera case is a
  test fixture, and three onboarding personas (Maya, Ravi, Lena) with LinkedIn-style PDFs live in
  `tests/fixtures/personas`.
- Knowledge vault (SPEC 5a, ADR 0006): `vault/sources.yaml` lists Tier 1–3 sources (eCFR 8 CFR 214.2(o) and
  204.5(h), INA, the USCIS Policy Manual chapters, I-129 / I-140, the G-1055 fee schedule, premium
  processing, processing times, the Visa Bulletin, the Federal Register, Kazarian, Chawathe, AAO decisions,
  secondary pages) with a freshness registry (fees, forms, processing times 7 days; Visa Bulletin monthly).
  Pages are fetched through the shared public-web guard, stored as content-addressed snapshots (history
  kept), chunked with exact offsets and searchable with full text + local embeddings.
  `lighthouse-gc vault sync | search | status | import`. The daily `vault-watch` job re-checks Tier 1 sources
  and notifies when one changes.
- rule-check gate (SPEC 5a): rule statements in every agent answer and briefing are checked against the
  vault: a judge model picks the rule claims and cites excerpts, and code verifies the quote is really in a
  fresh Tier 1/2 source. Badges: verified (with the quoted words and source), unverified, stale, conflict
  (Tier 1 sources disagree; also a notification). Unverified rules are refused in evidence summaries and
  letter text, and an Inbox item whose rules went stale can't be accepted until re-checked or rewritten.
  Re-check buttons on the Agent page, the briefing and Inbox items.
- The agent searches the vault first (`search_vault`; stale sources are re-fetched before use). Web searches
  about rules are refused unless they follow a vault search and are restricted to Tier 1 domains (Tier 2 after
  that); other searches stay open. Official pages the agent reads are kept in the vault as findings,
  searchable but never used to verify a rule until promoted.
- Knowledge page: every vault source by tier with freshness (checked, expires, page date, versions kept),
  recent changes with the changed lines, open conflicts with both citations and where they appeared, and
  per-source Re-fetch / Import saved page. Official pages the agent found can be added as sources.
- Bot-protection and maintenance pages are recognized even when served with HTTP 200, and recorded as
  unreadable. Pages from sites that block automated reading can be imported from a saved copy.

- Fees come from the regulation: eCFR 8 CFR 106.2 and 106.4 are the primary Tier 1 fee sources and the USCIS
  fee page is secondary (`secondary_to`). The primary governs; while it is fresh, a secondary page can't verify
  a fee on its own. rule-check always shows the judge the paragraph containing a claimed amount.
- rule-check backup: sentences mentioning a CFR section, USCIS, a fee, a form number, a day count or a
  criteria count are always checked, even if the judge's extraction misses them or calls them "not a rule"
  (one retry, then unverified with the reason).
- Tier 3 (Wikipedia, any non-official domain) can never verify a rule. Tier 1/2 sources must be on the
  manifest's official domains (workspace overrides included). A source redirected off them isn't stored.
  Re-checks use each source's current tier.
- Scholarly connectors: Semantic Scholar, OpenAlex, arXiv author pages and ORCID
  (`lighthouse-gc import <profile URL>` or the Sources page).
  - Each source tracks the author profile (citations, h-index and paper count where the source has them) and
    every paper.
  - Each paper is proposed for scholarly articles with its type (journal, conference, preprint), stage,
    venue and citations, and asks you to confirm you're an author.
  - A paper found by several connectors, or linked from GitHub or Hugging Face, is proposed once (by arXiv id,
    then DOI).
  - Free APIs, no keys; no contact email is sent.
- Website connector: any public page or sitemap (same-site pages, up to 25).
  - Pages are read readability-style: the article or main content, without navigation, headers, footers or
    asides, plus title, date, author and site from Open Graph / JSON-LD.
  - A page that mentions you (or your aliases) is proposed as press (an article about you or a passing
    mention), or as an award notice when it says you won. The proposal quotes the sentences that mention you.
  - Bot-protection pages (also when served with HTTP 200), login walls, maintenance pages and JavaScript-only
    pages are marked unreadable on the Sources page instead of being stored.
  - Same private-network guard as the agent's page reader: public hosts only, re-checked on every redirect.
- Manual-import sources (`manual: true`: uscis.gov, travel.state.gov) send a reminder with the page link when
  an imported copy passes its freshness window (once per lapse). The Knowledge page marks them.

### Fixed
- `as_of` memory queries dropped claims recorded late in the local evening (after midnight UTC).
- One clock (`lighthouse_gc.core.clock`): "today", day counts and calendar days are the person's local day
  (the machine's time zone; `TZ` overrides it), never the UTC date. Fixed in deadline days-left, pipeline
  staleness (now calendar days, matching the digest), the agent's "Today is", the briefing's "nothing changed
  since", chat-export dates, the Visa Bulletin month and fiscal year, and source "last sync" dates. A test
  fails if code reads the date anywhere else; frozen-clock tests at 23:59 / 00:01 local and UTC.

## [0.1.0] - 2026-10-06

First release: the local-first evidence command center (Phases 0, 1a, 1b, 1c). A Zenodo DOI is minted for
this release.

### Added
- Phase 0 core: workspace store, JSON Schemas for every file, `lighthouse-gc init / import / run / up / validate`.
- GitHub (public + fine-grained PAT, incl. 14-day traffic history) and Hugging Face connectors.
- O-1A and EB-1A profiles with a rule-based criteria engine; criterion overrides (gap / dropped).
- Evidence-aware memory (SPEC 5b): append-only observations, claims with verbatim excerpts and offsets,
  edges and review decisions; rebuildable SQLite index; bitemporal `as_of` queries.
- Event stages: only completed / published / granted evidence counts toward a criterion.
- Core/profile split: `lighthouse_gc.core` is domain-agnostic (enforced by tests).
- Web dashboard: Overview, Inbox (with claim provenance), Evidence, Metrics, Sources.
- Fictional "Alex Rivera" demo workspace, generated through the real connectors from recorded fixtures.
- Repo guard pre-commit hook: required spec sections, two-repo warning, no case workspaces, gitleaks.
- GitHub Actions CI: repo guard, ruff (lint + format), mypy, pytest on Python 3.11 and 3.13,
  `lighthouse-gc validate` on every example workspace, and the web type-check + build.
- `lighthouse-gc mcp`: read-only MCP server (stdio) with `get_scoreboard`, `list_gaps`,
  `query_claims(entity, as_of)`, `get_provenance(claim_id)` and `what_changed(since)`; every tool is
  annotated read-only and never writes a workspace file (tested).
- Drag-and-drop on the Evidence page (or click to choose): each file is snapshotted byte-for-byte in
  `memory/sources/` (tier `user`) and proposed in the Inbox with a guessed criterion, type and stage
  (an invitation is proposed as `invited`). Dropping onto a criterion card targets it. Accepting files
  the original bytes as `evidence/<crit>/<crit>_<date>_<slug>.<ext>`. Uploads can be previewed before
  filing; duplicates are detected by content hash.
- Source tiers on observations, candidates and exhibits (`platform`, `user`, `self_reported`, `tier1-3`).
- Claude / ChatGPT export import (`lighthouse-gc import <conversations.json|export.zip>` or the Sources
  page): every conversation becomes a transcript snapshot in `memory/` (tier `self_reported`) plus an
  import manifest with the export's sha256. A rule-based pass reads only the user's own messages and
  proposes deadline, pipeline and letter-writer candidates, each with a low-confidence claim quoting the
  exact sentence. Accepting adds them to `deadlines.json` / `pipeline.json` / `letters.json`.
- Self-reported material can never count toward a criterion: the Inbox refuses to make it an exhibit,
  candidate kind and tier aren't editable, and the criteria engine ignores self-reported exhibits.
- The demo workspace includes a fictional Claude export.
- Notifications: desktop (macOS / Linux / Windows), email (SMTP + STARTTLS), Slack and Discord webhooks,
  ntfy push. Named channels and per-event routes in `lighthouse.yaml`; secrets in the keychain
  (`lighthouse-gc secret set <ref>`). Channels can send `detail: minimal` (counts only). Webhooks only post
  to their real hosts, Discord can't @mention, and every send is logged locally for de-duplication.
  `lighthouse-gc notify test` and a Settings page.
- Scheduler: `lighthouse-gc up` runs the jobs in `lighthouse.yaml` `schedules` (APScheduler, local time),
  catches up on runs missed while the machine was off, and records results in `.lighthouse/cache/`
  (off by default with `--demo`). `/api/jobs` lists jobs with their next run; any job can run on demand.
- `deadline-check`: alerts once per deadline at 14 / 3 / 1 / 0 days and when overdue, plus pipeline
  follow-ups within 3 days. A failed send is retried on the next run.
- `digest`: weekly summary of what changed, top metric moves, deadlines in the next 14 days, stale pipeline
  items (no movement in 14+ days), next actions and the Inbox count.
- `sync` now notifies about new candidates and sync errors.
- `lighthouse-gc validate` checks every schedule's cron expression.
- `data/calendar.ics` (RFC 5545, all-day events with a 1-day reminder) from open deadlines and pipeline
  follow-ups, regenerated on every change and byte-for-byte deterministic. Served at `/calendar.ics` for
  calendar apps on this machine (`webcal://127.0.0.1:7777/calendar.ics`).
- Calendar page: month view, add / mark done / delete deadlines, subscribe link, and the recurring jobs with
  their next run and a "Run now" button. Deadline API: `GET/POST /api/deadlines`, `PATCH/DELETE /api/deadlines/{id}`.
- Pipeline page: kanban (Idea / Applied / Waiting / Done) with drag-and-drop and ← / → buttons, inline
  follow-up dates, and stale flags for items with no movement in 14+ days (changing stage resets the
  clock; editing notes doesn't). API: `GET/POST /api/pipeline`, `PATCH/DELETE /api/pipeline/{id}`.
- Letters page: writer roster with relationship, criteria covered, status (mark sent / signed), last
  contact and draft link; per-criterion coverage by independent / employer / co-author writers (declined
  excluded). Draft paths must stay inside `drafts/`. API: `/api/letters`, `/api/drafts/{path}`.
- Calendar week view (remembered per browser) and a full edit dialog for deadlines (title, date, kind,
  link, "needs me", done, delete), opened by clicking any deadline in the month or week view or the list.
- Letters: per-writer asks (letter, membership reference) as checkboxes and an editable last-contact date.
- Service layer (`lighthouse_gc/service.py`): every create / update / move from the Inbox, Pipeline,
  Letters, Calendar and Evidence pages goes through one place and is recorded in `data/changes.jsonl`
  (actor, action, before / after). A guard test fails if a route writes workspace files outside it, if a
  new write route isn't covered, or if a page sends a write without the API client.
- Agent engine (ADR 0005): one `Engine` interface with a Claude Agent SDK adapter (`claude-opus-5-5`) and a
  Codex stub. The harness is locked down to `WebSearch` plus Lighthouse's tools: no shell, no file tools,
  no user settings, hooks or MCP servers, and no session transcripts on disk. Tools: the MCP read tools,
  read-only views of the Inbox / deadlines / pipeline / letters, `read_page` (http(s) only, refuses private
  and local addresses including after redirects, snapshots the page as a memory observation), and
  `propose_*` write tools that go through the service layer to the Inbox. Evidence proposals must cite a
  snapshot and a verbatim quote. Tool results are redacted (emails, phones, amounts) before the model
  sees them. Per-run and monthly token / dollar caps (`agent.budget` in `lighthouse.yaml`). Every run is
  saved in `agent/runs/`, chat conversations in `agent/conversations/`.
- Chat panel on every page (✦ Ask): streams the agent's answer; shows each tool call as it happens (web
  searches, pages read with links, files touched, proposals with a link to the Inbox); stop button;
  conversation picker; month-to-date tokens and cost. Conversations are saved in `agent/conversations/`.
  API: `POST /api/agent/chat`, `GET /api/agent/runs/{id}/stream` (Server-Sent Events), stop, conversations,
  status.
- Agent page: every run (chat, manual, scheduled) with a kind filter; a "Run a task" box; month-to-date
  spend against the caps; and per run: live stream while running (with Stop), the step-by-step timeline,
  sources read with their snapshot ids, proposals linked to the Inbox, workspace changes from the audit
  trail, tokens (in / out / cache read) and cost. `GET /api/changes?actor=` exposes the audit trail.
- Model per run type: `agent.models` in `lighthouse.yaml` (`chat` and `task` default to `claude-opus-5-5`,
  `mission` to `claude-sonnet-5-5`). The old single `agent.model` key still loads.
- Prompt caching verified for the system prompt and tool definitions (a test keeps that prefix byte-stable).
  The Agent page shows cached / written / uncached input tokens per run and the month's cache hit rate.
- Redaction redacts only currency amounts among numbers (symbols, codes and words, e.g. $185k, 92,000 USD,
  €4.5M, 1,200 dollars). Plain numbers (downloads, stars, citations, dates, versions, ids, percentages)
  always pass through; emails and phone numbers are still redacted. 56 test cases, and punctuation next to an
  amount is preserved.
- Autopilot (off by default; per category in Settings): tracker updates, metrics and Tier-1 deadlines can be
  applied by the agent without asking, each logged as `auto` in `data/changes.jsonl` with one-click undo on
  the Agent page (undo refuses if the record changed since). New agent tools `propose_tracker_update` and
  `record_metric` (quote must contain the number); `propose_deadline` can cite a page. With autopilot off they
  land in the Inbox as "Tracker updates" / "Metrics". Nothing that could affect a criterion is ever
  auto-applied; the autopilot service refuses it, and a test runs every write tool with everything on and
  proves no exhibit, criterion status, override or profile moved.
- Missions (off by default; Settings → Missions): a weekly opportunity scout and a daily what-changed check,
  run by the scheduler on the missions model, inside the budget caps. Results are on the Agent page (with
  "Run now") and go out as a `mission` notification. The daily check skips, spending nothing, when nothing
  changed.
- New scheduled jobs and notification events merge into an existing `lighthouse.yaml` with their defaults;
  set a schedule to `''` to turn a job off.
- Overview briefing: a "This week" card with what changed and three things to do, written by the agent
  (`publish_briefing`, saved to `data/briefing.json`). To-dos that are Inbox decisions have Approve / Dismiss
  right there. The daily what-changed mission refreshes it, and so does the Refresh button.

### Changed
- Chat import saves only conversations that produced a suggestion; the rest leave no content behind.
  `lighthouse-gc import <export> --keep-all` (or the checkbox on the Sources page) keeps every
  conversation. The import manifest records the total count and which conversations were kept.

### Fixed
- `metrics-snapshot` default schedule: cron can't express "biweekly" (`mon/2` meant something else);
  it now runs weekly on Mondays and the job skips unless 13+ days have passed.
- Request bodies for `/api/notify/test` were read as a query parameter (model defined inside the app factory).
- `read_page` treated a bot-protection response (HTTP 202, empty body) as a page and saved an empty snapshot.
  Empty, script-only and non-200 responses are now errors the agent sees, and nothing is snapshotted.
- The same text read at two URLs shared one observation and lost the second source. Observations are now keyed
  by source and content (the snapshot file is still shared).
- The chat panel crashed in browsers where `scrollIntoView()` returns a Promise (an effect returned it).

[Unreleased]: https://github.com/ris3abh/areao1/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ris3abh/areao1/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ris3abh/areao1/releases/tag/v0.1.0
