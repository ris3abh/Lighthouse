"""rule-check gate (SPEC 5a): rule claims in agent answers, briefings and petition-facing text must match a
fresh vault chunk that entails them. The vault is filled from recorded fixtures; the judge model is mocked."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import anyio
import pytest
from agent_fakes import FakeEngine
from fastapi.testclient import TestClient
from test_vault import Pages, _at, public_dns  # noqa: F401  (fixture)

from areao1 import notify
from areao1.agent.runner import AgentRunner
from areao1.agent.tools import RunContext, build_tools
from areao1.core.models import AgentRun, RuleCitation, utcnow
from areao1.core.models import RuleCheck as RuleCheckModel
from areao1.core.workspace import WorkspaceError
from areao1.server.app import create_app
from areao1.service import Service
from areao1.vault import Vault
from areao1.vault.rulecheck import JudgeReply, RuleChecker, candidates, decide, engine_judge, refresh

W = {"X-AreaO1": "1"}
RULE = "EB-1A requires evidence of at least three of the ten criteria."
QUOTE = "at least three of the ten regulatory criteria"


class FakeJudge:
    """Reads the prompt like the real judge would. ``rules``: (sentence substring, excerpt phrase, verdict,
    source id or None). A phrase found in an offered excerpt (from that source) becomes cited evidence."""

    def __init__(self, rules=(), not_rules=(), fail: Exception | None = None, raw: str | None = None):
        self.rules, self.not_rules, self.fail, self.raw = list(rules), list(not_rules), fail, raw
        self.calls: list[str] = []

    async def __call__(self, system: str, prompt: str, model: str) -> JudgeReply:
        self.calls.append(prompt)
        if self.fail:
            raise self.fail
        if self.raw is not None:
            return JudgeReply(self.raw, {"input_tokens": 10, "output_tokens": 2}, 0.001)
        cands = re.findall(r'^(c\d+): "(.*)"  \(excerpts to compare: (.*)\)$', prompt, re.M)
        blocks = dict(re.findall(r"^\[(k\d+)\] Tier \d, ([^\n]*):\n", prompt, re.M))
        texts = dict(
            re.findall(r"^\[(k\d+)\] Tier \d, [^\n]*:\n(.*?)(?=\n\[k\d+\] Tier|\Z)", prompt, re.M | re.S)
        )
        claims = []
        for cid, sentence, keys in cands:
            if any(n in sentence for n in self.not_rules):
                claims.append({"candidate": cid, "is_rule": False})
                continue
            evidence = []
            for sub, phrase, verdict, source in self.rules:
                if sub not in sentence:
                    continue
                for key in [k.strip() for k in keys.split(",")]:
                    title = blocks.get(key, "")
                    if phrase in texts.get(key, "") and (source is None or source in title):
                        evidence.append({"chunk": key, "verdict": verdict, "quote": phrase})
                        break
            claims.append({"candidate": cid, "is_rule": True, "claim": sentence, "kind": "regulation",
                           "evidence": evidence})  # fmt: skip
        usage = {
            "input_tokens": 1200,
            "output_tokens": 80,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        return JudgeReply(json.dumps({"claims": claims}), usage, 0.004)


@pytest.fixture
def vault_ws(ws, http_mock, public_dns):  # noqa: F811
    pages = Pages(http_mock)
    pages.install()
    vault = Vault(ws)
    anyio.run(lambda: vault.sync())
    return ws


def _check(ws, text, judge):
    return anyio.run(lambda: RuleChecker(Vault(ws), judge, "judge-model").check(text))


class _Recorder:
    def __init__(self):
        self.sent = []

    def send(self, note, cfg, secret):
        self.sent.append(note)


# ----------------------------------------------------------------------------- the checker


def test_plain_answers_cost_nothing(vault_ws):
    judge = FakeJudge()
    check = _check(vault_ws, "Your ICML paper has 71 citations. Email Dr. Lee about the letter.", judge)
    assert check.claims == [] and check.note == "no rule statements" and judge.calls == []


def test_candidates_use_the_manifest_hints():
    hints = Vault.__new__(Vault)  # noqa: F841 - hints come from the manifest
    from areao1.vault import load_manifest

    found = candidates(
        "Intro.\n\n- The I-129 filing fee is $1,055.\n- Email Dr. Lee.\n" + RULE, load_manifest().rule_hints
    )
    assert [c.text for c in found] == ["The I-129 filing fee is $1,055.", RULE]


def test_verified_claim_cites_the_exact_words(vault_ws):
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6")])
    check = _check(vault_ws, f"Short answer: {RULE}", judge)
    [claim] = check.claims
    assert claim.status == "verified" and claim.reason == ""
    [cite] = claim.citations
    assert cite.source_id == "uscis-pm-6-f-2" and cite.tier == 1 and cite.quote == QUOTE
    assert Vault(vault_ws).snapshot_text(cite.sha256)[cite.start : cite.end] == QUOTE  # exact-quote check
    assert check.model == "judge-model" and check.cost_usd == 0.004 and check.blocking == []
    assert "Tier 1, USCIS Policy Manual, Volume 6" in judge.calls[0]


def test_a_quote_that_isnt_in_the_source_doesnt_count(vault_ws):
    judge = FakeJudge(raw=json.dumps({"claims": [{"candidate": "c1", "is_rule": True, "claim": RULE, "evidence": [
        {"chunk": "k1", "verdict": "entails", "quote": "the beneficiary must show ten of ten criteria"}]}]}))  # fmt: skip
    [claim] = _check(vault_ws, RULE, judge).claims
    assert (
        claim.status == "unverified"
        and claim.citations == []
        and claim.reason == "no vault source states this"
    )


def test_case_facts_are_not_rule_claims(vault_ws):
    judge = FakeJudge(not_rules=["Kazarian"])
    check = _check(vault_ws, "Your notes from Tuesday mention Kazarian twice.", judge)
    assert check.claims == [] and len(judge.calls) == 1


class SilentExtractor(FakeJudge):
    """A judge whose extraction returns nothing (first ``silent`` calls), then answers like FakeJudge."""

    def __init__(self, silent: int = 99, **kw):
        super().__init__(**kw)
        self.silent = silent
        self.systems: list[str] = []

    async def __call__(self, system, prompt, model):
        self.systems.append(system)
        if len(self.systems) <= self.silent:
            self.calls.append(prompt)
            return JudgeReply('{"claims": []}', {"input_tokens": 900, "output_tokens": 5}, 0.002)
        return await super().__call__(system, prompt, model)


BACKUP_TEXT = """Here's where things stand.
- Per 8 CFR 214.2(o)(3)(iii), the petition needs evidence.
- USCIS can take a while.
- The filing fee went up this year.
- File Form I-907 with the petition.
- You have 30 days to answer the RFE.
- You have 3 of 8 criteria banked so far.
- Email Dr. Lee on Friday about the draft."""


def test_backup_checks_regulated_sentences_even_when_extraction_returns_nothing(vault_ws):
    judge = SilentExtractor()
    check = _check(vault_ws, BACKUP_TEXT, judge)
    reasons = {c.sentence: c.reason for c in check.claims}
    assert list(reasons) == [
        "Per 8 CFR 214.2(o)(3)(iii), the petition needs evidence.",
        "USCIS can take a while.",
        "The filing fee went up this year.",
        "File Form I-907 with the petition.",
        "You have 30 days to answer the RFE.",
        "You have 3 of 8 criteria banked so far.",
    ]  # the plain sentences aren't claims; "30 days" isn't in the manifest's hints but is always checked
    assert all(c.status == "unverified" and c.citations == [] for c in check.claims)
    assert reasons["The filing fee went up this year."] == (
        "the checker gave no verdict; it mentions a fee, so it's always checked"
    )
    assert "a CFR section" in reasons["Per 8 CFR 214.2(o)(3)(iii), the petition needs evidence."]
    assert "a form number" in reasons["File Form I-907 with the petition."]
    assert "a day count" in reasons["You have 30 days to answer the RFE."]
    assert "a criteria count" in reasons["You have 3 of 8 criteria banked so far."]
    # The judge was asked twice: the retry names the missed sentences and says they must be treated as rules.
    assert len(judge.calls) == 2 and "Treat each one as a rule claim" in judge.systems[1]
    assert "Email Dr. Lee" not in judge.calls[1] and "30 days" in judge.calls[1]
    assert check.cost_usd == 0.004 and len(check.blocking) == 6


def test_backup_retry_can_verify_and_overrides_not_a_rule(vault_ws):
    # First pass: the extractor misses the sentence. Retry: it finds the quote and the claim is verified.
    judge = SilentExtractor(silent=1, rules=[("three of the ten", QUOTE, "entails", "Volume 6")])
    [claim] = _check(vault_ws, RULE, judge).claims
    assert claim.status == "verified" and len(judge.calls) == 2
    # A judge that calls a fee sentence "not a rule" is asked again; still no verdict -> unverified.
    judge = FakeJudge(not_rules=["fee"])
    [claim] = _check(vault_ws, "The I-140 fee is $715.", judge).claims
    assert claim.status == "unverified" and len(judge.calls) == 2


def test_backup_sentences_cant_enter_petition_text(vault_ws, http_mock):
    from areao1.vault.rulecheck import BACKUP, backup_reasons

    assert set(BACKUP) == {
        "a CFR section",
        "USCIS",
        "a fee",
        "a form number",
        "a day count",
        "a criteria count",
    }
    assert backup_reasons("An H-1B or O-1 visa holder") == []  # classifications aren't form numbers
    assert backup_reasons("Meets at least three criteria") == ["a criteria count"]
    assert backup_reasons("Premium processing takes fifteen business days") == ["a day count"]
    assert backup_reasons("See § 204.5 for details") == ["a CFR section"]

    # The extractor returns nothing, yet a day count in an evidence summary is still refused.
    http_mock.get("https://scholar.example/alex").respond(
        200, text="<html><body><p>Sparse gradient compression at scale. Cited by 71 papers.</p></body></html>",
        headers={"content-type": "text/html"})  # fmt: skip
    ctx, t = _tools(vault_ws, SilentExtractor())
    out = anyio.run(t["read_page"].handler, {"url": "https://scholar.example/alex"})
    obs = re.search(r'"observation_id": "(obs_[0-9a-f]+)"', out).group(1)
    crit = next(c for c in vault_ws.profile().criteria)
    base = {"criterion": crit.id, "evidence_type": crit.evidence_types[0], "title": "ICML paper",
            "observation_id": obs, "quote": "Cited by 71 papers."}  # fmt: skip
    with pytest.raises(ValueError, match="doesn't confirm"):
        anyio.run(
            t["propose_evidence"].handler,
            {**base, "summary": "Cited 71 times; RFE answers are due in 87 days."},
        )
    anyio.run(t["propose_evidence"].handler, {**base, "summary": "Cited 71 times at ICML."})


def test_tier1_disagreement_is_a_conflict(vault_ws):
    judge = FakeJudge(rules=[
        ("three of the ten", QUOTE, "entails", "Volume 6"),
        ("three of the ten", "A petitioner relying on evidence that is comparable", "contradicts", "Volume 2"),
    ])  # fmt: skip
    [claim] = _check(vault_ws, RULE, judge).claims
    assert claim.status == "conflict" and {c.verdict for c in claim.citations} == {"entails", "contradicts"}
    assert {c.source_id for c in claim.citations} == {"uscis-pm-6-f-2", "uscis-pm-2-m-4"}


FEE = "The Form I-129 filing fee for an O-1 petition is $1,055."
REG_QUOTE = "Petition for O Nonimmigrant Worker with 1 to 25 named beneficiaries: $1,055"
STALE_PAGE = ("<html><head><title>G-1055 Fee Schedule</title></head><body><main><h1>Fee schedule</h1>"
              + "<p>Form I-129, Petition for a Nonimmigrant Worker, O petitions: $1,000 filing fee. "
              "Fees are subject to change; check the current fee before you file.</p>" * 3
              + "</main></body></html>").encode()  # fmt: skip


@pytest.fixture
def fee_ws(ws, http_mock, public_dns):  # noqa: F811
    pages = Pages(http_mock)
    pages.page("uscis-g-1055", STALE_PAGE)  # the USCIS page lags behind the regulation
    pages.install()
    anyio.run(lambda: Vault(ws).sync())
    return ws


def test_the_fee_regulation_governs_over_the_uscis_fee_page(fee_ws):
    judge = FakeJudge(rules=[("$1,055", REG_QUOTE, "entails", "8 CFR 106.2"),
                             ("$1,055", "O petitions: $1,000 filing fee", "contradicts", "G-1055")])  # fmt: skip
    [claim] = _check(fee_ws, FEE, judge).claims
    assert "8 CFR 106.2" in judge.calls[0]  # the primary is always put in front of the judge
    by_source = {c.source_id: c for c in claim.citations}
    assert (
        by_source["ecfr-8cfr-106-2"].verdict == "entails"
        and by_source["ecfr-8cfr-106-2"].secondary_to is None
    )
    assert by_source["uscis-g-1055"].verdict == "contradicts"
    assert by_source["uscis-g-1055"].secondary_to == "ecfr-8cfr-106-2"
    assert (
        claim.status == "verified"
        and claim.reason == "a secondary page disagrees; the primary source governs"
    )
    assert refresh(RuleCheckModel(claims=[claim]), Vault(fee_ws)).claims[0].status == "verified"

    # The stale page alone can't verify a fee while the regulation is fresh in the vault.
    judge = FakeJudge(rules=[("$1,000", "O petitions: $1,000 filing fee", "entails", "G-1055")])
    [claim] = _check(fee_ws, "The Form I-129 filing fee for an O-1 petition is $1,000.", judge).claims
    assert [c.source_id for c in claim.citations] == ["uscis-g-1055"]
    assert claim.status == "unverified"
    assert (
        claim.reason
        == "only a secondary page says this; the primary source (ecfr-8cfr-106-2) doesn't confirm it"
    )
    assert refresh(RuleCheckModel(claims=[claim]), Vault(fee_ws)).claims[0].status == "unverified"


def _cite(source_id, verdict, secondary_to=None, tier=1, fresh=True):
    return RuleCitation(chunk_id="vc_x", source_id=source_id, title=source_id, tier=tier, url="https://x.gov",
                        quote="quoted words", start=0, end=12, sha256="0" * 64, checked_at=utcnow(),
                        verdict=verdict, fresh=fresh, secondary_to=secondary_to)  # fmt: skip


def test_decide_primary_and_secondary_sources():
    reg, page = "ecfr-8cfr-106-2", "uscis-g-1055"
    assert decide([_cite(reg, "entails"), _cite(page, "contradicts", reg)]) == (
        "verified", "a secondary page disagrees; the primary source governs")  # fmt: skip
    status, reason = decide([_cite(page, "entails", reg), _cite(reg, "contradicts")])
    assert status == "unverified" and reason == (
        "contradicted by a Tier 1 source (a secondary page agrees, but the primary source governs)"
    )
    # Secondary alone: verifies only while the primary isn't available fresh.
    assert decide([_cite(page, "entails", reg)], set())[0] == "verified"
    assert decide([_cite(page, "entails", reg)], {reg})[0] == "unverified"
    # Two independent Tier 1 primaries disagreeing is still a conflict.
    assert decide([_cite(reg, "entails"), _cite("uscis-pm-2-m-4", "contradicts")])[0] == "conflict"


def test_contradicted_by_tier1_alone_is_unverified(vault_ws):
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "contradicts", "Volume 6")])
    [claim] = _check(vault_ws, RULE, judge).claims
    assert claim.status == "unverified" and "contradicted" in claim.reason


def test_claims_go_stale_when_the_window_passes_or_the_source_changes(vault_ws, monkeypatch):
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6")])
    check = _check(vault_ws, RULE, judge)
    vault = Vault(vault_ws)
    assert refresh(check, vault).claims[0].status == "verified"
    _at(monkeypatch, timedelta(days=31))  # policy: 30 days
    stale = refresh(check, vault).claims[0]
    assert stale.status == "stale" and "re-check" in stale.reason and not stale.citations[0].fresh


def test_unavailable_judge_or_empty_vault_means_unverified(ws, vault_ws):
    for judge in (
        FakeJudge(fail=RuntimeError("not logged in")),
        FakeJudge(raw="Sorry, I can't help with that."),
    ):
        check = _check(vault_ws, RULE, judge)
        assert [c.status for c in check.claims] == ["unverified"] and "couldn't run" in check.note
    # A workspace whose vault was never synced can't verify anything.
    from areao1.scaffold import create_workspace

    empty = create_workspace(ws.root.parent / "empty", name="E", git=False)
    check = _check(empty, RULE, FakeJudge())
    assert check.claims[0].status == "unverified" and "vault sync" in check.note


def test_engine_judge_is_one_toolless_turn_and_reports_usage():
    engine = FakeEngine(
        [("usage", {"input_tokens": 900, "output_tokens": 40}), ("text", '{"claims": []}')], cost=0.002
    )
    reply = anyio.run(lambda: engine_judge(engine)("sys", "prompt", "gpt-6.1-sol"))
    req = engine.requests[0]
    assert (
        engine.tool_names == []
        and req.web_search is False
        and req.max_turns == 1
        and req.model == "gpt-6.1-sol"
    )
    assert (
        reply.text == '{"claims": []}'
        and reply.usage
        == {
            "input_tokens": 900,
            "output_tokens": 40,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        and reply.cost_usd == 0.002
    )


# ----------------------------------------------------------------------------- every answer


def test_every_answer_is_checked_and_the_judge_counts_toward_the_budget(vault_ws, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": rec})
    engine = FakeEngine(
        [("usage", {"input_tokens": 500, "output_tokens": 50}), ("text", f"{RULE} The fee is $9,999.")]
    )
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6")])

    async def go():
        runner = AgentRunner(vault_ws, engine=engine, judge=judge)
        run = await runner.start("chat", "what does EB-1A need?")
        events = [e async for e in runner.stream(run.id)]
        return await runner.wait(run.id), events

    run, events = anyio.run(go)
    statuses = {c.sentence: c.status for c in run.rule_check.claims}
    assert statuses == {RULE: "verified", "The fee is $9,999.": "unverified"}
    assert any(e["type"] == "rule_check" for e in events)
    assert run.usage.input_tokens == 500 + 1200 and run.cost_usd == pytest.approx(0.01 + 0.004)
    assert rec.sent == []  # no conflicts, no notification


def test_conflicts_in_answers_notify(vault_ws, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": rec})
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6"),
                             ("three of the ten", "A petitioner relying on evidence that is comparable", "contradicts", "Volume 2")])  # fmt: skip

    async def go():
        runner = AgentRunner(vault_ws, engine=FakeEngine([("text", RULE)]), judge=judge)
        return await runner.wait((await runner.start("manual", "x")).id)

    run = anyio.run(go)
    assert run.rule_check.claims[0].status == "conflict"
    [note] = rec.sent
    assert note.event == "vault" and note.title == "Official sources disagree" and f"run={run.id}" in note.url


# ----------------------------------------------------------------------------- petition-facing text


def _tools(ws, judge):
    run = AgentRun(kind="manual", engine="fake", model="t", prompt="p")
    ctx = RunContext(ws, run, checker=RuleChecker(Vault(ws), judge, "judge-model"))
    return ctx, {t.name: t for t in build_tools(ctx)}


def _propose_with_rules(vault_ws, http_mock):
    http_mock.get("https://scholar.example/alex").respond(
        200, text="<html><body><p>Sparse gradient compression at scale. Cited by 71 papers.</p></body></html>",
        headers={"content-type": "text/html"})  # fmt: skip
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6")])
    ctx, t = _tools(vault_ws, judge)
    out = anyio.run(t["read_page"].handler, {"url": "https://scholar.example/alex"})
    obs = re.search(r'"observation_id": "(obs_[0-9a-f]+)"', out).group(1)
    crit = next(c.id for c in vault_ws.profile().criteria)
    etype = next(c for c in vault_ws.profile().criteria if c.id == crit).evidence_types[0]
    base = {"criterion": crit, "evidence_type": etype, "title": "ICML paper", "observation_id": obs,
            "quote": "Cited by 71 papers."}  # fmt: skip

    with pytest.raises(ValueError, match="doesn't confirm"):
        anyio.run(
            t["propose_evidence"].handler, {**base, "summary": "Cited 71 times. The filing fee is $1,055."}
        )
    with pytest.raises(ValueError, match="doesn't confirm"):
        anyio.run(t["propose_letter_writer"].handler, {"name": "Dr. Ortiz", "relationship": "independent",
                                                       "credentials": "Regulations require five letters under 8 CFR 204.5."})  # fmt: skip
    letter = Service(vault_ws).add_letter(name="Dr. Lee", relationship="independent")
    with pytest.raises(ValueError, match="doesn't confirm"):
        anyio.run(t["propose_tracker_update"].handler, {"target_type": "letter", "target_id": letter.id,
                                                        "changes": {"credentials": "USCIS requires a PhD."}})  # fmt: skip
    assert not any(c.source.startswith("agent:") for c in vault_ws.pending_candidates())

    # Verified rule text goes through, and carries its check.
    out = anyio.run(t["propose_evidence"].handler, {**base, "summary": f"Cited 71 times. {RULE}"})
    cand = next(c for c in vault_ws.pending_candidates() if c.source.startswith("agent:"))
    assert "Proposed" in out and cand.rule_check.claims[0].status == "verified"
    return cand


def test_unverified_rules_cant_enter_exhibits_or_letters(vault_ws, http_mock):
    cand = _propose_with_rules(vault_ws, http_mock)
    assert cand.kind == "evidence"


def test_acceptance_rechecks_freshness_and_user_rewrites_are_theirs(vault_ws, monkeypatch, http_mock):
    cand = _propose_with_rules(vault_ws, http_mock)
    _at(monkeypatch, timedelta(days=31))  # the policy chapter it cites is now past its window
    with pytest.raises(WorkspaceError, match="doesn't confirm"):
        Service(vault_ws).accept_candidate(cand.id)
    Service(vault_ws).edit_candidate(
        cand.id, summary="Cited 71 times; I'll describe the standard in my own words."
    )
    assert next(c for c in vault_ws.inbox().candidates if c.id == cand.id).rule_check is None
    Service(vault_ws).accept_candidate(cand.id)
    assert any(e.title == "ICML paper" for e in vault_ws.exhibits().exhibits)


def test_briefing_rules_are_badged_not_blocked(vault_ws, monkeypatch):
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6")])
    ctx, t = _tools(vault_ws, judge)
    out = anyio.run(t["publish_briefing"].handler, {"changed": [RULE], "todos": [
        {"title": "Pay the $1,055 filing fee before Friday", "why": "Premium processing takes 15 business days."}]})  # fmt: skip
    assert "aren't confirmed" in out
    b = vault_ws.briefing()
    assert {c.status for c in b.rule_check.claims} == {"verified", "unverified"}
    c = TestClient(create_app(vault_ws, allowed_hosts=["testserver"], engine=FakeEngine()))
    shown = c.get("/api/briefing").json()["rule_check"]
    assert sorted(x["status"] for x in shown["claims"]) == ["unverified", "unverified", "verified"]


def test_recheck_endpoints(vault_ws, monkeypatch):
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6")])
    app = create_app(vault_ws, allowed_hosts=["testserver"], engine=FakeEngine([("text", RULE)]))
    app.state.runner._judge = judge
    c = TestClient(app)

    async def go():
        return await app.state.runner.wait((await app.state.runner.start("manual", "x")).id)

    run = anyio.run(go)
    _at(monkeypatch, timedelta(days=31))
    assert c.get(f"/api/agent/runs/{run.id}").json()["rule_check"]["claims"][0]["status"] == "stale"
    anyio.run(lambda: Vault(vault_ws).sync(ids=["uscis-pm-6-f-2"], force=True))  # refreshed by hand
    r = c.post(f"/api/rulecheck/runs/{run.id}", headers=W)
    assert r.status_code == 200 and r.json()["claims"][0]["status"] == "verified"
    assert c.post("/api/rulecheck/briefing", headers=W).status_code == 400  # no briefing yet


# ----------------------------------------------------------------------------- Tier 3 never verifies

WIKI_RULE = "O-1 petitions must include a $5,000 compliance bond."
WIKI_PAGE = ("<html><head><title>O-1 visa - Wikipedia</title></head><body><main><h1>O-1 visa</h1>"
             + "<p>Under the program, O-1 petitions must include a $5,000 compliance bond, refundable on departure. "
             "The visa is for individuals with extraordinary ability.</p>" * 3
             + "</main></body></html>").encode()  # fmt: skip


@pytest.fixture
def wiki_ws(ws, http_mock, public_dns):  # noqa: F811
    pages = Pages(http_mock)
    pages.page("wikipedia-o-1", WIKI_PAGE)  # only Wikipedia states this "rule"
    pages.install()
    anyio.run(lambda: Vault(ws).sync())
    return ws


def test_wikipedia_is_never_offered_to_the_judge_and_never_verifies(wiki_ws, http_mock):
    vault = Vault(wiki_ws)
    assert vault.manifest.source("wikipedia-o-1").tier == 3
    assert any(h.source_id == "wikipedia-o-1" for h in vault.search(WIKI_RULE, k=5))  # it's in the vault...
    judge = FakeJudge(rules=[("bond", "must include a $5,000 compliance bond", "entails", None)])
    [claim] = _check(wiki_ws, WIKI_RULE, judge).claims
    assert "Wikipedia" not in "".join(judge.calls) and "compliance bond, refundable" not in "".join(
        judge.calls
    )
    assert claim.status == "unverified" and claim.citations == []  # ...but never shown to the judge

    # Even a judge that cites the Wikipedia chunk directly (by its id) can't get it counted.
    wiki = next(h for h in vault.search(WIKI_RULE, k=5) if h.source_id == "wikipedia-o-1")
    raw = FakeJudge(raw=json.dumps({"claims": [{"candidate": "c1", "is_rule": True, "claim": WIKI_RULE, "evidence": [
        {"chunk": wiki.chunk_id, "verdict": "entails", "quote": "must include a $5,000 compliance bond"},
        {"chunk": "k99", "verdict": "entails", "quote": "must include a $5,000 compliance bond"}]}]}))  # fmt: skip
    [claim] = _check(wiki_ws, WIKI_RULE, raw).claims
    assert claim.status == "unverified" and claim.citations == []

    # And the gate refuses it in petition-facing text.
    http_mock.get("https://scholar.example/alex").respond(
        200, text="<html><body><p>Sparse gradient compression at scale. Cited by 71 papers.</p></body></html>",
        headers={"content-type": "text/html"})  # fmt: skip
    ctx, t = _tools(wiki_ws, judge)
    out = anyio.run(t["read_page"].handler, {"url": "https://scholar.example/alex"})
    obs = re.search(r'"observation_id": "(obs_[0-9a-f]+)"', out).group(1)
    crit = next(c for c in wiki_ws.profile().criteria)
    with pytest.raises(ValueError, match="doesn't confirm"):
        anyio.run(t["propose_evidence"].handler, {"criterion": crit.id, "evidence_type": crit.evidence_types[0],
                                                  "title": "ICML paper", "observation_id": obs,
                                                  "quote": "Cited by 71 papers.", "summary": f"Cited 71 times. {WIKI_RULE}"})  # fmt: skip


def test_decide_ignores_tier3_support_and_tier3_contradictions():
    assert decide([_cite("wikipedia-o-1", "entails", tier=3)]) == (
        "unverified",
        "only a secondary source says this",
    )
    assert (
        decide([_cite("wikipedia-o-1", "entails", tier=3), _cite("en-blog", "entails", tier=3)])[0]
        == "unverified"
    )
    # A Tier 3 page disagreeing with a Tier 1 source is not a conflict.
    assert decide([_cite("ecfr-8cfr-204-5-h", "entails"), _cite("wikipedia-eb-1", "contradicts", tier=3)]) == (
        "verified", "")  # fmt: skip
    # Stale Tier 3 support isn't "stale" (that would suggest a re-check could verify it).
    assert decide([_cite("wikipedia-o-1", "entails", tier=3, fresh=False)])[0] == "unverified"


def test_a_source_demoted_to_tier3_stops_verifying_on_refresh(vault_ws):
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "Volume 6")])
    check = _check(vault_ws, RULE, judge)
    assert check.claims[0].status == "verified"
    # The person moves the Policy Manual page to Tier 3 in their workspace manifest... (only possible by also
    # pointing it off the official domains: Tier 1/2 is tied to the domain lists).
    (vault_ws.root / "vault").mkdir(exist_ok=True)
    (vault_ws.root / "vault" / "sources.yaml").write_text(
        "version: 1\nsources:\n  - {id: uscis-pm-6-f-2, title: 'Policy Manual (mirror)', "
        "url: 'https://mirror.example/pm-6-f-2', tier: 3, kind: policy}\n"
    )
    again = refresh(check, Vault(vault_ws))
    assert again.claims[0].citations[0].tier == 3 and again.claims[0].status == "unverified"


def test_tier1_and_tier2_are_tied_to_official_domains(ws):
    from areao1.vault import load_manifest
    from areao1.vault.models import VaultManifest

    m = load_manifest()
    assert {s.id for s in m.sources if s.tier == 3} >= {"wikipedia-o-1", "wikipedia-eb-1"}
    assert m.tier_of("https://en.wikipedia.org/wiki/O-1_visa") is None
    assert all(m.tier_of(s.url) is not None and m.tier_of(s.url) <= s.tier for s in m.sources if s.tier < 3)
    data = m.model_dump()
    for sid, tier in (("wikipedia-o-1", 1), ("wikipedia-o-1", 2)):
        bad = {**data, "sources": [{**s, "tier": tier} if s["id"] == sid else s for s in data["sources"]]}
        with pytest.raises(ValueError, match="can only be Tier 3"):
            VaultManifest.model_validate(bad)
    # Tier 1 on a Tier 2 domain isn't allowed either (courtlistener can hold Tier 2, not Tier 1).
    bad = {**data, "sources": [*data["sources"], {"id": "cl", "title": "x", "url": "https://www.courtlistener.com/x",
                                                    "tier": 1, "kind": "case_law"}]}  # fmt: skip
    with pytest.raises(ValueError, match="Tier 1 needs an official domain"):
        VaultManifest.model_validate(bad)
    # A workspace override can't promote Wikipedia either.
    (ws.root / "vault").mkdir()
    (ws.root / "vault" / "sources.yaml").write_text(
        "version: 1\nsources:\n  - {id: wikipedia-o-1, title: 'O-1', url: 'https://en.wikipedia.org/wiki/O-1_visa', "
        "tier: 1, kind: secondary}\n"
    )
    with pytest.raises(ValueError, match="can only be Tier 3"):
        load_manifest(ws.root / "vault" / "sources.yaml")


def test_a_tier1_source_redirected_off_official_domains_isnt_stored(ws, http_mock, public_dns):  # noqa: F811
    pages = Pages(http_mock)
    pages.page("uscis-o1", b"", status=302)
    pages.install()
    http_mock.routes.clear()
    http_mock.get(url__regex=r"https://www\.uscis\.gov/working-in-the-united-states/temporary-workers/.*").respond(
        302, headers={"location": "https://en.wikipedia.org/wiki/O-1_visa"})  # fmt: skip
    http_mock.get("https://en.wikipedia.org/wiki/O-1_visa").respond(200, content=WIKI_PAGE,
                                                                     headers={"content-type": "text/html"})  # fmt: skip
    vault = Vault(ws)
    [r] = anyio.run(lambda: vault.sync(ids=["uscis-o1"]))
    assert r.status == "error" and "redirected off the official domains" in r.error
    assert vault.search(WIKI_RULE, k=5) == []
