"""Proof recipes (ADR 0017): a checklist once an activity is accepted / completed / granted / published (and a
two-item one at invited), items done only by exhibits, uploads preset by their item, links through the service
layer, missing items in This week, matches from Mail (by subject, or a verified organizer) to the Inbox, and the
read-only run_preflight tool. Everything here is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from areao1.criteria import proof
from areao1.criteria.models import MailItem
from areao1.resources import profiles_dir
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}
PDF = b"%PDF-1.4 invented"


def _exhibit(ws, title, *, stage=None, crit="judging", kind="panel_letter", tier=None):
    ex = ws.add_exhibit_file(content=PDF, filename="x.pdf", criterion=crit, evidence_type=kind, title=title,
                             on=date(2026, 3, 1), stage=stage)  # fmt: skip
    if tier:
        exs = ws.exhibits()
        next(e for e in exs.exhibits if e.id == ex.id).source_tier = tier
        ws.save_exhibits(exs)
    return ex


def _list(ws, anchor):
    return next(c for c in proof.checklists(ws) if c["anchor"] == anchor)


def test_every_bundled_recipe_loads_and_names_a_real_criterion():
    import json

    from areao1.core.schemas import SCHEMA_DIR
    from areao1.criteria.engine import load_profiles

    ids = {c.id for p in load_profiles().values() for c in p.criteria}
    files = sorted((profiles_dir() / "recipes").glob("*.yaml"))
    assert {f.stem for f in files} >= {"judging", "awards", "critical_role", "membership", "press",
                                       "scholarly_articles", "original_contributions", "high_salary"}  # fmt: skip
    for f in files:
        raw = yaml.safe_load(f.read_text())
        assert raw["criterion"] == f.stem and raw["criterion"] in ids, f.name
        for item in raw["items"]:
            assert all(k == k.lower() for k in item.get("match", {}).get("keywords", [])), (
                f.name,
                item["id"],
            )
            assert (
                "required" not in (item.get("why", "") + item["label"]).lower()
            )  # advice, not legal requirements
    assert "items" in json.loads((SCHEMA_DIR / "proof-recipe.schema.json").read_text())["properties"]
    judging = yaml.safe_load((profiles_dir() / "recipes" / "judging.yaml").read_text())
    assert [i["id"] for i in judging["items"]] == ["invitation", "acceptance", "submission_proof", "completion",
                                                   "event_page", "organizer_standing", "volume", "selection_criteria"]  # fmt: skip


def test_a_checklist_appears_once_an_activity_reaches_a_stage_that_matters(ws):
    invited = _exhibit(ws, "Invitation to judge Example Hacks", stage="invited", kind="judge_invite")
    done = _exhibit(ws, "Judged Example Hacks 2026", stage="completed")
    plain = _exhibit(ws, "Some document")  # not an activity
    anchors = {a["anchor"] for a in proof.anchors(ws)}
    assert f"exhibit:{done.id}" in anchors
    assert (
        f"exhibit:{invited.id}" in anchors and f"exhibit:{plain.id}" not in anchors
    )  # invited: the mini list
    c = _list(ws, f"exhibit:{done.id}")
    status = {i["id"]: i["status"] for i in c["items"]}
    assert status["completion"] == "done"  # the anchor itself is the completion (its stage matches)
    assert status["invitation"] == "missing" and status["selection_criteria"] == "missing"
    assert c["missing"] == 6  # selection criteria is optional ("if available")
    item = ws.add_pipeline_item(title="Mentor at Example Hacks", criterion="judging", stage="done")
    assert f"pipeline:{item.id}" in {a["anchor"] for a in proof.anchors(ws)}


def test_an_item_with_a_stage_needs_the_activity_at_that_stage(ws):
    thanks = _exhibit(ws, "Thank you for judging Example Hacks 2026", stage="completed", kind="judge_invite")
    status = {i["id"]: i["status"] for i in _list(ws, f"exhibit:{thanks.id}")["items"]}
    assert (
        status["completion"] == "done" and status["invitation"] == "missing"
    )  # typed judge_invite, but completed
    cert = _exhibit(
        ws, "Example Prize certificate", crit="awards", kind="award_certificate"
    )  # a document, no stage
    won = _exhibit(ws, "Won the Example Prize", stage="granted", crit="awards", kind="award_notice")
    item = next(i for i in _list(ws, f"exhibit:{won.id}")["items"] if i["id"] == "certificate")
    assert [s["id"] for s in item["suggestions"]] == [cert.id]  # matched by its type


def test_items_are_done_only_by_exhibits_linked_uploaded_or_waived(ws):
    done = _exhibit(ws, "Judged Example Hacks 2026", stage="completed")
    page = _exhibit(ws, "Example Hacks 2026 judges page")
    mine = _exhibit(ws, "My notes on Example Hacks 2026", tier="self_reported")
    anchor = f"exhibit:{done.id}"
    sugg = next(i for i in _list(ws, anchor)["items"] if i["id"] == "event_page")["suggestions"]
    assert [s["id"] for s in sugg] == [page.id]  # "judges" in its title; the self-reported note isn't offered
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        assert client.post("/api/proof/link", headers=W, json={"anchor": anchor, "item": "event_page",
                                                                 "exhibit_id": page.id}).status_code == 200  # fmt: skip
        up = client.post("/api/exhibits/upload", headers=W, files={"file": ("thanks.pdf", PDF, "application/pdf")},
                         data={"criterion": "judging", "evidence_type": "reviewer_record", "title": "Review receipt",
                               "date": "2026-03-03", "proof_anchor": anchor, "proof_item": "submission_proof"})  # fmt: skip
        assert up.status_code == 200
        client.post(
            "/api/proof/link", headers=W, json={"anchor": anchor, "item": "volume", "exhibit_id": mine.id}
        )
        r = client.post(
            "/api/proof/waive", headers=W, json={"anchor": anchor, "item": "organizer_standing", "note": ""}
        )
        assert r.status_code == 400  # a reason, always
        client.post("/api/proof/waive", headers=W, json={"anchor": anchor, "item": "organizer_standing",
                                                         "note": "The organizer is the university itself"})  # fmt: skip
        bad = client.post(
            "/api/proof/link", headers=W, json={"anchor": anchor, "item": "nope", "exhibit_id": page.id}
        )
        assert bad.status_code == 404
        status = {i["id"]: i["status"] for i in client.get("/api/proof").json()["checklists"][0]["items"]}
    assert status["event_page"] == "done" and status["submission_proof"] == "done"
    assert status["volume"] == "self_reported"  # linked for tracking, never done (SPEC §2a.4)
    assert status["organizer_standing"] == "waived"
    assert {c.action for c in ws.changes()} >= {"proof.link", "proof.waive", "evidence.upload"}
    assert f"exhibit:{page.id}" not in {
        a["anchor"] for a in proof.anchors(ws)
    }  # a proof item, not an activity
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        client.post("/api/proof/unlink", headers=W, json={"anchor": anchor, "item": "event_page"})
    assert next(i for i in _list(ws, anchor)["items"] if i["id"] == "event_page")["status"] == "missing"


def test_missing_items_show_in_this_week(ws):
    from areao1.criteria.overview import human_tasks

    _exhibit(ws, "Judged Example Hacks 2026", stage="completed")
    _exhibit(ws, "Won the Example Prize", stage="granted", crit="awards", kind="award_certificate")
    lines = [t for t in human_tasks(ws) if t["kind"] == "proof"]
    assert {t["title"] for t in lines} == {"Judged Example Hacks 2026: 6 proof items to save",
                                           "Won the Example Prize: 5 proof items to save"}  # fmt: skip
    assert all(t["link"].startswith("#/evidence?proof=exhibit:") for t in lines)


def test_matches_from_mail_go_to_the_inbox_and_link_on_accept(ws):
    done = _exhibit(ws, "Judged Example Hacks 2026", stage="accepted", kind="judge_invite")
    anchor = f"exhibit:{done.id}"
    at = datetime(2026, 3, 20, tzinfo=UTC)
    box = ws.mailbox()
    box.items = [
        MailItem(id="m1", thread_id="t1", at=at, from_name="Example Hacks", from_addr="team@hacks.example",
                 subject="Thank you for judging Example Hacks 2026!", category="judging"),
        MailItem(id="m2", thread_id="t2", at=at, from_name="Other Event", from_addr="team@other.example",
                 subject="Thank you for judging Riverside Jam", category="judging"),  # another event
        MailItem(id="m3", thread_id="t3", at=at, from_name="Maya", from_addr="maya@example.com", outgoing=True,
                 subject="Thanks for judging Example Hacks 2026", category="judging"),  # your own mail
    ]  # fmt: skip
    ws.save_mailbox(box)
    assert proof.propose(ws) == ["Proof: 1 possible match in your Inbox"]
    [cand] = [c for c in ws.inbox().candidates if c.fingerprint.startswith("proof:")]
    assert cand.proposal == {"proof": {"anchor": anchor, "item": "completion"}} and cand.stage == "completed"
    assert cand.raw_url and "mail.google.com" in cand.raw_url
    assert proof.propose(ws) == ["Proof: no new matches"]  # once
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        assert client.post(f"/api/inbox/{cand.id}/accept", headers=W, json={}).status_code == 200
    item = next(i for i in _list(ws, anchor)["items"] if i["id"] == "completion")
    assert item["status"] == "done" and item["via"] == "linked"
    assert [c.action for c in ws.changes()][-2:] == ["inbox.accept", "proof.link"]


def test_a_workspace_recipe_overrides_the_bundled_one(ws):
    (ws.root / "profiles" / "recipes").mkdir(parents=True, exist_ok=True)
    (ws.root / "profiles" / "recipes" / "judging.yaml").write_text(
        "criterion: judging\nlabel: Judging (our firm's list)\nitems:\n  - id: completion\n    label: The thank-you\n"
        "    match: {stages: [completed]}\n"
    )
    done = _exhibit(ws, "Judged Example Hacks 2026", stage="completed")
    c = _list(ws, f"exhibit:{done.id}")
    assert c["recipe"] == "Judging (our firm's list)" and c["missing"] == 0


def test_the_agent_reads_missing_proof_and_can_only_propose(ws):
    import json

    import anyio

    from areao1.agent import actions
    from areao1.agent.tools import RunContext, build_tools
    from areao1.core.models import AgentRun

    done = _exhibit(ws, "Judged Example Hacks 2026", stage="completed")
    ctx = RunContext(ws, AgentRun(kind="chat", engine="fake", model="test", prompt="test"))
    tools = {t.name: t for t in build_tools(ctx)}
    assert tools["missing_proof"].read_only
    out = json.loads(anyio.run(tools["missing_proof"].handler, {}))
    [activity] = out["activities"]
    assert activity["anchor"] == f"exhibit:{done.id}" and "invitation" in {
        m["item"] for m in activity["missing"]
    }
    assert not any("proof" in name and name != "missing_proof" for name in tools)  # no tool links or waives
    for action in ("proof.link", "proof.waive", "proof.unlink"):
        assert actions.covered(action) and action not in actions.TOOL_FOR  # the person's, with a reason


def _upload(client, anchor, item, title="proof.pdf", **form):
    return client.post("/api/exhibits/upload", headers=W, files={"file": (title, PDF, "application/pdf")},
                       data={"criterion": "judging", "title": title, "date": "2026-03-21", "proof_anchor": anchor,
                             "proof_item": item, **form})  # fmt: skip


def test_an_invitation_gets_a_two_item_list_and_the_full_recipe_once_accepted(ws):
    invited = _exhibit(ws, "Invitation to judge Example Hacks 2026", stage="invited", kind="judge_invite")
    anchor = f"exhibit:{invited.id}"
    c = _list(ws, anchor)
    assert [(i["id"], i["status"]) for i in c["items"]] == [("invitation", "done"), ("acceptance", "missing")]
    assert c["missing"] == 1 and c["stage"] == "invited"
    from areao1.criteria import preflight

    titles = [
        i["title"] for i in preflight.run(ws, save=False)["issues"] if i["kind"] == "invited_not_completed"
    ]
    assert len(titles) == 1  # its own rule, not a second "accepted, no completion" issue
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        r = _upload(client, anchor, "acceptance", "You're confirmed.pdf")  # no type, no stage: the item says
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == "accepted" and r.json()["evidence_type"] == "judge_invite"
    c = _list(ws, anchor)
    assert c["stage"] == "accepted" and len(c["items"]) == 8  # now the full judging recipe
    status = {i["id"]: i["status"] for i in c["items"]}
    assert (
        status["invitation"] == "done"
        and status["acceptance"] == "done"
        and status["completion"] == "missing"
    )


def test_a_criterion_without_its_own_invitation_items_uses_the_generic_two(ws):
    invited = _exhibit(
        ws, "Invited to speak at Example Summit", stage="invited", crit="press", kind="interview"
    )
    c = _list(ws, f"exhibit:{invited.id}")
    assert [i["id"] for i in c["items"]] == ["invitation", "acceptance"]
    assert c["items"][1]["preset"] == {"evidence_type": "interview", "stage": "accepted"}


def test_an_upload_from_a_checklist_is_preset_and_ticks_its_item(ws):
    done = _exhibit(ws, "Judged Example Hacks 2026", stage="accepted", kind="judge_invite")
    anchor = f"exhibit:{done.id}"
    rows = {i["id"]: i for i in _list(ws, anchor)["items"]}
    assert rows["completion"]["preset"] == {"evidence_type": "judge_invite", "stage": "completed"}
    assert rows["submission_proof"]["preset"] == {"evidence_type": "reviewer_record", "stage": None}
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        r = _upload(client, anchor, "completion", "Thank you for judging.pdf")
        assert r.status_code == 200, r.text
        ex = r.json()
        assert (ex["evidence_type"], ex["stage"]) == ("judge_invite", "completed")
        r = _upload(client, anchor, "submission_proof", "Scores export.pdf")
        assert r.json()["evidence_type"] == "reviewer_record" and r.json()["stage"] is None
        assert (
            _upload(client, anchor, "completion", evidence_type="", stage="").status_code == 200
        )  # same defaults
        assert client.post("/api/exhibits/upload", headers=W, files={"file": ("x.pdf", PDF, "application/pdf")},
                           data={"criterion": "judging", "title": "x", "date": "2026-03-21"}).status_code == 400  # fmt: skip
    rows = {i["id"]: i for i in _list(ws, anchor)["items"]}
    assert rows["completion"]["status"] == "done" and rows["completion"]["via"] == "linked"
    assert rows["submission_proof"]["status"] == "done"
    web = (Path(__file__).parents[1] / "web" / "src" / "pages" / "Evidence.tsx").read_text()
    assert "proof?.evidence_type" in web and "proof.stage" in web  # the form starts from the preset


def _auth(domain, ok=True):
    return {"verdict": "verified" if ok else "failed", "dmarc": "pass" if ok else "fail", "spf": None, "dkim": None,
            "dkim_domain": None, "from_domain": domain, "aligned": False, "by": "mx.example"}  # fmt: skip


def test_a_reply_from_the_verified_organizer_matches_without_naming_the_event(ws):
    accepted = _exhibit(ws, "Lakeside Hacks 2026 judging", stage="accepted", kind="judge_invite")
    anchor = f"exhibit:{accepted.id}"
    at = datetime(2026, 3, 20, tzinfo=UTC)
    box = ws.mailbox()
    box.items = [
        MailItem(id="m0", thread_id="t0", at=at, from_name="Lakeside Hacks", from_addr="judges@lakesidehacks.example",
                 subject="Invitation to judge Lakeside Hacks 2026", category="judging",
                 auth=_auth("lakesidehacks.example")),  # names the event: the organizer is lakesidehacks.example
        MailItem(id="m1", thread_id="t0", at=at, from_name="Lakeside Hacks", from_addr="team@mail.lakesidehacks.example",
                 subject="Re: Saturday - thanks for judging!", category="judging",
                 auth=_auth("mail.lakesidehacks.example")),  # no word of the event, verified organizer
        MailItem(id="m2", thread_id="t2", at=at, from_name="Lakeside Hacks", from_addr="team@lakesidehacks.example",
                 subject="Thanks for judging, again", category="judging",
                 auth=_auth("lakesidehacks.example", ok=False)),  # failed the sender check
        MailItem(id="m3", thread_id="t3", at=at, from_name="Lakeside Hacks", from_addr="team@lakesidehack5.example",
                 subject="Thanks for judging!", category="judging", auth=_auth("lakesidehack5.example")),  # look-alike
    ]  # fmt: skip
    ws.save_mailbox(box)
    found = {(c.proposal["proof"]["item"], c.fingerprint.rsplit(":", 1)[1]) for c in proof.proposals(ws)}
    assert found == {("invitation", "m0"), ("completion", "m1")}, (
        found
    )  # not the failed check, not the look-alike
    [cand] = [c for c in proof.proposals(ws) if c.fingerprint.endswith(":m1")]
    assert "verified sender from lakesidehacks.example" in cand.summary and cand.stage == "completed"
    assert cand.proposal["proof"]["anchor"] == anchor


def test_run_preflight_is_a_read_only_tool_for_the_agent_and_mcp(ws):
    import json

    import anyio

    from areao1.agent.tools import RunContext, build_tools
    from areao1.core.models import AgentRun
    from areao1.mcp import server as mcp_server

    _exhibit(ws, "Invitation to judge Example Hacks 2026", stage="invited", kind="judge_invite")
    _exhibit(ws, "Undated thing")
    before = len(ws.changes())
    ctx = RunContext(ws, AgentRun(kind="chat", engine="fake", model="test", prompt="test"))
    tools = {t.name: t for t in build_tools(ctx)}
    assert "list_preflight_issues" not in tools and tools["run_preflight"].read_only
    out = json.loads(anyio.run(tools["run_preflight"].handler, {}))
    assert any(i["kind"] == "invited_not_completed" for i in out["issues"]) and "summary" in out
    high = json.loads(anyio.run(tools["run_preflight"].handler, {"min_severity": "high"}))
    assert all(i["severity"] == "high" for i in high["issues"])
    assert "run_preflight" in mcp_server.READ_TOOLS and "preflight" not in mcp_server.READ_TOOLS
    assert "run_preflight" in mcp_server.TOOL_NAMES  # listed with the read-only hint (tests/test_mcp.py)
    assert not (ws.root / "data" / "preflight.json").exists() and len(ws.changes()) == before  # wrote nothing
