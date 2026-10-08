# 0015. OpenAI is the only engine

- Status: accepted
- Date: 2026-10-07
- Supersedes: ADR 0005 §1–2 and §7 (the Claude Agent SDK adapter, its harness lockdown and its cache notes),
  ADR 0009 §2's model table, and ADR 0013's amendment (an Anthropic API key)

## Context

The agent ran on the Claude Agent SDK: the Claude Code CLI as a harness, our tools as an in-process MCP server,
an Anthropic API key in the keychain. The owner is moving the product to OpenAI. Two engines with two keys
would double what onboarding asks, what Settings explains and what the tests must cover, so OpenAI becomes the
only runtime engine. Claude Code and Codex stay supported as *clients* that drive Area O1 from outside, over
the MCP server; that's a different thing from the engine that answers in the app.

## Decision

### 1. One engine: the OpenAI Responses API

`areao1/engine/openai_engine.py` implements the same `Engine.run(request, tools, emit)` interface over
`POST /v1/responses`, streamed:

- **Tools** are our `AgentTool`s as function tools. The loop is ours: run the model, execute each
  `function_call` with the tool's handler, send back `function_call_output`, repeat until a turn has no calls
  or `max_turns` is reached. Errors in a handler go back to the model as text, as before.
- **Stateless**: `store: false`; every turn resends the input items, including reasoning items with
  `reasoning.encrypted_content`. Nothing about a run is kept at OpenAI beyond what the API retains by policy;
  the conversation lives in the workspace, as before.
- **Web search** is a function tool, `web_search(query, allowed_domains)`, that we execute: the search policy
  (`EngineRequest.guard`) decides first, exactly as it did for the SDK's `WebSearch`, and only an allowed search
  runs, as one sub-request with OpenAI's hosted `web_search` tool (domain filter = `allowed_domains`). The
  result text, with its source URLs, goes back to the model. A hosted search tool in the main request would
  run before any guard could see it, so it's never offered there.
- **Nothing else is offered**: no hosted file search, code interpreter, computer use, shell or MCP tools. The
  only network the model reaches is through our tools (`read_page` keeps its private-address refusal).
- **Streaming**: `response.output_text.delta` becomes `text_delta`; each finished message `text`; each
  function call `tool_call` / `tool_result`; each response's usage `usage`.
- **Prompt caching** is automatic on these models. The prefix (instructions + tool definitions) stays
  byte-stable, as before (`tests/test_agent.py`), and each run sends a stable `prompt_cache_key` per workspace
  and task. Usage maps to the same counters: `cached_tokens` → cache reads, `cache_write_tokens` → cache writes,
  the rest of `input_tokens` → uncached input.
- **Cost** is computed from usage and a price table in the engine (USD per 1M tokens: input, cached input,
  output; cache writes at 1.25× input), plus $10 per 1,000 web searches. A model missing from the table records
  tokens and no cost, and the token caps still apply.
- **Budgets** behave as before: the runner's token caps stop a run through `emit`; the engine enforces
  `max_budget_usd` itself (the SDK did it before), stopping between turns once the run's cost reaches it, with
  the stop reason `budget: max_budget_usd`.

### 2. Models: three tiers, one line each

`agent.models` in `areao1.yaml` is now one line per tier, and so are the shipped defaults
(`agent/routing.py`):

| Tier | Model | Price per 1M (input / cached / output) | Used for |
|---|---|---|---|
| hard | `gpt-6.1-sol` | $2.00 / $0.10 / $10.00 | chat, hand-started runs, letters |
| mid | `gpt-6.1-sol` | $2.00 / $0.10 / $10.00 | missions, the rule-check judge, PDFs, cheap-mode chat |
| mundane | `gpt-6-luna` | $0.10 / $0.01 / $0.50 | chat extraction, long-chat summaries, mail sorting |

Upgrading a tier is one line (`hard: gpt-6-astra`), in the yaml or `AREAO1_MODEL_HARD`. A workspace whose
yaml still names Claude models, or has the old per-run-type slots, loads with the new defaults (a one-time
note says so).

### 3. One key: an OpenAI API key

Onboarding's "Your AI" step and Settings > Your AI take an OpenAI key (`sk-…`), check it with the free
model-list request (`GET /v1/models`), and keep it in the OS keychain (`openai:api_key`), or read
`OPENAI_API_KEY` from the environment. An Anthropic key saved before is removed from the keychain on start. The
`claude-agent-sdk` dependency, the bundled CLI and the Anthropic settings are removed.

### 4. The same guardrails, verified on the new engine

Nothing above the engine changes: the system prompt, the tools and their service-layer writes, redaction of
tool results, the verbatim-quote check, the eligibility-verdict guard, the rule check, the search policy, the
budget caps, autopilot's limits and every approval gate. To prove it, the test suite's scripted engine is now
the real OpenAI engine talking to a scripted fake Responses API: every agent, guardrail, budget, search-policy
and prompt-injection test runs through the new adapter's request building, streaming, tool loop and usage
accounting. No test calls OpenAI.

### 5. Claude Code and Codex drive Area O1 from outside

The MCP server (`areao1 mcp`) is unchanged. A skill pack documents how to use it: `.claude/skills/areao1/`
for Claude Code and `AGENTS.md` for Codex (and other agents that read it), with the setup command, the tools,
and the rules (read freely; writes only as Inbox proposals; never an eligibility verdict).

## Consequences

- One provider, one key, one price table to keep current. OpenAI's prices and model names change; the table
  lives in one file and a model missing from it still runs (tokens counted, cost unknown).
- Web search costs a sub-request per allowed search. It's also what lets the search policy refuse a search
  before it runs.
- Claude chat exports remain an import source; they have nothing to do with the engine.
