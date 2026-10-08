# Invited vs completed

An invitation to judge is not judging, so Area O1 tracks every activity's stage and counts only the completed ones.

## Stages

Each activity claim and exhibit can carry a stage:

| Kind of activity | Stages | Counts toward a criterion |
|---|---|---|
| Judging, talks, reviewing | `invited`, `accepted`, `completed`, `declined`, `cancelled` | `completed` |
| Papers | `preprint`, `submitted`, `published`, `retracted` | `published` |
| Memberships, awards | `applied`, `granted`, `denied` | `granted` |

Only `completed`, `published` and `granted` count. Evidence with no stage at all (a repo's star count, a press article) counts as it is.

In the Inbox and on the Evidence page, a stage chip shows the difference: a completed stage is solid, an earlier stage is an outline. On the Evidence page, an exhibit at an earlier stage is marked "not counted until completed".

## How stages are set

- **Email** (Gmail, `.eml` files, forwards, and the [daily opportunity check](opportunities.md)): a message is `completed` only when it says so explicitly, for example thanking you for judging or reviewing, confirming your review was received, or a certificate of appreciation. Everything else is `invited`.
- **The in-app agent** can't propose something as completed, published or granted unless the quote it cites shows it. An invitation quoted as a completion is refused, with a suggestion to propose it as `invited` and again once it's done.

When the completion arrives later (the organizer's thank-you, a certificate), it becomes its own candidate. Accept it, and the criterion can count it.

## How the scoreboard counts

The criteria engine is simple on purpose, so every status can be explained. Your profile (`o1a` or `eb1a`, in [`profiles/`](https://github.com/ris3abh/areao1/blob/main/profiles/o1a.yaml)) lists, for each criterion:

- **evidence types** it accepts, such as `judge_invite`, `reviewer_record`, `panel_letter` and `program_committee` for judging,
- **strength signals** that make the evidence stronger, such as "selective event", "multiple instances" and "documented scoring",
- **bank rules**: `min_exhibits` (exhibits needed) and `min_signals` (distinct signals needed).

For each criterion, an exhibit counts only when all of these hold:

1. it's filed under that criterion,
2. its evidence type is one the criterion lists,
3. its stage is completed (or it has no stage),
4. it isn't self-reported.

The signals are the ones your counted exhibits carry. "Multiple instances" is added on its own when the profile lists it and two or more exhibits count.

## The four statuses

| Status | When |
|---|---|
| **banked** | Counted exhibits ≥ `min_exhibits` and distinct signals ≥ `min_signals`. |
| **building** | At least one counted exhibit, but not enough yet; or nothing counted but something is in progress (invited, submitted...). |
| **gap** | Nothing counted and nothing in progress. |
| **dropped** | You marked the criterion dropped. |

You can also mark a criterion `gap` or `dropped` yourself (stored under `overrides` in `areao1.yaml`). Your override always wins, and the reason still shows what the rules say.

Each criterion has a reason in plain words, such as "Needs 1 more exhibit." or "1 exhibit not counted until completed (stage: invited)." The reason also says when an exhibit was ignored because it's self-reported, or filed with an evidence type the profile doesn't list.

## An example

Maya Chen's O-1A profile needs 2 exhibits and 1 signal to bank judging.

| What she has | Judging status |
|---|---|
| An invitation to judge Northwind Hacks (`invited`) | building: nothing completed yet |
| + the organizer's thank-you after the event (`completed`, signal "selective event") | building: needs 1 more exhibit |
| + a completed reviewer record for a workshop | banked: 2 exhibits, 2 signals (selective event, multiple instances) |

## What banked means

"Banked" means your accepted exhibits meet the profile's rules in Area O1. It's a way to track your file, not a legal assessment. Whether the evidence is enough is for an immigration attorney to assess and for USCIS to decide. See the [legal disclaimer](../reference/disclaimer.md).
