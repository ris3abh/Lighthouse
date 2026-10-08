"""Model routing (ADR 0009 §2, ADR 0015 §2): three tiers, picked by task from a fixed table, never by a model call.

A tier's model is, in order: AREAO1_MODEL_HARD / _MID / _MUNDANE from the environment or the workspace `.env`, the
tier's line in areao1.yaml (`agent.models`), or the shipped default below. All tiers run on OpenAI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from areao1.core import migrate, names
from areao1.core.models import AgentModels
from areao1.core.secrets import _read_dotenv, get_secret

Tier = Literal["hard", "mid", "mundane"]

# One line per tier: upgrade a tier by changing its line (or agent.models in areao1.yaml).
DEFAULTS: dict[Tier, str] = {
    "hard": "gpt-6.1-sol",
    "mid": "gpt-6.1-sol",
    "mundane": "gpt-6-luna",
}
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
ENV: dict[Tier, str] = {
    "hard": "AREAO1_MODEL_HARD",
    "mid": "AREAO1_MODEL_MID",
    "mundane": "AREAO1_MODEL_MUNDANE",
}


@dataclass(frozen=True)
class Route:
    task: str
    tier: Tier
    provider: Literal["openai"]
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
    env = _env(ENV[tier], workspace)
    if env and env.startswith("claude"):
        env = None  # a Claude model from before ADR 0015: use the tier's OpenAI model
    model = env or getattr(models or AgentModels(), tier) or DEFAULTS[tier]
    return Route(task, tier, "openai", model)


def table(
    models: AgentModels | None = None, workspace: Path | None = None, cheap: bool = False
) -> list[Route]:
    """Every task's route, for the Agent page and Settings."""
    return [route(t, models, workspace, cheap) for t in TASKS if t != "cheap_chat"]
