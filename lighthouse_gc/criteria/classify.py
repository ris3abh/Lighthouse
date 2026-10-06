"""First guess at where a dropped file belongs, from its name. Only a starting point for the Inbox.

The user always confirms criterion, evidence type and stage before anything is filed. A file whose name
mentions an invitation is proposed at stage ``invited``, because an invitation is not a completion.
"""

from __future__ import annotations

import re

from lighthouse_gc.criteria.models import Profile

# (pattern, criterion, evidence type). First match wins, so the more specific patterns come first.
RULES: list[tuple[str, str, str]] = [
    (r"review(er|ing)?|program.?committee|\bpc\b", "judging", "reviewer_record"),
    (r"judg", "judging", "judge_invite"),
    (r"award|prize|winner|first.?place|fellowship", "awards", "award_certificate"),
    (r"member", "membership", "membership_certificate"),
    (r"press|article|interview|podcast|news|feature", "press", "press_article"),
    (r"paper|arxiv|preprint|journal|proceedings|publication", "scholarly_articles", "paper"),
    (r"offer|pay.?stub|payslip|\bw-?2\b|salary|compensation", "high_salary", "pay_stub"),
    (r"org.?chart|role|employment|verification", "critical_role", "role_letter"),
    (r"patent", "original_contributions", "patent"),
    (r"exhibition|showcase|gallery", "display", "exhibition_record"),
]
INVITED = re.compile(r"invit", re.I)
COMPLETED = re.compile(r"complet|confirm|thank|certificate", re.I)


def classify(filename: str, profile: Profile) -> tuple[str, str, str | None]:
    """(criterion, evidence_type, stage). Empty criterion means "you decide"."""
    name = re.sub(r"[_\-.]+", " ", filename.lower())
    for pattern, criterion, etype in RULES:
        if not re.search(pattern, name):
            continue
        crit = profile.criterion(criterion)
        if crit is None:
            continue
        if etype not in crit.evidence_types:
            etype = crit.evidence_types[0]
        stage = None
        if criterion == "judging":
            stage = "invited" if INVITED.search(name) and not COMPLETED.search(name) else "completed"
        elif INVITED.search(name):
            stage = "invited"
        return criterion, etype, stage
    return "", "document", None
