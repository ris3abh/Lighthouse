# 0013. The front door: one line to a running onboarding

- Status: accepted
- Date: 2026-10-07
- Phase: build Part S (S1–S5), between Parts C and D

## Context

Onboarding (ADR 0008) starts once the dashboard is open, but getting there took a git clone, Python, pipx,
Node (to build the UI), `init` with a directory and `up` with that directory. Chat also required the Claude
Code CLI on PATH, although `claude-agent-sdk` ships its own copy. Every one of those steps loses people who
would get the most from Lighthouse: researchers, analysts and engineers who are not Python developers.

People hear about Lighthouse from a link. The first place they land is the landing page or the top of the
README, so that is where getting started has to begin and, ideally, end.

## Decision

1. **One command, no arguments.** `lighthouse-gc` alone starts Lighthouse. The first time, it creates a
   private workspace at `~/Lighthouse` (or `$LIGHTHOUSE_GC_HOME`), remembers it in the user config file
   (`~/.config/lighthouse-gc/config.json`; `%APPDATA%` on Windows), serves it and opens the browser into
   onboarding. Later runs reopen the remembered workspace. `init` and `up -w` stay for anyone with several
   cases or a custom location.
2. **The wheel is the product.** Releases build the UI and attach the wheel to the GitHub release; CI
   installs that wheel in a clean virtualenv and checks the dashboard is served. No Node or checkout is
   needed to use Lighthouse. Publishing to PyPI uses trusted publishing once the owner configures it; until
   then the installer uses the release wheel.
3. **A one-line installer.** `install.sh` (macOS, Linux) and `install.ps1` (Windows) install `uv` if
   missing, install Lighthouse as a `uv` tool on Python 3.12, then run `lighthouse-gc`. They are short
   enough to read before running and make no other change to the machine. CI runs them against a local wheel.
4. **AI is optional and set up in the app.** Everything except chat and agent runs works without a model.
   Onboarding gets a "Connect your AI" step, also in Settings: use the Claude Code login already on the
   machine if there is one, or paste an Anthropic API key (stored in the OS keychain, checked with a free
   model-list request, never written to the workspace). The step says what runs cost and that the monthly
   cap applies. The bundled CLI counts as available; PATH is no longer required.
5. **The landing page is static.** `docs/site/` holds a single page served by GitHub Pages: what Lighthouse
   is, the one line, a screenshot, what you need (a LinkedIn PDF; optionally an API key), the privacy
   promise and the not-legal-advice note. The README opens with the same three things.

A double-click desktop app (signed .dmg / .msi) is deliberately deferred: it needs signing certificates and
an update channel, and the one-line installer reaches the same audience first.

## Consequences

- The default workspace lives in the home directory, outside any app checkout, which keeps the two-repo rule
  by default.
- Releases become the distribution channel, so a tag must only be pushed from a green main.
- The installer pins nothing beyond "latest release"; a broken release breaks new installs until the next
  one, so release CI runs the same smoke test as the installer.
