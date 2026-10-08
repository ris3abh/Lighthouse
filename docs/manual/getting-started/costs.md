# Costs and budget caps

Area O1 itself is free; the AI features bill your OpenAI account, and caps in your settings stop runs before they
go over.

## What you pay for

Only runs that use your OpenAI key cost money: chat, agent runs and missions, letter drafts, the rule check, web
lookups, and the optional model steps (chat-import extraction, model mail sorting, reading a non-LinkedIn PDF).
The daily opportunity check, once you turn it on, may run one cheap web search per find that has no usable link
(`opportunities.verify_on_web`).
See [what needs a key](openai-key.md#what-needs-a-key-and-what-doesnt).

Area O1 computes each run's cost from the tokens OpenAI reports and a price table in the app
([`areao1/engine/openai_engine.py`](https://github.com/ris3abh/areao1/blob/main/areao1/engine/openai_engine.py)).
Prices for the default models, in US dollars per 1 million tokens:

| Model | Input | Cached input | Output | Default tier |
|---|---|---|---|---|
| `gpt-6.1-sol` | $2.00 | $0.10 | $10.00 | `hard`, `mid` |
| `gpt-6-luna` | $0.10 | $0.01 | $0.50 | `mundane` |
| `gpt-6-astra` | $10.00 | $1.00 | $50.00 | (an upgrade option) |

Cache writes cost 1.25 times the input rate. Prompt caching is automatic, so repeated instructions are billed at
the cached rate.

**Web search** costs **$0.01 per search** ($10 per 1,000), plus the tokens of the small sub-request that runs it
on the `mundane` tier. A run makes at most `agent.max_searches` searches (default **8**); at the cap it finishes
with what it found and says so.

!!! note "Prices change"
    These are the prices in the app's table (recorded 2026-10-07). OpenAI bills you at its own current rates, so
    check [OpenAI's pricing page](https://openai.com/api/pricing/) and your OpenAI usage dashboard.

## Typical costs

Examples from one setup on the default models; yours will vary with how long the conversation is and how much the
run reads:

| Run | About |
|---|---|
| A chat answer | $0.03 or less |
| An opportunity-scout mission with 10 web searches (before the default cap of 8) | $0.23, of which about $0.11 was searches |

## Budget caps

Spend is capped per run and per month. The caps live under `agent.budget` in your workspace's `areao1.yaml`:

```yaml
agent:
  budget:
    per_run_tokens: 300000
    per_run_usd: 2.0
    monthly_tokens: 10000000
    monthly_usd: 50.0
```

| Setting | Default | What happens at the cap |
|---|---|---|
| `per_run_tokens` | 300,000 | The run stops and says the per-run token budget was reached |
| `per_run_usd` | $2.00 | The run stops between turns once its cost reaches the cap |
| `monthly_tokens` | 10,000,000 | New runs are refused for the rest of the month |
| `monthly_usd` | $50.00 | New runs are refused for the rest of the month |

Tokens counted toward the caps are input, output and cache writes; cache reads are recorded but not counted.

When the monthly cap is reached, a chat-history import still runs with the local rules only, so you don't lose
the import.

Edit the numbers to suit you, and save the file. To be extra safe, also set a spending limit in your OpenAI
account.

## Where costs show

The **Agent** page shows:

- **This month**: dollars spent, tokens used against your monthly token cap (with a bar that turns red near the
  cap), your dollar cap, and the per-run caps.
- **Every run**: its tier, model and cost, including how many searches it made and what they cost.
- Each run's detail page: cost, searches, what it read and what it proposed.

Chat-import extraction and model mail sorting count toward the same month.

Missions are off until you turn them on in **Settings > Missions**, since they spend tokens without anyone
pressing a button. The daily what-changed mission is skipped, at no cost, when nothing changed.

## What costs nothing

These never call a model:

- **Connectors**: GitHub, Hugging Face, Semantic Scholar, OpenAlex, arXiv, ORCID and websites, plus metrics
  snapshots and sync.
- **Onboarding from a LinkedIn PDF**, read on your computer.
- **Gmail with rules-only sorting** (the default), `.eml` drops and sender checks.
- **Chat-history imports** with the local rules (the `areao1 import` command always works this way).
- **The knowledge vault**: fetching official sources, change signals, the community snapshot library, search.
- The scoreboard, the Inbox, the calendar, notifications and every other page.
- **Using Area O1 from Claude Code or Codex** over MCP: those agents bill their own accounts, not your OpenAI key.
