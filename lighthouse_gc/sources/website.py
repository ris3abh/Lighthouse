"""Website connector: any public page (or a sitemap of them), read readability-style through the same guard as
the agent's page reader: public hosts only (re-checked on every redirect), no private or local addresses.

Bot-protection pages, login walls, maintenance pages and JavaScript-only pages are marked *unreadable* on the
item instead of being stored as content; save the page from your browser and drop it on the Evidence page.

A page that mentions you is proposed for the Inbox: as an award notice when it says you won something, otherwise
as published material about you (press). The proposal quotes the sentences that mention you.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any
from urllib.parse import urlparse, urlunparse

import anyio
import httpx

from lighthouse_gc import web
from lighthouse_gc.core import clock
from lighthouse_gc.core.models import Candidate, ClaimDraft, ConnectorConfig, Evidence, MetricRow, TrackedItem
from lighthouse_gc.core.text import plural
from lighthouse_gc.sources.http import HttpClient, SourceError

API = ""
HEADERS: dict[str, str] = {}
MAX_PAGES = 25
MAX_QUOTES = 3

_URL_RE = re.compile(r"^https?://[^\s/]+[^\s]*$", re.I)
_AWARD = re.compile(
    r"\b(?:won|wins|winner|winners|awarded|recipient|recipients|honou?red with|received the)\b", re.I
)
_AWARD_NOUN = re.compile(r"\b(?:award|prize|medal|fellowship|grant|honou?r)\b", re.I)


def normalize(url: str) -> str:
    p = urlparse(url.strip())
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path or "/", "", p.query, ""))


class WebsiteSource:
    kind = "website"

    def __init__(self, http: HttpClient | None = None, config: ConnectorConfig | None = None,
                 today: Callable[[], date] = clock.today, names: list[str] | None = None,
                 client: httpx.AsyncClient | None = None):  # fmt: skip
        self.config = config or ConnectorConfig()
        self.today = today
        self.names = [n for n in (names or []) if len(n.strip()) >= 3]
        self.client = client  # tests pass a client; otherwise one per fetch
        self._pages: dict[str, web.Article | str] = {}

    # -- input -------------------------------------------------------------------------------

    @classmethod
    def detect(cls, url_or_handle: str) -> bool:
        return bool(_URL_RE.match(url_or_handle.strip()))

    @staticmethod
    def parse(url_or_handle: str) -> str:
        text = url_or_handle.strip()
        if not _URL_RE.match(text):
            raise ValueError(f"not an http(s) URL: {text!r}")
        return normalize(text)

    def source_url(self, handle: str) -> str:
        return handle

    @staticmethod
    def is_sitemap(url: str) -> bool:
        return urlparse(url).path.lower().endswith(("sitemap.xml", "sitemap_index.xml"))

    # -- fetching -------------------------------------------------------------------------------

    def _run(self, fn: Callable[[httpx.AsyncClient], Any]) -> Any:
        async def go() -> Any:
            if self.client is not None:
                return await fn(self.client)
            async with httpx.AsyncClient(
                timeout=20.0, headers={"User-Agent": web.user_agent("website connector")}
            ) as c:
                return await fn(c)

        return anyio.run(go)

    def read(self, url: str, *, strict: bool = False) -> web.Article | str:
        """The page's article, or why it's unreadable. Private / local addresses always raise; with ``strict``
        (a single page being added) other failures like HTTP 404 raise too, so a typo never becomes a source."""
        if url not in self._pages:
            try:
                self._pages[url] = self._run(lambda c: web.fetch_article(url, c))
            except web.UnsafeURL as exc:
                raise SourceError(f"website: {exc}") from exc
            except web.Unreadable as exc:
                reason = str(exc).removeprefix(url).strip()  # "can't be read automatically: HTTP 403"
                self._pages[url] = reason or "can't be read automatically"
            except (ValueError, httpx.HTTPError) as exc:
                if strict:
                    raise SourceError(f"website: {exc}") from exc
                self._pages[url] = f"{type(exc).__name__}: {exc}"[:300]
        return self._pages[url]

    # -- the Source interface -----------------------------------------------------------------

    def discover(self, handle: str, creds: str | None) -> list[TrackedItem]:
        if self.is_sitemap(handle):
            try:
                page = self._run(lambda c: web.get(handle, c))
                urls = web.sitemap_urls(page.text, handle, MAX_PAGES)
            except web.UnsafeURL as exc:
                raise SourceError(f"website: {exc}") from exc
            except (ValueError, httpx.HTTPError) as exc:
                raise SourceError(f"website: couldn't read the sitemap: {exc}") from exc
        else:
            urls = [handle]
        items = []
        for url in urls:
            got = self.read(url, strict=len(urls) == 1)
            items.append(TrackedItem(id=f"{self.kind}:{url}", kind="page", name=url, url=url,
                                     title=(got.title if isinstance(got, web.Article) else "")[:200] or url,
                                     unreadable=got if isinstance(got, str) else None))  # fmt: skip
        return items

    def snapshot(self, item: TrackedItem, creds: str | None) -> list[MetricRow]:
        return []  # pages have no numbers to track

    def candidates(self, item: TrackedItem, creds: str | None) -> list[Candidate]:
        got = self.read(item.url)
        if isinstance(got, str):
            return []  # unreadable: marked on the item
        quotes = self.mentions(got.text)
        if not quotes:
            return []
        host = urlparse(got.url).hostname or ""
        where = got.site_name or host
        award = any(_AWARD.search(q) and _AWARD_NOUN.search(q) for q in quotes)
        about = bool(self._names_re().search(got.title)) or len(quotes) >= 3
        if award:
            criterion, etype, stage, signals = "awards", "award_notice", "granted", []
            title = f"Award notice: {got.title}"
            summary = (f"{where} says you won: \"{quotes[0][:200]}\". Add the award's scope and selectivity "
                       "(how many entrants, who judged).")  # fmt: skip
        else:
            criterion, etype, stage = "press", "press_article" if about else "media_mention", "published"
            signals = ["about_the_person"] if about else []
            title = f"{'Article' if about else 'Mention'}: {got.title}"
            summary = (f"{where}{' (' + got.published + ')' if got.published else ''} mentions you "
                       f"{plural(len(quotes), 'time')}: \"{quotes[0][:200]}\". Check it's about you and that the outlet is "
                       "major media or a professional publication.")  # fmt: skip
        facts: dict[str, float | int | str] = {k: v for k, v in {
            "site": where, "published": got.published, "author": got.author, "mentions": len(quotes)}.items() if v}  # fmt: skip
        canonical = got.canonical or got.url
        return [Candidate(fingerprint=f"website:{canonical}:{criterion}", source=f"{self.kind}:{item.name}",
                          item_id=item.id, evidence_type=etype, proposed_criterion=criterion, title=title[:200],
                          summary=summary, confidence=0.45 if about or award else 0.3, raw_url=got.url,
                          signals=signals, facts=facts, stage=stage,  # type: ignore[arg-type]
                          ).with_evidence(self._evidence(got, quotes))]  # fmt: skip

    # -- helpers --------------------------------------------------------------------------------

    def _names_re(self, extra: tuple[str, ...] = ()) -> re.Pattern[str]:
        names = sorted([*self.names, *extra], key=len, reverse=True) or ["\x00no-name\x00"]
        return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in names) + r")(?!\w)", re.I)

    def mentions(self, text: str) -> list[str]:
        """Sentences (or lines) that mention the person, verbatim from the page text. Once the full name appears,
        the family name alone counts too ("Rivera said..."), as news articles write."""
        if not self.names:
            return []
        pattern = self._names_re()
        family = self.names[0].split()[-1]
        if pattern.search(text) and len(family) >= 4 and " " in self.names[0].strip():
            pattern = self._names_re((family,))
        out = []
        for line in text.split("\n"):
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])", line):
                if pattern.search(sentence) and sentence.strip() not in out:
                    out.append(sentence.strip())
        return out

    def _evidence(self, a: web.Article, quotes: list[str]) -> Evidence:
        header = [f"# {a.title}" if a.title else "# (untitled page)", "", f"URL: {a.url}"]
        header += [
            f"{k}: {v}"
            for k, v in (("Published", a.published), ("Author", a.author), ("Site", a.site_name))
            if v
        ]
        text = "\n".join(header) + "\n\n" + a.text + "\n"
        subject = f"web:{a.canonical or a.url}"
        claims = [ClaimDraft(subject=subject, subject_kind="other", subject_name=a.title or a.url, subject_url=a.url,
                             predicate="mentions_person", value=self.names[0], excerpt=q, valid_from=self.today(),
                             confidence="medium") for q in quotes[:MAX_QUOTES]]  # fmt: skip
        if a.published and f"Published: {a.published}" in text:
            claims.append(ClaimDraft(subject=subject, subject_kind="other", subject_name=a.title or a.url,
                                     subject_url=a.url, predicate="published", value=a.published,
                                     excerpt=f"Published: {a.published}", valid_from=self.today(), confidence="medium"))  # fmt: skip
        return Evidence(connector=self.kind, tier="tier3", source_url=a.url, payload=text, media_type="text/markdown",
                        claims=claims)  # fmt: skip
