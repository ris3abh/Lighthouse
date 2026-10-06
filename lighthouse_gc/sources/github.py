"""GitHub connector — public repos without auth, private repos and traffic with a fine-grained PAT.

Recommended token (read-only): Repository access = the repos to track; permissions
Metadata: read, Contents: read, Administration: read (Administration is needed for traffic only).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from lighthouse_gc.core.models import Candidate, ClaimDraft, ConnectorConfig, Evidence, MetricRow, TrackedItem
from lighthouse_gc.sources.base import Creds, artifact_id, field_claims, paper_candidate
from lighthouse_gc.sources.http import HttpClient

API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
TOKEN_URL = (
    "https://github.com/settings/personal-access-tokens/new"
    "?name=lighthouse-gc&description=Read-only+access+for+Lighthouse"
    "&metadata=read&contents=read&administration=read"
)

_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/(?P<path>[^?#\s]+)", re.I)
_HANDLE_RE = re.compile(r"^(?:gh|github):(?P<path>[\w.\-]+(?:/[\w.\-]+)?)$", re.I)
_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9\-]{0,38})$")
_REPO_RE = re.compile(r"^[\w.\-]+$")
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(?P<id>\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_RESERVED = {"settings", "marketplace", "explore", "topics", "trending", "sponsors", "notifications", "login"}

MAX_PAGES = 10


class GitHubSource:
    kind = "github"

    def __init__(
        self,
        http: HttpClient | None = None,
        config: ConnectorConfig | None = None,
        today: Callable[[], date] = date.today,
    ):
        self.http = http or HttpClient(API, kind=self.kind, headers=HEADERS)
        self.config = config or ConnectorConfig()
        self.today = today

    # -- input -------------------------------------------------------------------------------

    @classmethod
    def detect(cls, url_or_handle: str) -> bool:
        try:
            cls.parse(url_or_handle)
            return True
        except ValueError:
            return False

    @staticmethod
    def parse(url_or_handle: str) -> str:
        text = url_or_handle.strip()
        m = _HANDLE_RE.match(text)
        if m:
            parts = m["path"].split("/")
        else:
            m = _URL_RE.match(text)
            if not m:
                raise ValueError(f"not a GitHub URL or handle: {text!r}")
            parts = [p for p in m["path"].split("/") if p]
            if parts and parts[0].lower() == "orgs":
                parts = parts[1:2]
        if not parts or not _NAME_RE.match(parts[0]) or parts[0].lower() in _RESERVED:
            raise ValueError(f"not a GitHub account: {text!r}")
        if len(parts) >= 2:
            repo = parts[1].removesuffix(".git")
            if not _REPO_RE.match(repo):
                raise ValueError(f"not a GitHub repo: {text!r}")
            return f"{parts[0]}/{repo}"
        return parts[0]

    def source_url(self, handle: str) -> str:
        return f"https://github.com/{handle}"

    # -- discover ----------------------------------------------------------------------------

    def discover(self, handle: str, creds: Creds) -> list[TrackedItem]:
        if "/" in handle:
            return [self._item(self._repo(handle, creds))]

        user = self.http.get(f"/users/{handle}", token=creds).data
        login = user["login"]
        if creds:
            me = self.http.get("/user", token=creds, allow=(401, 403)).data
            if me and me.get("login", "").lower() == login.lower():
                repos = self._paginate("/user/repos", {"affiliation": "owner", "per_page": 100}, creds)
            elif user.get("type") == "Organization":
                repos = self._paginate(f"/orgs/{login}/repos", {"type": "all", "per_page": 100}, creds)
            else:
                repos = self._paginate(f"/users/{login}/repos", {"type": "owner", "per_page": 100}, creds)
        else:
            path = f"/orgs/{login}/repos" if user.get("type") == "Organization" else f"/users/{login}/repos"
            repos = self._paginate(path, {"per_page": 100}, creds)

        items = []
        for repo in repos:
            if repo.get("fork") and not self.config.include_forks:
                continue
            items.append(self._item(repo))
        return sorted(items, key=lambda i: i.id)

    def _item(self, repo: dict[str, Any]) -> TrackedItem:
        return TrackedItem(
            id=f"github:{repo['full_name']}",
            kind="repo",
            name=repo["full_name"],
            url=repo["html_url"],
            title=repo.get("description") or "",
            private=bool(repo.get("private")),
        )

    def _paginate(self, path: str, params: dict[str, Any], creds: Creds) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while page <= MAX_PAGES:
            resp = self.http.get(path, params={**params, "page": page}, token=creds)
            out.extend(resp.data or [])
            if 'rel="next"' not in resp.headers.get("link", ""):
                break
            page += 1
        return out

    def _repo(self, full_name: str, creds: Creds) -> dict[str, Any]:
        data: dict[str, Any] = self.http.get(f"/repos/{full_name}", token=creds).data
        return data

    def _count(self, path: str, creds: Creds, params: dict[str, Any] | None = None) -> int | None:
        """Count a list endpoint cheaply: per_page=1 and read the last page number from Link."""
        resp = self.http.get(
            path, params={**(params or {}), "per_page": 1}, token=creds, allow=(403, 404, 204)
        )
        if resp.status in (403, 404):
            return None
        if resp.status == 204 or not resp.data:
            return 0
        link = resp.headers.get("link", "")
        m = re.search(r'<([^>]+)>;\s*rel="last"', link)
        if not m:
            return len(resp.data)
        return int(parse_qs(urlparse(m.group(1)).query)["page"][0])

    # -- snapshot ----------------------------------------------------------------------------

    def snapshot(self, item: TrackedItem, creds: Creds) -> list[MetricRow]:
        repo = self._repo(item.name, creds)
        today = self.today()

        def row(metric: str, value: float, on: date = today) -> MetricRow:
            return MetricRow(date=on, source=self.kind, item=item.name, metric=metric, value=value)

        evidence = self._repo_evidence(item, repo)
        rows = [
            row("stars", repo["stargazers_count"]).with_evidence(evidence),
            row("forks", repo["forks_count"]).with_evidence(evidence),
            row("watchers", repo.get("subscribers_count", repo.get("watchers_count", 0))).with_evidence(
                evidence
            ),
            row("open_issues", repo.get("open_issues_count", 0)).with_evidence(evidence),
        ]
        contributors = self._count(f"/repos/{item.name}/contributors", creds, {"anon": 1})
        if contributors is not None:
            rows.append(row("contributors", contributors))
        releases = self._count(f"/repos/{item.name}/releases", creds)
        if releases is not None:
            rows.append(row("releases", releases))

        # Traffic needs push/admin access; GitHub only keeps 14 days, so store every daily point.
        if creds:
            for kind in ("views", "clones"):
                resp = self.http.get(f"/repos/{item.name}/traffic/{kind}", token=creds, allow=(403, 404))
                if not resp.ok or not resp.data:
                    continue
                traffic = Evidence(
                    connector=self.kind,
                    source_url=f"{API}/repos/{item.name}/traffic/{kind}",
                    payload=resp.data,
                    claims=field_claims(
                        artifact_id(self.kind, item.name), item.name, item.url, resp.data,
                        {f"{kind}_14d": "count", f"{kind}_unique_14d": "uniques"}, today,
                    ),
                )  # fmt: skip
                for point in resp.data.get(kind, []):
                    on = datetime.fromisoformat(point["timestamp"].replace("Z", "+00:00")).date()
                    rows.append(row(kind, point["count"], on).with_evidence(traffic))
                    rows.append(row(f"{kind}_unique", point["uniques"], on).with_evidence(traffic))
        return rows

    def _repo_evidence(self, item: TrackedItem, repo: dict[str, Any]) -> Evidence:
        fields = {"stars": "stargazers_count", "forks": "forks_count", "watchers": "subscribers_count",
                  "open_issues": "open_issues_count", "created_at": "created_at"}  # fmt: skip
        return Evidence(
            connector=self.kind,
            source_url=f"{API}/repos/{item.name}",
            payload=repo,
            claims=field_claims(
                artifact_id(self.kind, item.name), item.name, item.url, repo, fields, self.today()
            ),
        )

    # -- candidates --------------------------------------------------------------------------

    def candidates(self, item: TrackedItem, creds: Creds) -> list[Candidate]:
        repo = self._repo(item.name, creds)
        stars, forks = repo["stargazers_count"], repo["forks_count"]
        releases = self._count(f"/repos/{item.name}/releases", creds) or 0
        source_id = f"{self.kind}:{repo['owner']['login']}"
        out: list[Candidate] = []

        if stars >= self.config.min_stars_for_candidate:
            signals = []
            if stars >= 100:
                signals.append("widely_adopted")
            if forks >= 10:
                signals.append("used_by_others")
            if releases >= 3:
                signals.append("sustained_activity")
            desc = (repo.get("description") or "").strip()
            summary = f"{repo['full_name']} — ★ {stars:,} · {forks:,} forks · {releases} releases"
            if desc:
                summary += f" — {desc}"
            out.append(
                Candidate(
                    fingerprint=f"github:{repo['full_name'].lower()}:original_contributions",
                    source=source_id,
                    item_id=item.id,
                    evidence_type="open_source_project",
                    proposed_criterion="original_contributions",
                    title=f"Open-source project: {repo['full_name']}",
                    summary=summary,
                    confidence=round(min(0.9, 0.3 + math.log10(stars + 1) / 5), 2),
                    raw_url=repo["html_url"],
                    signals=signals,
                    facts={
                        "stars": stars,
                        "forks": forks,
                        "releases": releases,
                        "language": repo.get("language") or "",
                        "topics": ", ".join(repo.get("topics") or []),
                        "created": (repo.get("created_at") or "")[:10],
                    },
                ).with_evidence(self._repo_evidence(item, repo))
            )

        readme = self.http.get(
            f"/repos/{item.name}/readme",
            token=creds,
            accept="application/vnd.github.raw+json",
            raw=True,
            allow=(404,),
        )
        if readme.ok and readme.data:
            for arxiv_id in sorted(set(ARXIV_RE.findall(readme.data))):
                quote = next(m.group(0) for m in ARXIV_RE.finditer(readme.data) if m["id"] == arxiv_id)
                evidence = Evidence(
                    connector=self.kind,
                    source_url=f"{API}/repos/{item.name}/readme",
                    payload=readme.data,
                    media_type="text/markdown",
                    claims=[
                        ClaimDraft(
                            subject=artifact_id(self.kind, item.name),
                            subject_name=item.name,
                            subject_url=item.url,
                            predicate="links_paper",
                            value=f"arxiv:{arxiv_id}",
                            excerpt=quote,
                            valid_from=self.today(),
                            confidence="medium",  # a link doesn't prove authorship
                        )
                    ],
                )
                context = f"linked from the {repo['full_name']} README"
                out.append(paper_candidate(arxiv_id, source_id, item.id, context, evidence=evidence))
        return out
