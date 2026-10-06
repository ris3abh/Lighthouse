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
