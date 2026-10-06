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
- No CI workflow file yet (lint, mypy, pytest, web build, schema validation): add before the first push.

## Product track next (section 11a, Phase 1)

- Claude / ChatGPT conversation-export import → Inbox candidates
- Notifications, scheduler, pipeline / deadlines trackers
