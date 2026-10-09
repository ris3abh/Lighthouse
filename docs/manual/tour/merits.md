# Final merits

Your counted evidence as a whole: how it spreads across the years, and what it covers against rules you can read.
There is no score and no verdict on this page.

For EB-1A, meeting three criteria is the first step. In the second step (Kazarian v. USCIS, and the USCIS Policy
Manual), the officer weighs all the evidence together. O-1A reviews also look at the evidence as a whole. The page
is called **Final merits** for EB-1A and **The evidence as a whole** for O-1A.

## Themes

Five themes, each marked **Strong**, **Building** or **Missing** by a rule shown under it, with a sentence saying
why ("2 of 3 letter writers are independent") and, under **What's behind it**, the exhibits and letter writers it
rests on.

| Theme | Strong when | Building when |
|---|---|---|
| Independent recognition | at least 2 letter writers are independent, and at least half of all writers | 1 independent writer, or an award or press exhibit from outside your employer |
| Recognition outside your employer | at least 3 counted exhibits from organizations other than your employer | at least 1 |
| Evidence across multiple years | counted exhibits in at least 3 different years | 2 years |
| Peer-relative context | a field benchmark, or at least 2 exhibits with a selectivity signal | 1 such exhibit |
| External adoption | adoption by at least 2 independent organizations | 1 |

A status says what your counted evidence covers against the rule. It isn't a score, and the officer's weighing is
holistic.

The rules live in your profile (`final_merits` in `profiles/o1a.yaml` or `profiles/eb1a.yaml`), not in code, so
you can read them and change the thresholds.

### Your employer and who issued each exhibit

"Outside your employer" needs two things:

- **Your employer.** Area O1 reads it from your petitioner (when it's your employer) and from employer facts you
  haven't rejected. The note under the themes names it. Without one, the theme says your employer isn't recorded.
- **Who issued each exhibit.** The organization you set on the exhibit, or else the site it came from. Exhibits
  with neither are listed under **Who issued it**: type the organization and **Save**.

## Sustained acclaim, by year

A table of counted exhibits by criterion and year, with the span ("6 counted exhibits from 2024 to 2026") and any
years with nothing counted. Only counted exhibits appear: accepted, completed and not self-reported.

## Field benchmarks

How often your works are cited compared with works of the same field and year, from OpenAlex. They need your
OpenAlex author page in [Sources](sources.md); then press **Fetch from OpenAlex**.

- Nothing is fetched until you press the button, and it runs once per press, like every network action.
- Each benchmark is saved as a fact in [Memory](memory.md) quoting the OpenAlex response, waiting for your
  review. A benchmark you reject doesn't count.
- It reads as context: "Cited more than 92% of 2024 works in its field (OpenAlex)."

## The standard, from your vault

Each sentence about the legal standard quotes the passage it rests on, and is checked against your
[knowledge vault](../how-it-works/rule-check.md) copy of that source:

- **Verified**: the quote is in the current copy.
- **Stale**: the vault's copy has expired; sync Knowledge.
- **Unverified**: the quote isn't in the copy, or the source isn't in your vault yet.

An unverified sentence is shown as unverified, not hidden. For EB-1A the page quotes the Policy Manual's
two-step review and Kazarian; for O-1A, the Policy Manual's O-1 chapter.

## In the review packet

The themes and the standard are a section of the [review packet](../how-it-works/review-packet.md).

See [ADR 0019](https://github.com/ris3abh/areao1/blob/main/docs/adr/0019-final-merits.md) for the design.
