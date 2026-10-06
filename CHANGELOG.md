# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

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

### Changed
- Chat import saves only conversations that produced a suggestion; the rest leave no content behind.
  `lighthouse-gc import <export> --keep-all` (or the checkbox on the Sources page) keeps every
  conversation. The import manifest records the total count and which conversations were kept.

### Fixed
- `metrics-snapshot` default schedule: cron can't express "biweekly" (`mon/2` meant something else);
  it now runs weekly on Mondays and the job skips unless 13+ days have passed.
- Request bodies for `/api/notify/test` were read as a query parameter (model defined inside the app factory).
