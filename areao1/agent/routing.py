"""Model routing (ADR 0009 §2): three tiers, picked by task from a fixed table, never by a model call.

Tiers come from the environment or the workspace `.env` (AREAO1_MODEL_HARD / _MID / _MUNDANE). The mundane
tier uses OpenAI when an OpenAI key is set (OPENAI_API_KEY, or `openai:api_key` in the keychain), else Claude
Haiku. A model set in areao1.yaml that differs from the shipped default still wins, so a workspace that
chose its models keeps them."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from areao1.core import migrate, names
from areao1.core.models import AgentModels
from areao1.core.secrets import _read_dotenv, get_secret

Tier = Literal["hard", "mid", "mundane"]

DEFAULTS: dict[Tier, str] = {"hard": "claude-opus-5-5", "mid": "claude-sonnet-5-5",
                             "mundane": "claude-haiku-4-5-20251001"}  # fmt: skip
OPENAI_MUNDANE = "gpt-5-mini"
OPENAI_KEY_REF = "openai:api_key"

# task -> tier. Run kinds (chat, manual, scheduled) are tasks too.
TASKS: dict[str, Tier] = {
    "chat": "hard",
    "manual": "hard",
    "letter": "hard",
    "scheduled": "mid",
    "check": "mid",
    "pdf": "mid",
    "cheap_chat": "mid",
    "chat_extract": "mundane",
    "summarize": "mundane",
    "classify": "mundane",
}
# The areao1.yaml slot that overrides each task, when it was changed from the shipped default.
SLOT: dict[str, str] = {"chat": "chat", "cheap_chat": "chat", "manual": "task", "letter": "task",
                        "scheduled": "mission", "check": "check", "pdf": "check", "chat_extract": "mundane",
                        "summarize": "mundane", "classify": "mundane"}  # fmt: skip


@dataclass(frozen=True)
class Route:
    task: str
    tier: Tier
    provider: Literal["anthropic", "openai"]
    model: str


def _env(name: str, workspace: Path | None) -> str | None:
    """AREAO1_MODEL_HARD (or a Lighthouse-era LIGHTHOUSE_MODEL_HARD) from the environment, else the workspace .env.
    ``name`` is the new name; OPENAI_API_KEY has no prefix."""
    if name.startswith(names.ENV_PREFIX):
        value = migrate.env(name.removeprefix(names.ENV_PREFIX))
        if value:
            return value
    elif os.environ.get(name):
        return os.environ[name]
    if workspace is None:
        return None
    dotenv = _read_dotenv(workspace / ".env")
    old = [p + name.removeprefix(names.ENV_PREFIX) for p in names.PREVIOUS["env_prefixes"]]
    return dotenv.get(name) or next((dotenv[o] for o in old if dotenv.get(o)), None)


def openai_key(workspace: Path | None = None) -> str | None:
    return _env("OPENAI_API_KEY", workspace) or get_secret(OPENAI_KEY_REF)


def route(
    task: str, models: AgentModels | None = None, workspace: Path | None = None, cheap: bool = False
) -> Route:
    if cheap and task == "chat":
        task = "cheap_chat"
    tier = TASKS.get(task, "hard")
    slot = SLOT.get(task)
    shipped = AgentModels()
    if models is not None and slot and getattr(models, slot) != getattr(shipped, slot):
        model = getattr(models, slot)
        return Route(
            task,
            tier,
            "anthropic" if model.startswith("claude") else "openai",
            model,
        )
    if tier == "mundane" and openai_key(workspace):
        return Route(task, tier, "openai", _env("AREAO1_MODEL_MUNDANE", workspace) or OPENAI_MUNDANE)
    env = {
        "hard": "AREAO1_MODEL_HARD",
        "mid": "AREAO1_MODEL_MID",
        "mundane": "AREAO1_MODEL_MUNDANE",
    }[tier]
    model = _env(env, workspace) or DEFAULTS[tier]
    if tier == "mundane" and not model.startswith("claude"):
        model = DEFAULTS["mundane"]  # an OpenAI model name without an OpenAI key: stay on Claude
    return Route(task, tier, "anthropic", model)


def table(
    models: AgentModels | None = None, workspace: Path | None = None, cheap: bool = False
) -> list[Route]:
    """Every task's route, for the Agent page and Settings."""
    return [route(t, models, workspace, cheap) for t in TASKS if t != "cheap_chat"]
