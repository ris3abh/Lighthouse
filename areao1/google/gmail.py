"""Gmail threads with your case contacts (ADR 0014 §2)."""

from __future__ import annotations

from areao1.criteria.case import Case
from areao1.criteria.models import GmailThreads


def load_threads(ws: Case) -> GmailThreads:
    return ws.threads()
