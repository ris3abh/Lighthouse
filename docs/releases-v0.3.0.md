# Area O1 v0.3.0 (draft release notes, not published)

Area O1 is a local-first command center for an O-1A or EB-1A evidence file. This release finishes the evidence
loop: what to save after each activity, a preflight that finds what a reviewer would notice, a view of the
evidence as a whole, and a review packet your attorney can work from, with every fact traceable to its page.

## Highlights

- **Build review packet** (ADR 0020). Your name on the cover; exhibits numbered by criterion (`C4-01`, the index
  says how); every approved fact matched to the page its quote is on. An outline grouped by exhibit, main fact
  first, in the source's own words ("Acme Robotics runs FastQueue, as captured on September 15, 2025 (Exhibit
  C5-01).") with a footnote giving the page and the quote. Then the totality of the evidence (O-1A) or final merits
  (EB-1A), and the open issues. PDFs keep their original pages; emails, web pages and Word files are re-rendered
  as readable text, and the original files are in the attorney ZIP. A review PDF, an editable .docx, a matrix
  CSV, PROV-JSON provenance and the attorney ZIP. Every page says "Draft for attorney review"; the same inputs give
  the same files. It is never a petition.
- **Final merits** (ADR 0019). Your counted evidence by year, and five themes marked strong, building or missing
  by rules in your profile, each with the evidence behind it. OpenAlex field benchmarks when you ask. The standard
  is quoted word for word from the Policy Manual and Kazarian, with section citations, and checked against your
  vault's copy. No score.
- **Evidence preflight** (ADR 0018). Old values presented as current, unapproved facts in letters, facts that
  disagree, undated exhibits, invitations without proof of completion. Dated history (last year's readership next
  to this year's) isn't flagged. It never blocks anything, and agents can run it read-only (`run_preflight`).
- **Proof recipes** (ADR 0017). When something is done, a checklist of what to save for its criterion; at
  "invited", the invitation and your acceptance. Uploads from a checklist are filed as the right kind of proof, and
  a reply from the verified organizer counts as a match.
- **Bulk review**. Filter a long Inbox, select many, accept or reject as one batch, undo the batch; `a` and `r`
  decide one card with Undo, and accepting evidence by key asks first.

## Upgrading from 0.2.0

- Nothing to migrate. Exhibits filed before dates were tracked can be dated from their documents:
  `areao1 repair-dates` shows the changes, `areao1 repair-dates --apply` makes them.
- Set who issued an exhibit on the Final merits page when it can't be read from the exhibit's address.

## Install

```sh
curl -LsSf https://raw.githubusercontent.com/ris3abh/areao1/main/install.sh | sh
```

After publishing: add the v0.3.0 Zenodo DOI to CITATION.cff's identifiers (and to tests/test_site.py).

Full list of changes: [CHANGELOG.md](../CHANGELOG.md).
