# Chat-history imports

Drop a Claude or ChatGPT data export, and Area O1 picks out the deadlines, people and plans you mentioned in your
own messages.

If you've been thinking through your case with an AI assistant, those chats hold things worth tracking: "reviews
are due Oct 14", "I asked Dr. Rivera for a letter", a call for speakers you meant to apply to. A chat import turns
them into Inbox suggestions, so your trackers stay current.

!!! note "Self-reported: never counts toward a criterion"
    Everything a chat import suggests is **self-reported**. It helps you stay organized, but your workspace refuses
    to turn it into an exhibit, and the criteria engine ignores it. For evidence, upload the real document (the
    award letter, the thank-you email, the published paper).

## Get your export

| From | Where |
|---|---|
| **Claude** | Settings > Privacy > Export data. You get an email with a `.zip`. |
| **ChatGPT** | Settings > Data controls > Export. You get an email with a `.zip`. |

Choose the longest date range you can when you export.

## Import in the app

You can import on onboarding's **Chat history** step, or later on **Sources > Import your Claude or ChatGPT
history**.

1. Drop the `.zip`, its `.json` files, or the whole folder (or press **Choose a folder**).
2. Area O1 reads it **in memory on your computer**, following any `manifest.json` to the files it lists, and
   recognizes Claude and ChatGPT exports by their shape, not their file names.
3. Every conversation (and every Claude Project) is scored for relevance by local rules, with no model call. The
   picker shows the ones that look related to your case, and why: immigration terms, criteria words, names and
   projects from your profile, people who come up across several chats, dates next to deadline words. Claude
   Projects are weighted highest, since people often keep case material there.
4. Tick what you want and press **Import** (the button counts what you ticked). Nothing is saved until you do, and anything you don't tick leaves
   nothing in your workspace.

For what you ticked, Area O1:

- Saves each conversation or project as a private, self-reported snapshot in your workspace (`memory/`).
- Reads it with the local rules for **deadlines**, **pipeline items** and **letter writers**.
- If you've [connected your AI](../getting-started/openai-key.md), also reads it on the cheap `mundane` tier for
  **people**, **asks** (things you asked for or promised), **deadlines**, **opportunities**, **projects**,
  **links**, **decisions** and **metrics**. The cost shows on the Agent page and counts toward your monthly cap.
  Without a key, or once the monthly cap is reached, only the local rules run.

Each suggestion quotes the exact sentence it came from. A model's suggestion whose quote isn't in your text
character for character is dropped.

## Import from the command line

```sh
areao1 import ~/Downloads/claude-export.zip
areao1 import ~/Downloads/conversations.json
```

The command takes `conversations.json` or the export `.zip`. It doesn't show a picker: it reads every
conversation with the local rules only (deadlines, pipeline items, letter writers) and never calls a model.

Conversations that produced a suggestion are saved as snapshots; the rest are read and discarded. To keep every
conversation:

```sh
areao1 import ~/Downloads/claude-export.zip --keep-all
```

## Only your own messages

Area O1 reads **only your messages**, never the assistant's replies. An AI's statement isn't a fact about you,
so it's never quoted or turned into a suggestion. From a Claude Project, it reads the project's instructions and
knowledge files, which you wrote or chose.

## Formats

| Export | Files |
|---|---|
| ChatGPT | `conversations.json` (conversations with a `mapping` of messages) |
| Claude | `conversations.json` (conversations with `chat_messages`) and `projects.json` |

Files in an export that aren't chats (your account details, memories, settings) are skipped quietly. A file in a
format Area O1 doesn't know is named in a plain message, never dropped silently.

Exports change. Claude has also shipped a layout with a manifest and one dated file per conversation; support for
it is on the [roadmap](../reference/roadmap.md).

## For contributors: adding an export layout

A new layout is a small registered adapter in
[`areao1/sources/chat_intake.py`](https://github.com/ris3abh/areao1/blob/main/areao1/sources/chat_intake.py):

```python
from areao1.sources.chat_intake import Adapter, register_adapter

register_adapter(
    Adapter(
        name="claude_dated",
        label="Claude conversations (dated files)",
        detect=lambda item: isinstance(item, dict) and "conversation_uuid" in item and "turns" in item,
        parse=parse_dated_conversation,  # returns a Conversation (or a Project)
    )
)
```

Add a test with a **redacted sample** as the fixture: replace names, emails and message text with placeholders,
and keep the file names, the folder structure and every JSON key. Registered adapters are tried before the
built-in ones. See [Contributing](../reference/contributing.md).
