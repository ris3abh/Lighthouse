---
name: areao1
description: Work with this Area O1 immigration-case workspace (O-1A / EB-1A) from Claude Code. Use when the person asks about their case, their criteria, gaps, evidence, deadlines or letters, or shares something that matters for the case (an invitation, a result, a deadline, a letter writer).
---

# Driving Area O1 from Claude Code

Area O1 keeps the person's case in files in this workspace. Its own app (`areao1 up`, http://127.0.0.1:7777) runs
its agent on OpenAI; Claude Code works alongside it through Area O1's **MCP server**, which reads the case and can
send notes to the Inbox. You never need an OpenAI key for this.

## Setup (once)

```sh
claude mcp add areao1 -- areao1 mcp -w "$PWD"
```

Run it in this workspace folder (or pass the folder's path). `claude mcp list` should show `areao1`.

## Tools

| Tool | What it does |
|---|---|
| `what_changed(since)` | Claims, reviews, exhibits, Inbox candidates and metric changes since a date (YYYY-MM-DD). Start here. |
| `get_scoreboard()` | Each criterion: banked, building, gap or dropped. |
| `list_gaps()` | What's missing per criterion: exhibits, signals, in-progress items, pending Inbox candidates. |
| `query_claims(entity, as_of?)` | Facts about a person, paper, repo or event, each quoting its source verbatim. |
| `get_provenance(claim_id)` | Where a claim came from: snapshot, verified excerpt, reviews, versions. |
| `run_preflight(min_severity?)` | Runs preflight now: what a reviewer would notice: outdated or unsupported values cited, facts that disagree, invited without completed proof, captures without a primary copy, undated exhibits, each with its claims and exhibits. Nothing is written. |
| `propose_context(text, title?, topic?, client?)` | The only write: a note to the person's Inbox, self-reported. Pass `client="Claude Code"`. |

## How to work

1. Start a session with `what_changed(since=<last session>)` and `get_scoreboard()`.
2. Before relying on a fact, check it with `get_provenance`. Draft only from claims whose status is `approved` and
   that are current; where proof is missing, say what's unknown.
3. When the person shares something important (a deadline, an invitation, a result, a letter writer), offer to
   save it with `propose_context`, in their words. It goes to the Inbox; they decide.
4. An invitation is not a completion; a preprint is not a publication. Respect each claim's stage.
5. Never state that the person qualifies, will be approved, or meets a criterion. Only USCIS decides; an attorney
   assesses the case. Any judgment you add is an opinion: label it.

## Don't

- Edit `data/exhibits.json`, `evidence/` or `memory/*.jsonl` directly, or delete anything. Evidence only enters
  through the Inbox, accepted by the person.
- Write secrets (keys, app passwords, tokens) into any file. They live in the OS keychain.
- Send email for the person. Area O1 only sends an email the person approved on the Contacts page.

See `AGENTS.md` in this folder for the workspace layout and the full rules.
