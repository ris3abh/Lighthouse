"""The agent engine behind one interface (ADR 0005, ADR 0015): the OpenAI Responses API."""

from __future__ import annotations

from areao1.engine.base import Engine, EngineUnavailable


def get_engine(name: str = "openai") -> Engine:
    """The engine named in areao1.yaml. Only OpenAI is left; older names load as OpenAI (ADR 0015)."""
    from areao1.engine.openai_engine import OpenAIEngine

    return OpenAIEngine()


__all__ = ["Engine", "EngineUnavailable", "get_engine"]
