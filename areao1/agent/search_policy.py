"""Where the agent may search the web for rules (SPEC 5a, live fallback).

A web search whose query looks like a rule question (the manifest's ``rule_hints``) is allowed only after the
agent searched the knowledge vault in this run, and only restricted to official domains: Tier 1 first, Tier 2
after a Tier 1 search. Other searches (opportunities, people, events) stay open. Enforced on the engine's
built-in web search through ``EngineRequest.guard``; the model sees the reason when a search is refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from areao1.vault.models import VaultManifest

SEARCH_TOOLS = {"WebSearch", "web_search"}


def _host(domain: str) -> str:
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d[4:] if d.startswith("www.") else d


def _within(domain: str, allowed: list[str]) -> bool:
    h = _host(domain)
    return bool(h) and any(h == a or h.endswith("." + a) for a in allowed)


@dataclass
class SearchPolicy:
    manifest: VaultManifest
    vault_searched: bool = False
    tier1_searched: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)

    def is_rule_query(self, query: str) -> bool:
        return any(re.search(h, query, re.I) for h in self.manifest.rule_hints)

    async def __call__(self, tool: str, data: dict[str, Any]) -> str | None:
        if tool not in SEARCH_TOOLS:
            return None
        query = str(data.get("query", ""))
        reason = self._decide(query, [str(d) for d in data.get("allowed_domains") or []])
        self.log.append({"query": query, "allowed_domains": data.get("allowed_domains"), "denied": reason})
        return reason

    def _decide(self, query: str, domains: list[str]) -> str | None:
        if not self.is_rule_query(query):
            return None
        t1, t2 = self.manifest.tier1_domains, self.manifest.tier2_domains
        if not self.vault_searched:
            return ("This looks like a question about the rules. Call search_vault first; search the web only if the "
                    "vault has nothing fresh.")  # fmt: skip
        if not domains:
            return ("For rules, search official sources only: repeat the search with allowed_domains set to Tier 1 "
                    f"domains ({', '.join(t1)}).")  # fmt: skip
        if all(_within(d, t1) for d in domains):
            self.tier1_searched = True
            return None
        if all(_within(d, t1 + t2) for d in domains):
            if self.tier1_searched:
                return None
            return f"Search Tier 1 domains first ({', '.join(t1)}); Tier 2 ({', '.join(t2)}) only if that finds nothing."
        return (f"For rules, allowed_domains must be Tier 1 ({', '.join(t1)}) or, after that, Tier 2 "
                f"({', '.join(t2)}). Secondary sites can't be the source for a rule.")  # fmt: skip
