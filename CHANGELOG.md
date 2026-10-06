# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- GitHub Actions CI: repo guard, ruff (lint + format), mypy, pytest on Python 3.11 and 3.13,
  `lighthouse-gc validate` on every example workspace, and the web type-check + build.
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
