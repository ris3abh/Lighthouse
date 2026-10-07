"""Agent engine adapters behind one interface (ADR 0005): Claude Agent SDK today, Codex stubbed."""

from __future__ import annotations

from areao1.engine.base import Engine, EngineUnavailable


def get_engine(name: str) -> Engine:
    if name == "claude_code":
        from areao1.engine.claude_code import ClaudeAgentEngine

        return ClaudeAgentEngine()
    if name == "codex":
        from areao1.engine.codex import CodexEngine

        return CodexEngine()
    raise EngineUnavailable(f"engine {name!r} isn't available (use claude_code)")


__all__ = ["Engine", "EngineUnavailable", "get_engine"]
