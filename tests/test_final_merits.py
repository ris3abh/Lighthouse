"""The final-merits view (ADR 0019): a timeline of counted evidence, themes whose status a visible rule sets (with
the why), OpenAlex field benchmarks only on request, and the standard checked against the vault. No score, no
verdict. Everything here is invented."""

from __future__ import annotations

import gzip
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from areao1.criteria import merits
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}
PDF = b"%PDF-1.4 invented"
FIXTURES = Path(__file__).parent / "fixtures" / "vault"


def _exhibit(ws, title, *, crit, kind, on, url=None, org="", signals=(), tier=None):
    e = ws.add_exhibit_file(content=PDF, filename="x.pdf", criterion=crit, evidence_type=kind, title=title, on=on,
                            source_url=url)  # fmt: skip
    ex = ws.exhibits()
    for x in ex.exhibits:
        if x.id == e.id:
            x.organization, x.signals = org, list(signals)
            if tier:
                x.source_tier = tier
    ws.save_exhibits(ex)
    ws.after_change()
    return e


def _employer(ws, name="Example Systems"):
    person = ws.person()
    person.petitioner.name, person.petitioner.kind = name, "employer"
    ws.save_person(person)


def _case(ws):
    _employer(ws)
    for name, rel in (
        ("Dr. Ana Ruiz", "independent"),
        ("Prof. Lee Park", "independent"),
        ("Sam Boss", "employer"),
    ):
        ws.add_letter(name=name, relationship=rel, criteria=["judging"])
    _exhibit(ws, "Lakeside Hacks judges", crit="judging", kind="judge_invite", on=date(2024, 3, 1),
             url="https://www.lakesidehacks.example/judges", signals=["selective_event"])  # fmt: skip
    _exhibit(ws, "Example Weekly profile", crit="press", kind="press_article", on=date(2025, 5, 1),
             url="https://news.example/maya")  # fmt: skip
    _exhibit(
        ws,
        "Internal award",
        crit="awards",
        kind="award_certificate",
        on=date(2026, 1, 10),
        org="Example Systems Inc.",
    )
    _exhibit(ws, "Acme uses FastQueue", crit="original_contributions", kind="adoption_evidence", on=date(2026, 2, 1),
             org="Acme Robotics")  # fmt: skip
    _exhibit(ws, "My notes", crit="press", kind="press_article", on=date(2023, 1, 1), tier="self_reported")


def _themes(r):
    return {t.id: t for t in r.themes}


def test_themes_follow_their_rules_and_say_why(ws):
    _case(ws)
    r = merits.report(ws)
    t = _themes(r)
    assert t["independent_recognition"].status == "strong"
    assert t["independent_recognition"].why.startswith("2 of 3 letter writers are independent")
    assert (
        t["outside_employer"].status == "strong"
    )  # 3 outside: judging, press, Acme; the award is the employer's
    assert "3 counted exhibits from organizations other than Example Systems" in t["outside_employer"].why
    assert (
        "lakesidehacks.example" in t["outside_employer"].why
    )  # from the address when no organization is set
    assert t["multiple_years"].status == "strong" and "(2024, 2025, 2026)" in t["multiple_years"].why
    assert t["peer_context"].status == "building"  # one selectivity signal, no benchmark
    assert t["external_adoption"].status == "building" and "Acme Robotics" in t["external_adoption"].why
    assert all(x.rule.startswith("Strong:") for x in r.themes)  # the rule is shown with every status


def test_the_timeline_counts_only_counted_evidence(ws):
    _case(ws)
    r = merits.report(ws)
    assert [(y.year, y.count) for y in r.timeline] == [
        (2024, 1),
        (2025, 1),
        (2026, 2),
    ]  # self-reported 2023 left out
    assert r.first_year == 2024 and r.last_year == 2026 and r.gap_years == []
    _exhibit(ws, "Old paper", crit="scholarly_articles", kind="conference_paper", on=date(2020, 6, 1))
    assert merits.report(ws).gap_years == [2021, 2022, 2023]


def test_without_an_employer_outside_recognition_cannot_be_checked(ws):
    _exhibit(
        ws,
        "Judges page",
        crit="judging",
        kind="judge_invite",
        on=date(2025, 3, 1),
        url="https://hacks.example/j",
    )
    t = _themes(merits.report(ws))
    assert (
        t["outside_employer"].status == "missing" and "employer isn't recorded" in t["outside_employer"].why
    )


def test_setting_an_organization_moves_an_exhibit_inside_or_outside(ws):
    _case(ws)
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    acme = next(e for e in ws.exhibits().exhibits if e.title == "Acme uses FastQueue")
    c.post(f"/api/exhibits/{acme.id}/organization", headers=W, json={"organization": "Example Systems"})
    t = {x["id"]: x for x in c.get("/api/merits").json()["themes"]}
    assert t["external_adoption"]["status"] == "missing" and t["outside_employer"]["why"].startswith(
        "2 counted"
    )
    assert ws.changes()[-1].action == "evidence.organization"


class Canned:
    calls = 0

    def get(self, path, params=None):
        Canned.calls += 1
        works = [{"id": "https://openalex.org/W1", "display_name": "FastQueue: a paper", "publication_year": 2024,
                  "cited_by_count": 40, "citation_normalized_percentile": {"value": 0.92}},
                 {"id": "https://openalex.org/W2", "display_name": "No percentile", "publication_year": 2025,
                  "cited_by_count": 0, "citation_normalized_percentile": None}]  # fmt: skip
        return type("R", (), {"data": {"results": works}})()


def test_benchmarks_only_on_request_as_quoted_claims(ws):
    from areao1.core.models import SourceRecord
    from areao1.service import Service

    r = merits.report(ws)
    assert r.benchmarks == [] and r.openalex_authors == 0  # nothing fetched by looking; the page says add one
    src = ws.sources()
    src.sources.append(
        SourceRecord(id="openalex:A1", kind="openalex", handle="A1", url="https://openalex.org/A1")
    )
    ws.save_sources(src)
    assert merits.report(ws).openalex_authors == 1
    out = Service(ws).fetch_benchmarks(http=Canned())
    assert out == {"authors": 1, "benchmarks": 1}
    [b] = merits.report(ws).benchmarks
    assert (
        b.percentile == 92.0 and b.year == 2024 and b.work == "FastQueue: a paper" and b.review == "proposed"
    )
    claim = next(c for c in ws.memory.claims() if c.id == b.claim_id)
    assert '"citation_normalized_percentile": {"value": 0.92}' in claim.excerpt  # quotes the response
    assert _themes(merits.report(ws))["peer_context"].status == "strong"
    ws.memory.decide([b.claim_id], "rejected")
    assert (
        _themes(merits.report(ws))["peer_context"].status == "missing"
    )  # a rejected benchmark doesn't count


def test_the_standard_is_checked_against_the_vault(ws):
    from areao1.vault.store import Vault

    TestClient(create_app(ws, allowed_hosts=["testserver"])).put(
        "/api/profile", headers=W, json={"id": "eb1a"}
    )
    r = merits.report(ws, None)
    assert r.label == "Final merits" and {s.status for s in r.standard} == {"unverified"}
    vault = Vault(ws)
    vault.import_file("kazarian-v-uscis", (FIXTURES / "kazarian.pdf").read_bytes(), filename="kazarian.pdf")
    vault.import_file("uscis-pm-6-f-2", gzip.decompress((FIXTURES / "uscis-pm-eb1-extraordinary.html.gz").read_bytes()),
                      filename="pm.html")  # fmt: skip
    r = merits.report(ws, vault)
    assert [s.status for s in r.standard] == ["verified"] * len(r.standard), [
        (s.text, s.why) for s in r.standard
    ]
    assert all(s.link.startswith("https://") for s in r.standard)
    profile = ws.profile()
    profile.final_merits.standard[0].quote = "a sentence the Policy Manual does not contain anywhere at all"
    [first, *_] = merits.check_standard(profile, vault)
    assert first.status == "unverified" and "isn't in the current copy" in first.why


def test_no_score_and_no_verdict_in_the_view(ws):
    _case(ws)
    text = merits.report(ws).model_dump_json().lower()
    for word in ("probab", "likelihood", "chance of", "approvable", "you qualify", "eligible"):
        assert word not in text, word


def test_the_o1a_view_cites_the_o1_chapter(ws):
    from areao1.vault.store import Vault

    snap = next((Path(__file__).parents[1] / "community-vault" / "snapshots").glob("9c0e2d65*.html"))
    vault = Vault(ws)
    vault.import_file("uscis-pm-2-m-4", snap.read_bytes(), filename="o1.html")
    r = merits.report(ws, vault)
    assert r.profile == "o1a" and r.label == "The evidence as a whole"
    assert [s.status for s in r.standard] == ["verified", "verified"], [(s.text, s.why) for s in r.standard]
