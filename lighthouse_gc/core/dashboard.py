"""Generate DASHBOARD.md — the terminal / agent view of the workspace."""

from __future__ import annotations

from datetime import date

from lighthouse_gc.core import overview as views
from lighthouse_gc.core.models import Scoreboard
from lighthouse_gc.core.workspace import Workspace, _atomic_write

STATUS_ICON = {"banked": "✅ banked", "building": "🟡 building", "gap": "⬜ gap", "dropped": "➖ dropped"}

DISCLAIMER = (
    "Lighthouse is not legal advice and is not affiliated with USCIS. Criteria profiles are "
    "community-maintained summaries of public regulations (8 CFR 214.2(o), 8 CFR 204.5(h)). "
    "Always confirm strategy with an immigration attorney."
)


def _num(v: float) -> str:
    return f"{int(v):,}" if float(v).is_integer() else f"{v:,.2f}"


def _delta(v: float | None) -> str:
    if v is None:
        return "—"
    return ("+" if v > 0 else "") + _num(v)


def render(ws: Workspace, board: Scoreboard | None = None, today: date | None = None) -> str:
    today = today or date.today()
    board = board or ws.scoreboard()
    person = ws.person()
    profile = ws.profile(board.profile)
    lines: list[str] = []
    w = lines.append

    w(f"# Lighthouse — {person.name or ws.config().workspace_name}")
    w("")
    w(
        f"_Generated {today.isoformat()} from the files in `data/`. Do not edit by hand — run "
        "`lighthouse-gc run dashboard` to regenerate._"
    )
    w("")
    need = max(0, board.threshold - board.banked)
    w(
        f"**{board.profile_name}** — {board.banked} banked / {board.threshold} needed "
        f"(target {board.target}), {board.building} building."
        + (f" **{need} more criterion(s) to bank.**" if need else " **Threshold met.**")
    )
    w("")

    w("## Criteria")
    w("")
    w("| Criterion | Status | Exhibits | Signals | Notes |")
    w("|---|---|---:|---|---|")
    for c in board.criteria:
        signals = ", ".join(c.matched_signals) or "—"
        w(f"| {c.label} (`{c.id}`) | {STATUS_ICON[c.status]} | {c.exhibit_count} | {signals} | {c.reason} |")
    w("")
    if board.reviewer_note:
        w("> **Reviewer view (agent opinion, not a rule result):** " + board.reviewer_note)
        w("")

    tasks = views.human_tasks(ws, today)
    w("## This week (human-only)")
    w("")
    w(
        "\n".join(f"- [ ] {t['title']}" + (f" — due {t['due']}" if t.get("due") else "") for t in tasks)
        or "- Nothing due. 🎉"
    )
    w("")

    w("## Next deadlines")
    w("")
    deadlines = views.upcoming_deadlines(ws, 3, today)
    w(
        "\n".join(f"- **{d['due']}** ({d['days_left']}d) — {d['title']}" for d in deadlines)
        or "- None scheduled."
    )
    w("")

    pending = ws.pending_candidates(today)
    w(f"## Inbox — {len(pending)} pending")
    w("")
    by_crit: dict[str, int] = {}
    for cand in pending:
        by_crit[cand.proposed_criterion] = by_crit.get(cand.proposed_criterion, 0) + 1
    labels = {c.id: c.label for c in profile.criteria}
    w("\n".join(f"- {labels.get(k, k)}: {n}" for k, n in sorted(by_crit.items())) or "- Inbox zero.")
    w("")

    w("## Metrics (latest snapshot)")
    w("")
    series = views.metric_series(ws.metrics())
    if series:
        w("| Source | Item | Metric | Value | Δ since last | As of |")
        w("|---|---|---|---:|---:|---|")
        for (source, item, metric), points in sorted(series.items()):
            if metric not in views.HEADLINE_METRICS.get(source, ()):
                continue
            ld = views.latest_with_delta(points)
            w(
                f"| {source} | {item} | {metric} | {_num(ld['value'])} | {_delta(ld['delta'])} | {ld['date']} |"
            )
    else:
        w("No metrics yet. Run `lighthouse-gc run metrics-snapshot`.")
    w("")

    w("## Sources")
    w("")
    sources = ws.sources().sources
    for s in sources:
        tracked = sum(i.tracked for i in s.items)
        sync = s.last_sync.date().isoformat() if s.last_sync else "never"
        err = f" — ⚠️ {s.last_error}" if s.last_error else ""
        w(f"- `{s.id}` — {tracked} tracked item(s), last sync {sync}{err}")
    if not sources:
        w("- None yet. Run `lighthouse-gc import <url>`.")
    w("")
    w("---")
    w(f"_{DISCLAIMER}_")
    w("")
    return "\n".join(lines)


def write_dashboard(ws: Workspace, board: Scoreboard | None = None, today: date | None = None) -> None:
    _atomic_write(ws.root / "DASHBOARD.md", render(ws, board, today))
