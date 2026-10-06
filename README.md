# Lighthouse

**Evidence-grounded memory for long-running LLM agents, first applied to O-1A / EB-1A.**

In practice: a local-first command center for building an extraordinary-ability immigration case (O-1A now,
EB-1A too, more via community profiles) that anyone can install and use out of the box. Provenance follows the
[W3C PROV](https://www.w3.org/TR/prov-overview/) model; Lighthouse makes no performance claims beyond what its
evaluation harness measures (coming in a later phase).

Point Lighthouse at your work — GitHub, Hugging Face (more connectors coming) — and it turns it into a living
evidence file: a criteria scoreboard, a metrics trend, an evidence inbox, and a web dashboard. Your case lives
in a **private workspace directory** on your machine (its own Git repo); this repo only holds the app.

> **Not legal advice.** Lighthouse is not legal advice and is not affiliated with USCIS. Criteria profiles
> are community-maintained summaries of public regulations (8 CFR 214.2(o), 8 CFR 204.5(h)). Always confirm
> strategy with an immigration attorney. See [DISCLAIMER.md](DISCLAIMER.md).

## Status

**Phase 0 (core + dashboard)** — see [SPEC.md](SPEC.md) for the full plan and [TODO.md](TODO.md) for progress.

| Works today | Coming next (Phase 1+) |
|---|---|
| `init`, `import`, `run sync / metrics-snapshot / dashboard`, `up`, `validate` | scheduler, notifications |
| GitHub (public + fine-grained PAT, incl. 14-day traffic history) | Website, Semantic Scholar, OpenAlex, ORCID, arXiv |
| Hugging Face (models, datasets, Spaces, linked Papers) | Gmail triage, opportunity scans |
| O-1A + EB-1A rubrics, rule-based scoreboard | MCP server, Claude Code / Codex agent, chat |
| Dashboard: Overview, Inbox, Evidence, Metrics, Sources | Pipeline, Letters, Calendar, Opportunities |

## Quick start

Lighthouse isn't on PyPI yet. From a checkout:

```sh
git clone https://github.com/rishabhsharma/lighthouse && cd lighthouse
pipx install -e .                 # or: uv tool install -e .  /  pip install -e .
npm --prefix web install && npm --prefix web run build   # builds the dashboard into the package

lighthouse-gc up --demo           # try it on the fictional "Alex Rivera" workspace, no network needed
```

Your own case:

```sh
lighthouse-gc init ~/my-case --name "Your Name" --profile o1a
cd ~/my-case
lighthouse-gc import https://github.com/<you>
lighthouse-gc import https://huggingface.co/<you>
lighthouse-gc import https://github.com/<you>/<private-repo> --private   # prompts for a read-only token
lighthouse-gc up                  # http://127.0.0.1:7777
```

Then push `~/my-case` to a **private** remote if you want a backup. Never make it public.

## ⚠️ Contributing *and* using Lighthouse for your own case? Keep two separate repos

If you contribute to Lighthouse and also use it for your own filing, keep **two completely separate
repositories**:

| Repo | What goes in it | Visibility |
|---|---|---|
| **Your fork of this app repo** | code, profiles, connectors, docs, fictional fixtures only | public |
| **Your case workspace** (created with `lighthouse-gc init`) | your evidence, letters, metrics, personal data | **private** |

- Never create your case workspace inside your fork, and never copy filing documents, screenshots, real
  metrics or personal data into the fork, not even into `examples/` or test fixtures.
- Make the workspace a **fresh private repo**, not a fork: GitHub forks of a public repo can't be made private.
- Keep them in different folders (e.g. `~/code/lighthouse` and `~/my-case`), and check `git remote -v`
  before you push.
- The workspace's gitleaks pre-commit hook blocks tokens, but it can't recognize a passport scan or a pay stub.
  Keeping the repos separate is what protects your documents.

## How it works

1. **Connectors** (`lighthouse_gc/sources/`) discover your repos / models / datasets, snapshot their metrics
   into `data/metrics.csv`, and propose evidence **candidates**.
2. Candidates land in the **Inbox**. Nothing becomes evidence until you accept it. Accepting writes a capture
   file to `evidence/<criterion>/<crit>_<yyyy-mm-dd>_<slug>.md` and logs it in `data/exhibits.json`.
3. The **criteria engine** scores your exhibits against a YAML profile (`profiles/o1a.yaml`,
   `profiles/eb1a.yaml`): each criterion is `banked`, `building`, `gap` or `dropped`. Switching profiles
   re-scores the same evidence.
4. `DASHBOARD.md` and the web dashboard show where you stand.

All workspace data is plain JSON / CSV / Markdown with JSON Schemas (`lighthouse_gc/core/schemas/`), so you,
the dashboard, and any agent all edit the same files.

## Commands

| Command | What it does |
|---|---|
| `lighthouse-gc init <dir>` | create a private workspace (git repo + gitleaks pre-commit hook) |
| `lighthouse-gc import <url>` | add a source; auto-detects GitHub / Hugging Face (`--private` for a token) |
| `lighthouse-gc run sync` | refresh all sources, push new candidates to the Inbox |
| `lighthouse-gc run metrics-snapshot` | append today's metrics (and GitHub's 14-day traffic) to `metrics.csv` |
| `lighthouse-gc run dashboard` | re-score and regenerate `DASHBOARD.md` |
| `lighthouse-gc up [--demo]` | serve the dashboard on `127.0.0.1:7777` |
| `lighthouse-gc validate` | check every workspace file against its schema and naming rules |

`run` jobs are headless, so cron / launchd / GitHub Actions can call them until the built-in scheduler lands.

## Security and privacy

- Server binds to `127.0.0.1` only; foreign Host headers and cross-site writes are rejected.
- Tokens go to the OS keychain (`keyring`), with a gitignored `.env` fallback. `sources.json` only stores the
  keychain entry name.
- Use **read-only** tokens: GitHub fine-grained PAT with Metadata + Contents read (Administration read only
  if you want traffic); Hugging Face read token.
- No telemetry. The only network calls are to the sources you connect.

See [SECURITY.md](SECURITY.md).

## Development

```sh
uv venv && uv pip install -e '.[dev]'
.venv/bin/pytest                 # all tests use recorded fixtures, no live network
.venv/bin/ruff check . && .venv/bin/mypy
npm --prefix web run dev         # Vite dev server, proxies /api to 127.0.0.1:7777
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding connectors and profiles.

## License

[Apache-2.0](LICENSE).
