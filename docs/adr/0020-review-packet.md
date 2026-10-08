# 0020. The review packet

- Status: accepted
- Date: 2026-10-08
- Builds on: ADR 0004 (provenance), ADR 0017 (proof recipes), ADR 0018 (preflight), ADR 0019 (final merits)

## Context

The end of the loop is handing the case to an attorney. Today that means zipping a folder by hand. What an
attorney needs is an organized, numbered set of exhibits with an index, a way to check every factual sentence
against its source, the open issues, and a starting outline they can rewrite. What Area O1 has that no folder of
PDFs has is the provenance chain: claim to exhibit to the page and quote.

## Decision

1. **"Build review packet"**, never "generate petition". The packet is for attorney review. Every page of it and
   every generated paragraph is labeled "Draft for attorney review".
2. **Contents.**
   - **Exhibit numbering per criterion**: `C<n>-<nn>`, where `n` is the criterion's position in the active profile
     (Awards is C1 in O-1A) and `nn` the exhibit's order within it (by date, then title). Only counted exhibits
     are numbered; self-reported material never enters the packet as evidence (SPEC §2a).
   - A **table of contents** and a **criterion-specific exhibit index** (number, title, date, type, stage, pages).
   - The **claim -> exhibit -> page/quote matrix**: for every approved claim an exhibit cites, the claim, the
     exhibit number, the page where the quote appears (found by searching the exhibit's text; "not found" when it
     isn't, never guessed) and the verbatim quote.
   - A **support-letter / petition outline** drafted only from approved claims (template, or the hard model tier
     with the same grounding filter as letter drafts): every sentence ends with the claim ids behind it, unsupported
     sentences are dropped, eligibility verdicts are removed.
   - The **open preflight issues** (ADR 0018) and the **final merits** summary (ADR 0019).
3. **Outputs**, written to `exports/packet-<date>/` in the workspace:
   - an editable **.docx** (written directly as Office Open XML, no extra dependency),
   - a **review PDF** with continuous pagination ("Page 12 of 140" on every page, exhibits included) and an index
     that gives each exhibit's page range; exhibits that are PDFs are included as they are, images placed on
     pages, text captures typeset,
   - an **attorney export ZIP**: the packet (.docx and PDF), the original exhibit files, the matrix as CSV, the
     preflight issues, `provenance.json` (claims, observations, decisions, edges for the cited claims) and
     `provenance.prov.json` (W3C PROV-JSON).
4. **Reproducible.** The same inputs produce byte-identical outputs: ordering is deterministic, dates inside the
   files come from the inputs (the latest decision time), not the clock, and ZIP entries carry fixed timestamps. A
   `manifest.json` records the input hash; the packet's cover shows it.
5. **PDF library.** ReportLab (BSD) for typesetting, with its `invariant` mode for reproducible output; pypdf
   (already a dependency) to merge exhibit PDFs and stamp page numbers.

## Consequences

- One new dependency (ReportLab). The .docx writer is small and tested against a schema-valid minimal document.
- The packet is a snapshot: it doesn't update when the workspace changes. Building again writes a new folder;
  the same inputs give the same files.
- "Petition", "file" and "submit" stay out of the UI's verbs; the guard test checks the labels.
