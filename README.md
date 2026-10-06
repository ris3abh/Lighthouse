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

**Phase 0 and Phase 1a–1b are done** (core, dashboard, imports, alerts, trackers). See [SPEC.md](SPEC.md) for the full plan and [TODO.md](TODO.md) for progress.

| Works today | Coming next (Phase 1+) |
|---|---|
| Drag-and-drop evidence into the Inbox; read-only MCP server for agents | Letter drafting (agent) |
| Notifications, scheduler, deadline alerts, weekly digest | Google Calendar push |
| Calendar (+ `.ics` feed), Pipeline kanban, Letters roster | |
| Claude / ChatGPT export import → deadline, pipeline and letter-writer suggestions | LLM-assisted extraction |
| `init`, `import`, `run <job>`, `up`, `validate`, `notify`, `secret`, `mcp` | `export`, `purge` |
| GitHub (public + fine-grained PAT, incl. 14-day traffic history) | Website, Semantic Scholar, OpenAlex, ORCID, arXiv |
| Hugging Face (models, datasets, Spaces, linked Papers) | Gmail triage, opportunity scans |
| O-1A + EB-1A rubrics, rule-based scoreboard | MCP write tools (through the Inbox), Claude Code / Codex agent, chat |
| Dashboard: Overview, Inbox, Evidence, Metrics, Pipeline, Letters, Calendar, Sources, Settings | Opportunities, Chat |

## Quick start

Lighthouse isn't on PyPI yet. From a checkout:

```sh
git clone https://github.com/ris3abh/Lighthouse && cd Lighthouse
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
2. Every raw response becomes an **observation** in `memory/`, and every fact drawn from it becomes a **claim**
   that quotes its source verbatim, with offsets (e.g. `"stargazers_count": 1840` from
   `api.github.com/repos/…`). Claims are append-only: a new value supersedes the old one, and nothing is
   overwritten, so you can ask what was known on any date.
3. Candidates land in the **Inbox**, where you can expand the exact claims behind each one. Nothing becomes
   evidence until you accept it. Accepting approves those claims, writes a capture file to
   `evidence/<criterion>/<crit>_<yyyy-mm-dd>_<slug>.md`, and logs it in `data/exhibits.json`. Approval records
   your decision; it does not certify legal sufficiency.
4. The **criteria engine** (`lighthouse_gc/criteria/`) scores exhibits against a YAML profile
   (`profiles/o1a.yaml`, `profiles/eb1a.yaml`): each criterion is `banked`, `building`, `gap` or `dropped`.
   **An invitation is not a completion.** Only completed, published or granted evidence counts. Switching
   profiles re-scores the same evidence.
5. `DASHBOARD.md` and the web dashboard show where you stand.

**Your AI chats, organized.** Drop a Claude or ChatGPT data export on the Sources page, or run
`lighthouse-gc import ~/Downloads/export.zip`. Every conversation is saved as a private snapshot in your
workspace. Lighthouse reads only *your* messages (never the assistant's) and suggests deadlines, pipeline items
and letter writers ("I asked Dr. … for a letter", "reviews are due Oct 14"). These are **self-reported**: they
keep your trackers current, but they can never count toward a criterion. For that, upload the real document.

All workspace data is plain JSON / JSONL / CSV / Markdown with JSON Schemas (`lighthouse_gc/core/schemas/`), so
you, the dashboard, and any agent all read the same files. The core (`lighthouse_gc/core/`) knows nothing
about immigration. Profiles and scoring live in a separate layer, so other domains can reuse it.

## Commands

| Command | What it does |
|---|---|
| `lighthouse-gc init <dir>` | create a private workspace (git repo + gitleaks pre-commit hook) |
| `lighthouse-gc import <url>` | add a source; auto-detects GitHub / Hugging Face (`--private` for a token) |
| `lighthouse-gc import <export>` | import a Claude / ChatGPT export (`conversations.json` or the `.zip`) |
| `lighthouse-gc run sync` | refresh all sources, push new candidates to the Inbox |
| `lighthouse-gc run metrics-snapshot` | append today's metrics (and GitHub's 14-day traffic) to `metrics.csv` |
| `lighthouse-gc run dashboard` | re-score and regenerate `DASHBOARD.md` |
| `lighthouse-gc up [--demo]` | serve the dashboard on `127.0.0.1:7777` |
| `lighthouse-gc validate` | check every workspace file against its schema and naming rules |
| `lighthouse-gc notify test` | send a test notification to every routed channel |
| `lighthouse-gc secret set <ref>` | store a token / webhook URL / SMTP password in the OS keychain |
| `lighthouse-gc mcp` | read-only MCP server over stdio for Claude Code, Codex or any MCP client |

### Notifications

Desktop notifications work out of the box. To add email, Slack, Discord or ntfy, add a channel under
`notifications.channels` in `lighthouse.yaml` and route events to it:

```yaml
notifications:
  channels:
    desktop: {kind: desktop}
    slack: {kind: slack, secret_ref: notify:slack}   # detail defaults to full; use minimal for counts only
    phone: {kind: ntfy, topic: pick-an-unguessable-topic, detail: minimal}
  routes:
    deadline: [desktop, phone]
    digest: [slack]
```

Store secrets in the keychain, never in the file: `lighthouse-gc secret set notify:slack`. Then run
`lighthouse-gc notify test`. Anything sent to Slack, Discord, email or ntfy leaves your machine, so
`detail: minimal` sends only counts ("2 deadlines this week"), never titles.

### Calendar

Deadlines and pipeline follow-ups are written to `data/calendar.ics` on every change. To subscribe from
Apple Calendar, Outlook or Thunderbird on the same machine, use `webcal://127.0.0.1:7777/calendar.ics` while
`lighthouse-gc up` is running, or import the file. Google Calendar can't reach your laptop's localhost, so
import the `.ics` there (a one-way Google push is planned).

### Use it from Claude Code (or any MCP client)

```sh
claude mcp add lighthouse -- lighthouse-gc mcp -w ~/my-case
```

The server is **read-only**: `get_scoreboard`, `list_gaps`, `query_claims(entity, as_of)`,
`get_provenance(claim_id)` and `what_changed(since)`. Agents see each claim's verbatim source quote and review
status, and are told to draft only from approved claims.

### Scheduled jobs

`lighthouse-gc up` runs these in the background (edit the cron expressions under `schedules` in
`lighthouse.yaml`). Runs missed while your laptop was asleep catch up when `up` starts again.

| Job | Default | Does |
|---|---|---|
| `sync` | daily 08:00 | refresh sources; notify about new candidates and errors |
| `metrics-snapshot` | Mondays, every other week | append metrics (and GitHub's 14-day traffic) |
| `deadline-check` | daily 07:00 | alert at 14 / 3 / 1 / 0 days and when overdue; follow-ups; calendar |
| `digest` | Fridays 17:00 | what changed, stale pipeline items, next actions |

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
