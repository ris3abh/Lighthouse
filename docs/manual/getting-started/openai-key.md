# Add an OpenAI API key

An OpenAI API key turns on Area O1's chat and web lookups; everything else works without one.

## Add the key

1. Create a key at [platform.openai.com](https://platform.openai.com) > API keys. OpenAI keys start with `sk-`.
2. In Area O1, open **Settings > Your AI** (or the **Your AI** step of onboarding).
3. Paste the key and press **Check and save**.

Area O1 checks the key with OpenAI's free model-list request before saving it. If it works, it's stored in your
OS keychain (entry `openai:api_key`), never in your workspace. The card then says *Using your OpenAI API key*.

To remove it, press **Forget the key** on the same card.

### Or use an environment variable

If `OPENAI_API_KEY` is set in the environment Area O1 starts from, it's used when no key is saved in Settings:

```sh
export OPENAI_API_KEY=sk-...
areao1
```

A key saved in Settings wins over the environment variable.

### If the key isn't accepted

| Area O1 says | What to do |
|---|---|
| That doesn't look like an OpenAI API key | Paste the whole key; it starts with `sk-` |
| That's an Anthropic key | Area O1 runs on OpenAI only; create an OpenAI key |
| OpenAI refused that key | Check you copied all of it and that it isn't revoked |
| Couldn't reach OpenAI to check the key | Check your connection and try again |

## What needs a key, and what doesn't

| Needs a key | Works without one |
|---|---|
| **Ask**, the chat panel on every page | Onboarding from your LinkedIn PDF |
| Agent runs you start, and missions (scheduled agent runs) | Every connector: GitHub, Hugging Face, Semantic Scholar, OpenAlex, arXiv, ORCID, websites |
| Onboarding's web search for an award, judging role or membership | The Inbox, Evidence, Metrics, Pipeline, Contacts, Calendar, Knowledge and Memory pages |
| **Draft from claims** on the Letters page | The criteria scoreboard and `DASHBOARD.md` |
| The rule check against official sources | Gmail with rules-only mail sorting, `.eml` drops and sender checks |
| Reading a PDF that isn't a LinkedIn export | Chat-history imports with the local rules |
| People, asks, decisions and metrics from chat imports | The knowledge vault and its change signals |
| Model sorting of mail no rule could sort (off by default) | Notifications, the calendar file and scheduled jobs |

Without a key, the features in the left column say so and do nothing else. Nothing breaks.

!!! tip "Claude Code and Codex don't need this key"
    If you use Area O1 from Claude Code, Codex or another MCP client, that agent runs on its own account. The MCP
    server needs no OpenAI key. See [Set up your agent](../mcp/setup.md).

## The three model tiers

Area O1 picks a model by task from a fixed table, never by asking a model. There are three tiers, one line each in
`agent.models` in your workspace's `areao1.yaml`:

```yaml
agent:
  models:
    hard: gpt-6.1-sol      # chat, tasks you start, letters
    mid: gpt-6.1-sol       # missions, the rule check, PDFs, cheap-mode chat
    mundane: gpt-6-luna    # chat extraction, long-chat summaries, mail sorting
```

| Tier | Default model | Used for |
|---|---|---|
| `hard` | `gpt-6.1-sol` | Chat, runs you start by hand, letter drafts |
| `mid` | `gpt-6.1-sol` | Missions, the rule check, reading non-LinkedIn PDFs, chat in cheap mode |
| `mundane` | `gpt-6-luna` | Chat-import extraction, summaries, mail sorting, each web search |

To change a tier, change its line. An environment variable (or a line in the workspace's `.env`) overrides the
yaml: `AREAO1_MODEL_HARD`, `AREAO1_MODEL_MID` or `AREAO1_MODEL_MUNDANE`.

A model that isn't in Area O1's price table still runs: its tokens are counted and the token caps apply, but its
cost shows as unknown.

The Agent page shows which model each tier uses.

### Other agent settings

These also live under `agent:` in `areao1.yaml`:

| Setting | Default | What it does |
|---|---|---|
| `effort` | `medium` | How hard the model reasons: `low`, `medium`, `high`, `xhigh` or `max` |
| `web_search` | `true` | Whether runs may search the web |
| `max_searches` | `8` | Web searches per run; at the cap the run finishes with what it found and says so |
| `max_turns` | `25` | Model turns per run |
| `cheap_mode` | `false` | Chat on the `mid` tier instead of `hard` |
| `budget` | see [Costs](costs.md) | Per-run and monthly caps |

### Cheap mode

**Settings > Your AI > Cheap mode** runs chat answers on the `mid` tier instead of the `hard` one. Missions,
checks and summaries are unchanged. With the shipped defaults both tiers use the same model, so cheap mode only
saves money once you point `hard` at a larger model.

For prices and caps, see [Costs and budget caps](costs.md).
