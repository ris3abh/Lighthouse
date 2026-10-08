"""Chat can do what the pages do (ADR 0009 §1). Every page write, by its service action, maps to the chat tool
that makes the same change, or is the person's alone with the reason. tests/test_agent_actions.py fails when a
page write has no entry here.

Direct tools only exist in runs the person started (chat, hand-started tasks). Scheduled missions keep the
Inbox and autopilot rules of ADR 0005."""

from __future__ import annotations

# service action -> chat tool. Each one applies directly, is logged with the actor agent:<run>, and can be undone.
TOOL_FOR: dict[str, str] = {
    "deadline.add": "add_deadline",
    "deadline.update": "update_deadline",
    "deadline.delete": "delete_deadline",
    "pipeline.add": "add_pipeline_item",
    "pipeline.update": "update_pipeline_item",
    "pipeline.move": "update_pipeline_item",
    "pipeline.delete": "delete_pipeline_item",
    "letter.add": "add_letter_writer",
    "letter.update": "update_letter_writer",
    "letter.delete": "delete_letter_writer",
    "todo.update": "update_todo",
    "contact.add": "add_contact",
    "contact.update": "update_contact",
    "contact.delete": "delete_contact",
    "outreach.draft": "draft_email",  # a draft only: sending is yours
    "pipeline_item.undo": "undo_change",  # the page's Undo, for any change it can undo
}

INBOX = "Inbox decisions are yours: the agent proposes, you accept, edit, reject or snooze (ADR 0005)."
CRITERION = "It changes what counts toward a criterion, so you do it on the page; the agent links you there."
# service action (or prefix ending in ".") -> why the agent never does it
YOURS: dict[str, str] = {
    "inbox.accept": INBOX,
    "inbox.edit": INBOX,
    "inbox.reject": INBOX,
    "inbox.snooze": INBOX,
    "inbox.upload": "A file you choose to add; the agent can't pick files from your computer.",
    "evidence.upload": "A file you choose to add; the agent can't pick files from your computer.",
    "evidence.remap": CRITERION,
    "evidence.redate": "The date a document shows is something you read off it; the agent can't see your files.",
    "criterion.override": CRITERION,
    "profile.set": CRITERION,
    "vault.promote": "It changes which sources the rule check trusts.",
    "settings.autopilot": "It decides what the agent may do on its own.",
    "settings.missions": "It decides what the agent may do on its own.",
    "settings.agent": "It decides which model answers you and what that costs.",
    "settings.mail": "It decides whether your mail is sent to a model to be sorted.",
    "letter.draft": "You start a letter draft from Letters, so you choose when a model writes in a writer's voice.",
    "settings.opportunities": "It decides whether your mail is read every day for opportunities.",
    "inbox.recheck": "It re-runs the automatic check on the agent's own text.",
    "proof.": "Which document preserves a proof item is your call; the agent proposes matches to the Inbox.",
    "preflight.": "You run and dismiss preflight from Evidence; the agent reads the results (list_preflight_issues).",
    "briefing.recheck": "It re-runs the automatic check on the agent's own text.",
    "onboarding.": "Your own answers about yourself.",
    "outreach.send": "Sending an email in your name needs your approval, every time (ADR 0014 §5).",
    "outreach.edit": "Your words before they go out in your name.",
    "outreach.reject": "Your decision on a draft.",
}

# Where to send the person for an action that's theirs.
WHERE: dict[str, str] = {
    "evidence.remap": "#/evidence",
    "criterion.override": "#/evidence",
    "profile.set": "#/overview",
    "inbox.accept": "#/inbox",
    "settings.autopilot": "#/settings",
}


def covered(action: str) -> bool:
    return action in TOOL_FOR or any(action == k or (k.endswith(".") and action.startswith(k)) for k in YOURS)
