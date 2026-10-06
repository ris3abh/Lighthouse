# Lighthouse — Open-Source Build Spec

Oct 6, 2026 · @Rishabh Sharma

> **Name decision.** The project ships on PyPI as **`lighthouse-gc`**, the CLI command is **`lighthouse-gc`**,
> and the Python import package is **`lighthouse_gc`**. Wherever this spec says `lighthouse <cmd>` read
> `lighthouse-gc <cmd>`, and `lighthouse/` (the package dir) is `lighthouse_gc/`.

> **Priority: product first, research second.** The framing below is "evidence-grounded memory for agents",
> but the build order is user-first: Lighthouse must first be a friendly tool anyone can use out of the box.
> That means importing their Claude and ChatGPT sessions, dropping in evidence, updating trackers and getting
> notifications. The research and experimentation work (knowledge-vault rigor, evaluation harness, ablations,
> papers) comes after that product is solid. See section 11a.

## 1. What Lighthouse is

Lighthouse is an open-source system that gives long-running LLM agents an evidence-grounded memory. It turns
changing documents into traceable claims, routes them through human review, and lets future agents see what is
supported, disputed or outdated. Its first application is O-1A / EB-1A evidence organization: you point it at
your work (websites, GitHub repos public or private via PAT, Hugging Face, scholarly profiles, Gmail) and it
builds a living evidence file, metrics trend, pipeline, deadlines and web dashboard. The core (ingestion, claim
extraction, provenance, versioning, retrieval, review) is domain-agnostic; immigration criteria live in a
separate profile layer, and a second non-immigration profile (research portfolio) tests that the core
generalizes.

**The problem.** Building a case takes 6–18 months across many AI chats, inboxes and tabs. Requirements,
metrics, deadlines and who's-doing-what scroll away. Lighthouse makes a private workspace on disk the memory,
not the chat — one source of truth the agent keeps current, one screen to check.

**Who it's for.** Researchers, engineers, founders and creators assembling O-1 / EB-1 evidence, with or
without an attorney. It organizes evidence; it does not judge eligibility.

**Disclaimer (ships in README + dashboard footer).** Lighthouse is not legal advice and is not affiliated with
USCIS. Criteria profiles are community-maintained summaries of public regulations (8 CFR 214.2(o), 8 CFR
204.5(h)). Always confirm strategy with an immigration attorney.

## 2. Design principles

1. **Code is public, the case is private.** The app lives in the public repo. Each user's case lives in a
   separate workspace directory (its own private Git repo) created by `lighthouse init`. No personal data ever
   touches the app repo.
2. **Files are the source of truth.** Workspace data is Markdown + JSON + CSV in Git: human-readable,
   diffable, agent-editable. A local SQLite file is only a cache/index and can always be rebuilt from the files.
3. **Import, don't retype.** Every source is a connector that pulls facts and metrics automatically. Manual
   entry is the fallback, not the default.
4. **Human-in-the-loop for evidence.** Connectors and scans never file evidence directly. They drop candidates
   into an Inbox; the user accepts, edits or rejects. Approval records a decision; it does not certify truth or
   legal sufficiency.
5. **Thin app, fat agent.** The app does data, UI, scheduling and connectors. Writing, judgment and drafting go
   to the agent engine (Claude Code / Codex / API), which is swappable.
6. **Local-first, secrets never in Git.** Server binds to 127.0.0.1. Tokens live in the OS keychain. No
   telemetry. Optional Docker for an always-on private box.
7. **Reusable core, domain profiles.** `lighthouse.core` knows nothing about immigration. O-1A, EB-1A and the
   research-portfolio profile are YAML rubrics plus optional plugins, so the community can add domains without
   touching the core.
8. **Measure before claiming.** Every reliability claim in the README must come from the evaluation harness
   (section 5c). Graphs, provenance and human review are established ideas (see W3C PROV); the docs describe
   what Lighthouse implements and measures, not novelty.
9. **Ship in phases.** A usable dashboard with GitHub + Hugging Face import comes first; Gmail and opportunity
   scans come after.

## 3. Architecture

One local server owns data, UI, schedules and connectors; the agent engine does the writing and judgment;
everything lands in a private workspace only after you approve it.

The dashboard and chat call the server; the server pushes notifications and the calendar feed out. Connectors
and the agent both feed the inbox, and only approved items reach the workspace.

## 4. Import: source connectors

The import page takes a URL, a username or an account login and turns it into tracked sources. Each connector
implements one interface, so adding a new platform is one file.

```python
class Source(Protocol):
    kind: str                      # "github", "huggingface", ...
    def detect(url_or_handle) -> bool          # can I handle this input?
    def discover(handle, creds) -> list[Item]   # repos, datasets, papers, pages
    def snapshot(item, creds) -> list[Metric]   # dated numbers for metrics.csv
    def candidates(item, creds) -> list[Candidate]  # proposed evidence -> Inbox
```

| Connector | Input | Auth | Pulls (metrics + candidates) |
|---|---|---|---|
| GitHub | profile / org / repo URL | none for public; fine-grained PAT for private (read-only Metadata + Contents; Administration: read for traffic) | stars, forks, watchers, contributors, releases, 14-day views/clones (keep history, GitHub only retains 14 days), dependents, README, topics |
| Hugging Face | user / org / repo URL | none for public; read token for private/gated | model & dataset downloads (rolling 30d + all-time where available), likes, Spaces, Papers upvotes, linked repos |
| Website | any URL or sitemap | none | page text via readability, title/date/author, mentions of the user's name; classified as press / own-site / talk / award by the agent |
| Scholarly | ORCID, Semantic Scholar ID, OpenAlex ID, arXiv author | none (free APIs) | papers, citations, citing works, venues, h-index |
| Gmail | OAuth login or IMAP + app password | gmail.readonly scope, labels/queries you choose | judging & reviewer invites, acceptances, award notices, press requests, letter-writer replies, deadlines |
| Manual | file upload / form | — | any exhibit: certificates, letters, pay stubs, photos |

Notes for the builder:

- Google Scholar has no API and blocks scraping. Use Semantic Scholar + OpenAlex as defaults; offer Scholar
  only via an optional SerpAPI key.
- Gmail in an open-source app: gmail.readonly is a restricted scope, so a shared OAuth client would need Google
  verification. Each user creates their own Google Cloud OAuth client (setup wizard walks them through it). In
  "Testing" mode refresh tokens expire after 7 days, so also offer IMAP + app password as the low-friction path.
- Gmail privacy: only messages matching user-defined queries (e.g. `from:(devpost OR mlh) OR subject:(judge OR
  reviewer OR accepted)`) are fetched. Bodies stay local; only the minimum excerpt goes to the LLM for
  classification.
- LinkedIn / X: no import (ToS); support manual "paste a link" which goes through the Website connector.
- Rate limits: every connector uses ETag/conditional requests where supported, exponential backoff, and a
  per-source cache.

## 5. Evidence inbox and criteria engine

Every imported fact becomes a Candidate in the Inbox with: source, proposed criterion, one-line summary,
confidence, and a link to the raw item. Accepting it creates an Exhibit: a named file in
`evidence/<criterion>/`, logged in `data/exhibits.json`, and the scoreboard is recomputed.

Profiles are YAML rubrics in `profiles/`. Each criterion lists what counts, what evidence types satisfy it, and
the strength signals the engine checks.

```yaml
# profiles/o1a.yaml (excerpt)
id: o1a
name: O-1A Extraordinary Ability
threshold: 3            # criteria needed
target: 5
criteria:
  - id: judging
    label: Judging the work of others
    evidence_types: [judge_invite, reviewer_record, panel_letter]
    strength_signals: ["selective event", "multiple instances", "documented scoring"]
  - id: scholarly_articles
    label: Authorship of scholarly articles
    evidence_types: [paper, preprint, journal_article]
    strength_signals: ["peer-reviewed", "citations > 0", "major venue"]
  # ... awards, membership, press, original_contributions, critical_role, high_salary
```

- Statuses per criterion: **banked** (meets bar, documented), **building** (some evidence, more needed),
  **gap** (nothing yet), **dropped** (user decided not to pursue).
- Scoring: rule-based first (counts of accepted exhibits by type + signals). The agent adds a written "how a
  reviewer would see this" note, clearly labeled as an opinion.
- EB-1A is a second profile over the same evidence store: stricter rubric, plus a "final merits / sustained
  acclaim" narrative layer. Switching profile re-scores, never re-collects.
- Shipping profiles: o1a, eb1a in v1. Community targets: o1b, eb2-niw, uk-global-talent.

## 5a. Knowledge vault: verified O-1 / EB-1A guidance

Every statement Lighthouse makes about immigration rules (criteria wording, fees, forms, timelines, standards
of proof) must cite a vault source fetched within its freshness window, or it is shown as unverified and
blocked from petition-facing output. The vault cannot guarantee nothing is wrong; it guarantees every rule
claim is cited, dated, re-checked and flagged when it goes stale or conflicts.

What's in the vault (source tiers):

| Tier | Sources | Used for |
|---|---|---|
| 1 — Primary law & agency | 8 CFR 214.2(o), 8 CFR 204.5(h), INA 101(a)(15)(O) and 203(b)(1)(A) via eCFR; USCIS Policy Manual (O-1 and EB-1 chapters); I-129 / O supplement and I-140 instructions + current form editions; USCIS fee schedule; premium processing page; State Dept Visa Bulletin; Federal Register notices | criteria text, evidence rules, fees, forms, timelines, priority dates |
| 2 — Adjudication | Kazarian v. USCIS (two-step final-merits review), Matter of Chawathe (preponderance of evidence), AAO non-precedent decisions on O-1A / EB-1A | how criteria are applied, what fails |
| 3 — Secondary | attorney blogs, forums, practitioner guides | context only; never the sole source for a claim |

How it stays current:

- **Fetch + snapshot.** Each source is fetched, stored with URL, fetch time, content hash and effective date,
  chunked, and embedded locally (SQLite + sqlite-vec or LanceDB). Snapshots are kept, so you can see what a
  page said on any date.
- **Volatile-fact registry.** Facts that change get a TTL: fees and form editions 7 days, processing times 7
  days, Visa Bulletin monthly, regulations 30 days. Expired facts are re-fetched before use.
- **Change watch.** A daily vault-watch job diffs Tier 1 pages. A changed hash triggers a notification, marks
  every dependent claim stale, and lists what in your workspace it affects (e.g. a fee in your filing
  checklist).
- **Live fallback.** If the vault has no match, or the match is stale, the agent runs a web search restricted
  to Tier 1 domains first (uscis.gov, ecfr.gov, federalregister.gov, travel.state.gov, justice.gov), then
  Tier 2. New findings enter the vault as observations, not as facts (see 5b).

Grounded-answer rule (enforced, not suggested):

1. Agent drafts an answer or a dashboard text.
2. rule-check extracts each rule claim ("O-1A needs 3 of 8 criteria", "premium processing is 15 business
   days").
3. Each claim is matched to a vault chunk; the chunk must be fresh and must actually entail the claim (an LLM
   judge plus exact-quote check).
4. Pass → shown with an inline citation. Fail or stale → shown with an unverified badge, and it cannot be used
   in letters, the exhibit index or the attorney export until fixed.
5. Two Tier 1 sources disagree → shown as a conflict with both citations and a notification.

The vault ships as a public, community-maintained corpus manifest (`vault/sources.yaml` in the app repo: URLs,
tiers, TTLs). Fetched content and embeddings live in each user's workspace cache.

## 5b. Evidence-aware graph memory

Lighthouse's memory is a provenance graph, not a notes file: every fact the system knows is a claim tied to the
raw observation it came from, scored, dated, and approved by you before agents or petition documents may rely
on it. This replaces the chat-history problem with a store any agent can query.

The Evidence inbox (section 5) is stage 5's UI. Knowledge-vault rules (5a) enter the same graph as Tier 1
claims, so a draft letter's statement and the regulation it relies on sit one edge apart.

Data model:

| Node | Holds | Example |
|---|---|---|
| Observation | stable ID, raw snapshot, source URL or file, captured_at, sha256, connector | HF API response for a dataset |
| Claim | one factual statement: subject, predicate, value, event stage, event date, valid_from / valid_to, recorded_at, exact supporting excerpt + offsets, extracted_by (model + version), confidence, review status | "dataset X has 128 downloads", valid 2026-10-06 |
| Source | URL/domain, tier (1–3 or user), owner | huggingface.co, tier: platform |
| Entity | person, artifact (repo, dataset, paper), org, venue, event, letter writer | a hackathon, a co-author |
| Criterion / Rule | profile criterion or a vault regulation chunk | O-1A judging; 8 CFR 214.2(o)(3)(iii) |
| Exhibit | accepted file in evidence/ | judge invitation PDF |

| Edge | Meaning |
|---|---|
| DERIVED_FROM | claim → observation it was extracted from |
| ABOUT | claim → entity |
| SUPPORTS / CONTRADICTS | claim → criterion, rule or another claim |
| SUPERSEDES | newer claim → older claim on the same subject + predicate |
| REVIEWED_BY | claim → review record (decision, reviewer, timestamp, rationale) |
| CITES | exhibit or generated sentence → the approved claim IDs that support it |

**Confidence** is a band (high / medium / low), not a fake-precise number: Tier 1 or platform API sources start
high; LLM extraction from free text starts medium; corroboration by a second independent source raises it; age
past TTL or any CONTRADICTS edge lowers it.

**Review states:** proposed → corroborated (auto, ≥2 independent sources) → approved or rejected (you).
"Approved" means you recorded a decision, not that the claim is legally sufficient. Only approved, current,
source-supported claims can be cited in letters, the exhibit index or the attorney export. Revisions append a
new version; earlier versions and rejected claims are kept, so the same mistake isn't re-proposed.

**Event stages (invitation is not completion).** Activity claims carry a stage: invited → accepted → completed
(or declined). "We invite you to judge the event" supports *invited to judge*, never *completed judging*; a
later organizer confirmation supports completion. Both claims link to the same activity entity, and the
criteria engine only counts completed stages toward a criterion. The same rule applies to papers (submitted →
accepted → published) and memberships (applied → granted).

**Reasoning rule.** Agents draft only from current, approved, source-supported claims. Where proof is missing or
a conflict is unresolved, the draft states what is unknown and opens a review item instead of filling the gap.

**Temporal model (bitemporal):** valid_from/valid_to = when it was true in the world; recorded_at = when
Lighthouse learned it. Nothing is overwritten. This answers "what were my metrics on filing day?", powers the
trend charts, and shows exactly what changed since your last session.

**Agent memory:** agents never read raw chat. They call MCP tools: `query_claims(entity, as_of)`,
`get_provenance(claim_id)`, `what_changed(since)`, `find_gaps(criterion)`, `propose_claim(...)`. Agents may only
propose; verification is human. Each session starts with an auto-generated context pack (current scoreboard,
approved facts, open items, changes since last session), so a new chat starts where you left off.

**Storage:** start with versioned JSON in the workspace: `memory/claims.json`, `memory/relations.json`,
`memory/reviews.json`, `memory/outputs.json` (generated sentences → claim IDs), with raw source snapshots in
`memory/sources/` by hash. A local SQLite index is rebuilt from these files; a graph database is optional and
only added if queries demand it.

**Standards alignment.** The model maps onto W3C PROV: Source = prov:Entity, extraction and review =
prov:Activity, connectors, models and the user = prov:Agent; DERIVED_FROM = prov:wasDerivedFrom, REVIEWED_BY =
prov:wasAttributedTo via the review activity. `lighthouse export --prov` writes PROV-JSON so other tools can
read the graph.

**Dashboard:** a Memory page renders the graph (Cytoscape.js) with filters by criterion, entity, status and
date; a time slider replays it; clicking any number anywhere in the UI opens its provenance chain down to the
raw observation. A Knowledge page lists vault sources, freshness, recent rule changes and open conflicts.

## 5c. Evaluation harness

Lighthouse claims a reliability benefit only when this harness measures one. It compares three systems on the
same model, documents and token budget, using manually checked expected answers.

| System | What it is |
|---|---|
| Document RAG | chunks of the same sources, retrieved per question |
| Persistent-memory baseline | an off-the-shelf agent-memory approach (summaries / stored facts, no provenance or review) |
| Lighthouse | the claim graph with provenance, time, conflicts and approval |

**Scenarios** replay dated updates in order: judging (invite → accept → complete, plus a cancelled event),
publication (preprint → accepted → published, plus a retraction), conflicting metrics (two download counts from
different dates and endpoints), a rule change from the knowledge vault, and one non-immigration workflow
(research portfolio or grant reporting).

**Metrics:** unsupported-claim rate, citation correctness (does the cited excerpt entail the sentence),
stale-fact rate, invitation/completion errors, human review time per claim, latency and cost.

**Ablations:** remove graph links, temporal tracking and the approval gate one at a time to show what each
adds.

**Publishing:** fixtures, expected answers, scripts and failure cases live in `eval/` and run in CI on a small
subset. Every release attaches its results; the README quotes only numbers from the latest run.

## 6. Web dashboard

The dashboard is a first-class part of v1: a local web app at http://127.0.0.1:7777, started with
`lighthouse up`. It reads and writes the workspace through the API, so every UI change is also a Git-trackable
file change. DASHBOARD.md is still generated for terminal and agent use.

| Page | What it shows | Key actions |
|---|---|---|
| Overview | criteria scoreboard, profile progress (e.g. 2 banked / 3 needed), this week's human-only tasks, next 3 deadlines, metric sparklines | switch profile O-1A / EB-1A |
| Inbox | candidates from imports, Gmail and scans, grouped by criterion | accept, edit, reject, snooze |
| Evidence | exhibits per criterion with status have / need / gap, file previews, naming check | upload, re-map, mark gap |
| Metrics | line charts per source over time, deltas since last snapshot | snapshot now, export CSV |
| Pipeline | kanban of in-flight items (Idea, Applied, Waiting, Done) with staleness flags | add, move, set follow-up date |
| Letters | writer roster, relationship (employer / independent / co-author), criteria covered, status, draft | generate draft, mark sent / signed |
| Opportunities | scan results scored against your current gaps | add to pipeline, dismiss, mute source |
| Calendar | deadlines + recurring jobs, .ics subscribe link | add deadline |
| Sources | connected accounts and tracked items, last sync, errors | add source, re-auth, remove |
| Chat | side panel: agent with the whole workspace as context | ask, run a skill |
| Settings | engine, notification channels, schedules, profile, privacy toggles | test notification |

UX rules: one-screen Overview with no scrolling on a laptop; every number links to its source; dark/light
themes; works offline except for syncs.

## 7. Opportunity scans

Scans are scheduled search jobs that find things that would strengthen a weak criterion, then rank them by fit.
They run weekly by default and land in the Opportunities page, never directly in the pipeline.

| Scan | Feeds criterion | Sources |
|---|---|---|
| Hackathon judging | judging | Devpost, MLH, university hackathon sites |
| Peer review | judging | OpenReview venue reviewer calls, TMLR / journal reviewer signups, workshop PC calls |
| CFPs / talks | scholarly articles, press | WikiCFP, conference sites, meetup/talk CFPs |
| Awards & fellowships | awards | curated list in scans/awards.yaml (community-maintained) |
| Memberships | membership | IEEE Senior Member, ACM Distinguished/Senior, other selective bodies listed in the profile |
| Press | published material | journalist requests, newsletters accepting contributor features |

How a scan works: a scan is a YAML job (query, sources, criterion, schedule, filters like remote-only or
region). The runner fetches feeds/APIs where they exist and falls back to the agent's web search for the rest.
Each result is de-duplicated, given a fit score (gap criterion × deadline proximity × selectivity), and
summarized in one line.

Guardrails: respect robots.txt and ToS, cap requests per run, low volume by design (this is a weekly digest,
not a crawler). Users can add custom scans from the UI.

## 8. Scheduler, notifications, calendar, agent and chat

**Scheduler.** APScheduler runs inside `lighthouse up`. For machines that aren't always on,
`lighthouse run <job>` is a headless CLI that cron / launchd / GitHub Actions can call. Default schedule (all
editable in Settings):

| Job | Default | Does |
|---|---|---|
| sync | daily 08:00 | refresh all sources, push new candidates to Inbox |
| metrics-snapshot | Mon, biweekly | append dated rows to metrics.csv, store GitHub traffic before it expires |
| deadline-check | daily | alert on anything due within 14 days, regenerate calendar.ics |
| gmail-triage | every 6 h | classify matching emails into candidates / pipeline updates |
| opportunity-scan | Fri | run scans, score, list on Opportunities |
| digest | Fri 17:00 | weekly summary: what changed, stale pipeline items (no movement in 14 days), next actions |

**Notifications.** Pluggable channels: desktop (OS-native), email (SMTP), Slack / Discord webhook, ntfy.sh
push. Each event type can route to a different channel.

**Calendar.** calendar.ics is generated from deadlines + pipeline follow-ups and served at a local subscribe
URL. Optional one-way push to Google Calendar via OAuth.

**Agent engine.** (Design: `docs/adr/0005-agent-layer.md`.) The harness is locked down to web search
plus Lighthouse's own tools; agent writes go through the service layer and only *propose* to the Inbox
(autopilot rules may auto-apply a narrow class of tracker updates with undo); every run is recorded in
`agent/runs/` with its sources, proposals, changes and cost; per-run and monthly budgets live in
`lighthouse.yaml`. One adapter interface, three implementations: Claude Code (`claude -p` headless), Codex
(`codex exec`), or direct Anthropic/OpenAI API. Skills live in `skills/` and are copied into each workspace's
`.claude/skills/` (and an AGENTS.md for Codex):

- dashboard-generate, metrics-snapshot, evidence-intake, criteria-status, deadline-notify
- opportunity-scan, gmail-triage, letter-draft, petition-outline (EB-1 final-merits narrative)

**Chat.** Lighthouse ships an MCP server (`lighthouse mcp`) exposing tools like get_scoreboard, list_gaps,
add_candidate, update_pipeline, draft_letter. That gives "access to everything" in three places at once: the
dashboard's chat panel, Claude Code / Codex in the terminal, and any MCP-capable desktop client. Writes from
chat go through the same Inbox approval as imports.

## 9. Repo and workspace structure

Public app repo (what goes on GitHub):

```
lighthouse/
├── README.md  LICENSE  DISCLAIMER.md  SECURITY.md  CONTRIBUTING.md
├── pyproject.toml
├── lighthouse/
│   ├── cli.py               # init, up, run <job>, import <url>, mcp
│   ├── core/                # domain-agnostic: models, store, claims, provenance, review, retrieval
│   ├── criteria/            # domain layer: scores profiles over approved claims
│   ├── sources/             # github.py huggingface.py website.py gmail.py
│   │                        # semantic_scholar.py openalex.py orcid.py arxiv.py manual.py
│   ├── jobs/                # scheduler + sync, snapshot, deadlines, triage, scan, digest
│   ├── notify/              # desktop.py email.py slack.py discord.py ntfy.py
│   ├── engine/              # claude_code.py codex.py api.py
│   ├── mcp/                 # MCP server
│   └── server/              # FastAPI routes, serves built web UI
├── web/                     # React + Vite + Tailwind dashboard
├── profiles/                # o1a.yaml eb1a.yaml research-portfolio.yaml (+ community)
├── scans/                   # default scan jobs + awards.yaml
├── skills/                  # agent skills copied into workspaces
├── examples/demo-workspace/ # fictional persona "Alex Rivera" with seeded data
├── eval/                    # scenarios, fixtures, expected answers, baselines, results
├── docs/adr/                # dated architecture decision records
├── CITATION.cff  CHANGELOG.md  ADOPTERS.md
└── tests/
```

Private workspace (created by `lighthouse init ~/my-case`, its own private Git repo):

```
my-case/
├── lighthouse.yaml          # profile, schedules, channels (no secrets)
├── DASHBOARD.md             # generated
├── data/
│   ├── person.json          # name, field, status, filing target, petitioner
│   ├── sources.json         # connected sources + tracked items
│   ├── inbox.json           # pending candidates
│   ├── exhibits.json        # accepted evidence -> criterion
│   ├── criteria.json        # computed scoreboard
│   ├── metrics.csv          # date,source,item,metric,value
│   ├── pipeline.json  letters.json  deadlines.json  opportunities.json
│   └── calendar.ics         # generated
├── evidence/<criterion>/    # exhibit files, enforced naming: <crit>_<yyyy-mm-dd>_<slug>.<ext>
├── memory/                  # claims, relations, reviews, outputs JSON + sources/ snapshots
├── drafts/letters/
├── .claude/skills/  AGENTS.md
└── .gitignore               # .lighthouse/cache, *.db, any .env
```

Every JSON file has a versioned JSON Schema in `lighthouse/core/schemas/`, so agents and the UI validate the
same shape. Example letter record: `{id, name, relationship: employer|independent|coauthor, credentials,
criteria: [...], asks: [letter, membership_ref], status, draft_path, last_contact}`.

## 10. Tech stack, security and privacy

| Layer | Choice | Why |
|---|---|---|
| Backend + CLI | Python 3.11+, FastAPI, Typer, pydantic | best client libraries for HF (huggingface_hub), GitHub (httpx/PyGithub), Gmail, scholarly APIs |
| Scheduler | APScheduler (in-process) + `lighthouse run` for cron/launchd/Actions | no separate daemon to install |
| Web UI | React + Vite + Tailwind + Recharts, built into the Python package | one `pipx install lighthouse` gives everything |
| Storage | files in Git; SQLite cache in `.lighthouse/` (gitignored) | rebuildable index, fast queries for charts |
| Secrets | OS keychain via keyring; .env fallback (gitignored) | tokens never touch Git |
| Agent | Claude Code (default) / Codex / API adapter | config-swappable |
| Distribution | pipx, Docker image, GitHub Actions template | local, always-on box, or cloud-triggered |

Security and privacy requirements:

- Server binds to 127.0.0.1 only; Docker mode requires a password and is documented as LAN/VPN-only.
- PATs are read-only and the setup wizard links to pre-filled fine-grained token pages with minimum scopes.
- `lighthouse init` sets up a pre-commit hook (gitleaks) that blocks commits containing tokens.
- No telemetry. No calls except to sources the user connected and the chosen LLM.
- "Redact before LLM" toggle strips emails, phone numbers and salary figures from text sent to the engine.
- `lighthouse export` produces a zip of exhibits + an exhibit index for the attorney; `lighthouse purge` wipes
  cache and tokens.

## 11. Build phases

Each phase ends with something usable. Don't start the next phase until the current one's checklist passes
against the demo workspace and your own.

### Phase 0 — Core + dashboard (weekend 1)

- [ ] `lighthouse init` creates a workspace from a template, with schemas and .gitignore
- [ ] O-1A and EB-1A profiles load; criteria engine computes the scoreboard from exhibits.json
- [ ] GitHub (public + PAT) and Hugging Face connectors: discover, snapshot, candidates
- [ ] `lighthouse import <url>` auto-detects the connector
- [ ] metrics-snapshot appends to metrics.csv
- [ ] `lighthouse up` serves Overview, Sources, Metrics, Evidence and Inbox pages
- [ ] DASHBOARD.md generated; demo workspace renders with no network
- [ ] Memory store (5b): connectors write observations; claims, edges and decisions as append-only JSONL with a
      rebuildable index; Inbox approves claims
- [ ] Core/profile split: `lighthouse.core` imports nothing from immigration profiles (enforced by an
      import-lint test)
- [ ] Claims carry exact excerpt + offsets, event stage and extracted_by; criteria count only completed stages

### Phase 1 — Automation (weekend 2)

- [ ] Website + Semantic Scholar / OpenAlex / ORCID / arXiv connectors
- [ ] Scheduler with default jobs; `lighthouse run <job>` headless
- [ ] Notifications: desktop, email, Slack/Discord, ntfy
- [ ] Deadlines + calendar.ics + Calendar page; Pipeline kanban with staleness
- [ ] MCP server + Claude Code / Codex adapters + skills; Chat panel
- [ ] Knowledge vault (5a): vault/sources.yaml, fetch + snapshot + local embeddings, TTL registry, vault-watch
      job, Tier-1-first web search fallback
- [ ] rule-check gate on every agent answer and dashboard rule text; unverified / conflict badges; Knowledge page

### Phase 1c — Agent layer (see ADR 0005)

- [x] Agent engine: Claude Agent SDK adapter (Codex stubbed behind the same interface), web search on, the MCP
      read tools attached, plus write tools that call the service layer: they propose to the Inbox, or
      auto-apply per autopilot rules. Per-run and monthly token budget caps in lighthouse.yaml. Model mocked
      in tests.
- [x] Chat panel docked on every page: streaming, each tool call visible (search, page read, file touched),
      proposals linked to the Inbox, conversations saved in the workspace.
- [x] Agent page: every run (chat, manual, scheduled) with live stream, sources read, changes and proposals
      made, cost per run.
- [x] Autopilot rules: auto-apply with undo for tracker updates, metrics and Tier-1 deadlines; anything that
      could affect a criterion always needs approval.
- [x] Missions on the existing scheduler: weekly opportunity scout, daily what-changed check; results on the
      Agent page and via notifications.
- [ ] Overview briefing: agent-written "what changed / 3 things to do", with inline approvals.

### Phase 2 — Gmail, scans, letters (weekends 3–4)

- [ ] Gmail via OAuth (own client) and IMAP; query-scoped triage into Inbox
- [ ] Opportunity scans (judging, reviewing, CFPs, awards, memberships) + Opportunities page
- [ ] Letters page + letter-draft skill (per writer × criterion)
- [ ] EB-1A final-merits narrative layer; attorney export
- [ ] Memory page (graph view, time slider, provenance drill-down) + session context packs + MCP memory tools
- [ ] Evaluation harness (5c): three systems, five scenarios, metrics, ablations; research-portfolio profile +
      demo workspace

### Phase 3 — Open-source launch

- [ ] Docs site, setup wizard screenshots, 3-minute demo video using the demo persona
- [ ] pipx release, Docker image, GitHub Actions template
- [ ] Contributor guides for new connectors, profiles and scans
- [ ] Each release attaches eval/ results and a Zenodo DOI; PROV-JSON export documented

## 11a. Priorities: product first, research second

Lighthouse is a user-friendly tool first. Before the research and experimentation work, it must be something
anyone can install and use out of the box:

1. **Import your AI sessions.** Bring in Claude and ChatGPT conversation exports so the context scattered
   across chats becomes candidates in the Inbox (through the same approval flow as every other connector).
2. **Drop in evidence.** Upload certificates, letters, screenshots and PDFs with no setup.
3. **Update trackers.** Pipeline, deadlines, letters and metrics stay current with minimal typing.
4. **Get notified.** Deadlines, stale items and new candidates reach you on your chosen channel.

The research track comes after the product track is solid: knowledge-vault rigor (5a), the full claim graph
(5b), the evaluation harness, ablations and publications (5c). When ordering work inside a phase, product
items go first. Research items stay in the spec so the data model is designed for them from day one.

## 12. Open-source hygiene and kickoff

- License: Apache-2.0 (patent grant, friendly to companies and law firms adopting it).
- Fresh history: start a new repo; never fork from a private case repo. Run `gitleaks detect` before the first
  push.
- Demo data only: the demo persona, employer and metrics are fictional. Your own case becomes your private
  workspace, not part of the project.
- **Two repositories for contributor-users.** Anyone who both contributes and builds their own case keeps two
  separate repos: a public fork of the app for contributions, and a private workspace repo (created with
  `lighthouse init`, never a fork) for their case. Filing documents must never be committed to the public fork.
  GitHub forks of a public repo can't be made private, so the case repo must be a fresh private repo.
- Contribution surfaces: connectors, profiles, scans and skills each have a template + test fixture, so
  contributors never need real credentials (recorded API responses via respx/VCR).
- CI: lint, type-check, unit tests against fixtures, build web UI, schema validation of examples/.
- Dated, citable record: CITATION.cff, a Zenodo DOI per release, CHANGELOG.md, and ADRs in docs/adr/ so design
  decisions and authorship are timestamped from day one.
- Adoption, opt-in only: ADOPTERS.md and case studies are submitted by users with consent, describing what they
  use it for and why. No telemetry, ever; impact records never mix with anyone's private case.
- Positioning: the README leads with "evidence-grounded memory for long-running LLM agents, first applied to
  O-1A / EB-1A", cites W3C PROV, and makes no novelty or performance claims beyond the latest eval results.

Kickoff prompt for Claude Code / Codex (paste with this doc exported as SPEC.md):

```
Read SPEC.md. Build Phase 0 only.
1. Scaffold the public repo exactly as in section 9.
2. Write JSON Schemas + pydantic models for every workspace file first,
   including the memory store (observation, claim, edge, decision) in section 5b.
3. Implement the Source protocol, then GitHub and Hugging Face connectors with
   recorded-fixture tests (no live network in tests).
4. Implement the criteria engine against profiles/o1a.yaml and eb1a.yaml.
5. Build the FastAPI server and React pages: Overview, Sources, Metrics, Evidence, Inbox.
6. Create examples/demo-workspace with a fictional persona.
Stop when every Phase 0 checkbox passes. Keep a running TODO.md and do not
add features outside Phase 0.
```

Open decisions: project name ("Lighthouse" may collide on PyPI; check before publishing) — **resolved:
`lighthouse-gc`** — and whether to ship a hosted demo of the dashboard with the fictional persona (open).
