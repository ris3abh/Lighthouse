# 0018. Evidence preflight

- Status: accepted
- Date: 2026-10-08
- Builds on: ADR 0004 (append-only claims, SUPERSEDES / CONTRADICTS), ADR 0017 (proof recipes)

## Context

Before an attorney sees a case, the same mistakes recur: a metric quoted as 1,840 stars in one document and
2,100 in another, a job title that differs between the offer letter and a support letter, a letter draft citing a
citation count that has since been superseded, an exhibit that is a web capture with no PDF, an invitation that
was never followed by proof of completion. Each one is cheap to fix early and expensive to discover late.

## Decision

1. **A deterministic check, no model.** `areao1/criteria/preflight.py` runs a fixed set of checks over the
   workspace's files and returns a report: each issue has a stable id (a hash of its kind and the records
   involved), a `kind`, a `severity` (`high`, `medium`, `low`), a plain-language `title` and `detail`, and `refs`
   linking to the exact claims, exhibits, letters or drafts involved, with values and dates where they differ.
2. **The checks.**
   | Kind | Severity | Finds |
   |---|---|---|
   | `superseded_cited` | high | an exhibit, letter or draft citing a claim that a newer value supersedes |
   | `unsupported_cited` | high | a letter or draft citing a claim that isn't approved, or doesn't exist |
   | `conflicting_facts` | high (names), medium (titles, employers, dates) | approved claims about the same person or entity that disagree on a name, title or employer (across related predicates, or a document's value replaced by another document's), and an exhibit dated more than three days from the event its source describes |
   | `metric_mismatch` | medium | the same metric with different values in different documents (both values and dates shown) |
   | `invited_not_completed` | medium | an activity at `invited` / `accepted` whose completion proof isn't linked (ADR 0017) |
   | `capture_without_primary` | medium | an exhibit that is only a web capture (`.md`, `.html`, `.txt`) with no PDF or primary copy linked |
   | `claim_without_exhibit` | low | an approved, current claim that no exhibit cites |
   | `undated_exhibit` | low | an exhibit whose date is only the day it was filed, with no dated claim behind it |
3. **Run on demand.** "Run preflight" (Evidence page, CLI `areao1 preflight`, MCP and agent read tool) writes the
   latest report to `data/preflight.json`. Issues the person dismisses (with a reason) are kept in the file and
   shown as dismissed; a later run keeps the dismissal while the issue's id is unchanged.
4. **Never a gate.** Preflight never blocks anything. The review packet (ADR 0020) always carries the open issues
   list, so an attorney sees what the person saw.

## Consequences

- Checks read only workspace files; a new check is a function plus a test with invented data.
- Identity checks compare normalized values (case, punctuation, common abbreviations), so "Sr. Engineer" and
  "Senior Engineer" don't conflict; a real disagreement still shows both values with their sources.
- Severity is about how likely a reviewer is to notice, never about the case's chances: no score, no
  probability (SPEC §2a).
