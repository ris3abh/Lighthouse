# Area O1

**Your O-1A / EB-1A evidence file, built on your own computer.**

Area O1 turns your work (papers, code, talks, press, judging) into a living evidence file for an
extraordinary-ability case: a criteria scoreboard, an evidence inbox, metrics, deadlines, letters and a
dashboard. Start from your LinkedIn PDF; it takes a few minutes.

## Install and start

macOS / Linux, in Terminal:

```sh
curl -LsSf https://raw.githubusercontent.com/ris3abh/areao1/main/install.sh | sh
```

Windows, in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/ris3abh/areao1/main/install.ps1 | iex"
```

It installs [uv](https://docs.astral.sh/uv/) if you don't have it, installs Area O1, and opens it in your
browser; nothing else on your machine changes. The scripts are short: read [install.sh](install.sh) or
[install.ps1](install.ps1) first. Afterwards, start it again with `areao1`. The first run creates your
private workspace at `~/AreaO1`.

## What you need

- **Your LinkedIn profile as a PDF** (on LinkedIn: Profile > More > Save to PDF). It's read on your computer,
  with emails and phone numbers removed first. You can also skip it.
- **Optionally, an Anthropic API key** for chat and web lookups (everything else works without one).

Area O1 runs on your computer and serves the dashboard only to it (127.0.0.1). Your case is a folder of
plain files in its own git repo, and it's yours.

**Coming from Lighthouse?** This is the same project under its new name (ADR 0010). Your workspace, settings,
keychain entries and environment variables are picked up and moved on the first run, with a one-line notice
for each, and `lighthouse-gc` still works for now (it tells you the new name).

## About

Evidence-grounded memory for long-running LLM agents, first applied to O-1A / EB-1A.

In practice: a local-first command center for building an extraordinary-ability immigration case (O-1A now,
EB-1A too, more via community profiles) that anyone can install and use out of the box. Provenance follows the
[W3C PROV](https://www.w3.org/TR/prov-overview/) model; Area O1 makes no performance claims beyond what its
evaluation harness measures (coming in a later phase).

Point Area O1 at your work — GitHub, Hugging Face, Semantic Scholar, OpenAlex, arXiv, ORCID, any web page — and it turns it into a living
evidence file: a criteria scoreboard, a metrics trend, an evidence inbox, and a web dashboard. Your case lives
in a **private workspace directory** on your machine (its own Git repo); this repo only holds the app.

> **Not legal advice.** Area O1 is not legal advice and is not affiliated with USCIS. Criteria profiles
> are community-maintained summaries of public regulations (8 CFR 214.2(o), 8 CFR 204.5(h)). Always confirm
> strategy with an immigration attorney. See [DISCLAIMER.md](DISCLAIMER.md).

## Status

**Phase 0 and Phase 1a–1b are done** (core, dashboard, imports, alerts, trackers). See [SPEC.md](SPEC.md) for the full plan and [TODO.md](TODO.md) for progress.

| Works today | Coming next (Phase 1+) |
|---|---|
| Drag-and-drop evidence into the Inbox; read-only MCP server for agents | Letter drafting (agent) |
| Notifications, scheduler, deadline alerts, weekly digest | |
| Calendar (+ `.ics` feed), Pipeline kanban, Letters roster | |
| Claude / ChatGPT export import → deadline, pipeline and letter-writer suggestions | LLM-assisted extraction |
| `init`, `import`, `run <job>`, `up`, `validate`, `notify`, `secret`, `mcp` | `export`, `purge` |
| GitHub (public + fine-grained PAT, incl. 14-day traffic history) | |
| Hugging Face (models, datasets, Spaces, linked Papers) | Gmail triage, opportunity scans |
| Semantic Scholar, OpenAlex, arXiv, ORCID (papers, citations, venues, h-index) | |
| Website: any page or sitemap (readability text; mentions → press / award proposals; bot-blocked pages marked unreadable) | |
| O-1A + EB-1A rubrics, rule-based scoreboard | MCP write tools (through the Inbox), Claude Code / Codex agent, chat |
| Dashboard: Overview, Inbox, Evidence, Metrics, Pipeline, Letters, Calendar, Sources, Settings | Opportunities, Chat |

## From a checkout, and more than one case

To work on Area O1 itself, install it from a checkout:

```sh
git clone https://github.com/ris3abh/areao1 && cd Area O1
pipx install -e .                 # or: uv tool install -e .  /  pip install -e .
npm --prefix web install && npm --prefix web run build   # builds the dashboard into the package

areao1 init ~/my-case      # an empty, private workspace (a git repo of plain files)
areao1 up -w ~/my-case     # opens onboarding: start from your LinkedIn PDF, or skip
```

A case in a place you choose (or a second case), from the command line:

```sh
areao1 init ~/my-case --name "Your Name" --profile o1a
cd ~/my-case
areao1 import https://github.com/<you>
areao1 import https://huggingface.co/<you>
areao1 import https://github.com/<you>/<private-repo> --private   # prompts for a read-only token
areao1 up                  # http://127.0.0.1:7777
```

Then push `~/my-case` to a **private** remote if you want a backup. Never make it public.

## ⚠️ Contributing *and* using Area O1 for your own case? Keep two separate repos

If you contribute to Area O1 and also use it for your own filing, keep **two completely separate
repositories**:

| Repo | What goes in it | Visibility |
|---|---|---|
| **Your fork of this app repo** | code, profiles, connectors, docs, fictional fixtures only | public |
| **Your case workspace** (created with `areao1 init`) | your evidence, letters, metrics, personal data | **private** |

- Never create your case workspace inside your fork, and never copy filing documents, screenshots, real
  metrics or personal data into the fork, not even into `examples/` or test fixtures.
- Make the workspace a **fresh private repo**, not a fork: GitHub forks of a public repo can't be made private.
- Keep them in different folders (e.g. `~/code/areao1` and `~/my-case`), and check `git remote -v`
  before you push.
- The workspace's gitleaks pre-commit hook blocks tokens, but it can't recognize a passport scan or a pay stub.
  Keeping the repos separate is what protects your documents.

## How it works

1. **Connectors** (`areao1/sources/`) discover your repos / models / datasets, snapshot their metrics
   into `data/metrics.csv`, and propose evidence **candidates**.
2. Every raw response becomes an **observation** in `memory/`, and every fact drawn from it becomes a **claim**
   that quotes its source verbatim, with offsets (e.g. `"stargazers_count": 1840` from
   `api.github.com/repos/…`). Claims are append-only: a new value supersedes the old one, and nothing is
   overwritten, so you can ask what was known on any date.
3. Candidates land in the **Inbox**, where you can expand the exact claims behind each one. Nothing becomes
   evidence until you accept it. Accepting approves those claims, writes a capture file to
   `evidence/<criterion>/<crit>_<yyyy-mm-dd>_<slug>.md`, and logs it in `data/exhibits.json`. Approval records
   your decision; it does not certify legal sufficiency.
4. The **criteria engine** (`areao1/criteria/`) scores exhibits against a YAML profile
   (`profiles/o1a.yaml`, `profiles/eb1a.yaml`): each criterion is `banked`, `building`, `gap` or `dropped`.
   **An invitation is not a completion.** Only completed, published or granted evidence counts. Switching
   profiles re-scores the same evidence.
5. `DASHBOARD.md` and the web dashboard show where you stand.

**Your AI chats, organized.** Drop a Claude or ChatGPT data export on the Sources page, or run
`areao1 import ~/Downloads/export.zip`. Conversations that produced a suggestion are saved as private
snapshots in your workspace; the rest are read and discarded (add `--keep-all` to keep everything). Area O1 reads only *your* messages (never the assistant's) and suggests deadlines, pipeline items
and letter writers ("I asked Dr. … for a letter", "reviews are due Oct 14"). These are **self-reported**: they
keep your trackers current, but they can never count toward a criterion. For that, upload the real document.

All workspace data is plain JSON / JSONL / CSV / Markdown with JSON Schemas (`areao1/core/schemas/`), so
you, the dashboard, and any agent all read the same files. The core (`areao1/core/`) knows nothing
about immigration. Profiles and scoring live in a separate layer, so other domains can reuse it.

## Commands

| Command | What it does |
|---|---|
| `areao1 init <dir>` | create a private workspace (git repo + gitleaks pre-commit hook) |
| `areao1 import <url>` | add a source; auto-detects GitHub / Hugging Face / Semantic Scholar / OpenAlex / arXiv / ORCID / any web page or sitemap (`--private` for a token) |
| `areao1 import <export>` | import a Claude / ChatGPT export (`conversations.json` or the `.zip`) |
| `areao1 run sync` | refresh all sources, push new candidates to the Inbox |
| `areao1 run metrics-snapshot` | append today's metrics (and GitHub's 14-day traffic) to `metrics.csv` |
| `areao1 run dashboard` | re-score and regenerate `DASHBOARD.md` |
| `areao1 up` | serve the dashboard on `127.0.0.1:7777`; a new workspace opens into onboarding |
| `areao1 validate` | check every workspace file against its schema and naming rules |
| `areao1 notify test` | send a test notification to every routed channel |
| `areao1 secret set <ref>` | store a token / webhook URL / SMTP password in the OS keychain |
| `areao1 mcp` | MCP server over stdio for Claude Code, Claude desktop or any MCP client: read tools plus `propose_context`, which sends notes to your Inbox ([setup](docs/mcp.md)) |

### Ask the agent

Click **Ask** on any page to open the chat panel. The agent (Claude, through the Claude Agent SDK) reads
your workspace and the web. Each step is shown as it happens: searches, pages read, which workspace files
a tool touched. It can't change anything itself. Suggestions land in your **Inbox** and link there, and
evidence it proposes must quote the page it read, word for word. Conversations are saved in your
workspace (`agent/conversations/`); nothing is kept in `~/.claude`. You need Claude Code installed and logged
in (or `ANTHROPIC_API_KEY`). Spend is capped per run and per month in `areao1.yaml`:

```yaml
agent:
  models: {chat: claude-opus-5-5, task: claude-opus-5-5, mission: claude-sonnet-5-5}
  effort: medium
  web_search: true
  budget: {per_run_tokens: 300000, per_run_usd: 2.0, monthly_tokens: 10000000, monthly_usd: 50.0}
```

### Notifications

Desktop notifications work out of the box. To add email, Slack, Discord or ntfy, add a channel under
`notifications.channels` in `areao1.yaml` and route events to it:

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

Store secrets in the keychain, never in the file: `areao1 secret set notify:slack`. Then run
`areao1 notify test`. Anything sent to Slack, Discord, email or ntfy leaves your machine, so
`detail: minimal` sends only counts ("2 deadlines this week"), never titles.

### Calendar

Deadlines and pipeline follow-ups are written to `data/calendar.ics` on every change. To subscribe from
Apple Calendar, Outlook or Thunderbird on the same machine, use `webcal://127.0.0.1:7777/calendar.ics` while
`areao1 up` is running, or import the file. Google Calendar can't reach your laptop's localhost, so
import the `.ics` there.

### Gmail

Connect Gmail with an app password (Settings > Gmail): Area O1 reads only the headers of threads with your
contacts and sends only drafts you approve. See [docs/gmail.md](docs/gmail.md).

### Use it from Claude Code (or any MCP client)

```sh
claude mcp add areao1 -- areao1 mcp -w ~/my-case
```

The server is **read-only**: `get_scoreboard`, `list_gaps`, `query_claims(entity, as_of)`,
`get_provenance(claim_id)` and `what_changed(since)`. Agents see each claim's verbatim source quote and review
status, and are told to draft only from approved claims.

### Scheduled jobs

`areao1 up` runs these in the background (edit the cron expressions under `schedules` in
`areao1.yaml`). Runs missed while your laptop was asleep catch up when `up` starts again.

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
- No telemetry. The only network calls are to the sources you connect, the agent's model and web search when
  you use it, and the public sources in the knowledge vault manifest (`vault/sources.yaml`: eCFR, USCIS,
  State Department, Federal Register, court opinions). Turn the vault off with `vault: {enabled: false}` in
  `areao1.yaml`.

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
