"""Banter (ADR 0010 §4): the few lines of humor, from banter.json, which the web app reads too. Only the places
listed there use them, and tests/test_banter.py enforces the rules (never on serious screens, "alien" only about
us or in the legal term, never mocking USCIS, attorneys or other companies, at most one line per screen)."""

from __future__ import annotations

import json
from pathlib import Path

LINES: dict[str, str] = {
    k: v["text"]
    for k, v in json.loads(Path(__file__).with_name("banter.json").read_text()).items()
    if k != "_note"
}


def line(key: str, **values: str) -> str:
    return LINES[key].format(**values)
