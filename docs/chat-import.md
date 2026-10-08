# Importing your AI chat history

Drop a Claude or ChatGPT data export (the `.zip`, its folder, or the JSON files) on Onboarding's chat step or
Sources. Area O1 reads it in memory, follows any `manifest.json` to the files it lists, scores each conversation and
project for relevance locally, and shows a picker: only what you tick is read further, on the cheap model tier, and
everything it proposes is self-reported (it organizes your case; it never counts as evidence).

## Formats

- **ChatGPT**: `conversations.json` (a list of conversations with a `mapping` of messages).
- **Claude**: `conversations.json` (conversations with `chat_messages`) and `projects.json`.
- **Anything else** is named in a plain message ("not a Claude or ChatGPT format I know"), never dropped silently.

## A new export layout

Exports change. Claude has also shipped a layout with a manifest and dated files per conversation, and the adapter
for it waits for a **redacted sample**: replace names, emails and message text with placeholders, keep the file
names, the folder structure and every JSON key. With one, adding the layout is a small registered adapter in
`areao1/sources/chat_intake.py`:

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

plus a test with the redacted sample as a fixture. Registered adapters are tried before the built-in ones.
