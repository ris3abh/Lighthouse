"""Proof recipes (ADR 0017): once an activity is accepted, completed, granted or published, the proof worth saving
while it's still easy to get, per criterion, from profiles/recipes/*.yaml (workspace overrides first).

Checklists are derived on read from the recipe, the activity (its *anchor*) and the links in data/proofs.json. An
item is done only when an exhibit preserves it (the anchor itself when its type or stage matches, or one the
person linked or uploaded) or the person marked it not applicable. Self-reported exhibits never mark an item done
(SPEC §2a.4). Matches found in Mail or sources become Inbox candidates; nothing is linked without the person."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from areao1.core import clock
from areao1.core.models import NON_EVIDENTIARY_TIERS, Candidate, Exhibit
from areao1.criteria.case import Case
from areao1.criteria.models import Recipe, RecipeItem
from areao1.resources import profiles_dir

TRIGGER_STAGES = frozenset({"accepted", "completed", "granted", "published"})
OPEN_STAGES = frozenset(
    {"invited", "accepted"}
)  # an activity that isn't done yet: its completion proof matters
COMPLETION_STAGES = frozenset({"completed", "granted", "published"})
MAX_TASKS = 5
_STOP = {"the", "and", "for", "with", "from", "your", "you", "our", "this", "that", "into", "about", "invitation",
         "judge", "judging", "review", "reviewing", "award", "proof", "thank", "thanks", "re", "fwd"}  # fmt: skip


def recipe_dirs(ws: Case) -> list[Path]:
    return [profiles_dir() / "recipes", ws.root / "profiles" / "recipes"]  # later wins


def load_recipes(ws: Case) -> dict[str, Recipe]:
    out: dict[str, Recipe] = {}
    for d in recipe_dirs(ws):
        if d.is_dir():
            for path in sorted(d.glob("*.yaml")):
                recipe = Recipe.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
                out[recipe.criterion] = recipe
    return out


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower()) if w not in _STOP and not w.isdigit()}


def _has_keyword(text: str, item: RecipeItem) -> bool:
    low = f" {text.lower()} "
    return any(k in low for k in item.match.keywords)


def _matches_exhibit(item: RecipeItem, ex: Exhibit) -> bool:
    """An activity matches when its type and stage both fit what the item names: a thank-you filed as a
    judge_invite at "completed" is the completion, not the invitation, and an award notice isn't the certificate.
    A document with no stage matches by its type."""
    m = item.match
    if ex.stage is None:  # a document, not an activity: its type says what it is
        return bool(m.evidence_types and ex.evidence_type in m.evidence_types)
    if not m.evidence_types and not m.stages:
        return False
    types_ok = not m.evidence_types or ex.evidence_type in m.evidence_types
    return types_ok and (not m.stages or ex.stage in m.stages)


def _anchor_items(recipe: Recipe, evidence_type: str | None) -> bool:
    return not recipe.applies_to or evidence_type in recipe.applies_to


def anchors(ws: Case, recipes: dict[str, Recipe] | None = None) -> list[dict[str, Any]]:
    """Activities that get a checklist: exhibits at a trigger stage, pipeline items moved to done, and approved claims
    at a trigger stage that no exhibit cites yet. An exhibit linked as another activity's proof isn't one itself."""
    from areao1.criteria import constellation

    recipes = recipes if recipes is not None else load_recipes(ws)
    linked = {x.exhibit_id for x in ws.proofs().links if x.exhibit_id}
    out: list[dict[str, Any]] = []
    for ex in ws.exhibits().exhibits:
        if (ex.criterion in recipes and ex.stage in TRIGGER_STAGES and ex.id not in linked
                and ex.source_tier not in NON_EVIDENTIARY_TIERS and _anchor_items(recipes[ex.criterion], ex.evidence_type)):  # fmt: skip
            out.append({"anchor": f"exhibit:{ex.id}", "kind": "exhibit", "title": ex.title, "criterion": ex.criterion,
                        "stage": ex.stage, "date": ex.date.isoformat(), "exhibit": ex})  # fmt: skip
    for p in ws.pipeline().items:
        if p.stage == "done" and p.criterion in recipes:
            out.append({"anchor": f"pipeline:{p.id}", "kind": "pipeline", "title": p.title, "criterion": p.criterion,
                        "stage": "completed", "date": clock.local_date(p.moved_at).isoformat(), "exhibit": None})  # fmt: skip
    for s in constellation.stars(ws)["stars"]:
        if (s["status"] == "approved" and s["stage"] in TRIGGER_STAGES and not s["exhibits"]
                and s["criterion"] in recipes):  # fmt: skip
            out.append({"anchor": f"claim:{s['id']}", "kind": "claim", "title": f"{s['entity_name']}: {s['value']}",
                        "criterion": s["criterion"], "stage": s["stage"], "date": s["date"], "exhibit": None})  # fmt: skip
    out.sort(key=lambda a: (a["date"], a["anchor"]), reverse=True)
    return out


def checklists(ws: Case) -> list[dict[str, Any]]:
    recipes = load_recipes(ws)
    exhibits = {e.id: e for e in ws.exhibits().exhibits}
    links = {(x.anchor, x.item): x for x in ws.proofs().links}
    used = {x.exhibit_id for x in links.values() if x.exhibit_id}
    out = []
    for a in anchors(ws, recipes):
        recipe = recipes[a["criterion"]]
        anchor_ex: Exhibit | None = a["exhibit"]
        items = []
        for item in recipe.items:
            link = links.get((a["anchor"], item.id))
            row: dict[str, Any] = {"id": item.id, "label": item.label, "why": item.why, "optional": item.optional,
                                   "status": "missing", "via": None, "exhibit_id": None, "exhibit_title": None,
                                   "note": "", "suggestions": []}  # fmt: skip
            if link and link.status == "waived":
                row.update(status="waived", note=link.note)
            elif link and link.exhibit_id in exhibits:
                ex = exhibits[link.exhibit_id]
                counts = ex.source_tier not in NON_EVIDENTIARY_TIERS
                row.update(status="done" if counts else "self_reported", via="linked", exhibit_id=ex.id,
                           exhibit_title=ex.title)  # fmt: skip
            elif anchor_ex is not None and _matches_exhibit(item, anchor_ex):
                row.update(
                    status="done", via="anchor", exhibit_id=anchor_ex.id, exhibit_title=anchor_ex.title
                )
            if row["status"] in ("missing", "self_reported"):
                row["suggestions"] = [
                    {"id": ex.id, "title": ex.title}
                    for ex in exhibits.values()
                    if ex.criterion == a["criterion"] and ex.id != (anchor_ex.id if anchor_ex else None)
                    and ex.id not in used and ex.source_tier not in NON_EVIDENTIARY_TIERS
                    and (_matches_exhibit(item, ex) or _has_keyword(f"{ex.title} {ex.file}", item))
                ][:3]  # fmt: skip
            items.append(row)
        missing = [i for i in items if i["status"] in ("missing", "self_reported") and not i["optional"]]
        out.append({k: v for k, v in a.items() if k != "exhibit"} | {"recipe": recipe.label, "items": items,
                                                                       "missing": len(missing)})  # fmt: skip
    return out


def completion_missing(checklist: dict[str, Any]) -> bool:
    """For an activity still at invited / accepted: no completion item (a recipe item satisfied by a completed,
    granted or published stage) is done."""
    return checklist["stage"] in OPEN_STAGES and not any(
        i["status"] == "done"
        and i["id"] in ("completion", "certificate", "published_copy", "membership_proof")
        for i in checklist["items"]
    )


def tasks(ws: Case) -> list[dict[str, Any]]:
    """This week's lines: the activities with proof still to save, most recent first."""
    from areao1.core.text import plural

    out = []
    for c in checklists(ws):
        if c["missing"]:
            out.append({"kind": "proof", "title": f"{c['title']}: {plural(c['missing'], 'proof item')} to save",
                        "criterion": c["criterion"], "link": f"#/evidence?proof={c['anchor']}"})  # fmt: skip
    return out[:MAX_TASKS]


def missing(ws: Case) -> list[dict[str, Any]]:
    """For the agent's read tool: each activity's missing items with what would match them."""
    out = []
    for c in checklists(ws):
        gaps = [{"item": i["id"], "label": i["label"], "why": i["why"]} for i in c["items"]
                if i["status"] in ("missing", "self_reported") and not i["optional"]]  # fmt: skip
        if gaps:
            out.append(
                {"anchor": c["anchor"], "title": c["title"], "criterion": c["criterion"], "missing": gaps}
            )
    return out


def proposals(ws: Case) -> list[Candidate]:
    """Rule-based matches (no model) for missing items: case mail whose subject has the item's keywords and shares
    a distinctive word with the activity, and source items (pages) that do the same. Each is an Inbox candidate
    whose proposal names the item; accepting it files the exhibit and links it."""
    from areao1.google import opportunities

    recipes = load_recipes(ws)
    box = ws.mailbox()
    tracked = [(src, it) for src in ws.sources().sources for it in src.items]
    out: list[Candidate] = []
    for c in checklists(ws):
        recipe = recipes[c["criterion"]]
        words = _words(c["title"])
        if not words:
            continue
        for row in c["items"]:
            if row["status"] not in ("missing",):
                continue
            item = next(i for i in recipe.items if i.id == row["id"])
            if not item.match.keywords:
                continue
            for m in box.items:
                if m.outgoing or not _has_keyword(m.subject, item) or not (words & _words(m.subject)):
                    continue
                out.append(Candidate(
                    fingerprint=f"proof:{c['anchor']}:{item.id}:{m.id}", source=f"gmail:{m.thread_id}",
                    evidence_type=(item.match.evidence_types or [_type_of(ws, c)])[0], proposed_criterion=c["criterion"],
                    title=f"{item.label}: {m.subject}"[:200], raw_url=opportunities.gmail_link(m), source_tier="user",
                    summary=f"Email from {m.from_name or m.from_addr}, {clock.local_date(m.at).isoformat()}, may be the "
                            f"“{item.label.lower()}” proof for {c['title']}. Accept to file it and link it.",
                    stage=item.match.stages[0] if item.match.stages else None, confidence=0.6,  # type: ignore[arg-type]
                    proposal={"proof": {"anchor": c["anchor"], "item": item.id}},
                ))  # fmt: skip
            for src, it in tracked:
                text = f"{it.title or ''} {it.url or ''}"
                if not _has_keyword(text, item) or not (words & _words(text)):
                    continue
                out.append(Candidate(
                    fingerprint=f"proof:{c['anchor']}:{item.id}:{it.url}", source=src.id, item_id=it.id,
                    evidence_type=(item.match.evidence_types or [_type_of(ws, c)])[0], proposed_criterion=c["criterion"],
                    title=f"{item.label}: {it.title or it.url}"[:200], raw_url=it.url,
                    summary=f"A page from your sources may be the “{item.label.lower()}” proof for "
                            f"{c['title']}. Accept to file a capture and link it; save a PDF copy too.",
                    confidence=0.5, proposal={"proof": {"anchor": c["anchor"], "item": item.id}},
                ))  # fmt: skip
    return out


def _type_of(ws: Case, checklist: dict[str, Any]) -> str:
    crit = ws.profile().criterion(checklist["criterion"])
    return crit.evidence_types[0] if crit and crit.evidence_types else "document"


def propose(ws: Case, actor: str = "proof-match") -> list[str]:
    """Put new matches in the Inbox (each once: rejected ones stay rejected). Returns the job's summary line."""
    from areao1.core.text import plural
    from areao1.service import Service

    svc = Service(ws, actor=actor)
    added = [c for c in proposals(ws) if svc.propose_candidate(c) is not None]
    return [f"Proof: {plural(len(added), 'possible match', 'possible matches')} in your Inbox" if added
            else "Proof: no new matches"]  # fmt: skip
