"""Rule-based criteria engine: profile rubric + accepted exhibits -> scoreboard.

The rules are deliberately simple and explainable. For each criterion in the profile:

* only exhibits filed under the criterion *and* of one of its ``evidence_types`` count;
* strength signals are the union of the counted exhibits' ``signals`` that the profile lists, plus
  ``multiple_instances`` when the profile lists it and two or more exhibits count;
* ``banked``   — count >= ``bank.min_exhibits`` and distinct signals >= ``bank.min_signals``;
* ``building`` — at least one counted exhibit;
* ``gap``      — none;
* a user override in ``lighthouse.yaml`` (``dropped`` or ``gap``) always wins.

Judgment ("how would a reviewer see this?") is the agent's job and lives in ``reviewer_note``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from lighthouse_gc.core.models import CriterionScore, Exhibit, Profile, Scoreboard, utcnow
from lighthouse_gc.resources import profiles_dir

AUTO_MULTIPLE = "multiple_instances"


def load_profile(path: Path) -> Profile:
    return Profile.model_validate(yaml.safe_load(path.read_text()))


def load_profiles(*extra_dirs: Path) -> dict[str, Profile]:
    """Bundled profiles, overridden/extended by any ``*.yaml`` in ``extra_dirs`` (e.g. workspace/profiles)."""
    profiles: dict[str, Profile] = {}
    for directory in (profiles_dir(), *extra_dirs):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            profile = load_profile(path)
            profiles[profile.id] = profile
    return profiles


def score(
    profile: Profile,
    exhibits: Iterable[Exhibit],
    overrides: Mapping[str, str] | None = None,
) -> Scoreboard:
    overrides = overrides or {}
    exhibits = list(exhibits)
    rows: list[CriterionScore] = []

    for crit in profile.criteria:
        filed = [e for e in exhibits if e.criterion == crit.id]
        counted = [e for e in filed if e.evidence_type in crit.evidence_types]
        off_type = len(filed) - len(counted)

        listed = [s.id for s in crit.strength_signals]
        seen = {s for e in counted for s in e.signals}
        if AUTO_MULTIPLE in listed and len(counted) >= 2:
            seen.add(AUTO_MULTIPLE)
        matched = [s for s in listed if s in seen]
        missing = [s for s in listed if s not in seen]

        need_exhibits = max(0, crit.bank.min_exhibits - len(counted))
        need_signals = max(0, crit.bank.min_signals - len(matched))

        if not counted:
            status, reason = "gap", "No accepted exhibits yet."
        elif need_exhibits == 0 and need_signals == 0:
            status = "banked"
            reason = f"{len(counted)} exhibit(s) with {len(matched)} strength signal(s) meet the bar."
        else:
            status = "building"
            parts = []
            if need_exhibits:
                parts.append(f"{need_exhibits} more exhibit(s)")
            if need_signals:
                parts.append(f"{need_signals} more strength signal(s)")
            reason = "Needs " + " and ".join(parts) + "."
        if off_type:
            reason += f" {off_type} exhibit(s) filed here have an evidence type this profile doesn't list."

        override = overrides.get(crit.id)
        if override in ("dropped", "gap"):
            reason = f"Marked {override} by you. Rules say: {status} — {reason}"
            status = override

        rows.append(
            CriterionScore(
                id=crit.id,
                label=crit.label,
                status=status,  # type: ignore[arg-type]
                exhibit_count=len(counted),
                exhibit_ids=[e.id for e in counted],
                matched_signals=matched,
                missing_signals=missing,
                needed_exhibits=need_exhibits,
                reason=reason.strip(),
                overridden=override in ("dropped", "gap"),
            )
        )

    return Scoreboard(
        profile=profile.id,
        profile_name=profile.name,
        computed_at=utcnow(),
        threshold=profile.threshold,
        target=profile.target,
        banked=sum(r.status == "banked" for r in rows),
        building=sum(r.status == "building" for r in rows),
        criteria=rows,
    )
