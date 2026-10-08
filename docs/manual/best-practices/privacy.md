# Privacy habits

Small habits that keep your case data on your computer and out of places it doesn't belong.

Area O1 is built to keep your data local: it serves the dashboard only to your computer, stores secrets in your OS keychain and sends no telemetry. The full list of what it sends where is on [Privacy and security](../reference/privacy-security.md). These habits cover the parts that are up to you.

## Back up only to a private remote

Your workspace is its own git repo of plain files. Area O1 doesn't commit or push for you. To back it up, commit and push it to a **private** remote you control. Never make it public, and never push it to a fork of a public repo (forks can't be made private). If you also contribute code, read [Keep case and code apart](two-repos.md).

Other backups work too: an encrypted disk image, or your usual encrypted backup of your home folder. Whatever you use, check it's encrypted and private.

## Be careful what you paste into chats

The Area O1 agent removes emails, phone numbers and currency amounts from what it sends to OpenAI (`privacy.redact_before_llm`, on by default). Other chat tools don't do that for you.

- Don't paste passport numbers, A-numbers, receipt numbers, salary figures or full documents into any AI chat unless you're comfortable with that service keeping them.
- When you use Area O1 from another agent through MCP, that agent reads your workspace through read-only tools. What it sends to its own provider is governed by that agent's settings, not Area O1's.
- Chat exports you import are read on your computer. Only conversations that produced a suggestion are saved in your workspace (unless you use `--keep-all`).

## Keep notifications minimal

Desktop notifications stay on your computer. Email, Slack, Discord and ntfy leave it. For those channels, set `detail: minimal` so they carry counts only ("2 deadlines this week"), never titles:

```yaml
notifications:
  channels:
    phone: {kind: ntfy, topic: pick-an-unguessable-topic, detail: minimal}
```

For ntfy, pick a long, unguessable topic: anyone who knows a public topic name can read it.

## Use read-only tokens

Connectors only read, so give them only read access:

- **GitHub**: a fine-grained personal access token with *Metadata: read* and *Contents: read*. Add *Administration: read* only if you want traffic numbers.
- **Hugging Face**: a *read* token.

Store tokens with `areao1 import <url> --private` (it prompts and saves to the keychain) or `areao1 secret set <ref>`. Never put a token in `areao1.yaml` or any tracked file.

## Use an app password for Gmail

Area O1 connects to Gmail with an app password, not your Google password. It reads mail without marking it read and sends only drafts you approve.

- Create a dedicated app password for Area O1, so you can revoke it alone.
- To disconnect, use Settings > Gmail, then remove the app password on Google's App passwords page. Google has no way for Area O1 to revoke it for you.

## Check your employer's mail policy

Connect a personal Gmail account. Don't connect a work or school account unless your employer's policy allows third-party mail access, and remember an admin may have IMAP turned off for a reason. Case mail sent to a work address can still be saved as `.eml` and imported, if your policy allows that.

## Deleting a case

There's no purge command yet (it's on the [roadmap](../reference/roadmap.md)). To remove a case by hand:

1. Stop Area O1 (Ctrl+C in its terminal).
2. Delete the workspace folder (by default `~/AreaO1`), and any private remote or backup of it.
3. Remove its secrets from the keychain with `areao1 secret delete <ref>` for each one you stored, for example `areao1 secret delete openai:api_key` and `areao1 secret delete google:app-password`.
4. Revoke the tokens at their source: the GitHub token, the Hugging Face token, the Gmail app password, and the OpenAI key if you made one just for this.
5. Optionally remove the small user config file that remembers your last workspace: `~/.config/areao1/` (`%APPDATA%\areao1` on Windows).

See the [FAQ](../reference/faq.md) for removing the app itself.
