# 0017. Proof recipes

- Status: accepted
- Date: 2026-10-08
- Builds on: ADR 0004 (claims), ADR 0005 (Inbox approval), ADR 0007 (design system), ADR 0016 (opportunities)

## Context

People lose proof. The invitation to judge is in the Inbox, but by the time the case is assembled the reviews
portal has closed, the thank-you email is gone and nobody saved the event page that showed how selective it was.
Officers and attorneys ask for the same things every time, per kind of evidence: for judging, the invitation, the
acceptance, proof the reviews were submitted, the thank-you, the event page, the organizer's standing, how many
submissions were judged and the selection criteria. Today Area O1 knows an activity reached "completed" but not
what should be preserved now, while it's still easy to get.

## Decision

1. **Recipes are YAML, next to the profiles, community-editable.** `profiles/recipes/<criterion>.yaml`, one file
   per criterion id (shared by O-1A and EB-1A, which use the same ids), shipped with the package and overridable
   per workspace in `<workspace>/profiles/recipes/`. Each item has an `id`, a `label`, a one-line `why`, optional
   `optional: true` ("if available"), and a `match` block used to recognize it: `evidence_types`, `stages`, and
   `keywords` (lowercase phrases looked for in a title, subject or file name). A recipe may narrow by
   `evidence_types` when one criterion holds different kinds of evidence. A JSON Schema validates them; a test
   loads every bundled recipe.
2. **When a checklist appears.** An activity gets a proof checklist when it reaches a stage that matters:
   an exhibit at `accepted`, `completed`, `granted` or `published` (or with no stage, for documents that aren't
   activities, like a certificate), and a pipeline item moved to `done`. The checklist is derived on read from the
   recipe, its anchor (the exhibit or pipeline item) and stored links; nothing is generated ahead of time, so a
   recipe edit applies everywhere at once.
3. **Items are satisfied by exhibits, never by assertion.** An item is *done* when an exhibit is linked to it:
   the anchor exhibit itself when its type and stage match the item, an existing exhibit the person links, or a
   new upload filed from the checklist (criterion and stage preset). The person can also mark an item *not
   applicable* with a reason. Links and waivers live in `data/proofs.json` (`ProofLinks`), written only through the
   service layer (`proof.link`, `proof.unlink`, `proof.waive`), so they are logged and undoable.
4. **Missing items surface in This week**, one line per activity ("Judging at Example Hacks: 3 proof items to
   save"), most recent activity first, at most five lines, linking to the checklist on Evidence.
5. **Matches are proposed, not applied.** A rule-based matcher (no model) compares missing items' `keywords` with
   the Mail view's case mail (sender, subject) and with source items; a match becomes an Inbox candidate of kind
   `evidence` whose proposal names the checklist item. Accepting it files the exhibit and links it, as usual
   (ADR 0005). The agent gets one read tool, `missing_proof`, and may propose matches the same way; it can never
   link or waive an item itself.
6. **Self-reported material can't satisfy an item.** An exhibit whose source tier is `self_reported` can be
   linked for the person's own tracking but never marks an item done.

## Consequences

- One more workspace file (`data/proofs.json`, with a schema) and one more bundled folder (`profiles/recipes/`).
- The checklist is advice about what to keep, not a statement of what's legally required: the page says so, and
  recipes avoid "required" language.
- The packet (ADR 0020) and preflight (ADR 0018) read the same checklists, so "invited without completed proof"
  has one definition.

## Amendment (2026-10-09)

The code and this record had drifted; the owner chose, item by item:

1. **When a checklist appears (keep the code).** An exhibit at `accepted`, `completed`, `granted` or `published`,
   a pipeline item moved to `done`, and an approved claim at one of those stages that no exhibit cites yet. A
   document with no stage gets no checklist of its own (it is usually *the proof* for one), and neither does a
   self-reported exhibit or an exhibit already linked as another activity's proof. **New: at `invited`**, an
   activity gets a two-item checklist, the invitation and your acceptance (the recipe's own `invitation` and
   `acceptance` items when it has them, generic ones otherwise). The invitation is usually done by the anchor
   itself. Once the acceptance is saved, the activity counts as accepted and the full recipe follows. An
   invitation with no completion keeps its own preflight rule; the "accepted, no completion proof" rule applies
   from `accepted` only, so the two never double up.
2. **Uploads from a checklist are preset.** Each item carries a `preset`: the first evidence type it names that
   the criterion accepts (else the activity's own type), and the stage it names. The upload form starts from it,
   and the API fills it in when the form leaves either empty, so "the thank-you" is filed as the completion and
   ticks its item.
3. **Mail matching uses the sender's domain as well as the subject.** A message still needs one of the item's
   keywords in its subject. It belongs to the activity when its subject shares a distinctive word with it, *or*
   when its sender is the activity's organizer: the organization of a sender who passed the sender check (DMARC,
   or DKIM aligned with From; ADR 0014) and who is the host of the activity's source address or a verified sender
   of mail naming the activity (the invitation). A reply titled "Re: Saturday - thanks for judging!" from the
   organizer matches; the same subject from a look-alike domain, a failed check or a free mail provider doesn't.
