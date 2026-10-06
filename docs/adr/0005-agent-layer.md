# 5. Agent layer: engine adapters, grounded tools, the service layer, budgets

Date: 2026-10-06 · Status: accepted (Phase 1c items 1–3; autopilot and missions follow in items 4–6)

## Context

Phase 1c adds an agent the user can chat with from any page, run by hand, and (later) schedule. It must be
useful (web search, the whole workspace as context) without breaking Lighthouse's guarantees:

- nothing reaches evidence or a petition without the user's decision (SPEC 2.4);
- every fact traces to a verbatim source (5b); self-reported material never counts (11a / Phase 1a);
- case data stays on this machine except what the chosen model must see (SPEC 10);
- the engine is swappable (SPEC 8): Claude Code today, Codex behind the same interface;
- spend is bounded: per-run and monthly caps in `lighthouse.yaml`.

## Decision

### 1. One engine interface, adapters behind it

`lighthouse_gc/engine/base.py` defines `Engine.run(request, tools, emit) -> EngineResult` with a small
event vocabulary (`text_delta`, `text`, `tool_call`, `tool_result`, `usage`, `error`). Adapters:

- `engine/claude_code.py`: the Claude Agent SDK (`claude-agent-sdk`). It runs the Claude Code harness with
  our tools as an in-process SDK MCP server. Default model `claude-opus-5-5`, effort from config.
- `engine/codex.py`: a stub that raises `EngineUnavailable` until a Codex adapter is written. It sits
  behind the same interface, so switching `engine:` in `lighthouse.yaml` is the only change.

Tests never call a model: the Claude adapter takes an injectable `query` function, and the runner is
exercised end to end with a scripted fake engine.

### 2. A locked-down harness

The Claude Code harness is powerful, so the adapter starts from nothing and allows only what it needs:

- built-in tools: **`WebSearch` only** (`tools=["WebSearch"]`). No Bash, Read/Write/Edit, Glob/Grep, or
  WebFetch. A disallow list repeats this as a second guard;
- MCP: only our in-process server (`strict_mcp_config`). No user MCP servers, plugins, hooks or CLAUDE.md
  (`setting_sources=[]`);
- `permission_mode="dontAsk"` with an explicit allow list, so anything else is denied, never prompted;
- **no session persistence** (`--no-session-persistence`): transcripts don't land in `~/.claude`. The
  conversation lives in the workspace (`agent/conversations/`) and is replayed into each turn.

### 3. Tools: read freely, write only through the service layer, ground every proposal

- **Read tools** reuse the MCP read tools (`get_scoreboard`, `list_gaps`, `query_claims`, `get_provenance`,
  `what_changed`) plus read-only views of the Inbox, deadlines, pipeline and letters.
- **`read_page(url)`** replaces WebFetch. It fetches http(s) only, refuses private / loopback / link-local
  addresses (so a prompt-injected page can't reach `127.0.0.1:7777` or the LAN), caps size, extracts text,
  and snapshots it as a memory observation. That observation is what proposals cite.
- **Write tools only propose**: `propose_evidence`, `propose_deadline`, `propose_pipeline_item`,
  `propose_letter_writer` create Inbox candidates through `Service(actor="agent:<run>")`, so each one is
  in `data/changes.jsonl`. `propose_evidence` must cite an `observation_id` from `read_page` and a quote
  that occurs verbatim in it, or it is rejected. Its claim then passes the same exact-quote check as a
  connector's.
- Autopilot (Phase 1c item 4) will decide per proposal whether a narrow class of tracker changes may
  auto-apply with undo. Until then the policy function always returns "propose". Anything that could
  affect a criterion will always need approval.

Because writes can only become Inbox proposals, a prompt-injected web page can at worst fill the Inbox
with junk the user declines. It cannot change evidence, trackers or files.

### 4. Privacy

- `privacy.redact_before_llm` (default on) redacts emails, phone numbers and money amounts from tool results
  before the model sees them. The user's own chat messages are sent as typed.
- The only network calls are to the model provider (via the engine) and the pages the agent reads.

### 5. Runs, conversations and live streaming

- Every run (chat, manual, scheduled) is saved in `agent/runs/<run_id>.json`. It holds the prompt, the
  assistant's text, every tool call with its input and a result summary, the sources read (URL +
  observation id), the proposals and changes it made, token usage and cost. Chat turns also append to
  `agent/conversations/<id>.json`.
- The server runs the engine as an asyncio task and fans events out over Server-Sent Events
  (`/api/agent/runs/{id}/stream`), replaying from the start for late subscribers. The chat panel and the
  Agent page both subscribe.

### 6. Budgets

`lighthouse.yaml` → `agent.budget`: `per_run_tokens`, `per_run_usd`, `monthly_tokens`, `monthly_usd`.

- Tokens counted = input + output + cache-creation tokens (cache reads are recorded but not counted; they
  are cheap and would make agent loops look many times more expensive than they are).
- Before a run: refuse if the month's total (summed from `agent/runs/`) is at a cap.
- During a run: stop as soon as the run or month exceeds a token cap. The SDK's `max_budget_usd` is set to
  the tighter of the per-run and remaining-monthly dollar caps (a hard stop), and `task_budget` gives the
  model an advisory token target so it paces itself.
- Cost per run comes from the SDK's `total_cost_usd`.

### 7. Prompt caching (verified 2026-10-06)

The system prompt and tool definitions form the cached prefix, so they stay byte-stable: no dates, ids or
page names (those go in the user turn), and tools are built in a fixed order. `tests/test_agent.py` fails if
volatile content enters the prefix. The Claude Code harness applies the cache breakpoints. Measured on two
consecutive mission runs (`claude-sonnet-5-5`, demo workspace): run 1 wrote 4,850 and read 3,771 cached
tokens; run 2 read 6,759 and wrote 2,442, with only 26 uncached input tokens in each, and cost about 40% less.
The Agent page shows cached / written / uncached input per run and the month's cache hit rate.

## Consequences

- Chat history is replayed into each turn instead of resumed from a server-side session: more input tokens
  on long chats, but no transcripts outside the workspace. Compaction or summaries can come later.
- The Claude adapter needs the `claude` CLI installed and logged in (or `ANTHROPIC_API_KEY`). CI never needs
  either, because tests mock the model.
- New tools are added in one place (`agent/tools.py`), and write tools must go through `Service`. The
  service-layer guard test covers that.
