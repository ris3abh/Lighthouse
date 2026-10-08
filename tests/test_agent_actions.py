"""Chat can do what the pages do (D1, ADR 0009 §1): every page write maps to a chat tool or is the person's alone;
direct tools exist only in runs the person started, go through the service layer as agent:<run>, can be undone,
and never change what counts toward a criterion."""

from __future__ import annotations

from datetime import date

import anyio
import pytest
from test_agent import _run, _tools
from test_service_layer import SAMPLES

from areao1.agent.actions import TOOL_FOR, YOURS, covered
from areao1.criteria.models import Todo
from areao1.service import Service


def test_every_page_write_is_a_chat_tool_or_the_persons_alone(demo_ws):
    actions = {sample[2] for sample in SAMPLES.values()}
    missing = sorted(a for a in actions if not covered(a))
    assert not missing, f"page writes with no chat tool and no reason in agent/actions.py: {missing}"
    _, chat = _tools(demo_ws, _run(demo_ws, "chat"))
    assert set(TOOL_FOR.values()) <= set(chat)
    for action in YOURS:  # nothing the person decides has a tool
        verb = action.split(".")[-1] or action.rstrip(".")
        assert not [t for t in chat if t.startswith(verb) and action.split(".")[0] in t], action


def test_scheduled_runs_keep_the_inbox_rules(demo_ws):
    _, mission = _tools(demo_ws, _run(demo_ws, "scheduled"))
    assert not set(TOOL_FOR.values()) & set(mission)
    assert {"propose_deadline", "propose_tracker_update"} <= set(mission)


def _call(t, name, args):
    return anyio.run(t[name].handler, args)


def _undo_restores(ws, out: str, read):
    """The tool's change is the person's to undo, and undo puts things back exactly."""
    change = ws.changes()[-1]
    assert f"undo: {change.id}" in out and change.actor.startswith("agent:")
    assert Service(ws).undoable(change)
    before = read()
    Service(ws).undo(change.id)
    return before


@pytest.mark.parametrize(
    ("name", "args", "read"),
    [
        ("add_deadline", {"title": "NeurIPS reviewer signup", "due": "2026-11-03", "kind": "submission"}, "deadlines"),
        ("update_deadline", {"id": "{deadline}", "changes": {"due": "2026-12-01"}}, "deadlines"),
        ("delete_deadline", {"id": "{deadline}"}, "deadlines"),
        ("add_pipeline_item", {"title": "Apply: IEEE Senior Member", "stage": "idea"}, "pipeline"),
        ("update_pipeline_item", {"id": "{pipeline}", "changes": {"stage": "done"}}, "pipeline"),
        ("delete_pipeline_item", {"id": "{pipeline}"}, "pipeline"),
        ("add_letter_writer", {"name": "Dr. Sam Ortiz", "relationship": "independent"}, "letters"),
        ("update_letter_writer", {"id": "{letter}", "changes": {"last_contact": "2026-10-07"}}, "letters"),
        ("delete_letter_writer", {"id": "{letter}"}, "letters"),
        ("update_todo", {"id": "{todo}", "status": "done"}, "todos"),
        ("add_contact", {"name": "Prof. Lee", "emails": ["lee@uni.example"], "relationship": "recommender"}, "contacts"),
        ("update_contact", {"id": "{contact}", "changes": {"next_follow_up": "2026-10-20"}}, "contacts"),
        ("delete_contact", {"id": "{contact}"}, "contacts"),
    ],
)  # fmt: skip
def test_each_direct_tool_applies_through_the_service_and_undoes(demo_ws, name, args, read):
    demo_ws.add_todos(
        [
            Todo(
                id="todo_x",
                kind="judging",
                title="Upload proof of HackSeattle judging",
                item="HackSeattle",
                created=date(2026, 10, 1),
            )
        ]
    )
    ids = {"deadline": demo_ws.deadlines().deadlines[0].id, "pipeline": demo_ws.pipeline().items[0].id,
           "letter": demo_ws.letters().letters[0].id, "todo": "todo_x",
           "contact": demo_ws.add_contact(name="Dr. Sam Ortiz").id}  # fmt: skip
    args = {k: (v.format(**ids) if isinstance(v, str) else v) for k, v in args.items()}
    load = getattr(demo_ws, read)

    def reader():  # records by id (a restored record may come back in a different place in the file)
        data = load().model_dump(mode="json")
        return {r["id"]: r for r in next(v for k, v in data.items() if isinstance(v, list))}

    original = reader()
    scores = {(c.id, c.status) for c in demo_ws.recompute().criteria}
    inbox = len(demo_ws.pending_candidates())
    _, t = _tools(demo_ws, _run(demo_ws, "chat"))
    out = _call(t, name, args)
    assert reader() != original  # applied directly, not proposed
    assert len(demo_ws.pending_candidates()) == inbox
    assert {(c.id, c.status) for c in demo_ws.recompute().criteria} == scores  # never a criterion
    _undo_restores(demo_ws, out, reader)
    assert reader() == original


def test_a_letter_is_never_marked_sent_or_signed_by_chat(demo_ws):
    _, t = _tools(demo_ws, _run(demo_ws, "chat"))
    letter = demo_ws.letters().letters[0]
    with pytest.raises(ValueError, match="only the writer signs"):
        _call(t, "update_letter_writer", {"id": letter.id, "changes": {"status": "signed"}})
    assert demo_ws.letters().letters[0].status == letter.status


def test_undo_change_undoes_by_id(demo_ws):
    _, t = _tools(demo_ws, _run(demo_ws, "chat"))
    out = _call(
        t, "add_deadline", {"title": "Call with the attorney", "due": "2026-10-20", "kind": "personal"}
    )
    change_id = out.rsplit("undo: ", 1)[1]
    assert "Undone" in _call(t, "undo_change", {"change_id": change_id})
    assert not [d for d in demo_ws.deadlines().deadlines if d.title == "Call with the attorney"]


def test_a_read_only_run_gets_read_tools_and_inbox_proposals_only(demo_ws):
    """B18: onboarding lookups run read-only: no direct tracker writes, no autopilot paths, nothing but reading and
    proposing a find to the Inbox."""
    from areao1.agent.tools import READ_ONLY_RUN_WRITES, RunContext, build_tools
    from areao1.core.models import AgentRun

    run = AgentRun(kind="manual", engine="fake", model="test", prompt="lookup", read_only=True)
    tools = build_tools(RunContext(demo_ws, run))
    writes = {t.name for t in tools if not t.read_only}
    assert writes == set(READ_ONLY_RUN_WRITES) and not {t.name for t in tools} & set(TOOL_FOR.values())
    full = {
        t.name
        for t in build_tools(
            RunContext(demo_ws, AgentRun(kind="manual", engine="fake", model="t", prompt="p"))
        )
    }
    assert set(TOOL_FOR.values()) <= full  # a task you start yourself still has them
