"""A fictional filming workspace for the demo video (J1). Dev-only: never shipped (scripts/ isn't in the wheel or
the sdist), no real data, no network.

    python scripts/film_demo.py                 # builds ./film-maya and serves it at http://127.0.0.1:7920
    python scripts/film_demo.py --dir /tmp/maya --port 7921 --rebuild

"Maya Chen", a software engineer, with:
  - a seeded constellation: about 400 claims from 2024 to today (approved, pending, a superseded chain of citation
    counts, a few conflicts), with exhibits, so the Memory page's time slider replays real-looking history;
  - fake Gmail (the in-memory IMAP / SMTP of the test suite) and an in-memory keychain;
  - the scripted engine of the test suite: any chat question gets the same grounded answer, and its rule sentence
    comes back "verified" against a Tier 1 page in the vault (imported offline from the test fixtures);
  - one follow-up draft waiting for approval on Contacts.

Keys (type one and press Enter in this terminal):
  j   a verified judging invitation arrives in Gmail and the daily opportunity check runs (Inbox + notification)
  u   an unverified one arrives (a look-alike sender): it comes out suspicious
  r   rebuild the workspace from scratch
  q   quit
"""

from __future__ import annotations

import argparse
import gzip
import random
import shutil
import socket
import sys
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))  # the suite's fakes: FakeGmail, FakeEngine, FakeJudge
sys.path.insert(0, str(ROOT / "scripts"))

ANSWER = ("Here's where you stand. Judging and original contributions look strong, and press is building. EB-1A "
          "requires evidence of at least three of the ten criteria. Your next useful step is the "
          "Lakeside Hacks judging invitation in your Inbox: once you've judged, upload the thank-you note.")  # fmt: skip
RULE = "EB-1A requires evidence of at least three of the ten criteria."
QUOTE = "at least three of the ten regulatory criteria"
D = "%d-%b-%Y %H:%M:%S +0000"


def no_network() -> None:
    """Only this machine: the filming workspace never reaches the internet."""
    real = socket.getaddrinfo

    def local_only(host, *a, **k):  # type: ignore[no-untyped-def]
        if host in (None, "localhost", "127.0.0.1", "::1"):
            return real(host, *a, **k)
        # The same error a real outage gives (DNS can't resolve), so the app shows what it would offline.
        raise socket.gaierror(socket.EAI_NONAME, f"film_demo is offline (tried {host!r})")

    socket.getaddrinfo = local_only  # type: ignore[assignment]


class _MP:
    def setattr(self, obj, name, value):  # type: ignore[no-untyped-def]
        setattr(obj, name, value)


def fake_keychain() -> None:
    import keyring

    store: dict = {}
    keyring.get_password = lambda s, k: store.get((s, k))
    keyring.set_password = lambda s, k, v: store.__setitem__((s, k), v)
    keyring.delete_password = lambda s, k: store.pop((s, k), None)


def film_engine(steps: list | None = None):  # type: ignore[no-untyped-def]
    """The scripted engine: the same grounded chat answer to every question (not only the first), and a judge that
    verifies its rule sentence. ``steps`` replaces the script (the QA suite adds an undoable chat action)."""
    from agent_fakes import FakeEngine
    from test_rulecheck import FakeJudge

    from areao1.engine.base import AgentEvent, EngineResult
    from areao1.vault.rulecheck import JUDGE_SYSTEM

    judge = FakeJudge(rules=[(RULE[:40], QUOTE, "entails", None)], not_rules=["You have two banked"])

    script = steps or [("tool", "get_scoreboard", {}), ("tool", "list_gaps", {}), ("text", ANSWER)]

    class FilmEngine(FakeEngine):
        async def run(self, request, tools, emit):  # type: ignore[no-untyped-def]
            if request.system_prompt.startswith(JUDGE_SYSTEM[:60]):
                reply = await judge(request.system_prompt, request.prompt, request.model)
                await emit(AgentEvent("usage", reply.usage))
                return EngineResult(text=reply.text, cost_usd=0.0, stop_reason="end_turn")
            self.script = list(script)  # every question gets the answer, not only the first (B19)
            return await super().run(request, tools, emit)

    return FilmEngine(list(script), cost=0.0)


def build(root: Path) -> None:
    from mail_fakes import FakeGmail

    from areao1.core.models import ClaimDraft, Edge, Evidence
    from areao1.criteria.models import GmailThread, GmailThreads
    from areao1.google import mail, outreach
    from areao1.onboarding.models import OnboardingState
    from areao1.scaffold import create_workspace
    from areao1.service import Service
    from areao1.vault.store import Vault

    if root.exists():
        shutil.rmtree(root)
    ws = create_workspace(root, name="Maya Chen", git=False)
    person = ws.person()
    person.name = "Maya Chen"
    person.field = "Software engineer, distributed systems and developer tools"
    person.location = "Seattle, WA"
    person.petitioner.name, person.petitioner.kind = "Example Corp", "employer"
    ws.save_person(person)
    ws.save_onboarding(OnboardingState(status="done", step="done"))

    rng = random.Random(2026)
    # Every value reads as what it is (an event, a title, a count), never a bare index: the packet and Memory
    # show them to people.
    cities = [
        "Seattle",
        "Portland",
        "Austin",
        "Denver",
        "Boston",
        "Chicago",
        "Toronto",
        "Atlanta",
        "Phoenix",
        "Miami",
        "Raleigh",
        "Madison",
    ]
    projects = [
        "FastQueue",
        "trace-small",
        "queue-bench",
        "fq-operator",
        "spool",
        "tidepool",
        "ledgerline",
        "hopper",
        "batchwise",
        "relaykit",
        "drift-check",
        "keel",
    ]
    papers = [
        "Queues at scale",
        "Backpressure without tears",
        "Exactly-once, mostly",
        "Tracing small models",
        "Spooling for the edge",
        "Fair scheduling in practice",
        "Ledger replication",
        "Hop-by-hop retries",
        "Batching under load",
        "Relays and fan-out",
        "Detecting drift",
        "Keeping clusters level",
    ]

    def topic(pred: str, k: int, i: int, d: date) -> tuple[str, object, str]:
        """(subject name, value, the sentence it was read from)."""
        c, proj, paper = cities[k], projects[k], papers[k]
        return {
            "judged_event": (f"Example Hackathon Series {c}", f"Example Hackathon Series {c} {d.year}",
                             f"Judged the Example Hackathon Series {c} {d.year} finals."),
            "award_received": (f"Example Hackathon Series {c}", f"{c} mentor award {d.year}",
                               f"Won the Example Hackathon Series {c} mentor award {d.year}."),
            "press_mention": (f"Example Tech Weekly, {c} edition", f"Example Tech Weekly, {c} edition, {d:%B %Y}",
                              f"Featured in Example Tech Weekly, {c} edition, {d:%B %Y}."),
            "paper_published": (paper, paper, f"Published “{paper}” at Example Systems Conf {d.year}."),
            "citation_count": (paper, 3 * (i + 1), f"“{paper}” has {3 * (i + 1)} citations."),
            "repo_stars": (proj, 100 * (i + 1), f"{proj} has {100 * (i + 1):,} stars on GitHub."),
            "role_title": (proj, f"Tech lead, {proj}", f"Led the {proj} team as tech lead."),
            "membership_granted": (f"Example Engineering Society, {c} chapter", f"Example Engineering Society, {c} chapter",
                                   f"Admitted to the Example Engineering Society, {c} chapter."),
            "model_downloads": (proj, 1000 * (i + 1), f"{proj} was downloaded {1000 * (i + 1):,} times a month."),
        }[pred]  # fmt: skip

    topics = [("judged_event", 70), ("award_received", 25), ("press_mention", 35), ("paper_published", 30),
              ("citation_count", 40), ("repo_stars", 90), ("role_title", 25), ("membership_granted", 15),
              ("model_downloads", 70)]  # fmt: skip
    start, days = date(2024, 1, 15), (date.today() - date(2024, 1, 15)).days
    claims = []
    for t, (pred, count) in enumerate(topics):
        lines, drafts = [], []
        for i in range(count):
            when = start + timedelta(days=int(days * (i + rng.random()) / count))
            name, value, text = topic(pred, i % 12, i, when)
            lines.append(text)
            drafts.append(ClaimDraft(subject=f"artifact:{pred}-{i % 12}", subject_kind="artifact", subject_name=name,
                                     predicate=pred, value=value, excerpt=text, event_date=when,
                                     confidence=rng.choice(["high", "high", "medium", "low"])))  # fmt: skip
        claims += ws.memory.record(Evidence(connector=["github", "openalex", "upload", "website"][t % 4],
                                            source_url=f"https://maya-chen.example/source/{pred}",
                                            payload="\n".join(lines), media_type="text/plain", claims=drafts))  # fmt: skip
    old = [c for c in claims if c.event_date and c.event_date < date.today() - timedelta(days=60)]
    ws.memory.decide([c.id for c in old if rng.random() < 0.8], "approved", rationale="reviewed")
    cites = [c for c in claims if c.predicate == "citation_count"]
    edges = [Edge(type="SUPERSEDES", src=b.id, dst=a.id) for a, b in zip(cites, cites[1:], strict=False)]
    edges += [Edge(type="CONTRADICTS", src=claims[i].id, dst=claims[i + 1].id) for i in (12, 140, 260)]
    ws.memory._append("edges", edges)
    # Two criteria banked (judging, contributions), two building (awards, press): a case partway there. Each
    # exhibit is a real (fictional) PDF quoting what it's cited for, dated across three years, with who issued it
    # (scripts/demo_cases.py); one outdated readership figure stays cited, for preflight to flag.
    import demo_cases

    demo_cases.add_case(ws, "maya")
    ws.after_change()

    # Metrics history (fortnightly, since 2024), the pipeline and deadlines, so every page has something to show.
    from areao1.core.models import MetricRow

    rows, day, n = [], start, 0
    while day <= date.today():
        n += 1
        rows += [MetricRow(date=day, source="github", item="maya-chen/fastqueue", metric="stars", value=round(120 * n**1.35)),
                 MetricRow(date=day, source="github", item="maya-chen/fastqueue", metric="forks", value=round(9 * n**1.2)),
                 MetricRow(date=day, source="huggingface", item="maya-chen/trace-small", metric="downloads", value=round(800 * n**1.5)),
                 MetricRow(date=day, source="openalex", item="Maya Chen", metric="citations", value=round(3 * n**1.4))]  # fmt: skip
        day += timedelta(days=14)
    ws.append_metrics(rows)
    soon = date.today()
    for title, crit, stage, follow in (("Review for Example Systems Conf 2027", "judging", "applied", 5),
                                       ("Talk proposal: queues at scale", "press", "waiting", 12),
                                       ("Example Engineering Society senior membership", "membership", "idea", None),
                                       ("Mentor at Example Hackathon Series", "judging", "done", None)):  # fmt: skip
        ws.add_pipeline_item(title=title, criterion=crit, stage=stage,
                             follow_up=soon + timedelta(days=follow) if follow else None)  # fmt: skip
    for title, kind, days_out, crit in (("Example Systems Conf reviews due", "submission", 6, "judging"),
                                        ("Get the letter draft back from Dr. Natarajan", "follow_up", 10, None),
                                        ("Example Engineering Society application closes", "application", 23, "membership"),
                                        ("Target filing date", "filing", 75, None)):  # fmt: skip
        ws.add_deadline(title=title, kind=kind, due=soon + timedelta(days=days_out), criterion=crit)

    # The vault: a Tier 1 page imported offline from the test fixtures, so the chat's rule sentence verifies.
    page = gzip.decompress(
        (ROOT / "tests" / "fixtures" / "vault" / "uscis-pm-eb1-extraordinary.html.gz").read_bytes()
    )
    Vault(ws).import_file("uscis-pm-6-f-2", page, "Policy Manual EB-1.html")
    o1 = next((ROOT / "community-vault" / "snapshots").glob("9c0e2d65*.html")).read_bytes()  # the O-1 chapter
    Vault(ws).import_file("uscis-pm-2-m-4", o1, "Policy Manual O-1.html")

    # Contacts, a letter writer, Gmail, and one follow-up waiting for approval.
    omar = ws.add_contact(
        name="Omar Haddad",
        emails=["omar@hackseries.example"],
        relationship="organizer",
        org="Example Hackathon Series",
    )
    ws.add_contact(
        name="Dr. Priya Natarajan",
        emails=["priya@university.example"],
        relationship="recommender",
        org="Example University",
    )
    demo_cases.add_letters(ws, "maya")
    quiet = datetime.now(UTC) - timedelta(days=9)
    ws.save_threads(GmailThreads(threads=[GmailThread(id="18f1", subject="Judging the spring finals", contact_ids=[omar.id], last_at=quiet,
                                                      last_from="you", last_message_id="<maya-1@mail.example>")]))  # fmt: skip
    for d in outreach.follow_ups(ws):
        Service(ws, actor="follow-up").save_draft(d)
    gmail = FakeGmail(email="maya@gmail.example", bodies_ok=True)
    gmail.install(_MP())
    mail.connect(gmail.email, gmail.password)
    _GMAIL[0] = gmail
    print(f"built {root}: {len(claims)} claims, 6 exhibits, 2 contacts, 1 follow-up draft")


_GMAIL: list = [None]


def invite(ws_root: Path, verified: bool = True) -> None:
    """A judging invitation arrives, and the daily opportunity check runs (offline: the official page is stubbed).
    The verified one is from Lakeside Hacks' own domain; the other from a look-alike (Riverside Hack5)."""
    import anyio

    from areao1.criteria.case import Case
    from areao1.google import opportunities, verify

    g = _GMAIL[0]
    when = datetime.now(UTC) + timedelta(days=24)
    if verified:
        event, site = "Lakeside Hacks 2026", "lakesidehacks.example"
        auth = f"mx.google.com; dkim=pass header.d={site}; spf=pass; dmarc=pass header.from={site}"
    else:
        event, site = "Riverside Hacks 2026", "riversidehack5.example"
        auth = "mx.google.com; spf=fail; dkim=none; dmarc=fail"
    body = (f"Hi Maya, we'd love you to judge the systems track at {event} on {when:%B} {when.day}, {when.year}. "
            f"Details: https://{site}/judges")  # fmt: skip
    g.add(900 + len(g.messages), datetime.now(UTC).strftime(D), f"{event[:-5]} <judges@{site}>", g.email,
          f"Invitation to judge {event}", body=body, auth_results=auth)  # fmt: skip
    official = f"{event} · Judges · Finals on {when:%B} {when.day}, {when.year}."

    async def fetch(url: str):  # type: ignore[no-untyped-def]
        return url, event, official

    out = anyio.run(opportunities.run, Case(ws_root), None, verify.verifier(None, "gpt-6-luna", fetch))
    print(" · ".join(out["lines"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="film-maya")
    ap.add_argument("--port", type=int, default=7920)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    no_network()
    fake_keychain()
    root = Path(args.dir).resolve()
    build(root)

    import uvicorn

    from areao1.criteria.case import Case
    from areao1.server.app import create_app

    def serve() -> None:
        uvicorn.run(
            create_app(Case(root), engine=film_engine()),
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
        )

    threading.Thread(target=serve, daemon=True).start()
    print(
        f"Maya's filming workspace: http://127.0.0.1:{args.port}   keys: j (verified invite), u (unverified), r, q"
    )
    for line in sys.stdin:
        key = line.strip().lower()
        if key == "j":
            invite(root, True)
        elif key == "u":
            invite(root, False)
        elif key == "r":
            build(root)
            print("rebuilt: reload the page")
        elif key == "q":
            break


if __name__ == "__main__":
    main()
