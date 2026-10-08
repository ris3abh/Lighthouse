# MCP tools

Here is every tool the Area O1 MCP server offers: its parameters, what it returns, and an example.

The examples use made-up data for a made-up person, Maya Chen. Results are trimmed (`...`) to keep them short. Dates are `YYYY-MM-DD`; times are UTC.

| Tool | Parameters | Writes? |
|---|---|---|
| [`get_scoreboard`](#get_scoreboard) | none | no |
| [`list_gaps`](#list_gaps) | none | no |
| [`query_claims`](#query_claims) | `entity`, `as_of` (optional) | no |
| [`get_provenance`](#get_provenance) | `claim_id` | no |
| [`what_changed`](#what_changed) | `since` | no |
| [`propose_context`](#propose_context) | `text`, `title`, `topic`, `client` (all but `text` optional) | adds a note to the Inbox |

The read tools are marked read-only to the client. They score the case in memory and never change a workspace file. The only thing they may touch is the disposable search index under `.areao1/cache/`.

## get_scoreboard

The scoreboard for your active profile (O-1A or EB-1A): each criterion's status, how many exhibits count, and which strength signals they show. It's the same rule-based count as the Overview page; see [Invited vs completed](../how-it-works/invited-vs-completed.md) for how it works.

**Parameters:** none.

**Returns:**

| Field | Meaning |
|---|---|
| `profile`, `profile_name` | The active profile, e.g. `o1a`. |
| `banked`, `building` | How many criteria are banked, and how many are building. |
| `threshold`, `target` | The profile's threshold and target (O-1A: 3 and 5). |
| `criteria[]` | Per criterion: `id`, `label`, `status` (`banked`, `building`, `gap` or `dropped`), `exhibits_counted`, `in_progress`, `matched_signals`, `reason`. |
| `note` | A reminder that this is a rule-based status, not legal advice. |

**Example result:**

```json
{
  "profile": "o1a",
  "profile_name": "O-1A Extraordinary Ability",
  "banked": 1,
  "building": 2,
  "threshold": 3,
  "target": 5,
  "criteria": [
    {
      "id": "judging",
      "label": "Judging the work of others",
      "status": "building",
      "exhibits_counted": 1,
      "in_progress": 1,
      "matched_signals": ["selective_event"],
      "reason": "Needs 1 more exhibit. 1 exhibit not counted until completed (stage: invited)."
    },
    ...
  ],
  "note": "Rule-based status from accepted exhibits. Not legal advice and not affiliated with USCIS; confirm strategy with an immigration attorney."
}
```

## list_gaps

Every criterion that isn't banked or dropped, with exactly what's missing and what's already in flight.

**Parameters:** none.

**Returns:**

| Field | Meaning |
|---|---|
| `profile`, `banked`, `threshold` | As in `get_scoreboard`. |
| `still_needed_to_reach_threshold` | How many more criteria would need to be banked to reach the profile's threshold. |
| `gaps[]` | Per criterion: `id`, `label`, `status`, `needs_exhibits`, `needs_signals`, `missing_signals` (as labels), `accepted_evidence_types`, `in_progress` (exhibits filed but not at a completed stage), `pending_in_inbox` (evidence waiting for your review), `reason`. |
| `note` | The same not-legal-advice note. |

**Example result:**

```json
{
  "profile": "o1a",
  "banked": 1,
  "threshold": 3,
  "still_needed_to_reach_threshold": 2,
  "gaps": [
    {
      "id": "judging",
      "label": "Judging the work of others",
      "status": "building",
      "needs_exhibits": 1,
      "needs_signals": 0,
      "missing_signals": ["multiple instances", "documented scoring"],
      "accepted_evidence_types": ["judge_invite", "reviewer_record", "panel_letter", "program_committee"],
      "in_progress": [
        {"id": "exh_4b1e09c2a7d3", "title": "Judge invitation, Northwind Hacks 2026", "stage": "invited"}
      ],
      "pending_in_inbox": [
        {"id": "cand_91c0d4e2b8aa", "title": "Reviewer for the Example ML Workshop"}
      ],
      "reason": "Needs 1 more exhibit. 1 exhibit not counted until completed (stage: invited)."
    },
    ...
  ],
  "note": "..."
}
```

## query_claims

The facts Area O1 holds about one thing: a repo, a model, a paper, a person, an event. Each fact is a claim that quotes its source word for word. See [Claims and provenance](../how-it-works/claims.md).

**Parameters:**

| Name | Type | Meaning |
|---|---|---|
| `entity` | string, required | An entity id such as `artifact:github:mayachen/fastgrad`, or part of an id or name such as `fastgrad` (not case-sensitive). |
| `as_of` | string, optional | A date, `YYYY-MM-DD`. Returns what was true by that day **and** already known to Area O1 by the end of that day. Without it, you get the current claims. |

**Returns:**

| Field | Meaning |
|---|---|
| `entity` | What you asked for. |
| `matched_entities` | The entity ids that matched. |
| `as_of` | The date used, or `null`. |
| `claims[]` | Per claim: `id`, `subject`, `predicate`, `value`, `stage`, `valid_from`, `recorded_at`, `status` (`proposed`, `corroborated`, `approved` or `rejected`), `current` (nothing newer replaced it), `confidence` (`high`, `medium`, `low`), `excerpt` (the exact source words), `source_url`. |
| `rule` | A reminder: draft only from claims with status `approved`. |

**Example call:**

```json
{"entity": "fastgrad"}
```

**Example result:**

```json
{
  "entity": "fastgrad",
  "matched_entities": ["artifact:github:mayachen/fastgrad"],
  "as_of": null,
  "claims": [
    {
      "id": "clm_1ee3c3af9dcb",
      "subject": "artifact:github:mayachen/fastgrad",
      "predicate": "stars",
      "value": 1340,
      "stage": null,
      "valid_from": "2026-10-08",
      "recorded_at": "2026-10-08T13:48:00+00:00",
      "status": "approved",
      "current": true,
      "confidence": "high",
      "excerpt": "\"stargazers_count\": 1340",
      "source_url": "https://api.github.com/repos/mayachen/fastgrad"
    }
  ],
  "rule": "Draft only from claims with status 'approved'; say what is unknown instead of filling gaps."
}
```

With `{"entity": "fastgrad", "as_of": "2026-09-01"}` you'd get the star count Area O1 knew on September 1 instead.

## get_provenance

The full trail behind one claim, down to the saved copy of the source.

**Parameters:**

| Name | Type | Meaning |
|---|---|---|
| `claim_id` | string, required | A claim id from `query_claims` or `what_changed`, e.g. `clm_1ee3c3af9dcb`. |

**Returns:**

| Field | Meaning |
|---|---|
| `claim` | The claim, in the same shape as in `query_claims`. |
| `extracted_by` | Who read it: `kind` (`connector`, `model` or `user`), `name`, `version`. |
| `excerpt_offsets` | `[start, end]`: where the excerpt sits in the saved source. |
| `excerpt_verified` | `true` when the saved source still has exactly those words at those offsets. |
| `observation` | The saved source: `id`, `connector`, `source_url`, `captured_at`, `sha256`, `snapshot` (path under `memory/sources/`), `media_type`, `tier`, `filename`. |
| `entity` | What the claim is about: `id`, `kind`, `name`, `url`. |
| `reviews` | Your decisions on it: `decision` (`approved` or `rejected`), `reviewer`, `at`, `rationale`. |
| `supersedes`, `superseded_by` | Earlier and later versions (`id`, `value`, `valid_from`). |
| `cited_by` | Exhibits that rely on it (`exhibit_id`, `title`, `file`). |
| `prov` | The same chain in [W3C PROV](https://www.w3.org/TR/prov-overview/) terms: `entity`, `activity`, `agent`, `wasDerivedFrom`. |

**Example call:**

```json
{"claim_id": "clm_1ee3c3af9dcb"}
```

**Example result:**

```json
{
  "claim": {"id": "clm_1ee3c3af9dcb", "predicate": "stars", "value": 1340, "status": "approved", "current": true, ...},
  "extracted_by": {"kind": "connector", "name": "github", "version": ""},
  "excerpt_offsets": [40, 64],
  "excerpt_verified": true,
  "observation": {
    "id": "obs_0e3f60955496f6dd",
    "connector": "github",
    "source_url": "https://api.github.com/repos/mayachen/fastgrad",
    "captured_at": "2026-10-08T13:48:00Z",
    "sha256": "43fa0fbf...",
    "snapshot": "memory/sources/43fa0fbf....json",
    "media_type": "application/json",
    "tier": "platform",
    "filename": null
  },
  "entity": {"id": "artifact:github:mayachen/fastgrad", "kind": "artifact", "name": "mayachen/fastgrad", ...},
  "reviews": [
    {"id": "dec_139aef4ffc8c", "decision": "approved", "reviewer": "user", "at": "2026-10-08T13:48:00Z",
     "rationale": "accepted in the Inbox", ...}
  ],
  "supersedes": [{"id": "clm_53815768619b", "value": 1200, "valid_from": "2026-09-14"}],
  "superseded_by": [],
  "cited_by": [],
  "prov": {
    "entity": "obs_0e3f60955496f6dd",
    "activity": "extraction",
    "agent": "connector:github",
    "wasDerivedFrom": "obs_0e3f60955496f6dd"
  }
}
```

An unknown id fails with `no claim '<id>'`.

## what_changed

Everything recorded on or after a date. A good way to start a session where the last one ended.

**Parameters:**

| Name | Type | Meaning |
|---|---|---|
| `since` | string, required | A date, `YYYY-MM-DD`. |

**Returns:**

| Field | Meaning |
|---|---|
| `since` | The date used. |
| `claims[]` | New claims: `id`, `subject`, `predicate`, `value`, `previous_value`, `change` (`new` or `updated`). |
| `reviews[]` | Your approve and reject decisions in that time. |
| `exhibits_accepted[]` | Exhibits you accepted: `id`, `criterion`, `title`, `stage`. |
| `new_candidates[]` | New Inbox items that you haven't rejected: `id`, `kind`, `title`, `proposed_criterion`. |
| `metric_changes[]` | Metrics that moved: `source`, `item`, `metric`, `from`, `to`, `delta`. |

**Example call:**

```json
{"since": "2026-10-01"}
```

**Example result:**

```json
{
  "since": "2026-10-01",
  "claims": [
    {"id": "clm_1ee3c3af9dcb", "subject": "artifact:github:mayachen/fastgrad", "predicate": "stars",
     "value": 1340, "previous_value": 1200, "change": "updated"}
  ],
  "reviews": [{"claim_id": "clm_1ee3c3af9dcb", "decision": "approved", "at": "2026-10-08T13:48:00Z", ...}],
  "exhibits_accepted": [
    {"id": "exh_7f20c1d9e4b5", "criterion": "original_contributions", "title": "fastgrad on GitHub", "stage": null}
  ],
  "new_candidates": [
    {"id": "cand_2b276d24a192", "kind": "context", "title": "Asked to judge Northwind Hacks on Nov 8",
     "proposed_criterion": ""}
  ],
  "metric_changes": [
    {"source": "github", "item": "mayachen/fastgrad", "metric": "stars", "from": 1200, "to": 1340, "delta": 140}
  ]
}
```

A date that isn't `YYYY-MM-DD` fails with a message saying so.

## propose_context

Sends a note to your Inbox, under "Context from your AI tools". This is the only tool that writes anything.

**Parameters:**

| Name | Type | Meaning |
|---|---|---|
| `text` | string, required | The note, up to 4,000 characters. Facts in your words, not the agent's conclusions. |
| `title` | string, optional | A short title. Without one, the first line of `text` is used (up to 120 characters). |
| `topic` | string, optional | A word or two, such as `judging` or `letters`. |
| `client` | string, optional | The tool sending it, e.g. `Claude Code`. Shown as the note's source. |

**Returns:** `status` (`proposed` or `duplicate`), plus `candidate_id`, `tier` (always `self_reported`) and a `note` when it was added.

**Example call:**

```json
{
  "text": "Asked to judge Northwind Hacks on Nov 8. The invitation came from the organizers at northwindhacks.example.org.",
  "title": "Asked to judge Northwind Hacks on Nov 8",
  "topic": "judging",
  "client": "Claude Code"
}
```

**Example result:**

```json
{
  "status": "proposed",
  "candidate_id": "cand_2b276d24a192",
  "tier": "self_reported",
  "note": "Sent to the Inbox for review. It won't count toward any criterion."
}
```

Sending the exact same text again returns `{"status": "duplicate", "note": "That context is already in the Inbox."}` and adds nothing. Empty text, or text over 4,000 characters, fails with a message.

In the Inbox you can **Keep as a note**, **Edit**, **Snooze 7d** or **Dismiss**. A kept note is saved in memory as a self-reported observation. It never becomes evidence and never counts toward a criterion. To turn an invitation into evidence, add the real document (the email or letter) through the [Inbox](../tour/inbox.md) or a [connector](../connectors/index.md).

## Example prompts

Things to ask your agent once it's connected:

- "What changed in my Area O1 case since last Monday?"
- "Show my scoreboard. Which criteria are closest to banked?"
- "What does the judging criterion still need? List what's in progress."
- "What do we know about fastgrad? Quote the sources."
- "Where does the 1,340 stars figure come from? Check the provenance."
- "How many stars did fastgrad have on 2026-09-01, as far as Area O1 knew then?"
- "Draft a paragraph about my open-source work using only approved claims. Mark anything unknown."
- "I just got invited to review for a workshop on Dec 3. Save that to my Inbox."

Your agent is told not to give eligibility verdicts. If you ask "do I qualify?", expect it to describe what's banked and what's missing, and to point you to an immigration attorney for the judgment.
