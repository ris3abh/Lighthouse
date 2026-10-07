"""Rule-based criteria engine: profile rubric + accepted exhibits -> scoreboard.

The rules are deliberately simple and explainable. For each criterion in the profile:

* only exhibits filed under the criterion, of one of its ``evidence_types``, *and* at a completed
  stage (or with no stage) count — an invitation is not a completion;
* strength signals are the union of the counted exhibits' ``signals`` that the profile lists, plus
  ``multiple_instances`` when the profile lists it and two or more exhibits count;
* ``banked``   — count >= ``bank.min_exhibits`` and distinct signals >= ``bank.min_signals``;
* ``building`` — at least one counted exhibit, or evidence still at an earlier stage (invited, submitted);
* ``gap``      — none;
* exhibits from a self-reported source (e.g. imported chat history) never count;
* a user override in ``lighthouse.yaml`` (``dropped`` or ``gap``) always wins.

Judgment ("how would a reviewer see this?") is the agent's job and lives in ``reviewer_note``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from lighthouse_gc.core.models import NON_EVIDENTIARY_TIERS, Exhibit, stage_counts, utcnow
from lighthouse_gc.core.text import plural
from lighthouse_gc.criteria.models import CriterionScore, Profile, Scoreboard
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


def rules_digest(profile: Profile) -> str:
    """Changes whenever the profile's criteria, labels or rules change."""
    import hashlib

    return hashlib.sha256(profile.model_dump_json().encode()).hexdigest()[:16]


def score(
    profile: Profile,
    exhibits: Iterable[Exhibit],
    overrides: Mapping[str, str] | None = None,
) -> Scoreboard:
    overrides = overrides or {}
    exhibits = list(exhibits)
    rows: list[CriterionScore] = []

    for crit in profile.criteria:
        # Self-reported material (your own chat history, notes) never counts, however it got here.
        self_reported = [
            e for e in exhibits if e.criterion == crit.id and e.source_tier in NON_EVIDENTIARY_TIERS
        ]
        filed = [e for e in exhibits if e.criterion == crit.id and e.source_tier not in NON_EVIDENTIARY_TIERS]
        typed = [e for e in filed if e.evidence_type in crit.evidence_types]
        counted = [e for e in typed if stage_counts(e.stage)]
        in_progress = [e for e in typed if not stage_counts(e.stage)]
        off_type = len(filed) - len(typed)

        listed = [s.id for s in crit.strength_signals]
        seen = {s for e in counted for s in e.signals}
        if AUTO_MULTIPLE in listed and len(counted) >= 2:
            seen.add(AUTO_MULTIPLE)
        matched = [s for s in listed if s in seen]
        missing = [s for s in listed if s not in seen]

        need_exhibits = max(0, crit.bank.min_exhibits - len(counted))
        need_signals = max(0, crit.bank.min_signals - len(matched))

        if not counted and in_progress:
            status = "building"
            reason = "Nothing completed yet."
        elif not counted:
            status, reason = "gap", "No accepted exhibits yet."
        elif need_exhibits == 0 and need_signals == 0:
            status = "banked"
            reason = (f"{plural(len(counted), 'exhibit')} with {plural(len(matched), 'strength signal')} "
                      f"{'meets' if len(counted) == 1 else 'meet'} the bar.")  # fmt: skip
        else:
            status = "building"
            parts = []
            if need_exhibits:
                parts.append(f"{plural(need_exhibits, 'more exhibit')}")
            if need_signals:
                parts.append(f"{plural(need_signals, 'more strength signal')}")
            reason = "Needs " + " and ".join(parts) + "."
        if in_progress:
            stages = ", ".join(sorted({e.stage or "" for e in in_progress}))
            reason += f" {plural(len(in_progress), 'exhibit')} not counted until completed (stage: {stages})."
        if self_reported:
            reason += f" {plural(len(self_reported), 'self-reported exhibit')} ignored: self-reported items never count."
        if off_type:
            reason += (f" {plural(off_type, 'exhibit')} filed here {'has' if off_type == 1 else 'have'} an evidence type "
                       "this profile doesn't list.")  # fmt: skip

        override = overrides.get(crit.id)
        if override in ("dropped", "gap"):
            reason = f"Marked {override} by you. Rules say: {status} — {reason}"
            status = override

        rows.append(
            CriterionScore(
                id=crit.id,
                label=crit.label,
                short_label=crit.short_label or crit.label,
                status=status,  # type: ignore[arg-type]
                exhibit_count=len(counted),
                exhibit_ids=[e.id for e in counted],
                matched_signals=matched,
                missing_signals=missing,
                needed_exhibits=need_exhibits,
                in_progress_count=len(in_progress),
                reason=reason.strip(),
                overridden=override in ("dropped", "gap"),
            )
        )

    board = Scoreboard(
        profile=profile.id,
        profile_name=profile.name,
        computed_at=utcnow(),
        threshold=profile.threshold,
        target=profile.target,
        banked=sum(r.status == "banked" for r in rows),
        building=sum(r.status == "building" for r in rows),
        criteria=rows,
    )
    board.rules_digest = rules_digest(profile)
    return board
