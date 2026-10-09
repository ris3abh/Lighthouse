# Bulk review in the Inbox

A chat import can bring hundreds of suggestions at once. Bulk review lets you filter the Inbox, select many items
and decide them together, with one Undo for the whole batch.

Every decision in a batch still goes through the same rules as a single click, one item at a time. See [Review in
the Inbox](review.md) for what each decision does.

## How the Inbox is grouped

The [Inbox](../tour/inbox.md) shows:

1. **Evidence**, one card per criterion, in your profile's order. Items with no criterion yet are under "Needs a
   criterion".
2. **Trackers**, one card per kind: deadlines, pipeline ideas, letter writers, updates and metrics. These never
   count toward a criterion.
3. **Notes from your chats and tools**, last and collapsed. See [Notes are low priority](#notes-are-low-priority).

A group shows 50 items at first. **Show N more** shows the rest.

## Filters

Above the list, three filters narrow what's shown:

| Filter | Choices |
|---|---|
| **From** | Where items came from, with a count each: a chat export by provider and import day ("ChatGPT export, Oct 7"), "Agent suggestions" by day, "Gmail", "From your AI tools (MCP)", "Your uploads", or a source. |
| **Kind** | Evidence, Deadlines, Pipeline ideas, Letter writers, Updates, Metrics or Notes. |
| **Contains** | Words in the title or summary. |

The count beside the filters says how many items are shown, such as "20 of 397 shown". **Clear filters** resets
all three.

## Selecting

- **Click** an item's checkbox to select it.
- **Shift-click** another checkbox to select (or unselect) every item between the two, in the order shown.
- **The checkbox in a group's header** selects the whole group, including items not yet shown. It shows a dash when
  only some are selected.
- With a filter on, **Select all N matching** selects everything that matches.

When you use **Select all N matching**, Area O1 sends the filter itself along with the count you saw. If the Inbox
changed in the meantime, it refuses ("the Inbox changed: 21 items match now, not 20. Look again.") instead of
deciding items you didn't see.

## Batch actions

The bulk bar appears when you've selected something or turned on a filter. It shows how many are selected and
these buttons:

| Button | What it does |
|---|---|
| **Accept** | Accepts each selected item. Trackers are added to your deadlines, pipeline, letters and metrics. |
| **Reject** | Rejects each item. Rejected items don't come back on a re-import. |
| **Snooze 7d** | Hides each item for 7 days. |
| **Clear** | Unselects everything. |

If the selection includes evidence, **Accept** first asks "Accept as evidence?" and lists the items. **File N
exhibits** files them under their criteria and approves the claims behind them; **Cancel** stops. Without that
confirmation, evidence isn't accepted.

An item that fails its own rules is skipped and stays in the Inbox, for example a self-reported item, which can't
become an exhibit, or one the rule check blocks. The message says how many were done and why the first one wasn't,
such as "Accepted 18 items · 2 not: self-reported items can't become exhibits; upload the underlying document
instead".

## Keyboard keys

| Key | What it does |
|---|---|
| `j` | Move to the next card. |
| `k` | Move to the previous card. |
| `x` | Select or unselect the card you're on. |
| `a` | Press the card's **Accept**, **Add…** or **Keep…** button. |
| `r` | Press the card's **Reject** or **Dismiss** button. |

The card you're on has an outline. Keys do nothing while you're typing in a field, while a dialog is open, or with
Cmd, Ctrl or Alt held. `a` and `r` decide one card, the same as clicking its button, so they don't ask for
confirmation and aren't part of a batch.

## One Undo per batch

After a batch, a banner repeats what happened, with **Undo batch**. It undoes every decision in that batch, newest
first:

- every item goes back to the Inbox as pending, and a snooze is cleared,
- what accepting created is taken out: an exhibit and its file, a deadline, a pipeline item or a letter writer,
- the claims behind each item are reopened.

Memory is append-only, so undoing doesn't erase your decision. It records a new "reopened" decision for each claim
in `memory/decisions.jsonl`. The earlier approval or rejection stays on record, and the newer decision wins.

If a record changed again after the batch, Undo leaves it alone and says so, for example "Undone: 18 items back in
the Inbox; 2 left (…)". A batch can be undone once. The banner shows your most recent batch.

## Notes are low priority

A [chat import](../connectors/chat-imports.md) keeps a note only when it names a person (someone in your contacts or
letters counts), a date or deadline, or a case item such as judging, reviewing, an award, press, a paper, a
membership, a letter or the visa. Deadlines, pipeline ideas and letter writers always come through. Near-identical
items are merged, within the import and against everything already in your Inbox, decided or not.

The notes that remain are low priority. They sit last, in a collapsed group marked "Low priority · self-reported ·
never evidence". Filtering **Kind** to Notes opens it. To clear many at once, filter **From** to the export and
**Kind** to Notes, press **Select all N matching**, then **Reject**. If you change your mind, **Undo batch** brings
them all back.
