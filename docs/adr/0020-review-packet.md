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

## Amendment (2026-10-08, after Checkpoint B)

The first outline wrote each sentence from the claim's raw parts ("Maya Chen: award received 17, Exhibit C1-01.
[clm_…]"), which read as a template and leaked ids. Now:

- **One plain sentence per approved claim**, from a template chosen by the exhibit's evidence type and the claim's
  predicate (`areao1/criteria/sentences.py`): "Maya received the Northwind Engineering Excellence Award in 2024
  (Exhibit C1-01)." A template fires only when its predicate is the exhibit's headline fact (it must match the
  whole predicate, so `award_selectivity` never becomes "received 3 of 412 nominees") and every slot it needs
  reads as words. A count whose unit is known gets a metric sentence ("FastQueue had 4,800 GitHub stars as of
  September 2025"); anything else quotes the exhibit ("Exhibit C1-01 states: “…”"), which is always true to it.
- **Claim ids become footnotes** in the .docx (real Word footnotes) and the PDF (numbered notes under each
  criterion): each says the exhibit, the page, the packet page and the quote. Full ids appear only in
  `matrix.csv` and in the machine-readable provenance files. The matrix's claim column uses the same sentence.
- The grounding rule is unchanged: every sentence is built from exactly one approved, current claim and cites it;
  any sentence that reads as an eligibility verdict is dropped, even when it's a quote.
- A guard (`sentences.problems`) names what would make a line unreadable: an unfilled slot, `None`, a raw id, a
  snake_case word, or a predicate spelled out before a number. The tests run it over every template and value
  shape, and over every reader-facing line of Maya's and Ravi's packets.
- In the packet's issue table, a low-severity rule with more than three issues is one row naming the first few;
  `preflight.json` keeps every issue.

## Amendment (2026-10-09): the source's words

A template may not change what its quote says. It is used only when one of its verbs is in the quote, and it
writes that verb ("Harborview Robotics adopted sparse-router", not "uses"); every name it writes (the person, the
organization, the work, the value) must be in the quote; a date is written as the quote states it, and when the
quote gives none the sentence says "as captured on <the exhibit's date>" instead of implying when it happened.
Otherwise the sentence quotes the exhibit. A test sweeps every template, evidence type, value shape and quote and
fails on any word the sentence adds beyond the template's fixed words, or a year the quote doesn't state.
