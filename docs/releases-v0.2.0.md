# Area O1 v0.2.0 (draft release notes, not published)

Area O1 is a local-first command center for an O-1A or EB-1A evidence file. This release moves the agent to
OpenAI, adds the Memory constellation, a daily opportunity check that verifies invitations, a knowledge vault
that stays current without chores, Gmail with an app password, and letter drafts built only from approved facts.

## Highlights

- **OpenAI engine** (ADR 0015). The Responses API with Area O1's own tools, nothing stored at OpenAI, three model
  tiers one line each in `areao1.yaml` (hard and mid `gpt-6.1-sol`, mundane `gpt-6-luna`), web search capped per run
  and priced in every run's cost. Connect with an OpenAI API key; Claude Code and Codex drive Area O1 over MCP.
- **Memory** (ADR 0012). Every claim a star; click for its provenance trail, replay the case in date order.
- **Daily opportunity check** (ADR 0016). Off by default. Invitations in your mail become Inbox items that are
  verified (sender authentication and the event's official page), unconfirmed (a check-in drafted for your approval)
  or suspicious.
- **Vault without babysitting** (ADR 0011). Federal Register and eCFR change signals; a Chrome capture extension
  (`areao1 extension`); a community library of public-domain government-page snapshots
  (github.com/ris3abh/areao1-community-vault).
- **Gmail** (ADR 0014). An app password, no Google Cloud project; a read-only Mail view; `.eml` and forwarded
  originals with sender checks; sends only after Approve & send, with 10 seconds to undo.
- **Letters**. Drafts from approved claims only, each sentence citing its claims, for the writer to rewrite and sign.

## Upgrading from 0.1.0

- Paste an OpenAI API key in Settings > Your AI. A saved Anthropic key is removed from your keychain on start.
- Reconnect Gmail with an app password if you used the Google sign-in (it's removed on start, and revoked if possible).
- `agent.models` in `areao1.yaml` is now one line per tier; older settings load with the new defaults.

## Install

```sh
curl -LsSf https://raw.githubusercontent.com/ris3abh/areao1/main/install.sh | sh
```

Full list of changes: [CHANGELOG.md](../CHANGELOG.md).
