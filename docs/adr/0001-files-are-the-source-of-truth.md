# 1. Files are the source of truth

Date: 2026-10-06 · Status: accepted

## Context
Case data must be private, reviewable, diffable and editable by both people and agents, and must survive
the app being replaced.

## Decision
Every workspace fact lives in plain JSON / JSONL / CSV / Markdown inside the user's own Git repo, each with a
versioned JSON Schema. SQLite is only a cache/index under `.lighthouse/cache/` and can always be rebuilt.

## Consequences
Writes are atomic file replacements or appends; no migrations of a database are needed, but schema changes
need a `schema_version` bump. Concurrent writers are serialized per process only.
