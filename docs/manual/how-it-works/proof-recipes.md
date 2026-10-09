# Proof recipes

Once an activity is done, the proof behind it gets harder to find every week. A proof recipe lists what to save
while it's still easy to get.

## What a recipe is

There is one recipe per criterion, such as judging, awards or press. Each recipe lists items worth keeping. For
judging, that's the invitation, your acceptance, proof your reviews were submitted, the thank-you or certificate,
the event page that lists you, the organizer's standing, how many submissions you judged, and how judges were
selected.

Each item has a label and a one-line reason. An item marked "if available" is optional and never counts as
missing.

Recipes are suggestions of what reviewers commonly look for, not legal requirements. The checklist says so.

## When a checklist appears

An activity gets a proof checklist when it reaches a stage that matters:

- an exhibit at `accepted`, `completed`, `granted` or `published`,
- a [pipeline](../tour/pipeline.md) item moved to done,
- an approved claim at one of those stages that no exhibit cites yet.

A document with no stage (a certificate, a page) doesn't get one: it's usually the proof for an activity.
Self-reported exhibits don't get a checklist, and neither does an exhibit you linked as another activity's proof.
For more on stages, see [Invited vs completed](invited-vs-completed.md).

### At "invited": two items first

An activity still at `invited` gets a short checklist, "Invited: save these now": **the invitation** (usually done
already, by the invitation itself) and **your acceptance or the organizer's confirmation**. Once you save the
acceptance, the activity counts as accepted and the full recipe takes over, with both items already done.

The checklist is worked out each time you open the page, from the recipe and what you've saved. Nothing is
generated ahead of time, so a recipe edit applies to every activity at once.

## The checklist on Evidence

The checklists sit in the **Proof to save** panel on the [Evidence page](../tour/evidence.md). Each activity shows
its title, stage, criterion and date, and a count such as "3/8 saved · 4 to save". The first activity with gaps is
open; click any other to expand it.

An item is done only when an exhibit preserves it. That can be:

- **the activity's own exhibit**, when its evidence type and stage fit the item (a thank-you filed at `completed`
  is the completion, not the invitation),
- **an exhibit you link**, or
- **a new upload** filed from the checklist.

For each missing item you can:

| Button | What it does |
|---|---|
| **Upload** | Opens **Save proof** for that criterion, with the item's label as the title and its evidence type and stage already set (the thank-you is filed at `completed`, the acceptance at `accepted`). The file is filed as an exhibit and linked to the item. |
| **Link** | Choose an existing exhibit. "Looks like a match" lists up to three likely ones; "Link (2 likely)" says how many. |
| **Not applicable** | Say why it doesn't apply, then **Save**. The item is struck through. |

A linked item has **Unlink**, and a not-applicable item has **Undo**. Links and reasons are saved in
`data/proofs.json`, and every change is logged.

A self-reported exhibit can be linked for your own tracking, but it shows "Self-reported, doesn't count" and the
item stays missing.

On the [Pipeline](../tour/pipeline.md) page, a done item with gaps shows "N proof to save", linking to its checklist.

## Missing items in This week

Activities with missing items show up in **This week** on the [Overview](../tour/overview.md), one line each, such
as "Judging at Example Hacks: 3 proof items to save". The most recent activities come first, at most five. Each
line opens that activity's checklist on Evidence.

## Matches from Mail and sources

Area O1 also looks for proof you may already have. A rule-based matcher (no AI model) compares each missing item's
keywords with:

- **incoming mail** in your [Mail view](../connectors/gmail.md), after a Gmail sync: the subject must contain one of
  the item's keywords, and the message must belong to the activity. It does when its subject shares a distinctive
  word with the activity's title, or when it comes from the activity's organizer with a verified sender (the same
  sender check as in Mail). The organizer is the site the activity came from, or whoever sent you verified mail
  naming it, usually the invitation. So "Re: Saturday - thanks for judging!" from the organizer counts; the same
  subject from a look-alike domain, a failed sender check or a free mail address doesn't,
- **pages from your sources**, after a source sync: the same test on the page's title or address.

A match becomes an evidence candidate in the [Inbox](../tour/inbox.md), titled with the item's label, such as "The
thank-you or certificate after the event: Thanks for judging Example Hacks". Nothing is linked until you accept it.
Accepting files the exhibit and links it to the item. A match you reject stays rejected.

The in-app agent can read your missing items (the `missing_proof` tool) and propose a document it found the same
way, with a quote. It can't link or waive an item itself.

## Edit or add a recipe

Recipes are YAML files in `profiles/recipes/`, one per criterion, shared by O-1A and EB-1A. Here is part of
`judging.yaml`:

```yaml
criterion: judging
label: "Judging the work of others"
items:
  - id: completion
    label: "The thank-you or certificate after the event"
    why: "Confirms you completed the judging."
    match: {stages: [completed], keywords: [thank you for judging, thanks for judging, certificate of appreciation]}
  - id: selection_criteria
    label: "How judges were selected"
    why: "Shows the role was selective, if the organizer published it."
    optional: true
    match: {keywords: [judges are selected, selection of judges, reviewer selection]}
```

The `match` block says how an exhibit or a message is recognized as the item:

- `evidence_types` and `stages`: an exhibit with a listed type (and a listed stage, when stages are given) is the
  item,
- `keywords`: lowercase phrases looked for in a mail subject, a page title or address, or an exhibit's title and
  file name (for the "Looks like a match" list).

A recipe can also have `applies_to`, a list of evidence types it's for, when one criterion holds different kinds of
evidence. Left out, it applies to all of them.

To change a recipe for your own case, put a file in `<workspace>/profiles/recipes/`. A workspace recipe replaces the
bundled one with the same `criterion`. Each file is validated when it loads, so a misspelled field shows up as an
error instead of being ignored.

The design is recorded in
[ADR 0017](https://github.com/ris3abh/areao1/blob/main/docs/adr/0017-proof-recipes.md). [Evidence
preflight](preflight.md) reads the same checklists to flag an activity accepted without completion proof.
