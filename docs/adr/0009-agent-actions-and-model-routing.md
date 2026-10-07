# 0009. Chat can do what the pages do; three model tiers; long chats

- Status: accepted
- Date: 2026-10-07
- Phase: build Part D (D1–D3)

## Context

The chat could read everything but write very little: it proposed deadlines, pipeline items and evidence to
the Inbox, and changed trackers only when autopilot was on. Asking it to "move the IEEE reviewer item to
applied" or "add the NeurIPS deadline" sent you to the Inbox to approve what you had just asked for. Every run
also used the most expensive model, whatever the job, and long conversations replayed every earlier turn.

## Decision

### 1. One tool for every page action, with the page's rules (D1)

Every write a page can make has a chat tool that goes through the same service call, recorded with the actor
`agent:<run>`. What a run may do depends on who asked:

- **You asked (chat and hand-started runs).** Calendar and tracker writes apply directly, the way the page
  applies them: deadlines, pipeline items and letter writers (add, change, move, delete) and to-dos (done,
  dismissed). Each one is logged, shown in the reply with an Undo button, and listed on the Agent page. Undo
  now covers deletes, new letter writers and to-dos too.
- **Nobody asked (scheduled missions).** Unchanged: proposals go to the Inbox unless you switched on that
  autopilot category (ADR 0005 §3).
- **Anything that can change what counts toward a criterion** (accepting, editing, rejecting or snoozing an
  Inbox item, filing or remapping evidence, overriding a criterion, switching profiles, uploads, settings,
  promoting a vault finding) is never done by the agent. Evidence goes to the Inbox as a proposal; for the rest
  the agent says where to do it, with a link.
- **Outreach** (Part E) is drafted only; sending needs your approval each time. There is no send tool.

`agent/actions.py` holds the table of page actions: each maps to a tool, or is listed as yours only with the
reason. A test fails when a page write route is added without an entry, and when a tool's write bypasses the
service layer or can't be undone.

### 2. Three tiers, routed by task (D2)

| Tier | Default model | Used for |
|---|---|---|
| hard | `claude-opus-5-5` | chat, hand-started runs, anything written for the petition (letters, briefings) |
| mid | `claude-sonnet-5-5` | scheduled missions, the rule-check judge, reading a non-LinkedIn PDF, cheap mode chat |
| mundane | a small OpenAI model when `OPENAI_API_KEY` is set, else `claude-haiku-4-5-20251001` | chat-history extraction, summarizing long chats, short classification |

- Tiers come from the environment or the workspace `.env` (`LIGHTHOUSE_MODEL_HARD`, `LIGHTHOUSE_MODEL_MID`,
  `LIGHTHOUSE_MODEL_MUNDANE`, `OPENAI_API_KEY`); `.env.example` lists them. A model set explicitly in
  `lighthouse.yaml` still wins, so existing workspaces keep working.
- The router is a fixed table from task to tier (`agent/routing.py`), not a model call. Each run records its
  task, tier, provider and model, and the Agent page shows them with the cost.
- **The same protections on every provider.** The OpenAI path is tool-less and single-turn. Its input goes
  through the same redaction as Claude runs, its output through the same guardrails (eligibility verdicts
  replaced, refusals logged), and its cost counts toward the same monthly cap. Nothing it returns is written
  without the checks the Claude path has (verbatim quotes, self-reported tier for chat imports).

### 3. Long chats and cheap mode (D3)

- When a conversation's replayed history would pass about 6,000 tokens, the older turns are summarized on the
  mundane tier. The summary is saved with the conversation, the original turns are kept, and each new turn
  sends the summary plus the last six turns. The summary is shown at the top of the chat, marked as a summary.
- **Cheap mode** (a toggle in the chat header and in Settings, saved in `lighthouse.yaml`) runs chat on the mid
  tier instead of the hard one.

## Consequences

- Chat becomes the fastest way to keep trackers current, and every change it makes can be undone in one click.
- The criterion protection from ADR 0005 is unchanged and now covered for every page action, not only
  autopilot.
- A second provider means a second key and a second price table; without an OpenAI key, nothing changes
  except that the mundane tier uses Claude Haiku.
- Summaries can lose detail; the originals stay in the conversation file, and the Agent page shows what was
  sent.
