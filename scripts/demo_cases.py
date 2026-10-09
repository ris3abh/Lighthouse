"""Fictional cases with real exhibits, for the demo and for checking the review packet (ADR 0020). Dev-only: never
shipped, no real data, no network. Every person, organization, award and paper here is invented.

Each exhibit is a two-page PDF whose second page quotes exactly what the exhibit is cited for, so the packet's
matrix finds the page; its claims are recorded from that text, approved and cited.

    python scripts/demo_cases.py            # Maya's and Ravi's packets into out/packets/ (gitignored)

The workspaces themselves are built in the system temp folder: a case workspace never sits inside the repo
(scripts/check_repo.py refuses one).
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"


@dataclass
class C:
    """A claim the exhibit documents: its predicate, value and the exact sentence on the exhibit's second page."""

    predicate: str
    value: Any
    text: str
    on: date | None = None
    subject: str = ""  # the work or event it's about ("FastQueue"); defaults to the exhibit's organization


@dataclass
class X:
    criterion: str
    kind: str
    title: str
    on: date
    org: str
    claims: list[C]
    signals: list[str] = field(default_factory=list)
    stale: C | None = None  # an older value of one of the claims, still cited (preflight flags it)


CASES: dict[str, list[X]] = {
    "maya": [
        X(
            "judging",
            "panel_letter",
            "Judging at Example Hackathon Series",
            date(2024, 11, 9),
            "Example Hackathon Series",
            [
                C(
                    "judged_event",
                    "Example Hackathon Series 2024 finals",
                    "Maya Chen served as a judge for the Example Hackathon Series 2024 finals on November 9, 2024.",
                ),
                C("teams_judged", "38 teams", "The judging panel scored 38 finalist teams."),
            ],
            ["selective_event", "multiple_instances"],
        ),
        X(
            "judging",
            "program_committee",
            "Program committee, Example Systems Conf",
            date(2025, 6, 2),
            "Example Systems Conf",
            [
                C(
                    "program_committee",
                    "Example Systems Conf 2025",
                    "Maya Chen served on the program committee of Example Systems Conf 2025.",
                ),
                C("papers_reviewed", "14 papers", "She reviewed 14 submitted papers for the systems track."),
            ],
            ["selective_event"],
        ),
        X(
            "original_contributions",
            "open_source_project",
            "FastQueue open-source adoption",
            date(2025, 9, 15),
            "Acme Robotics",
            [
                C(
                    "repo_stars",
                    4800,
                    "The FastQueue repository had 4,800 GitHub stars in September 2025.",
                    subject="FastQueue",
                ),
                C(
                    "adopted_by",
                    "Acme Robotics",
                    "Acme Robotics runs FastQueue in production across its warehouse fleet.",
                    subject="FastQueue",
                ),
            ],
            ["widely_adopted", "used_by_others"],
        ),
        X(
            "original_contributions",
            "adoption_evidence",
            "FastQueue used across Example Corp",
            date(2026, 3, 3),
            "Example Corp",
            [
                C(
                    "monthly_downloads",
                    120000,
                    "The FastQueue package was downloaded 120,000 times in February 2026.",
                    on=date(2026, 2, 28),
                    subject="FastQueue",
                )
            ],
            ["sustained_activity"],
        ),
        X(
            "awards",
            "award_certificate",
            "Northwind Engineering Excellence Award",
            date(2024, 5, 20),
            "Northwind Engineering Foundation",
            [
                C(
                    "award_received",
                    "Northwind Engineering Excellence Award",
                    "Maya Chen received the Northwind Engineering Excellence Award on May 20, 2024.",
                ),
                C(
                    "award_selectivity",
                    "3 of 412 nominees",
                    "The jury selected 3 recipients from 412 nominees.",
                ),
            ],
        ),
        X(
            "press",
            "press_article",
            "Example Tech Weekly profile",
            date(2025, 2, 11),
            "Example Tech Weekly",
            [
                C(
                    "press_feature",
                    "The engineer making queues boring again",
                    "Example Tech Weekly profiled Maya Chen in “The engineer making queues boring again” on February 11, 2025.",
                ),
                C(
                    "monthly_readers",
                    52000,
                    "Example Tech Weekly reaches 52,000 readers a month.",
                    on=date(2025, 2, 11),
                    subject="Example Tech Weekly",
                ),
            ],
            stale=C(
                "monthly_readers",
                40000,
                "Example Tech Weekly reached 40,000 readers a month in 2024.",
                on=date(2024, 6, 1),
                subject="Example Tech Weekly",
            ),
        ),
    ],
    "ravi": [
        X(
            "awards",
            "award_certificate",
            "Best Paper Award, Workshop on Efficient Machine Learning",
            date(2025, 12, 13),
            "Workshop on Efficient Machine Learning",
            [
                C(
                    "award_received",
                    "Best Paper Award at the Workshop on Efficient Machine Learning 2025",
                    "Ravi Iyer received the Best Paper Award at the Workshop on Efficient Machine Learning 2025.",
                ),
                C(
                    "award_selectivity",
                    "1 of 214 accepted papers",
                    "One paper was chosen from 214 accepted papers.",
                ),
            ],
        ),
        X(
            "membership",
            "membership_certificate",
            "Senior Member, Example Society for Machine Intelligence",
            date(2026, 1, 10),
            "Example Society for Machine Intelligence",
            [
                C(
                    "membership",
                    "Example Society for Machine Intelligence as a Senior Member",
                    "Ravi Iyer was elected to the Example Society for Machine Intelligence as a Senior Member in January 2026.",
                ),
                C(
                    "membership_requirement",
                    "nomination by two Fellows",
                    "Senior Membership requires nomination by two Fellows and ten years of recognized contributions.",
                ),
            ],
        ),
        X(
            "judging",
            "program_committee",
            "Program committee, Conference on Example Neural Systems",
            date(2025, 7, 1),
            "Conference on Example Neural Systems",
            [
                C(
                    "program_committee",
                    "the Conference on Example Neural Systems 2025",
                    "Ravi Iyer served on the program committee of the Conference on Example Neural Systems 2025.",
                ),
                C("papers_reviewed", "6 papers", "He reviewed 6 submitted papers."),
            ],
            ["selective_event"],
        ),
        X(
            "judging",
            "reviewer_record",
            "Reviewer, Example Learning Symposium",
            date(2024, 8, 30),
            "Example Learning Symposium",
            [
                C(
                    "reviewer_for",
                    "the Example Learning Symposium 2024",
                    "Ravi Iyer reviewed for the Example Learning Symposium 2024.",
                )
            ],
        ),
        X(
            "scholarly_articles",
            "conference_paper",
            "Sparse Mixture Routing for Efficient Transformers",
            date(2025, 5, 1),
            "Example Learning Symposium",
            [
                C(
                    "paper_published",
                    "Sparse Mixture Routing for Efficient Transformers",
                    "Sparse Mixture Routing for Efficient Transformers, by Ravi Iyer, appeared in the proceedings in May 2025.",
                ),
                C(
                    "citation_count",
                    212,
                    "Sparse Mixture Routing for Efficient Transformers has been cited 212 times.",
                    on=date(2026, 9, 1),
                    subject="Sparse Mixture Routing for Efficient Transformers",
                ),
            ],
        ),
        X(
            "scholarly_articles",
            "journal_article",
            "Calibrated Uncertainty in Vision-Language Models",
            date(2024, 3, 15),
            "Journal of Example Machine Learning Research",
            [
                C(
                    "paper_published",
                    "Calibrated Uncertainty in Vision-Language Models",
                    "Calibrated Uncertainty in Vision-Language Models, by Ravi Iyer, was published in March 2024.",
                )
            ],
        ),
        X(
            "original_contributions",
            "open_source_project",
            "sparse-router library",
            date(2026, 2, 1),
            "Harborview Robotics",
            [
                C(
                    "repo_stars",
                    3100,
                    "The sparse-router repository had 3,100 GitHub stars in February 2026.",
                    subject="sparse-router",
                ),
                C(
                    "adopted_by",
                    "Harborview Robotics",
                    "Harborview Robotics adopted sparse-router for on-device inference.",
                    subject="sparse-router",
                ),
            ],
            ["used_by_others"],
        ),
    ],
}

LETTERS = {
    "maya": [("Dr. Priya Natarajan", "independent", "Professor of Computer Science", ["judging"]),
             ("Dr. Lena Ortiz", "independent", "Principal engineer, Acme Robotics", ["original_contributions"]),
             ("Sam Rivera", "employer", "Director of engineering, Example Corp", ["original_contributions"])],
    "ravi": [("Dr. Amara Okafor", "independent", "Professor of Computer Science, Example Polytechnic", ["scholarly_articles"]),
             ("Dr. Tomas Lindqvist", "independent", "Research director, Harborview Robotics", ["original_contributions"]),
             ("Dr. Mei Tanaka", "employer", "Head of research, Lakeshore AI Lab", ["judging"])],
}  # fmt: skip


def exhibit_pdf(title: str, org: str, lines: list[str]) -> bytes:
    """A two-page fictional exhibit: a letterhead page, then the facts it documents."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, invariant=1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 720, org)
    c.setFont("Helvetica", 12)
    c.drawString(72, 690, title)
    c.drawString(72, 660, "Fictional exhibit for the Area O1 demo. Every name here is invented.")
    c.showPage()
    c.setFont("Helvetica", 11)
    y = 720
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue()


def add_case(ws: Any, pid: str) -> list[str]:
    """Add the case's exhibits, with their claims recorded from the exhibit text, approved and cited. Returns the
    exhibit ids."""
    from areao1.core.models import ClaimDraft, Evidence

    ids = []
    for x in CASES[pid]:
        lines = [c.text for c in ([x.stale] if x.stale else []) + x.claims]
        pdf = exhibit_pdf(x.title, x.org, lines)
        e = ws.add_exhibit_file(content=pdf, filename=f"{x.title.lower().replace(' ', '-').replace(',', '')[:40]}.pdf",
                                criterion=x.criterion, evidence_type=x.kind, title=x.title, on=x.on,
                                signals=x.signals, stage="completed")  # fmt: skip
        exhibits = ws.exhibits()
        next(ex for ex in exhibits.exhibits if ex.id == e.id).organization = x.org
        ws.save_exhibits(exhibits)
        payload = "\n".join(lines)
        cited = []
        for c in (
            [x.stale] if x.stale else []
        ) + x.claims:  # the stale value first, so the newer one is current
            subject = c.subject or x.org
            [claim] = ws.memory.record(Evidence(connector="upload", source_url=f"file:{e.file}", payload=payload,
                                                media_type="text/plain",
                                                claims=[ClaimDraft(subject=f"artifact:{subject.lower().replace(' ', '-')}",
                                                                   subject_kind="artifact", subject_name=subject,
                                                                   predicate=c.predicate, value=c.value, excerpt=c.text,
                                                                   event_date=c.on or x.on, confidence="high")]))  # fmt: skip
            cited.append(claim.id)
        ws.memory.decide(cited, "approved", rationale="read on the exhibit")
        ws.memory.cite(e.id, cited)
        ids.append(e.id)
    ws.after_change()
    return ids


def add_letters(ws: Any, pid: str) -> None:
    for name, rel, cred, crits in LETTERS[pid]:
        ws.add_letter(name=name, relationship=rel, credentials=cred, criteria=crits)


def build_persona(pid: str, root: Path) -> Any:
    """A persona after onboarding from their LinkedIn PDF (tests/fixtures/personas), with the case added."""
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "scripts"))
    import film_demo
    from fastapi.testclient import TestClient
    from test_onboarding import answer_all, upload

    from areao1.criteria.case import Case
    from areao1.scaffold import create_workspace
    from areao1.server.app import create_app

    film_demo.no_network()
    film_demo.fake_keychain()
    if root.exists():
        shutil.rmtree(root)
    ws = Case(create_workspace(root, name="", git=False).root)
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    answer_all(c, upload(c, pid))
    for step in ("lookups_done", "chats_skip", "mail_skip", "tour_done"):
        c.post("/api/onboarding/step", headers={"X-AreaO1": "1"}, json={"step": step})
    add_case(ws, pid)
    add_letters(ws, pid)
    o1 = next((ROOT / "community-vault" / "snapshots").glob("9c0e2d65*.html")).read_bytes()
    from areao1.vault.store import Vault

    Vault(ws).import_file("uscis-pm-2-m-4", o1, "Policy Manual O-1.html")
    return ws


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("people", nargs="*", default=["maya", "ravi"])
    ap.add_argument("--out", default=str(OUT / "packets"))
    ap.add_argument("--workspaces", default=str(Path(tempfile.gettempdir()) / "areao1-demo-cases"))
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "scripts"))
    import film_demo

    from areao1.criteria import packet
    from areao1.criteria.case import Case
    from areao1.vault.store import Vault

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for pid in args.people:
        root = Path(args.workspaces) / pid
        if pid == "maya":
            film_demo.build(root)
            ws = Case(root)
        else:
            ws = build_persona(pid, root)
        m = packet.build(ws, Vault(ws))
        src = ws.root / "exports" / m["name"]
        for f in ("packet.pdf", "packet.docx", "matrix.csv"):
            shutil.copyfile(src / f, out / f"{pid}-{f}")
        print(f"{pid}: {m['name']} · {m['pages']} pages · {len(m['exhibits'])} exhibits · {m['claims']} claims · "
              f"{m['open_issues']} open issues · {m['dropped_sentences']} dropped → {out}/{pid}-packet.pdf")  # fmt: skip


if __name__ == "__main__":
    main()
