"""Read-only workspace queries exposed over MCP (SPEC 5b "Agent memory", 8 "Chat").

Plain functions over a :class:`~areao1.criteria.case.Case` that return JSON-able dicts, so they are
easy to test and reuse. None of them writes a workspace file. The only thing that may be touched is the
disposable SQLite index under ``.areao1/cache/``. Writes from agents (propose_claim, add_candidate)
arrive later and will go through the Inbox.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from areao1.core.models import Claim, stage_counts
from areao1.criteria import engine
from areao1.criteria.case import Case
from areao1.criteria.models import Scoreboard

NOTE = (
    "Rule-based status from accepted exhibits. Not legal advice and not affiliated with USCIS; "
    "confirm strategy with an immigration attorney."
)


class ToolError(ValueError):
    pass


def _board(ws: Case) -> Scoreboard:
    # Score in memory instead of ws.scoreboard(), which may write criteria.json.
    pid = ws.profile_id()
    return engine.score(ws.profile(pid), ws.exhibits().exhibits, ws.config().overrides.get(pid))


def _parse_day(value: str | None, name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ToolError(f"{name} must be an ISO date (YYYY-MM-DD), got {value!r}") from exc


# ----------------------------------------------------------------------------- scoreboard


def get_scoreboard(ws: Case) -> dict[str, Any]:
    board = _board(ws)
    return {
        "profile": board.profile,
        "profile_name": board.profile_name,
        "banked": board.banked,
        "building": board.building,
        "threshold": board.threshold,
        "target": board.target,
        "criteria": [
            {
                "id": c.id,
                "label": c.label,
                "status": c.status,
                "exhibits_counted": c.exhibit_count,
                "in_progress": c.in_progress_count,
                "matched_signals": c.matched_signals,
                "reason": c.reason,
            }
            for c in board.criteria
        ],
        "note": NOTE,
    }


def list_gaps(ws: Case) -> dict[str, Any]:
    """Criteria not yet banked (and not dropped), with exactly what's missing and what's already in flight."""
    board = _board(ws)
    profile = ws.profile(board.profile)
    pending: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cand in ws.pending_candidates():
        if cand.kind == "evidence":
            pending[cand.proposed_criterion].append({"id": cand.id, "title": cand.title})
    exhibits = ws.exhibits().exhibits
    gaps = []
    for row in board.criteria:
        if row.status in ("banked", "dropped"):
            continue
        crit = profile.criterion(row.id)
        labels = {s.id: s.label for s in crit.strength_signals} if crit else {}
        gaps.append(
            {
                "id": row.id,
                "label": row.label,
                "status": row.status,
                "needs_exhibits": row.needed_exhibits,
                "needs_signals": max(0, (crit.bank.min_signals if crit else 0) - len(row.matched_signals)),
                "missing_signals": [labels.get(s, s) for s in row.missing_signals],
                "accepted_evidence_types": crit.evidence_types if crit else [],
                "in_progress": [
                    {"id": e.id, "title": e.title, "stage": e.stage}
                    for e in exhibits
                    if e.criterion == row.id and not stage_counts(e.stage)
                ],
                "pending_in_inbox": pending.get(row.id, []),
                "reason": row.reason,
            }
        )
    return {
        "profile": board.profile,
        "banked": board.banked,
        "threshold": board.threshold,
        "still_needed_to_reach_threshold": max(0, board.threshold - board.banked),
        "gaps": gaps,
        "note": NOTE,
    }


# ----------------------------------------------------------------------------- memory


def _claim_view(c: Claim, status: str, current: bool, source_url: str | None) -> dict[str, Any]:
    return {
        "id": c.id,
        "subject": c.subject,
        "predicate": c.predicate,
        "value": c.value,
        "stage": c.stage,
        "valid_from": c.valid_from.isoformat() if c.valid_from else None,
        "recorded_at": c.recorded_at.isoformat(),
        "status": status,
        "current": current,
        "confidence": c.confidence,
        "excerpt": c.excerpt,
        "source_url": source_url,
    }


def _resolve_entities(ws: Case, entity: str) -> list[str]:
    entities = ws.memory.entities()
    exact = [e.id for e in entities if e.id == entity]
    if exact:
        return exact
    needle = entity.lower()
    return [e.id for e in entities if needle in e.id.lower() or needle in e.name.lower()]


def query_claims(ws: Case, entity: str, as_of: str | None = None) -> dict[str, Any]:
    """Claims about an entity: the current ones, or what Area O1 believed on ``as_of``.

    ``entity`` is an entity id (e.g. ``artifact:github:octo/repo``) or a case-insensitive fragment of an
    entity id or name (e.g. ``fastgrad``). Only claims with status ``approved`` may be cited in drafts.
    """
    if not entity.strip():
        raise ToolError("entity is required")
    day = _parse_day(as_of, "as_of")
    subjects = _resolve_entities(ws, entity)
    mem = ws.memory
    observations = {o.id: o for o in mem.observations()}
    superseded = {e.dst for e in mem.edges() if e.type == "SUPERSEDES"}
    out = []
    for subject in subjects:
        for claim, status in mem.query_claims(subject=subject, as_of=day):
            obs = observations.get(claim.observation_id)
            out.append(
                _claim_view(claim, status, claim.id not in superseded, obs.source_url if obs else None)
            )
    return {
        "entity": entity,
        "matched_entities": subjects,
        "as_of": day.isoformat() if day else None,
        "claims": out,
        "rule": "Draft only from claims with status 'approved'; say what is unknown instead of filling gaps.",
    }


def get_provenance(ws: Case, claim_id: str) -> dict[str, Any]:
    """The full chain behind one claim: source snapshot, verified excerpt, reviews, versions, citations."""
    mem = ws.memory
    claims = {c.id: c for c in mem.claims()}
    claim = claims.get(claim_id)
    if claim is None:
        raise ToolError(f"no claim {claim_id!r}")
    obs = next((o for o in mem.observations() if o.id == claim.observation_id), None)
    verified = False
    if obs is not None:
        path = ws.root / obs.snapshot
        if path.exists():
            verified = (
                path.read_text(encoding="utf-8")[claim.excerpt_start : claim.excerpt_end] == claim.excerpt
            )
    edges = mem.edges()
    statuses = mem.statuses()
    entity = next((e for e in mem.entities() if e.id == claim.subject), None)
    exhibits = {e.id: e for e in ws.exhibits().exhibits}
    cited_by = [
        {"exhibit_id": e.src, "title": exhibits[e.src].title, "file": exhibits[e.src].file}
        for e in edges
        if e.type == "CITES" and e.dst == claim_id and e.src in exhibits
    ]

    def brief(cid: str) -> dict[str, Any]:
        c = claims[cid]
        return {"id": cid, "value": c.value, "valid_from": c.valid_from.isoformat() if c.valid_from else None}

    return {
        "claim": _claim_view(
            claim,
            statuses[claim.id],
            not any(e.type == "SUPERSEDES" and e.dst == claim_id for e in edges),
            obs.source_url if obs else None,
        ),
        "extracted_by": claim.extracted_by.model_dump(),
        "excerpt_offsets": [claim.excerpt_start, claim.excerpt_end],
        "excerpt_verified": verified,
        "observation": obs.model_dump(mode="json") if obs else None,
        "entity": entity.model_dump(mode="json") if entity else None,
        "reviews": [d.model_dump(mode="json") for d in mem.decisions() if d.claim_id == claim_id],
        "supersedes": [brief(e.dst) for e in edges if e.type == "SUPERSEDES" and e.src == claim_id],
        "superseded_by": [brief(e.src) for e in edges if e.type == "SUPERSEDES" and e.dst == claim_id],
        "cited_by": cited_by,
        "prov": {
            "entity": obs.id if obs else None,
            "activity": "extraction",
            "agent": f"{claim.extracted_by.kind}:{claim.extracted_by.name}",
            "wasDerivedFrom": obs.id if obs else None,
        },
    }


def what_changed(ws: Case, since: str) -> dict[str, Any]:
    """Everything recorded on or after ``since`` (YYYY-MM-DD): new claims, reviews, exhibits, candidates and
    metric movement. Use it to start a session where the last one ended."""
    day = _parse_day(since, "since")
    if day is None:
        raise ToolError("since is required (YYYY-MM-DD)")
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    mem = ws.memory
    claims = {c.id: c for c in mem.claims()}
    previous = {e.src: e.dst for e in mem.edges() if e.type == "SUPERSEDES"}
    new_claims = []
    for c in claims.values():
        if c.recorded_at < start:
            continue
        old = claims.get(previous.get(c.id, ""))
        new_claims.append(
            {
                "id": c.id,
                "subject": c.subject,
                "predicate": c.predicate,
                "value": c.value,
                "previous_value": old.value if old else None,
                "change": "updated" if old else "new",
            }
        )
    metric_changes = []
    by_series: dict[tuple[str, str, str], list[tuple[date, float]]] = defaultdict(list)
    for r in ws.metrics():
        by_series[(r.source, r.item, r.metric)].append((r.date, r.value))
    for (source, item, metric), points in sorted(by_series.items()):
        points.sort()
        before = [v for d, v in points if d < day]
        after = [v for d, v in points if d >= day]
        if after and before and after[-1] != before[-1]:
            metric_changes.append(
                {"source": source, "item": item, "metric": metric, "from": before[-1], "to": after[-1],
                 "delta": after[-1] - before[-1]}
            )  # fmt: skip
    return {
        "since": day.isoformat(),
        "claims": new_claims,
        "reviews": [d.model_dump(mode="json") for d in mem.decisions() if d.at >= start],
        "exhibits_accepted": [
            {"id": e.id, "criterion": e.criterion, "title": e.title, "stage": e.stage}
            for e in ws.exhibits().exhibits
            if e.accepted_at >= start
        ],
        "new_candidates": [
            {"id": c.id, "kind": c.kind, "title": c.title, "proposed_criterion": c.proposed_criterion}
            for c in ws.inbox().candidates
            if c.created_at >= start and c.status != "rejected"
        ],
        "metric_changes": metric_changes,
    }
