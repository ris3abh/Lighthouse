"""Evidence preflight (ADR 0018): a deterministic check of the workspace before anyone else reads it. No model.

Each issue links to the exact claims, exhibits, letters and drafts involved, with values and dates where they
differ. Severity is about how likely a reader is to notice, never about the case's chances (SPEC §2a.1). Preflight
never blocks anything; the review packet carries the open issues (ADR 0020).

Memory keeps one current claim per subject and predicate: a different value from any source supersedes the old
one. So documents that disagree show up as a document still citing a superseded value, as two documents citing
different values of one metric, or as related predicates (``employer``, ``linkedin_employer``) disagreeing."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from areao1.core import clock
from areao1.core.models import utcnow
from areao1.criteria.case import Case

SEVERITIES = ("high", "medium", "low")
CAPTURE_EXTS = {".md", ".html", ".htm", ".txt"}
PRIMARY_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".eml", ".docx"}
# Identity facts that should agree across documents: predicate families, matched on the predicate's last part.
FAMILIES = {
    "name": re.compile(r"(?:^|_)(?:name|full_name|person_name|legal_name)$"),
    "title": re.compile(r"(?:^|_)(?:role|role_title|job_title|title_held|position)$"),
    "employer": re.compile(r"(?:^|_)(?:employer|company|organization|affiliation|works_at)$"),
}
FAMILY_LABEL = {"name": "name", "title": "job title", "employer": "employer"}
ABBREV = {"sr": "senior", "jr": "junior", "eng": "engineer", "engr": "engineer", "mgr": "manager", "dir": "director",
          "vp": "vice president", "swe": "software engineer", "dept": "department", "univ": "university",
          "intl": "international", "&": "and"}  # fmt: skip
SUFFIXES = {
    "inc",
    "llc",
    "ltd",
    "corp",
    "corporation",
    "co",
    "company",
    "gmbh",
    "plc",
    "the",
    "pvt",
    "limited",
}
CLAIM_IN_TEXT = re.compile(r"\bclm_[0-9a-f]{6,}\b")


def normalize(value: Any) -> str:
    words = re.sub(r"[^\w&\s]", " ", str(value).lower()).split()
    out = [ABBREV.get(w, w) for w in words]
    return " ".join(w for w in " ".join(out).split() if w not in SUFFIXES)


def _id(kind: str, *parts: str) -> str:
    return f"pf_{hashlib.sha256('|'.join((kind, *sorted(parts))).encode()).hexdigest()[:12]}"


class _Ctx:
    """Everything the checks read, loaded once."""

    def __init__(self, ws: Case):
        mem = ws.memory
        self.ws = ws
        self.claims = {c.id: c for c in mem.claims()}
        self.status = mem.statuses()
        self.edges = mem.edges()
        self.obs = {o.id: o for o in mem.observations()}
        self.entities = {e.id: e for e in mem.entities()}
        self.exhibits = {e.id: e for e in ws.exhibits().exhibits}
        self.letters = {lt.id: lt for lt in ws.letters().letters}
        self.newer = {e.dst: e.src for e in self.edges if e.type == "SUPERSEDES"}
        # Documents citing claims: exhibits, letters (CITES edges) and drafts (claim ids in the text).
        self.cites: dict[str, set[str]] = {}
        for e in self.edges:
            if e.type == "CITES":
                self.cites.setdefault(
                    e.src if not e.src.startswith("exh_") else f"exhibit:{e.src}", set()
                ).add(e.dst)
        for ex in self.exhibits.values():
            self.cites.setdefault(f"exhibit:{ex.id}", set()).update(ex.claim_ids)
        self.drafts: dict[str, str] = {}
        for path in sorted((ws.root / "drafts").rglob("*.md")) if (ws.root / "drafts").is_dir() else []:
            rel = path.relative_to(ws.root).as_posix()
            self.drafts[rel] = path.read_text(encoding="utf-8", errors="ignore")
            body = self.drafts[rel].split("\n## Sources", 1)[0]
            self.cites.setdefault(f"draft:{rel}", set()).update(CLAIM_IN_TEXT.findall(body))

    def head(self, claim_id: str) -> str:
        seen = {claim_id}
        while claim_id in self.newer and self.newer[claim_id] not in seen:
            claim_id = self.newer[claim_id]
            seen.add(claim_id)
        return claim_id

    def when(self, claim_id: str) -> str:
        c = self.claims[claim_id]
        return (c.event_date or c.valid_from or clock.local_date(c.recorded_at)).isoformat()

    def claim_ref(self, claim_id: str) -> dict[str, Any]:
        c = self.claims.get(claim_id)
        if c is None:
            return {"type": "claim", "id": claim_id, "label": "(no such claim)", "link": None}
        ent = self.entities.get(c.subject)
        obs = self.obs.get(c.observation_id)
        return {"type": "claim", "id": c.id, "label": f"{ent.name if ent else c.subject}: {c.predicate.replace('_', ' ')}",
                "value": c.value, "date": self.when(c.id), "status": self.status.get(c.id, "proposed"),
                "source": (obs.source_url if obs else None), "link": f"#/memory?claim={c.id}"}  # fmt: skip

    def doc_ref(self, doc: str) -> dict[str, Any]:
        kind, _, ident = doc.partition(":")
        if kind == "exhibit":
            ex = self.exhibits.get(ident)
            return {"type": "exhibit", "id": ident, "label": ex.title if ex else ident,
                    "link": f"#/evidence?c={ex.criterion}" if ex else "#/evidence"}  # fmt: skip
        if kind == "letter":
            lt = self.letters.get(ident)
            return {
                "type": "letter",
                "id": ident,
                "label": f"Letter from {lt.name}" if lt else ident,
                "link": "#/letters",
            }
        return {"type": "draft", "id": ident, "label": ident, "link": "#/letters"}

    def documents_citing(self, claim_id: str) -> list[str]:
        return sorted(d for d, ids in self.cites.items() if claim_id in ids)


def _issue(
    kind: str, severity: str, title: str, detail: str, refs: list[dict[str, Any]], *key: str
) -> dict[str, Any]:
    return {
        "id": _id(kind, *key),
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        "refs": refs,
    }


def superseded_cited(x: _Ctx) -> list[dict[str, Any]]:
    """One issue per document that cites values a newer one replaced."""
    out = []
    for doc, ids in sorted(x.cites.items()):
        old = [cid for cid in sorted(ids) if cid in x.claims and cid in x.newer]
        if not old:
            continue
        ref = x.doc_ref(doc)
        pairs = [(cid, x.head(cid)) for cid in old]
        shown = "; ".join(
            f"{x.claims[o].value} ({x.when(o)}) is now {x.claims[n].value} ({x.when(n)})"
            for o, n in pairs[:3]
        )
        more = f"; and {len(pairs) - 3} more" if len(pairs) > 3 else ""
        title = (f"{ref['label']} cites an outdated value" if len(pairs) == 1
                 else f"{ref['label']} cites {len(pairs)} outdated values")  # fmt: skip
        refs = [ref, *(r for o, n in pairs[:5] for r in (x.claim_ref(o), x.claim_ref(n)))]
        out.append(_issue("superseded_cited", "high", title, f"{shown}{more}.", refs, doc))
    return out


def unsupported_cited(x: _Ctx) -> list[dict[str, Any]]:
    """One issue per letter or draft citing claims that aren't approved or don't exist."""
    out = []
    for doc, ids in sorted(x.cites.items()):
        if doc.startswith("exhibit:"):
            continue  # exhibits cite the claims you accepted with them
        missing = [cid for cid in sorted(ids) if cid not in x.claims]
        unapproved = [cid for cid in sorted(ids) if cid in x.claims and x.status.get(cid) != "approved"]
        if not missing and not unapproved:
            continue
        ref = x.doc_ref(doc)
        parts = []
        if missing:
            parts.append(
                f"{len(missing)} that doesn't exist in memory"
                if len(missing) == 1
                else f"{len(missing)} that don't exist in memory"
            )
        if unapproved:
            states = sorted({x.status.get(c) or "not reviewed" for c in unapproved})
            parts.append(f"{len(unapproved)} not approved ({', '.join(states)})")
        out.append(_issue("unsupported_cited", "high", f"{ref['label']} cites claims it can't rest on",
                          f"It cites {' and '.join(parts)}. Approve them in the Inbox or Memory, or redraft without them.",
                          [ref, *(x.claim_ref(c) for c in (missing + unapproved)[:10])], doc))  # fmt: skip
    return out


def _current_approved(x: _Ctx) -> list[str]:
    return [cid for cid in x.claims if cid not in x.newer and x.status.get(cid) == "approved"]


def conflicting_facts(x: _Ctx) -> list[dict[str, Any]]:
    """Identity facts: current approved claims of one family (name, title, employer) about one subject that
    disagree, and approved documents whose identity value was superseded by a different one. Event dates: the same
    event value recorded with different dates."""
    out = []
    groups: dict[tuple[str, str], list[str]] = {}
    for cid in _current_approved(x):
        claim = x.claims[cid]
        for fam, rx in FAMILIES.items():
            if rx.search(claim.predicate) and isinstance(claim.value, str):
                groups.setdefault((claim.subject, fam), []).append(cid)
    for cid, newer in x.newer.items():  # a document's identity value replaced by another document's
        c, n = x.claims.get(cid), x.claims.get(newer)
        if c and n and x.status.get(cid) == "approved" and c.observation_id != n.observation_id:
            for fam, rx in FAMILIES.items():
                if (
                    rx.search(c.predicate)
                    and isinstance(c.value, str)
                    and normalize(c.value) != normalize(n.value)
                ):
                    groups.setdefault((c.subject, fam), []).extend([cid, newer])
    for (subject, fam), ids in sorted(groups.items()):
        ids = sorted(set(ids))
        values = {normalize(x.claims[i].value) for i in ids}
        if len(values) < 2:
            continue
        ent = x.entities.get(subject)
        shown = "; ".join(f"“{x.claims[i].value}” ({x.when(i)})" for i in ids)
        severity = "high" if fam == "name" else "medium"
        note = (
            ""
            if fam == "name"
            else " If it changed over time, that's fine: make sure each document is dated."
        )
        out.append(_issue("conflicting_facts", severity,
                          f"Different {FAMILY_LABEL[fam]}s for {ent.name if ent else subject}",
                          f"Documents say {shown}.{note}", [x.claim_ref(i) for i in ids], subject, fam))  # fmt: skip
    # The same event recorded with different dates (value unchanged).
    for cid, newer in x.newer.items():
        c, n = x.claims.get(cid), x.claims.get(newer)
        if (c and n and c.event_date and n.event_date and c.event_date != n.event_date
                and normalize(c.value) == normalize(n.value)):  # fmt: skip
            ent = x.entities.get(c.subject)
            out.append(_issue("conflicting_facts", "medium", f"Two dates for {ent.name if ent else c.subject}",
                              f"One source says {c.event_date.isoformat()}, another {n.event_date.isoformat()}.",
                              [x.claim_ref(cid), x.claim_ref(newer)], cid, newer))  # fmt: skip
    # An exhibit dated differently from the event its own source describes.
    for ex in sorted(x.exhibits.values(), key=lambda e: (e.date, e.id)):
        for cid in sorted(x.cites.get(f"exhibit:{ex.id}", set())):
            c = x.claims.get(cid)
            if (
                c
                and c.event_date
                and not isinstance(c.value, (int, float))
                and abs((ex.date - c.event_date).days) > 3
            ):
                out.append(_issue("conflicting_facts", "medium", f"Two dates for {ex.title}",
                                  f"The exhibit is dated {ex.date.isoformat()}; its source says {c.event_date.isoformat()}.",
                                  [x.doc_ref(f"exhibit:{ex.id}"), x.claim_ref(cid)], ex.id, cid))  # fmt: skip
    return out


def metric_mismatch(x: _Ctx) -> list[dict[str, Any]]:
    """Two documents citing different values of the same metric (both shown, with dates)."""
    out = []
    chains: dict[tuple[str, str], set[str]] = {}
    for ids in x.cites.values():
        for cid in ids:
            c = x.claims.get(cid)
            if c and isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
                chains.setdefault((c.subject, c.predicate), set()).add(cid)
    for (subject, predicate), ids in sorted(chains.items()):
        by_value: dict[Any, list[str]] = {}
        for cid in sorted(ids):
            by_value.setdefault(x.claims[cid].value, []).append(cid)
        if len(by_value) < 2:
            continue
        ent = x.entities.get(subject)
        docs = sorted({d for cid in ids for d in x.documents_citing(cid)})
        shown = "; ".join(
            f"{v} ({', '.join(x.when(c) for c in cs)})"
            for v, cs in sorted(by_value.items(), key=lambda kv: str(kv[0]))
        )
        out.append(_issue("metric_mismatch", "medium",
                          f"{predicate.replace('_', ' ').capitalize()} differs between documents for {ent.name if ent else subject}",
                          f"Values: {shown}. Use one dated value, or say each document's date.",
                          [*(x.doc_ref(d) for d in docs), *(x.claim_ref(c) for c in sorted(ids))], subject, predicate))  # fmt: skip
    return out


def invited_not_completed(x: _Ctx) -> list[dict[str, Any]]:
    from areao1.criteria import proof

    out = []
    completed = [e for e in x.exhibits.values() if e.stage in proof.COMPLETION_STAGES]
    for ex in sorted(x.exhibits.values(), key=lambda e: (e.date, e.id)):
        if ex.stage != "invited":
            continue
        words = proof._words(ex.title)
        need = min(
            2, len(words)
        )  # "Judged Riverside Jam 2026" completes "Invitation to judge Riverside Jam 2026"
        if any(e.criterion == ex.criterion and len(words & proof._words(e.title)) >= need for e in completed):
            continue
        out.append(_issue("invited_not_completed", "medium", f"{ex.title}: invited, no proof it happened",
                          "An invitation doesn't count. Save the thank-you, certificate or program once it's done.",
                          [x.doc_ref(f"exhibit:{ex.id}")], ex.id))  # fmt: skip
    for c in proof.checklists(x.ws):
        if proof.completion_missing(c):
            out.append(_issue("invited_not_completed", "medium", f"{c['title']}: accepted, no completion proof yet",
                              "Save the thank-you or certificate after the event (proof checklist on Evidence).",
                              [{"type": "proof", "id": c["anchor"], "label": c["title"],
                                "link": f"#/evidence?proof={c['anchor']}"}], c["anchor"]))  # fmt: skip
    return out


def capture_without_primary(x: _Ctx) -> list[dict[str, Any]]:
    out = []
    primaries = [e for e in x.exhibits.values() if Path(e.file).suffix.lower() in PRIMARY_EXTS]
    linked = {(link.anchor, link.exhibit_id) for link in x.ws.proofs().links}
    for ex in sorted(x.exhibits.values(), key=lambda e: (e.date, e.id)):
        if Path(ex.file).suffix.lower() not in CAPTURE_EXTS:
            continue
        has_copy = any((p.source_url and p.source_url == ex.source_url) or (f"exhibit:{ex.id}", p.id) in linked
                       for p in primaries)  # fmt: skip
        if not has_copy:
            where = "the email" if ex.source_url and "mail.google.com" in ex.source_url else "the page"
            out.append(_issue("capture_without_primary", "medium", f"{ex.title}: a capture only",
                              f"Area O1 saved its text. Save {where} as a PDF (or the original .eml) and upload it, so "
                              "the exhibit doesn't depend on a page that can change.", [x.doc_ref(f"exhibit:{ex.id}")],
                              ex.id))  # fmt: skip
    return out


def claim_without_exhibit(x: _Ctx) -> list[dict[str, Any]]:
    """Approved current claims no exhibit cites, one issue per entity (they can be many)."""
    cited = {cid for d, ids in x.cites.items() if d.startswith("exhibit:") for cid in ids}
    by_subject: dict[str, list[str]] = {}
    for cid in _current_approved(x):
        if cid not in cited:
            by_subject.setdefault(x.claims[cid].subject, []).append(cid)
    out = []
    for subject, ids in sorted(by_subject.items()):
        ent = x.entities.get(subject)
        out.append(_issue("claim_without_exhibit", "low",
                          f"{ent.name if ent else subject}: {len(ids)} approved fact{'s' if len(ids) != 1 else ''} with no exhibit",
                          "Approved facts are only as strong as the document behind them; file the primary document.",
                          [x.claim_ref(c) for c in ids[:10]], subject))  # fmt: skip
    return out


def undated_exhibit(x: _Ctx) -> list[dict[str, Any]]:
    out = []
    for ex in sorted(x.exhibits.values(), key=lambda e: (e.date, e.id)):
        if ex.date_source == "unconfirmed":
            out.append(_issue("undated_exhibit", "low", f"{ex.title}: date unconfirmed",
                              "No date was known when it was filed. Set the date the document shows (Evidence > Set date).",
                              [x.doc_ref(f"exhibit:{ex.id}")], ex.id))  # fmt: skip
            continue
        if ex.date_source is not None or ex.date != clock.local_date(ex.accepted_at):
            continue
        dated = any(x.claims[c].event_date or x.claims[c].valid_from not in (None, ex.date)
                    for c in ex.claim_ids if c in x.claims)  # fmt: skip
        if not dated:
            out.append(_issue("undated_exhibit", "low", f"{ex.title}: no document date",
                              "Its date is the day it was filed. Set the date the document shows, or run "
                              "`areao1 repair-dates`.", [x.doc_ref(f"exhibit:{ex.id}")], ex.id))  # fmt: skip
    return out


CHECKS = (superseded_cited, unsupported_cited, conflicting_facts, metric_mismatch, invited_not_completed,
          capture_without_primary, claim_without_exhibit, undated_exhibit)  # fmt: skip


def report_path(ws: Case) -> Path:
    return ws.data_dir / "preflight.json"


def latest(ws: Case) -> dict[str, Any] | None:
    path = report_path(ws)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def run(ws: Case, *, save: bool = True, today: date | None = None) -> dict[str, Any]:
    """Run every check. ``save`` writes data/preflight.json (keeping dismissals); without it nothing is written."""
    x = _Ctx(ws)
    issues = [i for check in CHECKS for i in check(x)]
    issues.sort(key=lambda i: (SEVERITIES.index(i["severity"]), i["kind"], i["title"]))
    prev = latest(ws) or {}
    dismissed = {k: v for k, v in (prev.get("dismissed") or {}).items()}
    for i in issues:
        i["dismissed"] = i["id"] in dismissed
        if i["dismissed"]:
            i["dismissed_note"] = dismissed[i["id"]].get("note", "")
    open_ = [i for i in issues if not i["dismissed"]]
    report = {"run_at": utcnow().isoformat(), "issues": issues, "dismissed": dismissed,
              "counts": {s: sum(1 for i in open_ if i["severity"] == s) for s in SEVERITIES},
              "by_kind": {k: sum(1 for i in open_ if i["kind"] == k) for k in sorted({i["kind"] for i in issues})},
              "exhibits": len(x.exhibits), "claims": len(x.claims)}  # fmt: skip
    if save:
        ws.save_preflight(report)
    return report


def summary(report: dict[str, Any]) -> str:
    c = report["counts"]
    total = sum(c.values())
    return (f"Preflight: {total} open issue{'s' if total != 1 else ''} ({c['high']} high, {c['medium']} medium, "
            f"{c['low']} low) across {report['exhibits']} exhibits and {report['claims']} claims")  # fmt: skip
