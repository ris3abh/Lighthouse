"""rule-check (SPEC 5a, grounded-answer rule): every rule claim in agent-written text must match a fresh vault
chunk that entails it.

1. Sentences that may state a rule are picked out with the manifest's ``rule_hints`` (no model call when none
   match, so ordinary answers cost nothing extra). Sentences that mention a CFR section, USCIS, a fee, a form
   number, a day count or a criteria count (:data:`BACKUP`, in code, not configurable) are always checked:
   if the judge skips one or calls it "not a rule", it's asked again, and if it still gives no verdict the
   sentence is shown as unverified.
2. Each candidate is matched against the vault (Tier 1 and 2, hybrid search).
3. One judge call (the ``check`` model) decides which candidates are rule claims and, for each, which
   excerpts entail or contradict it, quoting the excerpt word for word.
4. Deterministic checks decide the status: the quote must appear in the excerpt; the excerpt must be the
   source's current snapshot and fresh; Tier 3 never verifies on its own.
   verified = a fresh Tier 1/2 excerpt entails it and no fresh Tier 1 excerpt contradicts it;
   conflict = Tier 1 sources disagree; stale = only stale excerpts support it; otherwise unverified.
   A secondary source (``secondary_to`` in the manifest, e.g. the USCIS fee page under the fee regulation)
   never outvotes its primary: when they disagree, the primary decides, and while the primary is fresh in the
   vault a secondary copy can't verify a claim on its own.

Statuses are re-evaluated whenever a check is shown or used (:func:`refresh`), so a claim goes stale when its
source changes or its freshness window passes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from lighthouse_gc.core.models import RuleCheck, RuleCitation, RuleClaim
from lighthouse_gc.engine.base import AgentEvent, Engine, EngineRequest
from lighthouse_gc.vault.models import VaultHit
from lighthouse_gc.vault.store import Vault

MAX_CANDIDATES = 12
CHUNKS_PER_CANDIDATE = 4
MAX_CHUNKS = 20

JUDGE_SYSTEM = """\
You check statements about immigration rules against excerpts from official sources. You answer with JSON only.

For each candidate sentence:
- Decide whether it states a rule: law, regulation, agency policy, a fee, a form or edition, a timeline,
  a standard of proof, or how criteria are applied. Facts about the person's own case, plans and advice are
  not rules.
- For a rule, restate it in one short sentence ("claim"), give its kind (fees, form, processing_times,
  visa_bulletin, regulation, statute, policy, case_law, other), and list the excerpts that explicitly state it
  ("entails") or explicitly say something incompatible ("contradicts"). For each, copy the supporting words
  from that excerpt exactly, character for character ("quote"). Don't cite an excerpt that is only related.

Return: {"claims": [{"candidate": "c1", "is_rule": true, "claim": "...", "kind": "fees",
"evidence": [{"chunk": "k2", "verdict": "entails", "quote": "..."}]}]}
Include every candidate exactly once."""


@dataclass
class JudgeReply:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None


Judge = Callable[[str, str, str], Awaitable[JudgeReply]]


def engine_judge(engine: Engine) -> Judge:
    """A judge that runs one tool-less, single-turn request on the agent engine (same lockdown as runs)."""

    async def judge(system: str, prompt: str, model: str) -> JudgeReply:
        usage: dict[str, int] = {}

        async def emit(ev: AgentEvent) -> None:
            if ev.type == "usage":
                for k, v in ev.data.items():
                    usage[k] = usage.get(k, 0) + int(v)

        request = EngineRequest(system_prompt=system, prompt=prompt, model=model, effort="low", web_search=False,
                                max_turns=1, max_budget_usd=0.5)  # fmt: skip
        result = await engine.run(request, [], emit)
        if result.is_error:
            raise RuntimeError(result.error or "judge failed")
        return JudgeReply(result.text, usage, result.cost_usd)

    return judge


# ----------------------------------------------------------------------------- candidates


@dataclass
class Candidate:
    id: str
    text: str
    start: int
    end: int
    backup: list[str] = field(default_factory=list)  # what makes it always-checked ("a fee", "a form number")


# Always checked, whatever the manifest's hints or the judge say. Names are shown in the badge's reason.
_N = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|thirty|sixty|ninety)"
BACKUP: dict[str, re.Pattern[str]] = {
    "a CFR section": re.compile(r"\b\d+\s*C\.?\s?F\.?\s?R\b|§\s*\d+\.\d+", re.I),
    "USCIS": re.compile(r"\bUSCIS\b"),
    "a fee": re.compile(r"\bfees?\b|\$\s?\d", re.I),
    "a form number": re.compile(r"\b[A-Z]{1,2}-\d{2,5}[A-Z]{0,2}\b"),
    "a day count": re.compile(rf"\b{_N}[- ](?:business |calendar )?days?\b", re.I),
    "a criteria count": re.compile(rf"\b{_N}\b[^.;\n]{{0,30}}\bcriteri(?:a|on)\b", re.I),
}
MAX_BACKUP = 30

RETRY_SYSTEM = (
    JUDGE_SYSTEM
    + """

Every candidate in this request mentions a regulated fact (a CFR section, USCIS, a fee, a form number, a day
count or a criteria count). Treat each one as a rule claim (is_rule true) and check it against the excerpts."""
)


_ABBREV = re.compile(
    r"(?:\b(?:v|No|Nos|Inc|Cir|Dec|Sec|seq|e\.g|i\.e|U\.S|C\.F\.R|U\.S\.C|Mr|Ms|Dr|St|al|etc|cf|Fed|Reg|Supp|App)|\b[A-Z])\.$"
)


def sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) of sentences and list items, ignoring code blocks; abbreviations don't end a sentence."""
    masked = re.sub(r"```.*?```", lambda m: " " * len(m.group(0)), text, flags=re.S)
    spans: list[tuple[int, int]] = []
    for line in re.finditer(r"[^\n]+", masked):
        start = line.start()
        body = line.group(0)
        lead = re.match(r"\s*(?:[-*+]\s+|\d+[.)]\s+|#+\s+|>\s*)?", body)
        offset = lead.end() if lead else 0
        cur = start + offset
        for m in re.finditer(r"[.!?][\"”')\]]*(?=\s+[A-Z(\[\"“$]|\s*$)", body):
            end = start + m.end()
            if _ABBREV.search(masked[cur:end]):
                continue
            if masked[cur:end].strip():
                spans.append((cur, end))
            cur = end
        if masked[cur : line.end()].strip():
            spans.append((cur, line.end()))
    return [(s + len(text[s:e]) - len(text[s:e].lstrip()), e) for s, e in spans if text[s:e].strip()]


def backup_reasons(sentence: str) -> list[str]:
    return [name for name, p in BACKUP.items() if p.search(sentence)]


def candidates(text: str, hints: list[str]) -> list[Candidate]:
    """Hint matches (up to MAX_CANDIDATES) plus every always-checked sentence (up to MAX_BACKUP)."""
    patterns = [re.compile(h, re.I) for h in hints]
    out: list[Candidate] = []
    hinted = backed = 0
    for s, e in sentences(text):
        sentence = text[s:e].strip()
        plain = re.sub(r"[*_`]", "", sentence)
        if len(plain) < 12:
            continue
        backup = backup_reasons(plain)
        hint = any(p.search(plain) for p in patterns)
        if backup and backed < MAX_BACKUP:
            backed += 1
        elif hint and hinted < MAX_CANDIDATES:
            hinted += 1
            backup = []
        else:
            continue
        out.append(Candidate(id=f"c{len(out) + 1}", text=plain, start=s, end=e, backup=backup))
    return out


# ----------------------------------------------------------------------------- verification


def find_quote(quote: str, text: str) -> tuple[int, int] | None:
    """Exact match first, then the same words with any whitespace between them."""
    quote = quote.strip().strip('"“”')
    if len(quote) < 8:
        return None
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    words = quote.split()
    m = re.search(r"\s+".join(re.escape(w) for w in words), text)
    return (m.start(), m.end()) if m else None


def decide(citations: list[RuleCitation], fresh_sources: set[str] | None = None) -> tuple[str, str]:
    """``fresh_sources``: ids of sources whose current snapshot is fresh (a secondary copy can't verify alone
    while its primary is one of them)."""
    fresh = [c for c in citations if c.fresh]
    entails = [c for c in fresh if c.verdict == "entails" and c.tier in (1, 2)]
    t1_yes = {c.source_id for c in fresh if c.verdict == "entails" and c.tier == 1}
    t1_no = {c.source_id for c in fresh if c.verdict == "contradicts" and c.tier == 1}
    primary_yes = {
        c.source_id for c in fresh if c.verdict == "entails" and c.tier == 1 and not c.secondary_to
    }
    primary_no = {
        c.source_id for c in fresh if c.verdict == "contradicts" and c.tier == 1 and not c.secondary_to
    }
    overruled = False
    if primary_yes or primary_no:  # a secondary copy never outvotes the primary source
        t1_yes, t1_no = primary_yes, primary_no
        want = "contradicts" if primary_yes else "entails"
        overruled = any(c.secondary_to and c.verdict == want for c in fresh)
    else:
        unconfirmed = [c for c in entails if c.secondary_to and c.secondary_to in (fresh_sources or set())]
        if unconfirmed and len(unconfirmed) == len(entails):
            return (
                "unverified",
                f"only a secondary page says this; the primary source ({unconfirmed[0].secondary_to}) doesn't confirm it",
            )
    if t1_yes and t1_no and (t1_yes - t1_no or t1_no - t1_yes):
        return "conflict", "Tier 1 sources disagree"
    if t1_no:
        return "unverified", "contradicted by a Tier 1 source" + (
            " (a secondary page agrees, but the primary source governs)" if overruled else ""
        )
    if entails:
        return "verified", "a secondary page disagrees; the primary source governs" if overruled else ""
    if any(c.verdict == "entails" and c.tier in (1, 2) for c in citations):
        return "stale", "its sources are past their freshness window or changed since; re-check"
    if any(c.verdict == "entails" for c in citations):
        return "unverified", "only a secondary source says this"
    return "unverified", "no vault source states this"


def refresh(check: RuleCheck | None, vault: Vault) -> RuleCheck | None:
    """Re-evaluate freshness (source changed or window passed) and the resulting statuses."""
    if check is None:
        return None
    state = vault.state()
    out = check.model_copy(deep=True)
    for claim in out.claims:
        if not claim.citations:
            continue
        for c in claim.citations:
            st = state.get(c.source_id) or {}
            src = vault.manifest.source(c.source_id)
            checked = st.get("checked_at")
            c.secondary_to = src.secondary_to if src else None
            # The tier comes from the manifest now, not from when it was checked: a source demoted to Tier 3
            # (or turned into an unreviewed finding) stops verifying.
            c.tier = 3 if src is None or src.finding else src.tier
            c.fresh = bool(
                src and checked and st.get("sha") == c.sha256 and vault.is_fresh(src, _dt(checked))
            )
        if claim.status != "unverified" or claim.reason != "rule-check couldn't run":
            claim.status, claim.reason = decide(claim.citations, fresh_ids(vault, state))  # type: ignore[assignment]
    return out


def fresh_ids(vault: Vault, state: dict[str, dict[str, Any]] | None = None) -> set[str]:
    state = vault.state() if state is None else state
    out = set()
    for s in vault.manifest.sources:
        checked = (state.get(s.id) or {}).get("checked_at")
        if checked and (state.get(s.id) or {}).get("sha") and vault.is_fresh(s, _dt(checked)):
            out.add(s.id)
    return out


def _dt(value: str) -> Any:
    from datetime import datetime

    return datetime.fromisoformat(value)


# ----------------------------------------------------------------------------- the checker


class RuleChecker:
    def __init__(self, vault: Vault, judge: Judge | None, model: str):
        self.vault = vault
        self.judge = judge
        self.model = model
        self.usage: dict[
            str, int
        ] = {}  # judge tokens spent through this checker (counted in the run's budget)
        self.cost_usd = 0.0

    async def check(self, text: str) -> RuleCheck:
        found = candidates(text, self.vault.manifest.rule_hints)
        if not found:
            return RuleCheck(model=None, note="no rule statements")
        chunks: dict[str, VaultHit] = {}
        per: dict[str, list[str]] = {}
        for cand in found:
            per[cand.id] = []
            for hit in self._with_primaries(cand.text, _diverse(
                self.vault.search(cand.text, k=CHUNKS_PER_CANDIDATE * 4, tiers={1, 2}, findings=False)
            ) + self._by_amount(cand.text)):  # fmt: skip
                key = next((k for k, h in chunks.items() if h.chunk_id == hit.chunk_id), None)
                if key is None and len(chunks) < MAX_CHUNKS:
                    key = f"k{len(chunks) + 1}"
                    chunks[key] = hit
                if key and key not in per[cand.id]:
                    per[cand.id].append(key)
        if not chunks:
            return self._unchecked(found, "the knowledge vault is empty; run `lighthouse-gc vault sync`")
        if self.judge is None:
            return self._unchecked(found, "rule-check couldn't run: no judge configured")
        cost = 0.0
        try:
            verdicts, spent = await self._ask(JUDGE_SYSTEM, found, per, chunks)
            cost += spent
            # Backup: always-checked sentences the judge skipped or called "not a rule" are asked about again.
            answered = {str(v.get("candidate")) for v in verdicts if v.get("is_rule")}
            missed = [c for c in found if c.backup and c.id not in answered]
            if missed:
                again, spent = await self._ask(RETRY_SYSTEM, missed, per, chunks)
                cost += spent
                retried = {c.id for c in missed}
                verdicts = [v for v in verdicts if str(v.get("candidate")) not in retried]
                verdicts += [{**v, "is_rule": True} for v in again if str(v.get("candidate")) in retried]
        except Exception as exc:  # judge unavailable or unparseable: nothing is verified
            return self._unchecked(found, f"rule-check couldn't run: {type(exc).__name__}: {exc}"[:300])
        claims = []
        fresh = fresh_ids(self.vault)
        by_id = {c.id: c for c in found}
        judged = set()
        for v in verdicts:
            match = by_id.get(str(v.get("candidate")))
            if match is None or not v.get("is_rule") or match.id in judged:
                continue
            judged.add(match.id)
            citations = []
            for ev in v.get("evidence") or []:
                excerpt = chunks.get(str(ev.get("chunk")))
                verdict = ev.get("verdict")
                if (
                    excerpt is None
                    or verdict not in ("entails", "contradicts")
                    or str(ev.get("chunk")) not in per[match.id]
                ):
                    continue
                span = find_quote(str(ev.get("quote", "")), excerpt.text)
                if span is None:
                    continue  # the exact-quote check failed: the judge's citation doesn't count
                citations.append(RuleCitation(chunk_id=excerpt.chunk_id, source_id=excerpt.source_id, title=excerpt.title,
                                              tier=excerpt.tier, url=excerpt.url, quote=excerpt.text[span[0]:span[1]],
                                              start=excerpt.start + span[0], end=excerpt.start + span[1],
                                              sha256=excerpt.sha256, checked_at=excerpt.checked_at, verdict=verdict,
                                              fresh=excerpt.fresh, secondary_to=self._secondary_to(excerpt.source_id)))  # fmt: skip
            status, reason = decide(citations, fresh)
            claims.append(
                RuleClaim(
                    text=str(v.get("claim") or match.text)[:400],
                    sentence=match.text[:600],
                    start=match.start,
                    end=match.end,
                    kind=str(v.get("kind") or "other")[:40],
                    status=status,
                    reason=reason,
                    citations=citations,
                )
            )  # type: ignore[arg-type]
        for c in found:
            if c.backup and c.id not in judged:
                claims.append(RuleClaim(text=c.text[:400], sentence=c.text[:600], start=c.start, end=c.end,
                                        status="unverified", reason=f"the checker gave no verdict; it mentions "
                                        f"{' and '.join(c.backup[:2])}, so it's always checked"))  # fmt: skip
        claims.sort(key=lambda c: c.start)
        return RuleCheck(model=self.model, claims=claims, cost_usd=round(cost, 6),
                         note=None if claims else "no rule statements")  # fmt: skip

    async def _ask(self, system: str, found: list[Candidate], per: dict[str, list[str]],
                   chunks: dict[str, VaultHit]) -> tuple[list[dict[str, Any]], float]:  # fmt: skip
        reply = await self.judge(system, _prompt(found, per, chunks), self.model)  # type: ignore[misc]
        for k, n in reply.usage.items():
            self.usage[k] = self.usage.get(k, 0) + n
        self.cost_usd += reply.cost_usd or 0.0
        return _parse(reply.text), reply.cost_usd or 0.0

    def _secondary_to(self, source_id: str) -> str | None:
        src = self.vault.manifest.source(source_id)
        return src.secondary_to if src else None

    def _by_amount(self, sentence: str) -> list[VaultHit]:
        """The best paragraph stating each dollar amount in the sentence: a fee claim stands or falls on the
        paragraph with that figure, which plain relevance can rank below many paragraphs about fees."""
        out: list[VaultHit] = []
        for amount in dict.fromkeys(re.findall(r"\$\s?\d[\d,]*(?:\.\d+)?", sentence)):
            figure = amount.lstrip("$ ").rstrip(".,")
            out += [
                h for h in self.vault.search(figure, k=3, tiers={1, 2}, findings=False) if figure in h.text
            ][:1]
        return out

    def _with_primaries(self, query: str, hits: list[VaultHit]) -> list[VaultHit]:
        """When a secondary copy (e.g. the USCIS fee page) is among the excerpts, add the best excerpt of its
        primary source (the fee regulation) so the judge can compare them."""
        have = {h.source_id for h in hits}
        out = list(hits)
        for h in hits:
            src = self.vault.manifest.source(h.source_id)
            primary = src.secondary_to if src else None
            if primary and primary not in have:
                out += self.vault.search(query, k=1, sources={primary}, findings=False)
                have.add(primary)
        return out

    def _unchecked(self, found: list[Candidate], why: str) -> RuleCheck:
        return RuleCheck(model=None, note=why, claims=[
            RuleClaim(text=c.text[:400], sentence=c.text[:600], start=c.start, end=c.end, status="unverified",
                      reason="rule-check couldn't run") for c in found])  # fmt: skip


def _diverse(hits: list[VaultHit], per_source: int = 2) -> list[VaultHit]:
    """Best hits, at most two per source, so the judge sees the regulation and the policy, not four
    paragraphs of one page."""
    seen: dict[str, int] = {}
    out = []
    for h in hits:
        if seen.get(h.source_id, 0) < per_source:
            seen[h.source_id] = seen.get(h.source_id, 0) + 1
            out.append(h)
        if len(out) == CHUNKS_PER_CANDIDATE:
            break
    return out


def _prompt(found: list[Candidate], per: dict[str, list[str]], chunks: dict[str, VaultHit]) -> str:
    lines = ["Candidate sentences:"]
    for c in found:
        lines.append(f'{c.id}: "{c.text}"  (excerpts to compare: {", ".join(per[c.id]) or "none"})')
    lines.append("\nExcerpts:")
    for key, h in chunks.items():
        lines.append(f"[{key}] Tier {h.tier}, {h.title}:\n{h.text}\n")
    return "\n".join(lines)


def notify_conflicts(ws: Any, check: RuleCheck | None, page: str) -> None:
    """Tier 1 sources disagreeing is worth a notification (once per claim and set of sources)."""
    if check is None:
        return
    from lighthouse_gc.notify import Notification, send

    for c in check.claims:
        if c.status != "conflict":
            continue
        sources = sorted({x.source_id for x in c.citations})
        lines = [f'· {x.title} ({x.verdict}): "{x.quote[:160]}"\n  {x.url}' for x in c.citations]
        port = ws.config().server.port
        send(ws, Notification("vault", "Official sources disagree", f"{c.text}\n" + "\n".join(lines),
                              url=f"http://127.0.0.1:{port}/#/{page}", priority="high",
                              minimal_body="Two official sources disagree on a rule. Check the Knowledge page.",
                              key="conflict:" + c.text[:80] + ":" + ",".join(sources)))  # fmt: skip


def blocking_message(check: RuleCheck) -> str:
    items = "; ".join(f'"{c.sentence[:140]}" ({c.status}: {c.reason})' for c in check.blocking[:4])
    return (f"This text states rules the knowledge vault doesn't confirm: {items}. Rule statements in "
            "petition-facing text must cite a fresh official source. Leave the rule out, or rephrase it to match "
            "the source exactly.")  # fmt: skip


def briefing_text(changed: list[str], todos: list[Any]) -> str:
    lines = [c.rstrip(".") + "." for c in changed]
    for t in todos:
        title = t.title if hasattr(t, "title") else t.get("title", "")
        why = t.why if hasattr(t, "why") else t.get("why", "")
        lines.append(title.rstrip(".") + "." + (f" {why.rstrip('.')}." if why else ""))
    return "\n".join(lines)


def _parse(text: str) -> list[dict[str, Any]]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("the judge didn't return JSON")
    data = json.loads(text[start : end + 1])
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        raise ValueError("the judge's JSON has no claims list")
    return [c for c in claims if isinstance(c, dict)]
