# The skill pack

Every workspace comes with written instructions for Claude Code and Codex, so they use your case the way Area O1 expects.

## What's in your workspace

| File | For | What it is |
|---|---|---|
| `.claude/skills/areao1/SKILL.md` | Claude Code | A skill named `areao1`. Claude Code loads it when you ask about your case, criteria, gaps, evidence, deadlines or letters, or share something that matters for the case. |
| `AGENTS.md` | Codex and other agents that read it | The workspace guide: rules, the folder layout, useful commands, and a section called "Driving Area O1 from Claude Code or Codex". |

Both are plain Markdown. You can read them in any editor. The originals ship with Area O1 in [`areao1/templates/workspace/`](https://github.com/ris3abh/areao1/blob/main/areao1/templates/workspace/AGENTS.md).

## What they tell agents

Both files give the same rules. In short:

- **Connect through the MCP server.** The setup line (`claude mcp add ...` or `codex mcp add ...`) and the six tools, with what each one does.
- **Start each session** with `what_changed(since=<last session>)` and `get_scoreboard()`.
- **Check before relying on a fact.** Use `get_provenance`. Draft only from claims whose status is `approved` and that are current. Where proof is missing, say what's unknown.
- **Offer to save what matters.** When you share a deadline, an invitation, a result or a letter writer, the agent offers to send it with `propose_context`, in your words, with its own name as `client`.
- **An invitation is not a completion**, and a preprint is not a publication. Respect each claim's stage.
- **No verdicts.** Never say you qualify, will be approved or meet a criterion. Any judgment is an opinion and must be labeled as one.
- **Don't touch evidence or memory files.** Never edit `data/exhibits.json`, `evidence/` or `memory/*.jsonl` directly, and never delete anything. Evidence enters only through the Inbox, accepted by you.
- **No secrets in files.** Keys and tokens live in the OS keychain.
- **Never send email for you.** Area O1 only sends an email you approved on the Contacts page.

`AGENTS.md` adds the folder layout (what lives in `data/`, `evidence/`, `memory/`, `drafts/letters/`), the file naming rule for exhibits, and a few commands (`areao1 up`, `areao1 run sync`, `areao1 validate` and others). It also tells agents to run `areao1 validate` after editing a `data/*.json` file and not to edit generated files such as `DASHBOARD.md` and `data/criteria.json`.

The MCP server sends the agent a shorter version of the same rules when it connects, so clients that never read these files still get them.

## When they're installed

- `areao1 init` (and the first-run setup) writes both files into a new workspace.
- Each time the app starts (`areao1 up`), Area O1 checks the workspace. If `SKILL.md` is missing, it adds it. If `AGENTS.md` is missing, it writes it. If `AGENTS.md` exists but has no "Driving Area O1 from Claude Code or Codex" section, it appends that section.

It only adds what's missing. It never rewrites a file you already have, so your own edits to `AGENTS.md` stay.

## Refresh them after an update

Because existing files are never overwritten, a newer version of Area O1 doesn't replace your copies. To get the current ones:

1. Stop the app.
2. To refresh the skill, delete `.claude/skills/areao1/SKILL.md`.
3. To refresh the Claude Code and Codex section of `AGENTS.md`, delete that section (from its heading to the next `## ` heading). To refresh the whole guide, delete `AGENTS.md`. Copy out any notes of your own first.
4. Start the app again with `areao1 up`. The missing pieces are written from the installed version.

## Add your own notes

You can add your own sections to `AGENTS.md`, for example how you like letters drafted. Keep the rules section as it is: it's what keeps agents from editing evidence directly.
