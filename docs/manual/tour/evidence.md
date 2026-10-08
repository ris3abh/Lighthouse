# Evidence

Your accepted exhibits, criterion by criterion, and what each criterion still needs.

![The Evidence page: the Awards criterion is building, with its strength signals and one completed exhibit](../assets/shots/evidence-light.webp#only-light)
![The Evidence page: the Awards criterion is building, with its strength signals and one completed exhibit](../assets/shots/evidence-dark.webp#only-dark)


## What's on it

- **The drop zone.** Drop certificates, letters, screenshots, PDFs or `.eml` emails, or click to choose.
  They go to your [Inbox](inbox.md) with a suggested criterion and stage; nothing is filed until you accept.
  Drop onto a criterion to propose it there.
- **One card per criterion**, with its status, *have / need* counts, and its **strength signals** (for
  Awards: national or international scope, selective, awarded for excellence). Signals your exhibits show are
  marked; the card says what's missing ("Needs 1 more strength signal").
- **Exhibits** under each criterion, with date, evidence type and stage. **Preview** opens the file;
  **Re-map** moves it to another criterion.

## Card actions

| Action | Use it when |
|---|---|
| **Upload** | You have a document for this criterion. You'll pick its evidence type, date, stage and the strength signals it shows. |
| **Mark gap** | Treat the criterion as a known gap whatever its evidence. |
| **Drop** | You've decided not to pursue this criterion; it leaves the count. |

Files live in `evidence/<criterion>/` in your workspace, named `<criterion>_<yyyy-mm-dd>_<slug>`, and are
listed in `data/exhibits.json`. Switching between O-1A and EB-1A re-scores the same exhibits against the other
profile.

See also: [Evidence that holds up](../best-practices/evidence.md).
