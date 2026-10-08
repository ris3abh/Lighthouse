# What agents can and can't do

Agents can read your case and suggest things, but only you decide what becomes evidence, what counts and what gets sent.

This page covers two kinds of agent: AI tools connected over MCP (Claude Code, Claude Desktop, Codex) and Area O1's own in-app agent, which runs on OpenAI.

## AI tools connected over MCP

| Can | Can't |
|---|---|
| Read the scoreboard, the gaps, claims, provenance and recent changes. | Change any case file through the server. |
| Send a note to your Inbox with `propose_context`. | Make that note evidence, or make it count toward a criterion. |
| | Accept, reject or edit Inbox items, exhibits, letters or settings. |
| | Send email. |

Five of the six tools are read-only. The sixth, `propose_context`, can only add a note to the Inbox. A note is marked self-reported. If you keep it, it's saved as a self-reported observation, and self-reported material never counts toward a criterion, however it got there.

A coding agent also has your file system, which the MCP server doesn't control. That's why the [skill pack](skill-pack.md) tells it never to edit `data/exhibits.json`, `evidence/` or `memory/*.jsonl` directly, never to delete anything, and to run `areao1 validate` after editing a data file. Keep your workspace in Git (`areao1 init` sets this up) so you can see and undo any change.

## Nothing becomes evidence without you

Evidence enters the case one way: you accept it in the [Inbox](../tour/inbox.md). Connectors, the in-app agent and MCP tools can only propose. See [Review in the Inbox](../how-it-works/review.md).

Accepting records your decision. It doesn't certify that something is true or legally sufficient.

## Drafting only from approved claims

Every fact in Area O1 is a claim that quotes its source. Agents are told to draft only from claims you approved that nothing newer replaced, and to say what's unknown instead of filling a gap.

The Letters page enforces this in code: a letter draft is built from approved claims only, and a factual sentence that cites no approved claim is dropped. See [Claims and provenance](../how-it-works/claims.md).

## The in-app agent

Area O1's own agent (the [Agent page](../tour/agent.md) and the chat panel) runs on OpenAI with your key. What it may change depends on who started the run.

### Runs you start

In a chat or a task you start by hand, the agent can do what the tracker pages do:

- add, update and delete deadlines, pipeline items, letter writers and contacts,
- update to-dos,
- write an email draft (it can't send it).

Each change is applied, logged with the agent as the actor, and can be undone from the Agent page.

### Scheduled missions and autopilot

Missions run on a schedule without you (see [Settings](../tour/settings.md)). Their suggestions go to the Inbox, except where you turned on **Agent autopilot** in Settings. Every autopilot category is off by default:

| Autopilot setting | What it lets the agent apply on its own |
|---|---|
| Tracker updates | Move pipeline items, set follow-ups and notes, update a letter writer's status or last contact, edit or mark deadlines done. |
| Metrics | Record a metric value it read from a page and quoted. |
| Tier-1 deadlines | Add a deadline quoted from a Tier 1 source (official law and agency sites in the vault, such as uscis.gov or ecfr.gov). |

Each auto-applied change can be undone on the Agent page. A tracker change outside the allowed fields (for example, a pipeline item's criterion) goes to the Inbox instead.

### Always yours

Whatever autopilot allows, these are never done by an agent:

- accepting, editing, snoozing or rejecting Inbox items,
- uploading evidence, moving an exhibit to another criterion, marking a criterion dropped, changing the profile,
- changing autopilot, missions, model or mail settings, or which sources the rule check trusts,
- starting a letter draft in a writer's voice (you start it from Letters),
- marking a letter sent or signed (only the writer signs, only you send),
- sending email.

## The rule check

Statements about the rules (fees, forms, deadlines, criteria wording) are checked against the official sources in the knowledge vault. A statement that isn't verified can't enter an exhibit or a letter writer's record as the agent wrote it, and the agent's write tools refuse it. If you rewrite the text in your own words, the words are yours and the check is cleared. See [Rule check and the knowledge vault](../how-it-works/rule-check.md).

## Email needs Approve & send

No agent sends mail. The in-app agent and the daily opportunity check can only write drafts. An email goes out only after you press **Approve & send** on the [Contacts page](../tour/contacts.md), and you get a few seconds to undo it. Agents and autopilot can't approve.

## No legal advice

Area O1 isn't legal advice and isn't affiliated with USCIS. The in-app agent has checks in code, not just in its instructions:

- **Verdicts are replaced.** If an answer says you're eligible, qualify, or will be approved, that sentence is replaced with a note that only USCIS decides and an immigration attorney can assess your case.
- **An invitation isn't a completion.** The agent can't propose something as completed, published or granted unless the quote it cites shows it. An invitation quoted as a completion is refused.
- **Web pages are data.** Text from a web page is marked as untrusted, and text that tries to instruct an AI is flagged and never followed.
- **No people-search sites.** People-search and personal social sites are off limits. Contacts are looked up on public professional pages only.

Every refusal is logged in `agent/refusals.jsonl` and listed on the Agent page.

MCP clients get the same rules as instructions, but Area O1 can't enforce them inside another tool's model. Treat any judgment from any AI as an opinion. See the [legal disclaimer](../reference/disclaimer.md).
