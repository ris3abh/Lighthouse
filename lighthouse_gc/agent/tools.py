"""The agent's tools (ADR 0005 §3): read freely, read the web through a guarded snapshotting fetch, and write
only by proposing to the Inbox through the service layer."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from lighthouse_gc import __version__
from lighthouse_gc.agent.redact import redact
from lighthouse_gc.core.models import (
    AgentRun,
    Candidate,
    ClaimDraft,
    Deadline,
    Evidence,
    PipelineItem,
    RunSource,
)
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.criteria.models import Letter
from lighthouse_gc.engine.base import AgentTool
from lighthouse_gc.mcp import tools as read
from lighthouse_gc.service import Service

MAX_PAGE_BYTES = 2_000_000
MAX_RESULT_CHARS = 20_000
MAX_REDIRECTS = 3


@dataclass
class RunContext:
    ws: Case
    run: AgentRun
    redact: bool = True
    svc: Service = field(init=False)

    def __post_init__(self) -> None:
        self.svc = Service(self.ws, actor=f"agent:{self.run.id}")

    def out(self, value: Any) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        if self.redact:
            text = redact(text)
        return text[:MAX_RESULT_CHARS] + ("…[truncated]" if len(text) > MAX_RESULT_CHARS else "")


# ----------------------------------------------------------------------------- web


class UnsafeURL(ValueError):
    pass


def check_url(url: str) -> None:
    """Only public http(s) hosts: a page the agent reads must not be able to point it at this machine or the LAN."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURL("only http(s) URLs can be read")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURL(f"can't resolve {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL(f"refusing to read {parsed.hostname}: it resolves to a private or local address")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"}
    BLOCK = {
        "p",
        "div",
        "br",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "section",
        "article",
        "blockquote",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    p = _Text()
    p.feed(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return " ".join(p.title.split()), text


async def fetch_page(url: str, client: httpx.AsyncClient | None = None) -> tuple[str, str, str]:
    """(final url, title, text). Follows up to 3 redirects, re-checking each hop."""
    own = client is None
    client = client or httpx.AsyncClient(
        timeout=15.0, headers={"User-Agent": f"lighthouse-gc/{__version__} (agent)"}
    )
    try:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url)
            resp = await client.get(url, follow_redirects=False)
            if resp.is_redirect and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                continue
            if resp.status_code >= 400:
                raise ValueError(f"HTTP {resp.status_code} from {url}")
            if len(resp.content) > MAX_PAGE_BYTES:
                raise ValueError("page is larger than 2 MB")
            ctype = resp.headers.get("content-type", "")
            if "html" in ctype:
                title, text = html_to_text(resp.text)
            elif ctype.startswith("text/") or "json" in ctype:
                title, text = "", resp.text
            else:
                raise ValueError(f"can't read {ctype or 'unknown content type'} (only HTML and text)")
            return url, title, text
        raise ValueError("too many redirects")
    finally:
        if own:
            await client.aclose()


# ----------------------------------------------------------------------------- tool schemas

S = dict[str, Any]


def _obj(props: S, required: list[str]) -> S:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


STR: S = {"type": "string"}
DATE: S = {"type": "string", "description": "YYYY-MM-DD"}


def build_tools(ctx: RunContext, http: httpx.AsyncClient | None = None) -> list[AgentTool]:
    ws = ctx.ws

    async def t_scoreboard(args: S) -> str:
        return ctx.out(read.get_scoreboard(ws))

    async def t_gaps(args: S) -> str:
        return ctx.out(read.list_gaps(ws))

    async def t_claims(args: S) -> str:
        return ctx.out(read.query_claims(ws, args["entity"], args.get("as_of")))

    async def t_provenance(args: S) -> str:
        return ctx.out(read.get_provenance(ws, args["claim_id"]))

    async def t_changed(args: S) -> str:
        return ctx.out(read.what_changed(ws, args["since"]))

    async def t_profile(args: S) -> str:
        p = ws.profile()
        return ctx.out({"id": p.id, "name": p.name, "threshold": p.threshold, "criteria": [
            {"id": c.id, "label": c.label, "evidence_types": c.evidence_types,
             "strength_signals": [s.id for s in c.strength_signals]} for c in p.criteria]})  # fmt: skip

    async def t_inbox(args: S) -> str:
        return ctx.out([{"id": c.id, "kind": c.kind, "title": c.title, "criterion": c.proposed_criterion,
                         "source": c.source, "summary": c.summary[:200]} for c in ws.pending_candidates()])  # fmt: skip

    async def t_deadlines(args: S) -> str:
        return ctx.out([d.model_dump(mode="json") for d in ws.deadlines().deadlines if not d.done])

    async def t_pipeline(args: S) -> str:
        return ctx.out([p.model_dump(mode="json", exclude={"created_at"}) for p in ws.pipeline().items])

    async def t_letters(args: S) -> str:
        return ctx.out([lt.model_dump(mode="json") for lt in ws.letters().letters])

    async def t_read_page(args: S) -> str:
        url, title, text = await fetch_page(args["url"], http)
        obs = ws.memory.snapshot(
            Evidence(connector="agent", source_url=url, payload=text, media_type="text/plain")
        )
        ctx.run.sources.append(RunSource(url=url, title=title, observation_id=obs.id))
        return ctx.out({"observation_id": obs.id, "url": url, "title": title, "text": text})

    def _page(obs_id: str, quote: str) -> tuple[Any, str]:
        obs = ws.memory.observation(obs_id)
        if obs is None or obs.connector != "agent":
            raise ValueError(
                f"unknown observation {obs_id!r}: call read_page first and cite its observation_id"
            )
        text = ws.memory.snapshot_text(obs)
        if not quote.strip() or quote not in text:
            raise ValueError("the quote must appear word for word in the page you read; copy it exactly")
        return obs, text

    def _propose(cand: Candidate) -> str:
        added = ctx.svc.propose_candidate(cand)
        if added is None:
            return "Already in the Inbox or already decided; nothing new was proposed."
        ctx.run.proposals.append(added.id)
        return f"Proposed to the Inbox as {added.id}. The user decides whether to accept it."

    async def t_propose_evidence(args: S) -> str:
        crit = ws.profile().criterion(args["criterion"])
        if crit is None:
            raise ValueError(f"unknown criterion {args['criterion']!r}; see get_profile")
        if args["evidence_type"] not in crit.evidence_types:
            raise ValueError(f"evidence_type must be one of {crit.evidence_types} for {crit.id}")
        obs, text = _page(args["observation_id"], args["quote"])
        key = hashlib.sha256(f"{obs.source_url}\n{args['quote']}".encode()).hexdigest()[:16]
        evidence = Evidence(connector="agent", source_url=obs.source_url, payload=text, media_type="text/plain",
                            claims=[ClaimDraft(subject=f"page:{obs.sha256[:16]}", subject_kind="other",
                                               subject_name=args["title"][:80], subject_url=obs.source_url,
                                               predicate="supports_criterion", value=crit.id,
                                               excerpt=args["quote"], stage=args.get("stage"),
                                               valid_from=date.today(), confidence="medium")])  # fmt: skip
        cand = Candidate(kind="evidence", fingerprint=f"agent:{crit.id}:{key}", source=f"agent:{ctx.run.id}",
                         evidence_type=args["evidence_type"], proposed_criterion=crit.id, title=args["title"][:120],
                         summary=args["summary"][:500], confidence=0.5, raw_url=obs.source_url,
                         stage=args.get("stage"))  # fmt: skip
        return _propose(cand.with_evidence(evidence))

    async def t_propose_deadline(args: S) -> str:
        proposal = {"title": args["title"], "due": args["due"], "kind": args.get("kind", "other"),
                    "url": args.get("url"), "human_only": True}  # fmt: skip
        Deadline.model_validate(proposal)
        cand = Candidate(kind="deadline", fingerprint=f"agent:deadline:{args['title'].lower()}:{args['due']}",
                         source=f"agent:{ctx.run.id}", evidence_type="agent_suggestion", proposed_criterion="",
                         title=args["title"][:120], summary=args.get("why", "")[:500] or "Suggested by the agent.",
                         raw_url=args.get("url"), proposal=proposal)  # fmt: skip
        return _propose(cand)

    async def t_propose_pipeline(args: S) -> str:
        proposal = {
            k: args[k] for k in ("title", "stage", "criterion", "url", "notes", "follow_up") if args.get(k)
        }
        PipelineItem.model_validate(proposal)
        cand = Candidate(kind="pipeline", fingerprint=f"agent:pipeline:{args['title'].lower()}",
                         source=f"agent:{ctx.run.id}", evidence_type="agent_suggestion", proposed_criterion="",
                         title=args["title"][:120], summary=args.get("why", "")[:500] or "Suggested by the agent.",
                         raw_url=args.get("url"), proposal=proposal)  # fmt: skip
        return _propose(cand)

    async def t_propose_letter(args: S) -> str:
        proposal = {k: args[k] for k in ("name", "relationship", "credentials", "criteria") if args.get(k)}
        Letter.model_validate(proposal)
        cand = Candidate(kind="letter", fingerprint=f"agent:letter:{args['name'].lower()}",
                         source=f"agent:{ctx.run.id}", evidence_type="agent_suggestion", proposed_criterion="",
                         title=f"Letter writer: {args['name']}", summary=args.get("why", "")[:500] or "Suggested by the agent.",
                         proposal=proposal)  # fmt: skip
        return _propose(cand)

    criteria = [c.id for c in ws.profile().criteria]
    return [
        AgentTool("get_scoreboard", "Current criteria scoreboard (banked / building / gap / dropped).", _obj({}, []), t_scoreboard),
        AgentTool("list_gaps", "Criteria not yet banked: what's missing, what's in progress, what's in the Inbox.", _obj({}, []), t_gaps),
        AgentTool("get_profile", "The active profile's criteria, accepted evidence types and strength signals.", _obj({}, []), t_profile),
        AgentTool("query_claims", "Claims about an entity (id or name fragment), optionally as of a date.",
                  _obj({"entity": STR, "as_of": DATE}, ["entity"]), t_claims),
        AgentTool("get_provenance", "Full provenance of one claim: source snapshot, verified quote, reviews.",
                  _obj({"claim_id": STR}, ["claim_id"]), t_provenance),
        AgentTool("what_changed", "Claims, reviews, exhibits, candidates and metric moves since a date.",
                  _obj({"since": DATE}, ["since"]), t_changed),
        AgentTool("list_inbox", "Pending Inbox candidates.", _obj({}, []), t_inbox),
        AgentTool("list_deadlines", "Open deadlines.", _obj({}, []), t_deadlines),
        AgentTool("list_pipeline", "Pipeline items with stage and follow-up dates.", _obj({}, []), t_pipeline),
        AgentTool("list_letters", "Recommendation letter writers and their status.", _obj({}, []), t_letters),
        AgentTool("read_page", "Fetch a public web page as text and save a snapshot. Returns an observation_id you "
                  "must cite when proposing evidence from it.", _obj({"url": STR}, ["url"]), t_read_page),
        AgentTool("propose_evidence", "Propose evidence for a criterion. Requires an observation_id from read_page and "
                  "a quote copied word for word from that page. Goes to the Inbox for the user to decide.",
                  _obj({"criterion": {"type": "string", "enum": criteria}, "evidence_type": STR, "title": STR,
                        "summary": STR, "observation_id": STR, "quote": STR,
                        "stage": {"type": "string", "enum": ["invited", "accepted", "completed", "declined",
                                                             "preprint", "submitted", "published", "applied",
                                                             "granted"]}},
                       ["criterion", "evidence_type", "title", "summary", "observation_id", "quote"]),
                  t_propose_evidence, read_only=False),
        AgentTool("propose_deadline", "Propose a deadline (goes to the Inbox).",
                  _obj({"title": STR, "due": DATE, "kind": {"type": "string", "enum": ["application", "submission",
                        "filing", "follow_up", "personal", "other"]}, "url": STR, "why": STR}, ["title", "due"]),
                  t_propose_deadline, read_only=False),
        AgentTool("propose_pipeline_item", "Propose a pipeline item, e.g. an opportunity to apply to (goes to the Inbox).",
                  _obj({"title": STR, "stage": {"type": "string", "enum": ["idea", "applied", "waiting", "done"]},
                        "criterion": {"type": "string", "enum": criteria}, "url": STR, "notes": STR,
                        "follow_up": DATE, "why": STR}, ["title"]),
                  t_propose_pipeline, read_only=False),
        AgentTool("propose_letter_writer", "Propose a recommendation letter writer (goes to the Inbox).",
                  _obj({"name": STR, "relationship": {"type": "string", "enum": ["independent", "employer", "coauthor"]},
                        "credentials": STR, "criteria": {"type": "array", "items": {"type": "string", "enum": criteria}},
                        "why": STR}, ["name", "relationship"]),
                  t_propose_letter, read_only=False),
    ]  # fmt: skip
