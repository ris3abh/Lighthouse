"""The engine interface every adapter implements (ADR 0005 §1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

EventType = Literal["text_delta", "text", "tool_call", "tool_result", "usage", "error"]


@dataclass
class AgentEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTool:
    """A tool the engine exposes to the model. ``handler`` returns the text the model sees."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[str]]
    read_only: bool = True
    touches: tuple[str, ...] = ()  # workspace paths it reads (or, if not read_only, writes), shown in the UI


@dataclass
class EngineRequest:
    system_prompt: str
    prompt: str
    model: str
    effort: str = "medium"
    web_search: bool = True
    max_turns: int = 25
    max_budget_usd: float | None = None
    task_budget_tokens: int | None = None


@dataclass
class EngineResult:
    text: str = ""
    cost_usd: float | None = None
    stop_reason: str | None = None
    is_error: bool = False
    error: str | None = None


Emit = Callable[[AgentEvent], Awaitable[None]]


class EngineUnavailable(RuntimeError):
    """The engine can't run here (not installed, not logged in, not implemented)."""


class StopRun(Exception):
    """Raised by ``emit`` to end a run early (budget reached, user pressed stop)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Engine(Protocol):
    name: str

    def available(self) -> tuple[bool, str]:
        """(usable, human-readable reason)."""
        ...

    async def run(self, request: EngineRequest, tools: list[AgentTool], emit: Emit) -> EngineResult: ...
