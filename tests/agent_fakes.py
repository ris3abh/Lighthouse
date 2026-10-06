"""A scripted engine for tests: drives the real runner and the real tools without calling any model."""

from __future__ import annotations

from typing import Any

from lighthouse_gc.engine.base import AgentEvent, AgentTool, Emit, EngineRequest, EngineResult, StopRun


class FakeEngine:
    """``script`` steps: ("text", str) | ("tool", name, args) | ("usage", {...}) | ("fail", message)."""

    name = "fake"

    def __init__(self, script: list[tuple[Any, ...]] | None = None, cost: float = 0.01):
        self.script = script or [("text", "Hello from the fake engine.")]
        self.cost = cost
        self.requests: list[EngineRequest] = []
        self.tool_names: list[str] = []
        self.tool_outputs: list[tuple[str, bool, str]] = []

    def available(self) -> tuple[bool, str]:
        return True, "fake"

    async def run(self, request: EngineRequest, tools: list[AgentTool], emit: Emit) -> EngineResult:
        self.requests.append(request)
        self.tool_names = [t.name for t in tools]
        by_name = {t.name: t for t in tools}
        last = ""
        try:
            for i, step in enumerate(self.script):
                if step[0] == "text":
                    last = step[1]
                    await emit(AgentEvent("text_delta", {"text": step[1]}))
                    await emit(AgentEvent("text", {"text": step[1]}))
                elif step[0] == "tool":
                    _, name, args = step
                    tid = f"tool_{i}"
                    await emit(AgentEvent("tool_call", {"id": tid, "name": name, "input": args}))
                    try:
                        out, ok = await by_name[name].handler(args), True
                    except Exception as exc:
                        out, ok = f"Error: {exc}", False
                    self.tool_outputs.append((name, ok, out))
                    await emit(AgentEvent("tool_result", {"id": tid, "ok": ok, "summary": out[:300]}))
                elif step[0] == "usage":
                    await emit(AgentEvent("usage", step[1]))
                elif step[0] == "fail":
                    raise RuntimeError(step[1])
        except StopRun as stop:
            return EngineResult(text=last, cost_usd=self.cost, stop_reason=stop.reason)
        return EngineResult(text=last, cost_usd=self.cost, stop_reason="end_turn")
