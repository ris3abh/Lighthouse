"""The contacts view (ADR 0014 §4): stored contacts, plus every letter writer not yet linked to one, each with
what it's linked to and its Gmail threads. Editing a letter writer's entry makes it a stored contact."""

from __future__ import annotations

from typing import Any

from areao1.criteria.case import Case

LETTER_PREFIX = "letter:"


def threads_by_contact(ws: Case) -> dict[str, list[dict[str, Any]]]:
    """Gmail threads (E2) grouped by contact id; empty until Gmail is connected."""
    from areao1.google.gmail import load_threads

    out: dict[str, list[dict[str, Any]]] = {}
    for t in load_threads(ws).threads:
        for cid in t.contact_ids:
            out.setdefault(cid, []).append(t.model_dump(mode="json"))
    return out


def views(ws: Case) -> list[dict[str, Any]]:
    letters = {lt.id: lt for lt in ws.letters().letters}
    pipeline = {p.id: p for p in ws.pipeline().items}
    threads = threads_by_contact(ws)
    stored = ws.contacts().contacts
    linked = {lid for c in stored for lid in c.letter_ids}
    out = []
    for c in stored:
        out.append({**c.model_dump(mode="json"), "virtual": False,
                    "letters": [{"id": lid, "name": letters[lid].name, "status": letters[lid].status}
                                for lid in c.letter_ids if lid in letters],
                    "pipeline": [{"id": pid, "title": pipeline[pid].title, "stage": pipeline[pid].stage}
                                 for pid in c.pipeline_ids if pid in pipeline],
                    "threads": sorted(threads.get(c.id, []), key=lambda t: t["last_at"], reverse=True)})  # fmt: skip
    for lt in letters.values():
        if lt.id in linked:
            continue
        out.append({"id": f"{LETTER_PREFIX}{lt.id}", "name": lt.name, "emails": [], "org": "", "notes": "",
                    "relationship": "recommender", "asks": [a.replace("_", " ") for a in lt.asks],
                    "next_follow_up": None, "last_touch": lt.last_contact.isoformat() if lt.last_contact else None,
                    "letter_ids": [lt.id], "pipeline_ids": [], "tier": "self_reported", "virtual": True,
                    "letters": [{"id": lt.id, "name": lt.name, "status": lt.status}], "pipeline": [],
                    "threads": []})  # fmt: skip
    return sorted(out, key=lambda c: (c["next_follow_up"] or "9999", c["name"].lower()))


def from_letter(ws: Case, contact_id: str) -> dict[str, Any] | None:
    """The fields a letter writer's entry starts from when it becomes a stored contact."""
    if not contact_id.startswith(LETTER_PREFIX):
        return None
    lid = contact_id.removeprefix(LETTER_PREFIX)
    lt = next((x for x in ws.letters().letters if x.id == lid), None)
    if lt is None:
        return None
    return {"name": lt.name, "relationship": "recommender", "letter_ids": [lt.id],
            "asks": [a.replace("_", " ") for a in lt.asks], "last_touch": lt.last_contact}  # fmt: skip
