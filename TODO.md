# TODO — Phase 0

Running checklist against [SPEC.md](SPEC.md) section 11. Product-first ordering (section 11a).

## Phase 0 checklist

- [x] `lighthouse-gc init` creates a workspace from a template, with schemas and .gitignore
      (+ git init, gitleaks pre-commit hook, AGENTS.md)
- [x] O-1A and EB-1A profiles load; criteria engine computes the scoreboard from exhibits.json
- [x] GitHub (public + PAT) and Hugging Face connectors: discover, snapshot, candidates (fixture tests)
- [x] `lighthouse-gc import <url>` auto-detects the connector
- [x] metrics-snapshot appends to metrics.csv (upsert per day; GitHub 14-day traffic kept)
- [ ] `lighthouse-gc up` serves Overview, Sources, Metrics, Evidence and Inbox pages
      — API done and tested; React shell + Overview + Inbox written; Evidence, Metrics, Sources pages to do;
      build + browser check to do
- [x] DASHBOARD.md generated; demo workspace renders with no network (tested)
- [ ] Memory store (5b): observations from connectors; claims, edges, decisions as append-only JSONL with a
      rebuildable index; Inbox approves claims
- [ ] Core/profile split: `lighthouse_gc.core` imports nothing from immigration profiles; move the criteria
      engine to `lighthouse_gc/criteria/`; import-lint test
- [ ] Claims carry exact excerpt + offsets, event stage and extracted_by; criteria count only completed stages

## Repo scaffolding from the updated section 9

- [ ] `eval/`, `docs/adr/` (first ADRs: name `lighthouse-gc`, files-as-truth, product-first ordering)
- [ ] `CITATION.cff`, `CHANGELOG.md`, `ADOPTERS.md`
- [ ] `profiles/research-portfolio.yaml` (Phase 2 per checklist; stub dir placement only now)
- [x] Repo guard: `scripts/check_repo.py` via `.githooks/pre-commit` and `tests/test_repo_hygiene.py`
      (enable per clone: `git config core.hooksPath .githooks`)

## Known gaps / deferred

- GitHub dependents count (no API; needs HTML scraping) — deferred.
- Built web UI is gitignored; release CI must build it before the wheel (Phase 3).
- SQLite cache/index not needed yet; arrives with the memory store index.

## Product track queued for Phase 1 (section 11a)

- Claude / ChatGPT conversation-export import → Inbox candidates
- Notifications, scheduler, pipeline / deadlines trackers
