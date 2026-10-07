# Security

Area O1 handles sensitive personal data (immigration evidence, salary, correspondence) and access tokens.
The app is designed so that data stays on your machine.

## Design guarantees

- **Code is public, the case is private.** No personal data belongs in this repository. Your case lives in a
  separate workspace directory created by `areao1 init`.
- **Localhost only.** `areao1 up` binds to `127.0.0.1`. The server rejects requests whose `Host` header
  isn't `127.0.0.1` / `localhost` (DNS-rebinding protection) and requires an `X-AreaO1: 1` header on every
  write, which cross-site pages can't send.
- **Secrets never in Git.** Tokens are stored in the OS keychain via `keyring`, or a gitignored `.env` in the
  workspace if no keychain is available. Workspace files only hold the keychain entry name.
- **Pre-commit secret scan.** `areao1 init` installs a Git pre-commit hook that runs
  [gitleaks](https://github.com/gitleaks/gitleaks) on staged changes and blocks commits that contain secrets.
- **Read-only tokens.** Connectors only read. Use the minimum scopes:
  - GitHub fine-grained PAT: *Metadata: read*, *Contents: read*; add *Administration: read* only for traffic.
  - Hugging Face: a *read* token.
- **No telemetry.** The only outbound calls are to the sources you connected.
- **Evidence previews** are served with `Content-Security-Policy: sandbox` and only from `evidence/`.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's "Report a vulnerability" (Security advisories) on this
repository rather than opening a public issue. Include steps to reproduce and the affected version. We aim to
acknowledge reports within 7 days.

## Before you push this repo

Contributors: run `gitleaks detect` before pushing, and never commit a real workspace, real tokens, or real
personal data. Test fixtures must be recorded against fictional or public data only.
