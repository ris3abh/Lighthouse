# Area O1 v0.3.0 (draft release notes, not published)

Area O1 is a local-first command center for an O-1A or EB-1A evidence file. This release finishes the evidence
loop: what to save after each activity, a preflight that finds what a reviewer would notice, a view of the
evidence as a whole, and a review packet your attorney can work from, with every fact traceable to its page.

## Highlights

- **Build review packet** (ADR 0020). Numbered exhibits by criterion (`C4-01`), an index with page ranges, every
  approved fact matched to the page its quote is on, an outline of plain sentences with footnotes ("Maya received
  the Northwind Engineering Excellence Award in 2024 (Exhibit C1-01)."), final merits and the open issues. A
  review PDF, an editable .docx, a matrix CSV, PROV-JSON provenance and an attorney ZIP. Every page says "Draft for
  attorney review"; the same inputs give the same files. It is never a petition.
- **Final merits** (ADR 0019). Your counted evidence by year, and five themes marked strong, building or missing
  by rules in your profile, each with the evidence behind it. OpenAlex field benchmarks when you ask. No score.
- **Evidence preflight** (ADR 0018). Outdated values still cited, unapproved facts in letters, conflicting facts,
  undated exhibits, invitations without proof of completion. It never blocks anything.
- **Proof recipes** (ADR 0017). When something is done, a checklist of what to save for its criterion.
- **Bulk review**. Filter a long Inbox, select many, accept or reject as one batch, undo the batch.

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
