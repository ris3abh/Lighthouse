"""The constellation memory map's data (ADR 0012): every claim as a star in its criterion's cluster, with what the sky
needs to draw it (status, confidence, conflict, superseded, date) and where its trail leads (source, citing
exhibits). Read-only; the memory files are unchanged."""

from __future__ import annotations

import re
from typing import Any

from areao1.core import clock
from areao1.criteria.case import Case

CONFIDENCE = {"high": 1.0, "medium": 0.66, "low": 0.33}
# A claim's criterion from its predicate, when nothing that cites it says (first match wins).
PREDICATE_HINTS: list[tuple[str, str]] = [
    (r"judg|review|program_committee|jury", "judging"),
    (r"award|prize|fellowship|winner|hackathon_win", "awards"),
    (r"member", "membership"),
    (r"press|article_about|interview|podcast|media|mention", "press"),
    (r"paper|citation|publication|preprint|h_index|scholar", "scholarly_articles"),
    (r"salary|compensation|pay", "high_salary"),
    (r"role|title|employ|lead|manager", "critical_role"),
    (r"star|fork|download|like|repo|model|dataset|contribut|patent|adoption", "original_contributions"),
    (r"exhibit|showcase|display", "display"),
]


def _status(review: str, superseded: bool) -> str:
    if superseded:
        return "superseded"
    return {"approved": "approved", "rejected": "rejected"}.get(review, "pending")


def stars(ws: Case) -> dict[str, Any]:
    mem = ws.memory
    profile = ws.profile()
    criteria = [c.id for c in profile.criteria]
    statuses = mem.statuses()
    edges = mem.edges()
    observations = {o.id: o for o in mem.observations()}
    entities = {e.id: e for e in mem.entities()}
    exhibits = {e.id: e for e in ws.exhibits().exhibits}
    superseded = {e.dst for e in edges if e.type == "SUPERSEDES"}
    conflicts = {x for e in edges if e.type == "CONTRADICTS" for x in (e.src, e.dst)}
    cited: dict[str, list[str]] = {}
    for e in edges:
        if e.type == "CITES" and e.src in exhibits:
            cited.setdefault(e.dst, []).append(e.src)
    by_candidate: dict[str, str] = {}
    for cand in ws.inbox().candidates:
        if cand.proposed_criterion:
            for cid in cand.claim_ids:
                by_candidate.setdefault(cid, cand.proposed_criterion)

    def criterion_of(claim_id: str, predicate: str) -> str:
        for ex in cited.get(claim_id, []):
            if exhibits[ex].criterion in criteria:
                return exhibits[ex].criterion
        if by_candidate.get(claim_id) in criteria:
            return by_candidate[claim_id]
        for pattern, crit in PREDICATE_HINTS:
            if crit in criteria and re.search(pattern, predicate):
                return crit
        return "other"

    out = []
    for c in mem.claims():
        obs = observations.get(c.observation_id)
        when = c.event_date or c.valid_from or clock.local_date(c.recorded_at)
        ent = entities.get(c.subject)
        out.append({
            "id": c.id, "criterion": criterion_of(c.id, c.predicate), "entity": c.subject,
            "entity_name": ent.name if ent else c.subject.split(":", 1)[-1], "predicate": c.predicate,
            "value": c.value if not isinstance(c.value, str) else c.value[:120], "stage": c.stage,
            "date": when.isoformat(), "confidence": CONFIDENCE.get(c.confidence, 0.66), "band": c.confidence,
            "status": _status(statuses.get(c.id, "proposed"), c.id in superseded), "review": statuses.get(c.id),
            "conflict": c.id in conflicts, "source": c.observation_id,
            "source_url": obs.source_url if obs else None, "connector": obs.connector if obs else None,
            "exhibits": cited.get(c.id, []),
        })  # fmt: skip
    out.sort(key=lambda s: (s["date"], s["id"]))
    labels = {c.id: (c.short_label or c.label) for c in profile.criteria}
    clusters = [{"id": cid, "label": labels[cid]} for cid in criteria]
    if any(s["criterion"] == "other" for s in out):
        clusters.append({"id": "other", "label": "Other"})
    return {"clusters": clusters, "stars": out,
            "exhibits": {eid: {"title": e.title, "criterion": e.criterion} for eid, e in exhibits.items()}}  # fmt: skip
