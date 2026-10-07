"""Claude Agent SDK adapter (ADR 0005 §1–2).

Runs the Claude Code harness locked down to: the built-in ``WebSearch`` tool and our in-process MCP tools.
No shell, no file tools, no user settings, hooks, plugins or MCP servers, and no session transcripts on
disk. ``query`` is injectable so tests never call a model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from lighthouse_gc.engine.base import (
    AgentEvent,
    AgentTool,
    Emit,
    EngineRequest,
    EngineResult,
    EngineUnavailable,
    StopRun,
)
from lighthouse_gc.engine.connect import find_cli, stored_key

SERVER = "lighthouse"
BLOCKED_BUILTINS = ["Bash", "BashOutput", "KillShell", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit",
                    "Glob", "Grep", "WebFetch", "Task", "TodoWrite", "Skill", "SlashCommand"]  # fmt: skip


def tool_id(name: str) -> str:
    return f"mcp__{SERVER}__{name}"


def short_name(name: str) -> str:
    return name.removeprefix(f"mcp__{SERVER}__")


class ClaudeAgentEngine:
    name = "claude_code"

    def __init__(self, query: Callable[..., AsyncIterator[Any]] | None = None):
        self._query = query

    def available(self) -> tuple[bool, str]:
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError:
            return False, "claude-agent-sdk isn't installed (pip install claude-agent-sdk)"
        if self._query is None and find_cli()[0] is None:
            return (
                False,
                "No Claude Code found. Connect your AI in Settings > Agent (an Anthropic API key works).",
            )
        return True, "ready"

    def options(self, request: EngineRequest, tools: list[AgentTool]) -> Any:
        from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, TaskBudget, create_sdk_mcp_server, tool
        from mcp.types import ToolAnnotations

        sdk_tools = []
        for t in tools:
            sdk_tools.append(
                tool(t.name, t.description, t.input_schema,
                     annotations=ToolAnnotations(readOnlyHint=t.read_only, destructiveHint=False))(_wrap(t))
            )  # fmt: skip
        server = create_sdk_mcp_server(SERVER, tools=sdk_tools)
        builtins = ["WebSearch"] if request.web_search else []
        key = stored_key()  # a key from Settings goes to the CLI process only, never into the workspace
        return ClaudeAgentOptions(
            env={"ANTHROPIC_API_KEY": key} if key else {},
            system_prompt=request.system_prompt,
            model=request.model,
            effort=request.effort,  # type: ignore[arg-type]
            tools=builtins,
            allowed_tools=[*builtins, *(tool_id(t.name) for t in tools)],
            disallowed_tools=list(BLOCKED_BUILTINS),
            mcp_servers={SERVER: server},
            strict_mcp_config=True,
            setting_sources=[],
            permission_mode="dontAsk",
            max_turns=request.max_turns,
            max_budget_usd=request.max_budget_usd,
            task_budget=TaskBudget(total=request.task_budget_tokens) if request.task_budget_tokens else None,
            include_partial_messages=True,
            extra_args={"no-session-persistence": None},
            hooks={"PreToolUse": [HookMatcher(matcher="WebSearch", hooks=[_guard_hook(request.guard)])]}
            if request.guard
            else None,
        )

    async def run(self, request: EngineRequest, tools: list[AgentTool], emit: Emit) -> EngineResult:
        ok, why = self.available()
        if not ok:
            raise EngineUnavailable(why)
        from claude_agent_sdk import (
            AssistantMessage,
            ResultMessage,
            ServerToolUseBlock,
            StreamEvent,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        if self._query is None:
            from claude_agent_sdk import query as sdk_query

            self._query = sdk_query
        result = EngineResult()
        seen_messages: set[str] = set()
        texts: list[str] = []
        stream = self._query(prompt=request.prompt, options=self.options(request, tools))
        try:
            async for msg in stream:
                if isinstance(msg, StreamEvent):
                    ev = msg.event or {}
                    delta = ev.get("delta") or {}
                    if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        await emit(AgentEvent("text_delta", {"text": delta.get("text", "")}))
                elif isinstance(msg, AssistantMessage):
                    if msg.error:
                        await emit(AgentEvent("error", {"error": msg.error}))
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            texts.append(block.text)
                            await emit(AgentEvent("text", {"text": block.text}))
                        elif isinstance(block, ToolUseBlock | ServerToolUseBlock):
                            name = short_name(block.name)
                            await emit(
                                AgentEvent("tool_call", {"id": block.id, "name": name, "input": block.input})
                            )
                    # One API message can arrive as several AssistantMessages; count its usage once.
                    key = msg.message_id or str(id(msg))
                    if msg.usage and key not in seen_messages:
                        seen_messages.add(key)
                        await emit(AgentEvent("usage", _usage(msg.usage)))
                elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            await emit(AgentEvent("tool_result", {"id": block.tool_use_id, "ok": not block.is_error,
                                                                   "summary": _summary(block.content)}))  # fmt: skip
                elif isinstance(msg, ResultMessage):
                    result.cost_usd = msg.total_cost_usd
                    result.stop_reason = msg.subtype if msg.is_error else (msg.stop_reason or msg.subtype)
                    result.is_error = msg.is_error
                    if msg.is_error:
                        result.error = "; ".join(msg.errors or []) or msg.subtype
                    if msg.result and not texts:
                        texts.append(msg.result)
        except StopRun as stop:
            result.stop_reason = stop.reason
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        result.text = texts[-1] if texts else ""
        return result


def _guard_hook(guard: Callable[[str, dict[str, Any]], Awaitable[str | None]]) -> Any:
    async def hook(data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        reason = await guard(str(data.get("tool_name", "")), dict(data.get("tool_input") or {}))
        if reason is None:
            return {}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": reason}}  # fmt: skip

    return hook


def _wrap(t: AgentTool) -> Callable[[dict[str, Any]], Any]:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            text = await t.handler(args)
            return {"content": [{"type": "text", "text": text}]}
        except Exception as exc:  # the model sees the error and can recover
            return {"content": [{"type": "text", "text": f"Error: {exc}"}], "is_error": True}

    return handler


def _usage(raw: dict[str, Any]) -> dict[str, int]:
    keys = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return {k: int(raw.get(k) or 0) for k in keys}


def _summary(content: Any) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    else:
        text = ""
    text = " ".join(text.split())
    return text[:300] + ("…" if len(text) > 300 else "")
