# 0019. The final merits workspace

- Status: accepted
- Date: 2026-10-08
- Builds on: ADR 0006 (vault and rule check), ADR 0012 (constellation), profiles' `narrative` layer

## Context

For EB-1A, meeting three criteria is step one. Under the two-step review in Kazarian v. USCIS and the USCIS
Policy Manual (Vol. 6, Part F, Ch. 2), the officer then weighs the totality of the evidence: is the acclaim
sustained, is it recognized beyond the person's own employer, how does the record compare with others in the
field. O-1A reviews also look at the evidence as a whole. The `eb1a.yaml` profile already names this layer
(`final_merits`) and leaves it "written by the agent". A model's opinion of someone's acclaim is exactly the kind
of guess Area O1 should not make.

## Decision

1. **A Final merits page, built from rules over approved evidence.** It shows:
   - **Sustained-acclaim timeline**: counted exhibits (approved, completed, not self-reported) by year and by
     criterion, with the span of years and the gaps.
   - **Themes**, each with a status of `strong`, `building` or `missing` computed by a rule, the exhibits behind
     it, and a sentence saying why. The themes and their rules:
     | Theme | Strong when | Building when |
     |---|---|---|
     | Independent recognition | at least half of letter writers are independent and at least 2 are | any independent writer, or an award / press exhibit from outside the employer |
     | Recognition outside the employer | at least 3 counted exhibits from organizations other than the employer | at least 1 |
     | Evidence across multiple years | counted exhibits in at least 3 distinct years | 2 distinct years |
     | Peer-relative context | at least 1 field benchmark (OpenAlex) or 2 exhibits carrying a selectivity signal | 1 selectivity signal |
     | External adoption / implementation | adoption exhibits or claims from at least 2 independent adopters | 1 |
     The thresholds live in the profile (`final_merits.themes`), not in code, so they're visible and editable.
   - **Field benchmarks** from OpenAlex where available: for the person's works, OpenAlex's citation percentile
     against works of the same field and year. Fetched only when the person presses the button, stored as claims
     quoting the OpenAlex response, and shown as context ("cited more than 92% of 2023 works in its field"), never
     as a verdict.
   - **Citations to the standard**, rule-checked: the page's explanation of the two-step review cites Kazarian and
     the Policy Manual passages from the vault, and each sentence carries the rule-check badge (verified,
     unverified, conflict). An unverified sentence is shown as unverified, not hidden.
2. **No score, no probability, no verdict** (SPEC §2a). Statuses describe the evidence in the workspace against a
   visible rule; the page says what each status means and that the officer's weighing is holistic.
3. **O-1A too.** The same page works for O-1A with the profile's own themes; it's labeled as a view of the
   evidence as a whole, not as a separate legal step.

## Consequences

- `profiles/*.yaml` gain a `final_merits` block (themes with rule thresholds); `narrative` prompts stay for the
  outline (ADR 0020).
- Employer is read from approved `employer` / `role_title` claims and the person's profile; exhibits name their
  organization in a field the person can correct, so "outside the employer" is checkable.
- OpenAlex calls are the only new network use; they're user-initiated and cached as claims.

## Amendment (2026-10-09): watching the quoted wording

The standard is quoted word for word, so a change in the source's wording has to be noticed.
`areao1/vault/standard.py` compares a source's current text with the quoted passages and with the community
library's newest hash-verified snapshot, sentence by sentence.

- **Daily, on the person's machine**, inside `vault-watch` (no separate job): the quoted sources are read live,
  because uscis.gov serves a browser-like client there. A change opens a GitHub issue with `gh` only when
  `vault.report_wording` is on (default off, so no install files issues on anyone's behalf). A fresh snapshot is
  pushed to the community library only when `vault.share_captures` is on and the person can push to it, when the
  wording changed or the library's newest copy is over 30 days old. Nothing is concluded from a page that didn't
  load.
- **Weekly, in CI** (`scripts/check_vault_fixtures.py`): Kazarian is read live; uscis.gov blocks GitHub's runners, so
  the Policy Manual chapters are compared through the community snapshot, reported with its capture date. Only a
  real mismatch fails; a source with neither a live copy nor a snapshot newer than 30 days is "stale", a warning.
