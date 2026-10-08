"""Serve a throwaway, fictional workspace for the browser suite (tests/e2e). Offline and fake throughout: DNS is
local-only, Gmail is the in-memory fake, the keychain lives in memory, and the model is the scripted engine. It
never opens a real workspace, mailbox or API key.

    python tests/e2e/serve.py <scenario> <workspace dir> <port>

Scenarios:
  film            Maya's filming workspace (scripts/film_demo.py) plus a verified and a suspicious invitation in the
                  Inbox and Mail, an uploaded PDF and .eml waiting, and a chat that adds a deadline (undoable)
  persona:<id>    maya / ravi / lena after onboarding (from their LinkedIn PDF), with an email and a PDF in the
                  Inbox and the first evidence accepted
  empty           a new workspace that opens into onboarding
Prints "READY <port>" once it serves."""

from __future__ import annotations

import sys
import threading
import time
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

PERSONAS = ROOT / "tests" / "fixtures" / "personas"
W = {"X-AreaO1": "1"}
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def thank_you_eml(name: str, event: str = "Example Hacks 2026") -> bytes:
    m = EmailMessage()
    m["Authentication-Results"] = (
        "mx.google.com; dkim=pass header.d=examplehacks.org; spf=pass; dmarc=pass header.from=examplehacks.org"
    )
    m["From"], m["To"], m["Subject"] = (
        "Example Hacks <team@examplehacks.org>",
        f"{name} <qa@work.example>",
        f"Thank you for judging {event}",
    )
    m["Date"] = "Sat, 03 Oct 2026 18:00:00 +0000"
    m.set_content(
        f"Hi {name.split()[0]}, thank you for judging at {event}! Your scores helped pick the 12 winning teams."
    )
    return bytes(m)


def engine():  # type: ignore[no-untyped-def]
    """The scripted engine: every chat reads the scoreboard, adds one deadline (an undoable chat action) and answers."""
    from film_demo import ANSWER, film_engine

    return film_engine([("tool", "get_scoreboard", {}),
                        ("tool", "add_deadline", {"title": "QA follow-up deadline", "due": "2026-12-01", "kind": "other"}),
                        ("text", ANSWER)])  # fmt: skip


def prepare(scenario: str, root: Path):  # type: ignore[no-untyped-def]
    import film_demo
    from fastapi.testclient import TestClient

    from areao1.criteria.case import Case
    from areao1.google import outreach
    from areao1.scaffold import create_workspace
    from areao1.server.app import create_app

    film_demo.no_network()
    film_demo.fake_keychain()
    outreach.UNDO_SECONDS = 4.0  # long enough to see and press Undo send, short enough for a test
    if scenario == "film":
        film_demo.build(root)
        film_demo.invite(root, True)
        film_demo.invite(root, False)
        ws = Case(root)
        c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
        c.post("/api/inbox/upload", headers=W, files=[("files", ("thank-you.eml", thank_you_eml("Maya Chen"), "message/rfc822")),
                                                      ("files", ("award-certificate.pdf", PDF, "application/pdf"))])  # fmt: skip
        return ws
    if scenario == "empty":
        import shutil

        if root.exists():
            shutil.rmtree(root)
        create_workspace(root, name="", git=False)
        return Case(root)
    if scenario.startswith("persona:"):
        import shutil

        from test_onboarding import answer_all, upload

        pid = scenario.split(":", 1)[1]
        if root.exists():
            shutil.rmtree(root)
        ws = Case(create_workspace(root, name="", git=False).root)
        c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
        view, _ = answer_all(c, upload(c, pid))
        for step in ("lookups_done", "chats_skip", "mail_skip", "tour_done"):
            c.post("/api/onboarding/step", headers=W, json={"step": step})
        name = ws.person().name or pid.title()
        c.post("/api/inbox/upload", headers=W, files=[("files", ("thank-you.eml", thank_you_eml(name), "message/rfc822")),
                                                      ("files", ("press-profile.pdf", PDF, "application/pdf"))])  # fmt: skip
        first = next((x for x in c.get("/api/inbox").json() if x.get("proposed_criterion")), None)
        if first:
            c.post(f"/api/inbox/{first['id']}/accept", headers=W, json={})
        return ws
    raise SystemExit(f"unknown scenario {scenario!r}")


def main() -> None:
    scenario, root, port = sys.argv[1], Path(sys.argv[2]).resolve(), int(sys.argv[3])
    ws = prepare(scenario, root)
    import uvicorn

    from areao1.server.app import create_app

    app = create_app(ws, engine=engine())
    threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning"), daemon=True
    ).start()
    import socket

    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    print(f"READY {port}", flush=True)
    for _line in sys.stdin:  # serve until the test closes stdin
        pass


if __name__ == "__main__":
    main()
