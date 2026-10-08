"""Summarize one or more browser-suite runs (tests/e2e): a per-page status, coverage of interactive elements, and
every finding grouped, marked consistent (in every run) or flaky (in some). Used by `areao1 qa` and by hand:

    python tests/e2e/report.py <run dir> [<run dir> ...] [--json out.json]
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PAGES = ["overview", "inbox", "evidence", "metrics", "pipeline", "letters", "contacts", "contacts?view=mail",
         "calendar", "agent", "memory", "knowledge", "sources", "settings", "not-a-page"]  # fmt: skip
WARNINGS = {"dead_control", "keyboard_unreachable", "http_4xx", "slow", "axe_minor", "self_link", "unusable",
            "request_failed"}  # fmt: skip


def _page_of(f: dict[str, Any]) -> str:
    m = re.search(r"#/([\w?=-]+)", f.get("where", ""))
    if m:
        return m.group(1)
    test = f.get("test", "")
    m = re.search(r"\[([\w?=-]+)\]$", test)
    return m.group(1) if m and m.group(1) in PAGES else "flows"


def _key(f: dict[str, Any]) -> tuple[str, str, str]:
    """The same problem across runs: kind, page and the message with ports, ids and numbers taken out."""
    msg = re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1", f["message"])
    msg = re.sub(r"\b(?:cand|exh|clm|dl|pipe|run|conv|chg)_[0-9a-f]+\b", "<id>", msg)
    return f["kind"], _page_of(f), msg


def load(run: Path) -> list[dict[str, Any]]:
    path = run / "findings.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    )


def coverage(run: Path) -> dict[str, dict[str, int]]:
    path = run / "coverage.jsonl"
    out: dict[str, dict[str, int]] = {}
    for line in path.read_text().splitlines() if path.exists() else []:
        c = json.loads(line)
        out[c["route"]] = {k: c[k] for k in ("elements", "exercised", "static", "skipped")}
    return out


def summarize(runs: list[Path]) -> dict[str, Any]:
    per_run = [load(r) for r in runs]
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    hits: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for n, findings in enumerate(per_run):
        for f in findings:
            k = _key(f)
            hits[k].add(n)
            if k not in seen:
                seen[k] = {**f, "page": _page_of(f), "count": 0}
            seen[k]["count"] += 1
    issues = []
    for k, f in seen.items():
        f["runs"] = len(hits[k])
        f["flaky"] = len(hits[k]) < len(runs)
        f["warning"] = f["kind"] in WARNINGS
        issues.append(f)
    issues.sort(key=lambda f: (f["warning"], f["page"], f["kind"], f["message"]))
    cov = coverage(runs[0])
    pages = []
    for p in [*PAGES, "flows"]:
        errs = [f for f in issues if f["page"] == p and not f["warning"] and not f["flaky"]]
        warns = [f for f in issues if f["page"] == p and (f["warning"] or f["flaky"])]
        broken = any(f["kind"] in ("pageerror", "http_5xx") for f in errs)
        status = "broken" if broken else "issues" if errs else "warnings" if warns else "pass"
        c = cov.get(p, {})
        pages.append({"page": p, "status": status, "errors": len(errs), "warnings": len(warns),
                      "elements": c.get("elements"), "exercised": (c.get("exercised", 0) + c.get("static", 0)) if c else None})  # fmt: skip
    total = sum(c["elements"] for c in cov.values())
    done = sum(c["exercised"] + c["static"] for c in cov.values())
    return {"runs": len(runs), "pages": pages, "issues": issues,
            "coverage": {"elements": total, "exercised": done, "percent": round(100 * done / total, 1) if total else None}}  # fmt: skip


def markdown(s: dict[str, Any]) -> str:
    out = [f"# QA report ({s['runs']} run{'s' if s['runs'] != 1 else ''})", "",
           f"Coverage: {s['coverage']['exercised']} of {s['coverage']['elements']} interactive elements "
           f"({s['coverage']['percent']}%)", "", "| Page | Status | Errors | Warnings | Exercised |", "|---|---|---|---|---|"]  # fmt: skip
    for p in s["pages"]:
        ex = f"{p['exercised']}/{p['elements']}" if p["elements"] else ""
        out.append(f"| {p['page']} | {p['status']} | {p['errors']} | {p['warnings']} | {ex} |")
    out += ["", "## Findings", ""]
    for f in s["issues"]:
        tag = "warning" if f["warning"] else "error"
        out.append(f"- **{f['kind']}** ({tag}, {'flaky' if f['flaky'] else 'consistent'}, {f['runs']}/{s['runs']} runs) "
                   f"{f['page']}: {f['message']}")  # fmt: skip
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    runs = [Path(a) for a in args if a != out]
    s = summarize(runs)
    if out:
        Path(out).write_text(json.dumps(s, indent=1, default=str))
    sys.stdout.write(markdown(s))
    return 1 if any(not f["warning"] and not f["flaky"] for f in s["issues"]) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
