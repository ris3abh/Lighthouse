"""Evidence preflight (ADR 0018): every check finds its problem with links to the records involved, severities,
stable ids so dismissals stick, and nothing blocks. Everything here is invented."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from areao1.core.models import ClaimDraft, Evidence
from areao1.criteria import preflight
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}
PDF = b"%PDF-1.4 invented"


def _claim(
    ws, subject, predicate, value, *, connector="upload", url="upload:doc.txt", when=None, approve=True
):
    text = f"{predicate.replace('_', ' ')}: {value}"
    [c] = ws.memory.record(Evidence(connector=connector, source_url=url, payload=text, media_type="text/plain",
                                    claims=[ClaimDraft(subject=subject, subject_kind="person" if subject.startswith("person") else "artifact",
                                                       subject_name=subject.split(":")[-1].replace("-", " ").title(),
                                                       predicate=predicate, value=value, excerpt=text, event_date=when)]))  # fmt: skip
    if approve:
        ws.memory.decide([c.id], "approved", rationale="test")
    return c


def _exhibit(
    ws, title, *, ext="pdf", url=None, stage=None, on=date(2026, 2, 1), crit="judging", kind="panel_letter"
):
    return ws.add_exhibit_file(content=PDF if ext == "pdf" else b"# capture", filename=f"x.{ext}", criterion=crit,
                               evidence_type=kind, title=title, on=on, stage=stage, source_url=url)  # fmt: skip


def _kinds(report):
    return [(i["kind"], i["severity"], i["title"]) for i in report["issues"]]


def _stars(ws):
    old = _claim(
        ws, "artifact:fastqueue", "stars", 1840, url="https://press.example/fastqueue", when=date(2025, 6, 1)
    )
    new = _claim(ws, "artifact:fastqueue", "stars", 2100, connector="github", url="https://api.github.example/repos/x",
                 when=date(2026, 9, 1))  # fmt: skip
    return old, new


def _of(report, kind):
    return [i for i in report["issues"] if i["kind"] == kind]


def test_a_document_from_back_then_citing_the_value_it_had_then_is_not_outdated(ws):
    old, new = _stars(ws)
    press = _exhibit(ws, "Example Weekly profile", crit="press", kind="press_article", on=date(2026, 2, 1))
    ws.memory.cite(press.id, [old.id])  # written before the newer count existed
    lt = ws.add_letter(name="Dr. Example Writer", relationship="independent", criteria=["press"])
    ws.memory.cite(f"letter:{lt.id}", [new.id])
    report = preflight.run(ws, save=False)
    assert _of(report, "superseded_cited") == []
    assert _of(report, "metric_mismatch") == []  # stars change over time; both values are dated: a history


def test_a_document_presenting_an_older_value_as_current_is_outdated(ws):
    old, new = _stars(ws)
    later = _exhibit(ws, "Example Weekly follow-up", crit="press", kind="press_article", on=date(2026, 9, 20))
    ws.memory.cite(later.id, [old.id])  # dated after the newer count, citing only the old one
    lt = ws.add_letter(name="Dr. Example Writer", relationship="independent", criteria=["press"])
    ws.memory.cite(f"letter:{lt.id}", [old.id])  # a letter speaks as of today
    sup = {i["refs"][0]["id"]: i for i in _of(preflight.run(ws, save=False), "superseded_cited")}
    assert set(sup) == {later.id, lt.id}
    i = sup[later.id]
    assert i["severity"] == "high" and i["title"] == "Example Weekly follow-up cites an outdated value"
    assert "1,840 (2025-06-01) is now 2,100 (2026-09-01)" in i["detail"] and "reads as current" in i["detail"]
    assert {r["id"] for r in i["refs"]} == {later.id, old.id, new.id}
    assert all(r["link"] for r in i["refs"])


def test_citing_both_values_is_history_and_an_undated_old_value_is_outdated(ws):
    old, new = _stars(ws)
    both = _exhibit(ws, "Growth chart", crit="press", kind="press_article", on=date(2026, 9, 20))
    ws.memory.cite(both.id, [old.id, new.id])
    assert _of(preflight.run(ws, save=False), "superseded_cited") == []
    undated = _claim(ws, "artifact:spool", "stars", 300, url="https://press.example/spool")
    _claim(ws, "artifact:spool", "stars", 900, connector="github", url="https://api.github.example/repos/s",
           when=date(2026, 9, 1))  # fmt: skip
    early = _exhibit(ws, "Spool launch post", crit="press", kind="press_article", on=date(2025, 1, 1))
    ws.memory.cite(early.id, [undated.id])
    [i] = _of(preflight.run(ws, save=False), "superseded_cited")
    assert (
        i["refs"][0]["id"] == early.id
        and "300 (undated)" in i["detail"]
        and "Give the old value its date" in i["detail"]
    )


def test_values_that_should_agree_still_differ(ws):
    a = _claim(ws, "event:example-hacks", "panel_size", 9, when=date(2025, 3, 1))
    b = _claim(ws, "event:example-hacks", "panel_size", 12, url="upload:other.txt", when=date(2025, 3, 1))
    e1 = _exhibit(ws, "Judges page")
    e2 = _exhibit(ws, "Organizer letter", on=date(2026, 3, 1))
    ws.memory.cite(e1.id, [a.id])
    ws.memory.cite(e2.id, [b.id])
    [mm] = _of(preflight.run(ws, save=False), "metric_mismatch")  # not a metric that changes over time
    assert (
        mm["severity"] == "medium" and "9 (2025-03-01)" in mm["detail"] and "12 (2025-03-01)" in mm["detail"]
    )
    assert {r["type"] for r in mm["refs"]} >= {"exhibit", "claim"}
    assert preflight.time_varying("monthly_readers") and preflight.time_varying("citation_count")
    assert not preflight.time_varying("panel_size")


def test_drafts_citing_unapproved_or_missing_claims(ws):
    ok = _claim(ws, "event:example-hacks", "judged_event", "systems track")
    pending = _claim(ws, "event:example-hacks", "judged_round", "finals", approve=False)
    (ws.root / "drafts" / "letters").mkdir(parents=True, exist_ok=True)
    (ws.root / "drafts" / "letters" / "writer.md").write_text(
        f"Maya judged the systems track. [{ok.id}] Maya judged the finals. [{pending.id}] "
        f"Maya chaired the event. [clm_0123456789ab]\n\n---\n\n## Sources\n\n- [clm_ffffffffffff] ignored\n"
    )
    [issue] = [i for i in preflight.run(ws, save=False)["issues"] if i["kind"] == "unsupported_cited"]
    assert (
        issue["title"] == "drafts/letters/writer.md cites claims it can't rest on"
        and issue["severity"] == "high"
    )
    assert "1 that doesn't exist in memory and 1 not approved (proposed)" in issue["detail"]
    assert {r["id"] for r in issue["refs"]} == {
        "drafts/letters/writer.md",
        "clm_0123456789ab",
        pending.id,
    }  # not the Sources list


def test_identity_facts_that_disagree_but_not_spelling_variants(ws):
    _claim(ws, "person:maya", "linkedin_employer", "Example Corp", url="upload:linkedin.pdf")
    _claim(
        ws, "person:maya", "employer", "Example Corporation, Inc.", url="upload:offer.pdf"
    )  # same, normalized
    _claim(ws, "person:maya", "linkedin_role", "Sr. Software Engineer", url="upload:linkedin.pdf")
    _claim(ws, "person:maya", "role_title", "Staff Engineer", url="upload:offer.pdf")
    _claim(ws, "person:maya", "linkedin_name", "Maya Chen", url="upload:linkedin.pdf")
    _claim(ws, "person:maya", "legal_name", "Maya L. Chen", url="upload:passport-page.pdf")
    facts = [i for i in preflight.run(ws, save=False)["issues"] if i["kind"] == "conflicting_facts"]
    titles = {i["title"]: i for i in facts}
    assert set(titles) == {"Different names for Maya", "Different job titles for Maya"}  # employers agree
    assert titles["Different names for Maya"]["severity"] == "high"
    assert titles["Different job titles for Maya"]["severity"] == "medium"
    assert "“Sr. Software Engineer”" in titles["Different job titles for Maya"]["detail"]
    assert preflight.normalize("Sr. Eng, Example Corp.") == preflight.normalize("senior engineer example")


def test_an_exhibit_dated_differently_from_the_event_it_shows(ws):
    c = _claim(
        ws,
        "event:example-hacks-2026",
        "judged_event",
        "judge",
        url="upload:invite.pdf",
        when=date(2026, 3, 1),
    )
    ex = _exhibit(ws, "Example Hacks 2026 certificate", on=date(2026, 3, 8))
    ws.memory.cite(ex.id, [c.id])
    near = _exhibit(ws, "Example Hacks 2026 photo", on=date(2026, 3, 2))  # within a few days: fine
    ws.memory.cite(near.id, [c.id])
    [dates] = [i for i in preflight.run(ws, save=False)["issues"] if i["title"].startswith("Two dates")]
    assert dates["title"] == "Two dates for Example Hacks 2026 certificate"
    assert "dated 2026-03-08" in dates["detail"] and "says 2026-03-01" in dates["detail"]


def test_invited_without_completion_captures_without_a_primary_and_undated(ws):
    _exhibit(ws, "Invitation to judge Example Hacks 2026", stage="invited", kind="judge_invite")
    _exhibit(ws, "Invitation to judge Riverside Jam 2026", stage="invited", kind="judge_invite")
    _exhibit(ws, "Judged Riverside Jam 2026", stage="completed")  # this one happened
    _exhibit(ws, "Example Hacks judges page", ext="md", url="https://hacks.example/judges")
    _exhibit(ws, "Riverside Jam judges page", ext="md", url="https://jam.example/judges")
    _exhibit(ws, "Riverside Jam judges page (PDF)", url="https://jam.example/judges")  # its primary copy
    from areao1.core import clock

    legacy = _exhibit(ws, "Certificate with no date shown", on=clock.today())
    ex = ws.exhibits()
    next(e for e in ex.exhibits if e.id == legacy.id).date_source = None  # filed before dates were tracked
    ws.save_exhibits(ex)
    report = preflight.run(ws, save=False)
    kinds = _kinds(report)
    assert (
        "invited_not_completed",
        "medium",
        "Invitation to judge Example Hacks 2026: invited, no proof it happened",
    ) in kinds
    assert not any("Riverside Jam 2026: invited" in t for _, _, t in kinds)
    assert ("capture_without_primary", "medium", "Example Hacks judges page: a capture only") in kinds
    assert not any(t == "Riverside Jam judges page: a capture only" for _, _, t in kinds)
    assert ("undated_exhibit", "low", "Certificate with no date shown: no document date") in kinds
    sev = [i["severity"] for i in report["issues"]]
    assert sev == sorted(sev, key=preflight.SEVERITIES.index)  # high first


def test_approved_facts_without_an_exhibit_are_grouped_per_entity(ws):
    for i in range(12):
        _claim(ws, "artifact:fastqueue", f"metric_{i}", i)
    [low] = [i for i in preflight.run(ws, save=False)["issues"] if i["kind"] == "claim_without_exhibit"]
    assert low["severity"] == "low" and low["title"] == "Fastqueue: 12 approved facts with no exhibit"
    assert len(low["refs"]) == 10  # a sample, not all of them


def test_run_save_dismiss_and_the_dismissal_sticks(ws):
    _exhibit(ws, "Invitation to judge Example Hacks 2026", stage="invited", kind="judge_invite")
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        assert client.get("/api/preflight").json() == {"report": None}
        report = client.post("/api/preflight/run", headers=W).json()["report"]
        issue = next(i for i in report["issues"] if i["kind"] == "invited_not_completed")
        assert (
            client.post(f"/api/preflight/{issue['id']}/dismiss", headers=W, json={"note": ""}).status_code
            == 400
        )
        after = client.post(
            f"/api/preflight/{issue['id']}/dismiss", headers=W, json={"note": "Judging is next week"}
        ).json()
        again = client.post("/api/preflight/run", headers=W).json()["report"]
    assert next(i for i in after["report"]["issues"] if i["id"] == issue["id"])["dismissed"]
    same = next(i for i in again["issues"] if i["id"] == issue["id"])
    assert same["dismissed"] and same["dismissed_note"] == "Judging is next week"
    assert again["counts"]["medium"] == report["counts"]["medium"] - 1
    assert [c.action for c in ws.changes()][-3:] == ["preflight.run", "preflight.dismiss", "preflight.run"]
    assert len(ws.changes()[-1].model_dump_json()) < 2000  # the log keeps counts, not the report


def test_the_cli_and_nothing_written_without_save(ws):
    from areao1.cli import app

    _exhibit(ws, "Invitation to judge Example Hacks 2026", stage="invited", kind="judge_invite")
    preflight.run(ws, save=False)
    assert preflight.latest(ws) is None
    out = CliRunner().invoke(app, ["preflight", "-w", str(ws.root)])
    assert out.exit_code == 0, out.output
    assert (
        out.output.startswith("Preflight: ") and "medium Invitation to judge Example Hacks 2026" in out.output
    )
    assert preflight.latest(ws) is not None
