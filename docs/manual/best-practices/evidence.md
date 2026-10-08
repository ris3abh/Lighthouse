# Evidence that holds up

How to build an evidence file where every item is real, dated and traceable to its source.

Area O1 organizes evidence; it doesn't judge eligibility. A criterion marked **banked** only means your accepted exhibits meet the simple rule in the profile YAML. The habits below make the file easier for you and your attorney to rely on. They are practical suggestions, not legal advice, so confirm your strategy with an immigration attorney.

## Count what happened, not what was offered

An invitation is not a completion. Area O1 counts only evidence whose stage is completed, published or granted. An invitation to judge, a submitted paper or an accepted talk you haven't given yet stays in your trackers, but it doesn't count toward a criterion.

- When you upload an exhibit, set **Stage** honestly. The upload form says it plainly: only completed, published or granted count.
- Keep invitations in the Pipeline, and upload the proof once the event is done (a thank-you from the organizer, the published program, the reviewer record).
- For a certificate or a pay stub, choose "Not an activity".

See [Invited vs completed](../how-it-works/invited-vs-completed.md).

## Prefer primary documents to self-reports

Things you told Area O1 yourself (onboarding answers, chat imports, "I judged HackExample 2025") are **self-reported**. They keep your to-dos and trackers current, but they never count toward a criterion. The document that proves them does.

Good primary documents:

- an award letter or certificate from the organization that gave it
- a reviewer or program-committee record from the conference system
- the published article, with its title, date, author and outlet
- a membership letter that states the admission requirements
- an employment or salary document from the employer

Upload the real file on the Evidence page (**Upload exhibit**), not a summary of it.

## Keep the source text verbatim

Every fact Area O1 draws from a source is a claim that quotes the source word for word, with its position in the raw response. Nothing becomes evidence until you accept it in the Inbox. This lets anyone trace a number back to where it came from.

- Don't retype figures by hand when a connector can read them. A GitHub star count read from the API carries its quote; a number you typed doesn't.
- When the agent proposes evidence from a web page, it must quote the page it read. If the quote doesn't support the claim, reject it.

See [Claims and provenance](../how-it-works/claims.md).

## Capture pages with a date

Web pages change and disappear. An accepted candidate is written to `evidence/<criterion>/<criterion>_<yyyy-mm-dd>_<slug>.md`, so every capture carries its date in the file name. For important pages (press articles, award announcements, a judging roster), also save a PDF from your browser and upload it as an exhibit, so you have a copy if the page goes away.

Run `areao1 validate` now and then. It checks every workspace file against its schema and the evidence naming rules.

## Show the strength signals

Each criterion in a profile lists **strength signals**: what makes a piece of evidence strong for that criterion. For example, the O-1A awards criterion in `profiles/o1a.yaml` lists national or international scope, selectivity, and being awarded for excellence rather than participation. A criterion banks when it has enough accepted exhibits **and** enough distinct signals (`bank.min_exhibits` and `bank.min_signals`).

When you upload an exhibit, tick only the signals the document itself shows, under **Strength signals this document shows**. If an award is selective but the certificate doesn't say so, add a document that does (a published acceptance rate, the size of the field).

The EB-1A profile (`profiles/eb1a.yaml`) uses the same criterion ids with a stricter rubric: more exhibits and more signals for most criteria. Read both files on GitHub: [o1a.yaml](https://github.com/ris3abh/areao1/blob/main/profiles/o1a.yaml), [eb1a.yaml](https://github.com/ris3abh/areao1/blob/main/profiles/eb1a.yaml).

## Look for independent corroboration

One source saying something is weaker than several unrelated sources saying it. Some practical habits:

- Press: articles in several independent outlets, each primarily about you or your work.
- Contributions: adoption by people outside your team (downstream projects, citations, usage numbers) next to your own description.
- Letters: writers who know your work without having worked with you (see [Letters](letters.md)).

## Keep a metrics history

A single number is a snapshot; a trend shows impact over time. The `metrics-snapshot` job appends dated rows to `data/metrics.csv` (with GitHub's 14-day traffic, if your token allows it). When `areao1 up` is running it takes a snapshot about every two weeks; you can also run it yourself:

```sh
areao1 run metrics-snapshot
```

Keep it running from early on. GitHub only keeps 14 days of traffic data, so a gap in snapshots is a gap you can't fill later.

## Review every claim before you accept

Accepting a candidate approves its claims and files the exhibit. Before you accept:

1. Expand the claims behind the candidate and read the quoted source text.
2. Check the stage (invited or completed) and the criterion it's filed under.
3. Edit the title or summary if it overstates what the source says.
4. Reject anything you can't back up with a document.

Approval records your decision; it doesn't certify legal sufficiency. See [Review](../how-it-works/review.md).
