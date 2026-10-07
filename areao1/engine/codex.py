"""Codex adapter: a stub behind the same interface (ADR 0005 §1). Switch with ``engine: codex`` once it lands."""

from __future__ import annotations

from areao1.engine.base import AgentTool, Emit, EngineRequest, EngineResult, EngineUnavailable


class CodexEngine:
    name = "codex"

    def available(self) -> tuple[bool, str]:
        return False, "The Codex adapter isn't implemented yet; set `engine: claude_code` in areao1.yaml."

    async def run(self, request: EngineRequest, tools: list[AgentTool], emit: Emit) -> EngineResult:
        raise EngineUnavailable(self.available()[1])
