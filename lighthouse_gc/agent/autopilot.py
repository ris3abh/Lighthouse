"""Autopilot policy (ADR 0005 §3): which agent changes may be applied without the user's approval.

Three categories, each off by default and toggled in Settings: tracker updates, metrics, Tier-1 deadlines.
Whatever is switched on, nothing that could affect a criterion is ever auto-applied. ``AUTO_ACTIONS`` is the
complete list of service actions autopilot may perform. ``Service(auto=True)`` refuses everything else, and
a test proves the two sets never overlap.
"""

from __future__ import annotations

import functools
from typing import Any

from lighthouse_gc.core.models import AutopilotConfig

# Service actions autopilot may perform, per category.
CATEGORY_ACTIONS: dict[str, frozenset[str]] = {
    "tracker_updates": frozenset({"pipeline.update", "pipeline.move", "letter.update", "deadline.update"}),
    "metrics": frozenset({"metrics.record"}),
    "tier1_deadlines": frozenset({"deadline.add"}),
}
AUTO_ACTIONS: frozenset[str] = frozenset().union(*CATEGORY_ACTIONS.values())

# Actions that can change what counts toward a criterion. Never auto-applied, whatever the settings.
CRITERION_ACTIONS: frozenset[str] = frozenset({
    "inbox.accept", "inbox.edit", "inbox.upload", "evidence.upload", "evidence.remap", "criterion.override",
    "profile.set", "settings.autopilot", "settings.missions", "vault.promote",
})  # fmt: skip

# Fields autopilot may change on each tracker. Anything else (e.g. a pipeline item's criterion, a letter's
# criteria) goes to the Inbox instead.
AUTO_FIELDS: dict[str, frozenset[str]] = {
    "pipeline_item": frozenset({"stage", "follow_up", "notes", "url", "title"}),
    "letter": frozenset({"status", "last_contact", "asks", "credentials"}),
    "deadline": frozenset({"done", "due", "title", "url", "kind"}),
}


@functools.cache
def _manifest() -> Any:
    from lighthouse_gc.vault import load_manifest

    return load_manifest()


class AutopilotRefused(PermissionError):
    pass


def is_tier1(url: str | None) -> bool:
    """On a Tier 1 domain of the vault manifest (SPEC 5a: primary law and agency sources)."""
    return _manifest().tier_of(url or "") == 1


def allowed(category: str, cfg: AutopilotConfig) -> bool:
    return bool(getattr(cfg, category, False))


def fields_allowed(target_type: str, changes: dict[str, object]) -> bool:
    return bool(changes) and set(changes) <= AUTO_FIELDS.get(target_type, frozenset())
