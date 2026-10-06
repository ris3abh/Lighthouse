"""Regenerate examples/demo-workspace — the fictional "Alex Rivera" persona.

    .venv/bin/python scripts/make_demo.py

Everything here is fictional. Sources are imported through the real connectors, but every HTTP response
is served from the recorded fixtures in tests/fixtures (respx), so this never touches the network and
the demo's memory/ (observations, quoted claims, decisions) comes from the same pipeline a user's import
does. Run it after changing a model, then commit the result.
"""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import respx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from conftest import mock_github, mock_hf  # noqa: E402

from lighthouse_gc.core.models import (  # noqa: E402
    Deadline,
    Deadlines,
    MetricRow,
    Pipeline,
    PipelineItem,
)
from lighthouse_gc.core.workspace import _atomic_write, dump_model  # noqa: E402
from lighthouse_gc.criteria.models import FilingTarget, Letter, Letters, Person, Petitioner  # noqa: E402
from lighthouse_gc.jobs.sync import import_source  # noqa: E402
from lighthouse_gc.scaffold import create_workspace  # noqa: E402

TARGET = ROOT / "examples" / "demo-workspace"


def at(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC)


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    ws = create_workspace(TARGET, name="Alex Rivera", profile="o1a", git=False)

    cfg = ws.config()
    cfg.workspace_name = "demo-workspace"
    cfg.overrides = {"o1a": {"high_salary": "dropped"}}
    ws.save_config(cfg)
    ws.save_person(
        Person(
            name="Alex Rivera",
            aliases=["A. Rivera"],
            field="Machine learning systems (distributed training, robotics perception)",
            current_status="F-1 STEM OPT",
            location="Pittsburgh, PA",
            filing_target=FilingTarget(profile="o1a", target_date=date(2027, 3, 1)),
            petitioner=Petitioner(name="Fernhill Robotics, Inc. (fictional)", kind="employer"),
        )
    )

    # ---- metric history before today's import (biweekly Monday snapshots, synthetic)
    snaps = [date(2026, 6, 1) + timedelta(days=14 * i) for i in range(9)]
    series = {
        ("github", "arivera-demo/fastgrad"): {"stars": (1210, 1751), "forks": (140, 202), "watchers": (31, 42),
                                              "contributors": (28, 36), "releases": (9, 11)},
        ("github", "arivera-demo/tinyserve"): {"stars": (20, 42), "forks": (1, 3), "watchers": (2, 4)},
        ("huggingface", "arivera-demo/tiny-vlm"): {"downloads": (8000, 14349), "downloads_all_time": (41000, 107068),
                                                   "likes": (120, 217)},
        ("huggingface", "datasets/arivera-demo/robo-grasp-10k"): {"downloads": (900, 2101),
                                                                  "downloads_all_time": (3100, 13139),
                                                                  "likes": (12, 28)},
        ("huggingface", "papers/2509.04321"): {"upvotes": (0, 31)},
    }  # fmt: skip
    rows = []
    for i, d in enumerate(snaps):
        for (src, item), metrics in series.items():
            for metric, (a, b) in metrics.items():
                value = round(a + (b - a) * (i / (len(snaps) - 1)) ** 1.3)
                if metric == "upvotes" and i < 6:
                    continue  # the paper appeared in September
                rows.append(MetricRow(date=d, source=src, item=item, metric=metric, value=value))
    ws.append_metrics(rows)

    # ---- import through the real connectors, HTTP served from recorded fixtures. The token is fake and
    # goes to an in-memory keychain, never the OS keychain.
    import keyring

    fake: dict[tuple[str, str], str] = {}
    keyring.set_password = lambda s, k, v: fake.__setitem__((s, k), v)  # type: ignore[assignment]
    keyring.get_password = lambda s, k: fake.get((s, k))  # type: ignore[assignment]
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        mock_github(router, authed=True, include_private=False)
        mock_hf(router)
        import_source(ws, "github:arivera-demo", token="demo-token-not-real", sleep=lambda s: None)
        import_source(ws, "https://huggingface.co/arivera-demo", sleep=lambda s: None)

    # Show the GitHub source as public: there is no real token behind the demo.
    for src in ws.sources().sources:
        ws.update_source(src.id, auth="none", secret_ref=None)

    # ---- the user's decisions in the Inbox (approve / reject records claims' review state)
    pending = {c.title: c for c in ws.pending_candidates()}
    ws.accept_candidate(pending["Open-source project: arivera-demo/fastgrad"].id, date=date(2026, 9, 1))
    ws.reject_candidate(pending["Hugging Face space: arivera-demo/tiny-vlm-demo"].id)

    # ---- manual uploads (the user filed these documents themselves)
    uploads = [
        ("judging", "panel_letter", "HackMIT 2026 judging completed - organizer confirmation", date(2026, 3, 16),
         "completed", ["selective_event", "documented_scoring"],
         "Organizer letter confirming Alex judged the ML track (1 of 12 judges; 140 teams), with the rubric."),
        ("judging", "reviewer_record", "NeurIPS 2026 workshop reviewer record", date(2026, 6, 20), "completed",
         ["selective_event"], "Reviewed 4 submissions for the Efficient ML workshop. OpenReview export."),
        ("judging", "judge_invite", "MLH Fall 2026 judge invitation", date(2026, 9, 12), "invited", [],
         "Invitation only. Counts once the organizer confirms judging was completed."),
        ("scholarly_articles", "conference_paper", "Sparse gradient compression at scale (ICML 2025)",
         date(2025, 12, 2), "published", ["peer_reviewed", "major_venue", "cited"],
         "First author. Peer-reviewed main-track paper; 63 citations as of Oct 2026."),
        ("scholarly_articles", "preprint", "RoboGrasp-10k preprint", date(2026, 5, 10), "preprint", ["cited"],
         "Second author. Preprint under review; counts once published."),
        ("awards", "hackathon_win", "DevFest 2025 hackathon - first place", date(2025, 11, 18), "granted", [],
         "First place out of 85 teams. Needs evidence of selectivity and reach."),
        ("critical_role", "role_letter", "Fernhill Robotics role letter (draft)", date(2026, 8, 15), None,
         ["critical_capacity"], "Draft letter from the VP Engineering describing the perception lead role."),
    ]  # fmt: skip
    for crit, etype, title, on, stage, signals, summary in uploads:
        body = (
            f"# {title}\n\n{summary}\n\n"
            "> Demo exhibit for the fictional persona Alex Rivera. Not a real document.\n"
        )
        ws.add_exhibit_file(
            content=body.encode(),
            filename=f"{title}.md",
            criterion=crit,
            evidence_type=etype,
            title=title,
            on=on,
            summary=summary,
            signals=signals,
            stage=stage,
        )

    # ---- trackers
    _atomic_write(ws.data_dir / "deadlines.json", dump_model(Deadlines(deadlines=[
        Deadline(id="dl_demo_letter", title="Send draft letter to Dr. Priya Natarajan", due=date(2026, 10, 9),
                 kind="follow_up", criterion="original_contributions"),
        Deadline(id="dl_demo_reviews", title="NeurIPS 2026 workshop reviews due", due=date(2026, 10, 14),
                 kind="submission", criterion="judging", url="https://example.org/openreview"),
        Deadline(id="dl_demo_ieee", title="IEEE Senior Member application", due=date(2026, 11, 1),
                 kind="application", criterion="membership"),
        Deadline(id="dl_demo_filing", title="Target O-1A filing date", due=date(2027, 3, 1), kind="filing"),
        Deadline(id="dl_demo_done", title="Request ICML citation report", due=date(2026, 9, 15), done=True),
    ])))  # fmt: skip
    _atomic_write(ws.data_dir / "pipeline.json", dump_model(Pipeline(items=[
        PipelineItem(id="pipe_demo_ieee", title="IEEE Senior Member", criterion="membership", stage="applied",
                     follow_up=date(2026, 10, 20), created_at=at("2026-08-01T10:00:00"),
                     moved_at=at("2026-09-10T10:00:00")),
        PipelineItem(id="pipe_demo_press", title="Pitch fastgrad story to an ML newsletter", criterion="press",
                     created_at=at("2026-09-01T10:00:00"), moved_at=at("2026-09-01T10:00:00")),
        PipelineItem(id="pipe_demo_mlh", title="MLH Fall hackathon: confirm judging completed", criterion="judging",
                     stage="waiting", follow_up=date(2026, 10, 8), url="https://example.org/mlh-judges",
                     created_at=at("2026-09-05T10:00:00"), moved_at=at("2026-09-12T10:00:00")),
    ])))  # fmt: skip
    _atomic_write(ws.data_dir / "letters.json", dump_model(Letters(letters=[
        Letter(id="let_demo_natarajan", name="Dr. Priya Natarajan (fictional)", relationship="independent",
               credentials="Professor of Computer Science, (fictional) Lakeshore University",
               criteria=["original_contributions", "judging"], status="drafting",
               draft_path="drafts/letters/natarajan.md", last_contact=date(2026, 9, 28)),
        Letter(id="let_demo_webb", name="Marcus Webb (fictional)", relationship="employer",
               credentials="VP Engineering, Fernhill Robotics (fictional)", criteria=["critical_role"],
               status="asked", last_contact=date(2026, 8, 15)),
        Letter(id="let_demo_okafor", name="Dr. Lena Okafor (fictional)", relationship="coauthor",
               credentials="Research Scientist, (fictional) Meridian Labs", criteria=["scholarly_articles"],
               asks=["letter", "membership_ref"]),
    ])))  # fmt: skip
    (ws.root / "drafts/letters/natarajan.md").write_text(
        "# Draft — letter from Dr. Priya Natarajan (fictional)\n\n"
        "_Demo draft. The letter-draft skill (Phase 2) writes these per writer × criterion, citing only "
        "approved claims._\n"
    )
    shutil.rmtree(ws.cache_dir.parent, ignore_errors=True)  # cache is local-only, never shipped
    board = ws.after_change()
    print(f"demo written to {TARGET}: {board.banked} banked / {board.threshold} needed")


if __name__ == "__main__":
    main()
