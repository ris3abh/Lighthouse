# 4. Append-only claim memory with verbatim excerpts

Date: 2026-10-06 · Status: accepted

## Context
Agents must not rely on facts nobody can trace, and the same mistake must not be re-proposed after a user
rejects it. Chat history is not an auditable memory.

## Decision
Connectors attach the raw response they read. The store keeps it as a content-addressed snapshot
(`memory/sources/<sha256>`) and appends claims to `memory/claims.jsonl`; every claim carries the exact excerpt
and its offsets into that snapshot, and the store refuses a claim whose excerpt isn't found verbatim. Edges
(DERIVED_FROM, ABOUT, SUPERSEDES, REVIEWED_BY, CITES) and review decisions are appended too; nothing is
rewritten. A different value on the same subject + predicate SUPERSEDES the previous claim; the same value
from an independent connector corroborates it. Claims are bitemporal (`valid_from` vs `recorded_at`).
JSONL for the first version (Phase 0 checklist) instead of the single JSON files sketched in SPEC 5b's
storage note, because append-only lines diff and merge cleanly in Git.

## Consequences
Review status is derived (latest decision, else corroborated / proposed). The SQLite index is disposable.
Editing a snapshot is detected by `lighthouse-gc validate` (sha256 + exact-quote check).
