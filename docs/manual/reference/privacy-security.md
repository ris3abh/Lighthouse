# Privacy and security

What Area O1 protects, how, and the complete list of places it connects to.

Area O1 handles sensitive personal data (immigration evidence, salary, correspondence) and access tokens. It's designed so that data stays on your computer. For day-to-day habits, see [Privacy habits](../best-practices/privacy.md).

## Code is public, the case is private

No personal data belongs in the app repository. Your case lives in a separate workspace folder created on the first run (`~/AreaO1`) or by `areao1 init`: a git repo of plain files that's yours. Back it up only to a private remote. If you contribute code too, see [Keep case and code apart](../best-practices/two-repos.md).

## The dashboard is for your computer only

- `areao1 up` binds to `127.0.0.1`. Nothing else on your network can reach it. The host isn't configurable.
- The server rejects requests whose `Host` header isn't `127.0.0.1` or `localhost`. This blocks DNS-rebinding attacks, where a web page tricks your browser into talking to a local server under another name.
- Every write requires an `X-AreaO1: 1` header. A cross-site page can't send that header, so another site open in your browser can't change your workspace.
- Evidence previews (from `evidence/`), uploads waiting to be filed and letter drafts (from `drafts/`) are served with `Content-Security-Policy: sandbox`, so a file you upload can't run scripts in the dashboard.

## Secrets live in the keychain

- Tokens, webhook URLs, the SMTP password, the Gmail app password and your OpenAI key go to the OS keychain through [keyring](https://pypi.org/project/keyring/), under the service name `areao1`.
- If no keychain is available, they go to a `.env` file in the workspace, which is gitignored.
- Workspace files only store the keychain entry name (`secret_ref`), never the secret. `data/sources.json` names the entry for a private source; `areao1.yaml` names the entry for a notification channel.
- An environment variable `AREAO1_<REF>` (for example `AREAO1_NOTIFY_SLACK` for `notify:slack`) overrides the keychain, and `OPENAI_API_KEY` works when no key is saved in Settings.

Manage secrets with `areao1 secret set <ref>` and `areao1 secret delete <ref>`.

## Read-only tokens

Connectors only read. Use the minimum scopes:

- **GitHub**: a fine-grained personal access token with *Metadata: read* and *Contents: read*. Add *Administration: read* only if you want GitHub's 14-day traffic numbers.
- **Hugging Face**: a *read* token.

## No telemetry

Area O1 has no analytics, crash reporting or usage tracking. It doesn't check for updates.

## Every network call

These are the only places Area O1 connects to, and only when the feature is on:

| Destination | When | What |
|---|---|---|
| The sources you connect | `areao1 import`, the `sync` and `metrics-snapshot` jobs | GitHub, Hugging Face, Semantic Scholar, OpenAlex, arXiv, ORCID, or the website you added. Read only. |
| OpenAI (`api.openai.com`) | When you use the agent: chat, missions, letter drafts, the rule check, model mail sorting | Requests use the Responses API with `store: false`, so OpenAI doesn't store the conversation. Emails, phone numbers and currency amounts are removed first (`privacy.redact_before_llm`). Conversations are saved in your workspace (`agent/conversations/`). |
| Gmail (`imap.gmail.com`, `smtp.gmail.com`) | Only if you connect Gmail | The mailbox is opened read-only and messages are fetched with `PEEK`, so nothing is marked read, moved or labelled. Area O1 sends only the drafts you approve. |
| Official pages in `vault/sources.yaml` | The `vault-watch` job, `areao1 vault sync` | eCFR, USCIS, State Department, Federal Register and court opinion pages, fetched for the knowledge vault |
| Federal Register and eCFR change feeds | The `vault-watch` job | To notice when a relevant rule changes |
| The community snapshot library (`raw.githubusercontent.com/ris3abh/areao1-community-vault`) | The `vault-watch` job | Hash-verified copies of official pages that block automated reading. Turn off with `vault: {community: false}`. |
| Event pages, Devpost or MLH | The daily opportunity check, if on and `opportunities.verify_on_web` is true | To confirm an invitation's event and date |
| Your notification channels | When a notification is routed to them | Slack, Discord, ntfy or your SMTP server, as you configure. Desktop notifications stay on your computer. |

Turn the whole vault off with `vault: {enabled: false}` in `areao1.yaml`.

One more call can happen once: if you upgrade from an old version that connected Google with OAuth, Area O1 revokes that old token at Google on start and removes it from the keychain.

The installers (`install.sh`, `install.ps1`) download uv and the Area O1 release from GitHub. That's the installer, not the app.

## The capture extension's limits

The optional browser extension saves official pages that block automated reading. It:

- has only the `storage` and `scripting` permissions, plus access to the vault's official domains and `127.0.0.1`
- reads a page only when its address matches one of the vault's sources exactly, and only when you visit it
- never opens, reloads or fetches pages on its own
- sends the page only to Area O1 on `127.0.0.1`, with a capture token (Area O1 stores only the token's hash)

**Share captures with the community library** is off by default. When on, it prepares captures of public U.S. government pages in a local outbox; nothing is uploaded automatically. See [Capture extension and community vault](../how-it-works/extension.md).

## The pre-commit secret scan

`areao1 init` installs a git pre-commit hook in the workspace that runs [gitleaks](https://github.com/gitleaks/gitleaks) on staged changes and blocks commits that contain tokens or keys. If gitleaks isn't installed, the hook skips the scan and prints a warning. It can't recognize a passport scan or a pay stub, so it's no substitute for keeping the workspace private.

## Report a vulnerability

Please report vulnerabilities privately through GitHub's **Report a vulnerability** (Security advisories) on the [repository](https://github.com/ris3abh/areao1/security), not in a public issue. Include steps to reproduce and the affected version (`areao1 --version`). The aim is to acknowledge reports within 7 days.

Contributors: run `gitleaks detect` before pushing, and never commit a real workspace, real tokens or real personal data. Test fixtures must be recorded against fictional or public data only. The full policy is in [SECURITY.md](https://github.com/ris3abh/areao1/blob/main/SECURITY.md).
