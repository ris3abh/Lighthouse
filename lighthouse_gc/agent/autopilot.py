"""Autopilot policy (ADR 0005 §3): which agent changes may be applied without the user's approval.

Three categories, each off by default and toggled in Settings: tracker updates, metrics, Tier-1 deadlines.
Whatever is switched on, nothing that could affect a criterion is ever auto-applied. ``AUTO_ACTIONS`` is the
complete list of service actions autopilot may perform. ``Service(auto=True)`` refuses everything else, and
a test proves the two sets never overlap.
"""

from __future__ import annotations

from urllib.parse import urlparse

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
    "profile.set", "settings.autopilot", "settings.missions",
})  # fmt: skip

# Fields autopilot may change on each tracker. Anything else (e.g. a pipeline item's criterion, a letter's
# criteria) goes to the Inbox instead.
AUTO_FIELDS: dict[str, frozenset[str]] = {
    "pipeline_item": frozenset({"stage", "follow_up", "notes", "url", "title"}),
    "letter": frozenset({"status", "last_contact", "asks", "credentials"}),
    "deadline": frozenset({"done", "due", "title", "url", "kind"}),
}

# Tier 1 (SPEC 5a): primary law and agency sources.
TIER1_DOMAINS = ("uscis.gov", "ecfr.gov", "federalregister.gov", "travel.state.gov", "justice.gov")


class AutopilotRefused(PermissionError):
    pass


def is_tier1(url: str | None) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in TIER1_DOMAINS)


def allowed(category: str, cfg: AutopilotConfig) -> bool:
    return bool(getattr(cfg, category, False))


def fields_allowed(target_type: str, changes: dict[str, object]) -> bool:
    return bool(changes) and set(changes) <= AUTO_FIELDS.get(target_type, frozenset())
