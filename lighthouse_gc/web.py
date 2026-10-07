"""Fetching public web pages safely: one guard for the agent's page reader, the knowledge vault and the website
connector. Only public http(s) hosts (re-checked on every redirect), size-capped, and bot-protection pages are
recognised as unreadable instead of being stored as content."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from lighthouse_gc import __version__

MAX_PAGE_BYTES = 2_000_000
MAX_REDIRECTS = 3


def user_agent(purpose: str) -> str:
    return f"lighthouse-gc/{__version__} ({purpose}; +https://github.com/ris3abh/Lighthouse)"


class Unreadable(ValueError):
    """The site answered, but not with the page: a bot check, a login wall, or an empty body."""


# Titles and markers of bot-protection and access-request pages (often served with HTTP 200).
_BLOCK_TITLES = re.compile(
    r"\b(attention required|just a moment\.*|request access|access denied|are you a robot|security check|"
    r"verify you are human|pardon our interruption|403 forbidden|captcha)\b",
    re.IGNORECASE,
)
_DOWN_TITLES = re.compile(
    r"\b(under maintenance|temporarily unavailable|service unavailable|site maintenance)\b", re.I
)
_BLOCK_MARKERS = ("cf-chl-", "challenge-platform", "g-recaptcha", "hcaptcha", "_incapsula_resource",
                  "px-captcha", "please enable cookies")  # fmt: skip


def blocked_reason(status: int, title: str, raw: str) -> str | None:
    if status in (401, 403, 429, 451):
        return f"HTTP {status}"
    if status == 202 and not raw.strip():
        return "no readable content (HTTP 202, empty body)"
    if _BLOCK_TITLES.search(title.strip()):
        return f"bot-protection page ({title.strip()[:60]})"
    if _DOWN_TITLES.search(title.strip()):
        return f"site unavailable ({title.strip()[:60]})"
    head = raw[:20_000].lower()
    if len(raw) < 60_000 and any(m in head for m in _BLOCK_MARKERS):
        return "bot-protection page"
    return None


@dataclass
class Fetched:
    url: str
    status: int
    content_type: str
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


async def get(url: str, client: httpx.AsyncClient, *, max_bytes: int = MAX_PAGE_BYTES) -> Fetched:
    """GET a public URL, following up to 3 redirects and re-checking each hop. Raises :class:`UnsafeURL`,
    :class:`Unreadable` (blocked), or ValueError (other HTTP errors, too large)."""
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        resp = await client.get(url, follow_redirects=False)
        if resp.is_redirect and resp.headers.get("location"):
            url = urljoin(url, resp.headers["location"])
            continue
        ctype = resp.headers.get("content-type", "").lower()
        title = ""
        if "html" in ctype:
            m = re.search(r"<title[^>]*>(.*?)</title>", resp.text[:50_000], re.S | re.I)
            title = " ".join(m.group(1).split()) if m else ""
        reason = blocked_reason(resp.status_code, title, resp.text if "html" in ctype or not ctype else "x")
        if reason:
            raise Unreadable(f"{url} can't be read automatically: {reason}")
        if resp.status_code >= 400:
            raise ValueError(f"HTTP {resp.status_code} from {url}")
        if resp.status_code != 200 or not resp.content.strip():
            raise Unreadable(f"{url} returned no readable content (HTTP {resp.status_code})")
        if len(resp.content) > max_bytes:
            raise ValueError(f"page is larger than {max_bytes // 1_000_000} MB")
        return Fetched(url=url, status=resp.status_code, content_type=ctype, content=resp.content)
    raise ValueError("too many redirects")


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
    """(final url, title, text) for the agent's page reader."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=15.0, headers={"User-Agent": user_agent("agent")})
    try:
        try:
            page = await get(url, client)
        except Unreadable as exc:
            # e.g. 202 with an empty body: a bot-protection challenge, not the page.
            raise ValueError(f"{exc}. The site may block automated reading. Try another source, or cite the "
                             "search result as unverified.") from exc  # fmt: skip
        if "html" in page.content_type:
            title, text = html_to_text(page.text)
        elif page.content_type.startswith("text/") or "json" in page.content_type:
            title, text = "", page.text
        else:
            raise ValueError(f"can't read {page.content_type or 'unknown content type'} (only HTML and text)")
        if len(text.strip()) < 40:
            raise ValueError(
                f"{page.url} has almost no readable text (it may need JavaScript); try another source"
            )
        return page.url, title, text
    finally:
        if own:
            await client.aclose()


# ----------------------------------------------------------------------------- readability (website connector)


@dataclass
class Article:
    url: str
    title: str
    text: str
    published: str | None = None  # ISO date as the page states it
    author: str | None = None
    site_name: str | None = None
    canonical: str | None = None
    description: str | None = None


class _Readable(HTMLParser):
    """The main text of a page, readability-style: the <article> (or <main>) when there is one, without
    navigation, headers, footers, asides, forms and scripts; plus the page's metadata."""

    SKIP = _Text.SKIP | {"aside", "button", "template", "dialog"}
    BLOCK = _Text.BLOCK | {"main", "figcaption", "dd", "dt", "td", "th", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.canonical: str | None = None
        self.times: list[str] = []
        self.ld: list[str] = []
        self.parts: dict[str, list[str]] = {"article": [], "main": [], "body": []}
        self._skip = 0
        self._in: dict[str, int] = {"article": 0, "main": 0}
        self._title = self._ldjson = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "link" and "canonical" in a.get("rel", "").lower() and a.get("href"):
            self.canonical = a["href"]
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._ldjson = True
            self.ld.append("")
        if tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._title = True
        elif tag in self._in:
            self._in[tag] += 1
        if tag in self.BLOCK:
            self._add("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._ldjson = False
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._title = False
        elif tag in self._in and self._in[tag]:
            self._in[tag] -= 1
        if tag in self.BLOCK:
            self._add("\n")

    def handle_data(self, data: str) -> None:
        if self._ldjson:
            self.ld[-1] += data
        elif self._title:
            self.title += data
        elif not self._skip:
            self._add(data)

    def _add(self, data: str) -> None:
        self.parts["body"].append(data)
        for k, depth in self._in.items():
            if depth:
                self.parts[k].append(data)


def _clean(parts: list[str]) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parts))
    lines = [line.strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _ld_fields(blobs: list[str]) -> dict[str, str]:
    """headline, datePublished and author name from JSON-LD (Article / NewsArticle / BlogPosting...)."""
    import json

    out: dict[str, str] = {}
    for blob in blobs:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        nodes = (
            data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        )
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for key in ("headline", "datePublished"):
                if isinstance(node.get(key), str) and key not in out:
                    out[key] = node[key]
            author = node.get("author")
            author = author[0] if isinstance(author, list) and author else author
            name = (
                author.get("name")
                if isinstance(author, dict)
                else author
                if isinstance(author, str)
                else None
            )
            if name and "author" not in out:
                out["author"] = str(name)
    return out


def readable(html: str, url: str) -> Article:
    p = _Readable()
    p.feed(html)
    ld = _ld_fields(p.ld)
    body = _clean(p.parts["body"])
    text = next((t for t in (_clean(p.parts["article"]), _clean(p.parts["main"])) if len(t) >= 200), body)
    m = p.meta
    published = (m.get("article:published_time") or ld.get("datePublished") or m.get("citation_publication_date")
                 or m.get("date") or m.get("dc.date") or (p.times[0] if p.times else None))  # fmt: skip
    title = m.get("og:title") or ld.get("headline") or " ".join(p.title.split())
    return Article(url=url, title=title.strip(), text=text, published=published[:10] if published else None,
                   author=m.get("author") or m.get("article:author") or ld.get("author"),
                   site_name=m.get("og:site_name"), canonical=urljoin(url, p.canonical) if p.canonical else None,
                   description=m.get("og:description") or m.get("description"))  # fmt: skip


MIN_ARTICLE_TEXT = 200


async def fetch_article(url: str, client: httpx.AsyncClient | None = None) -> Article:
    """A page's main text and metadata through the same guard as the agent's page reader. Raises
    :class:`UnsafeURL` (private or local address), :class:`Unreadable` (bot check, login wall, maintenance,
    or a JavaScript-only page with no text) or ValueError (HTTP errors, unsupported content)."""
    own = client is None
    client = client or httpx.AsyncClient(
        timeout=20.0, headers={"User-Agent": user_agent("website connector")}
    )
    try:
        page = await get(url, client)
        if "html" in page.content_type:
            article = readable(page.text, page.url)
        elif page.content_type.startswith("text/plain"):
            article = Article(url=page.url, title="", text=page.text.strip())
        else:
            raise ValueError(f"can't read {page.content_type or 'unknown content type'} (only HTML and text)")
        if len(article.text) < MIN_ARTICLE_TEXT:
            raise Unreadable(f"{page.url} has almost no readable text (it may need JavaScript)")
        return article
    finally:
        if own:
            await client.aclose()


def sitemap_urls(xml: str, base: str, limit: int = 25) -> list[str]:
    """Page URLs (<loc>) from a sitemap, same host as ``base`` only. Refuses DTDs and entities."""
    if re.search(r"<!DOCTYPE|<!ENTITY", xml, re.I):
        raise ValueError("the sitemap contains a DTD; refusing to parse it")
    host = urlparse(base).hostname
    out: list[str] = []
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, re.I):
        if urlparse(loc).hostname == host and loc not in out:
            out.append(loc)
        if len(out) >= limit:
            break
    return out
