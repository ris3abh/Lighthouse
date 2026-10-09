# Commands

Every `areao1` command, its options, and the jobs it runs on a schedule.

Run `areao1 --help`, or `areao1 <command> --help`, for the same information in your terminal.

## Quick reference

| Command | What it does |
|---|---|
| `areao1` | Open your workspace in the browser, creating `~/AreaO1` the first time |
| `areao1 init <dir>` | Create a private workspace (a git repo with a gitleaks pre-commit hook) |
| `areao1 import <url>` | Add a source; auto-detects GitHub, Hugging Face, Semantic Scholar, OpenAlex, arXiv, ORCID, or any web page or sitemap (`--private` for a token) |
| `areao1 import <export>` | Import a Claude or ChatGPT export (`conversations.json` or the `.zip`) |
| `areao1 run sync` | Refresh all sources and push new candidates to the Inbox |
| `areao1 run metrics-snapshot` | Append today's metrics (and GitHub's 14-day traffic) to `data/metrics.csv` |
| `areao1 run dashboard` | Re-score the criteria and regenerate `DASHBOARD.md` |
| `areao1 up` | Serve the dashboard on `127.0.0.1:7777`; a new workspace opens into onboarding |
| `areao1 validate` | Check every workspace file against its schema and the evidence naming rules |
| `areao1 preflight` | Evidence preflight: what a reviewer would notice, by severity (writes `data/preflight.json`) |
| `areao1 packet` | Build review packet: numbered exhibits, the claim/exhibit/page matrix, an outline, as .docx, PDF and ZIP |
| `areao1 repair-dates` | Date exhibits filed before dates were tracked, from the documents themselves (`--apply` to write) |
| `areao1 qa` | The browser QA suite, from a checkout of the repo (contributors) |
| `areao1 notify test` | Send a test notification to every channel routed for `test` |
| `areao1 secret set <ref>` | Store a token, webhook URL or SMTP password in the OS keychain |
| `areao1 secret delete <ref>` | Remove a secret from the keychain (and the workspace `.env` fallback) |
| `areao1 vault ...` | The knowledge vault: `sync`, `import`, `search`, `status` |
| `areao1 extension` | Show where the capture extension is and how to load it in Chrome |
| `areao1 mcp` | Run a read-only MCP server over stdio for Claude Code, Codex, Claude desktop or any MCP client |
| `areao1 --version` | Show the version |

## Which workspace a command uses

Commands that take `--workspace` / `-w` look for a workspace in this order:

1. the `--workspace` you pass
2. the `AREAO1_WORKSPACE` environment variable
3. the nearest parent of the current folder that contains `areao1.yaml`
4. the workspace you opened last

If none is found, the command says: "No workspace found. Run `areao1` to start, `areao1 init <dir>`, or pass --workspace."

## areao1

```sh
areao1
```

With no command, Area O1 finds your workspace as above and opens it in the browser. If there's none yet, it creates your private workspace at `~/AreaO1` (or `AREAO1_HOME` if you set it) and opens onboarding. It also runs the scheduled jobs, like `areao1 up`.

## areao1 init

```sh
areao1 init <path> [--name "Your Name"] [--profile o1a|eb1a] [--no-git]
```

Create a private case workspace.

| Option | Default | What it does |
|---|---|---|
| `<path>` | required | Folder to create, for example `~/my-case` |
| `--name` | empty | Your name, for `data/person.json` |
| `--profile` | `o1a` | Criteria profile: `o1a` or `eb1a` |
| `--git` / `--no-git` | `--git` | Run `git init` and install the gitleaks pre-commit hook |

## areao1 import

```sh
areao1 import <url> [--private] [--token-env VAR] [--no-snapshot] [--keep-all] [-w <dir>]
```

Add a source. Area O1 detects the connector, discovers items and proposes candidates for your Inbox.

`<url>` can be a GitHub or Hugging Face URL or handle (`github:octo`, `hf:octo`), a scholarly profile (Semantic Scholar, OpenAlex, `arxiv.org/a/<id>`, an ORCID iD), any web page or sitemap, or a Claude or ChatGPT export (`conversations.json` or the export `.zip`).

| Option | Default | What it does |
|---|---|---|
| `--private` | off | Prompt for a read-only token and store it in the keychain |
| `--token-env VAR` | none | Read the token from this environment variable instead |
| `--snapshot` / `--no-snapshot` | `--snapshot` | Also take a metrics snapshot now |
| `--keep-all` | off | Chat exports: also save conversations that produced no suggestions |
| `-w`, `--workspace` | see above | Workspace folder |

See [Connectors](../connectors/index.md) and [Chat-history imports](../connectors/chat-imports.md).

## areao1 run

```sh
areao1 run <job> [-w <dir>]
areao1 run --list
```

Run one job headless, for cron, launchd or GitHub Actions. `--list` shows every job. The job names are the ones in [Scheduled jobs](#scheduled-jobs), plus `dashboard`.

A `metrics-snapshot` you run yourself always takes a snapshot. When the scheduler runs it, it skips if the last snapshot is less than 13 days old, so it stays every other week.

## areao1 up

```sh
areao1 up [--port 7777] [--no-scheduler] [--no-open] [-w <dir>]
```

Serve the dashboard on `http://127.0.0.1` (your computer only).

| Option | Default | What it does |
|---|---|---|
| `--port` | `server.port` in `areao1.yaml` (7777) | Port to serve on |
| `--scheduler` / `--no-scheduler` | on | Run the scheduled jobs in the background |
| `--open` / `--no-open` | `--open` | Open the dashboard in a browser |
| `-w`, `--workspace` | see above | Workspace folder |

If the port is taken by something else, Area O1 tries the next 19 ports and tells you which one it used. If the same workspace is already running, it opens that instead of starting a second copy.

## areao1 validate

```sh
areao1 validate [-w <dir>]
```

Check every workspace file against its JSON Schema and the evidence naming rules (`evidence/<criterion>/<criterion>_<yyyy-mm-dd>_<slug>.<ext>`). Prints each problem, or that the workspace is valid. Exits with status 1 if anything is wrong.

## areao1 notify test

```sh
areao1 notify test [--channel <name>] [-w <dir>]
```

Send a test notification to every channel routed for the `test` event, or only to `--channel`. See [Configuration](configuration.md#notifications).

## areao1 secret

```sh
areao1 secret set <ref> [-w <dir>]
areao1 secret delete <ref> [-w <dir>]
```

`set` prompts for the secret (hidden) and stores it in the OS keychain under `<ref>`, for example `notify:slack` (a channel's `secret_ref`). `delete` removes it from the keychain and the workspace `.env` fallback.

## areao1 vault

The knowledge vault holds official sources, fetched, snapshotted and searchable. See [Rule check and the knowledge vault](../how-it-works/rule-check.md).

| Command | What it does |
|---|---|
| `areao1 vault sync [-s <id>]... [--force]` | Fetch the sources that are due (never fetched or past their freshness window). `-s` / `--source` limits it to these source ids; `--force` re-fetches even if still fresh. |
| `areao1 vault import <source> <file>` | Import a page you saved from your browser, for sources that block automated reading |
| `areao1 vault search <query> [-k 5]` | Search the vault (full text and local embeddings); `-k` sets how many results |
| `areao1 vault status` | Each source's tier, freshness, last check and last change |

Each takes `-w` / `--workspace`.

## areao1 preflight

```sh
areao1 preflight [-w <dir>]
```

The same checks as **Run preflight** on Evidence, printed by severity and written to `data/preflight.json`. It
never changes your evidence. See [Evidence preflight](../how-it-works/preflight.md).

## areao1 packet

```sh
areao1 packet [-w <dir>]
```

Build review packet into `exports/packet-<date>-<hash>/` in your workspace: the review PDF, an editable .docx,
`matrix.csv`, the preflight issues, provenance files and an attorney ZIP. Every page is labeled "Draft for
attorney review". The same inputs give the same files. See [The review packet](../how-it-works/review-packet.md).

## areao1 repair-dates

```sh
areao1 repair-dates [-w <dir>] [--apply]
```

For exhibits filed before Area O1 tracked document dates: sets each one's date from the document itself (an
email's Date header, a PDF's creation date, its facts' event dates), or marks it "date unconfirmed" when the only
date is the day it was filed. Without `--apply` it only shows what it would change.

## areao1 qa

```sh
areao1 qa [--runs 3] [-k <expression>] [--out <dir>]
```

For contributors, from a checkout of the repo: the browser suite in `tests/e2e` (every page and control, the main
flows, light and dark, laptop and phone, accessibility checks). It only uses throwaway fictional workspaces, fake
Gmail and a scripted model. `--runs` repeats the suite to tell flaky failures from real ones. Findings,
screenshots and the report go to `out/qa/` (gitignored) unless you pass `--out`. It needs
`pip install -e '.[dev,e2e]'`, `playwright install chromium` and `npm --prefix web install`.

## areao1 extension

```sh
areao1 extension
```

Prints the folder of the capture extension and how to load it: in Chrome, open `chrome://extensions`, turn on Developer mode, click **Load unpacked** and choose that folder. Then pair it in Area O1 under Knowledge. See [Capture extension and community vault](../how-it-works/extension.md).

## areao1 mcp

```sh
areao1 mcp [-w <dir>]
```

Run a read-only MCP server over stdio. Register it with your agent, for example:

```sh
claude mcp add areao1 -- areao1 mcp -w ~/my-case    # Claude Code
codex mcp add areao1 -- areao1 mcp -w ~/my-case     # Codex
```

Its tools are `get_scoreboard`, `list_gaps`, `query_claims`, `get_provenance` and `what_changed`, plus `propose_context`, which sends notes to your Inbox. See [MCP and agents](../mcp/index.md).

## Scheduled jobs

`areao1 up` (and `areao1` with no command) runs these in the background. Change a job's cron expression under `schedules` in `areao1.yaml`, or set it to `''` to turn it off. Runs missed while your laptop was asleep catch up when `up` starts again.

| Job | Default | Does |
|---|---|---|
| `sync` | daily 08:00 | Refresh sources; notify about new candidates and errors |
| `metrics-snapshot` | Mondays, every other week | Append metrics (and GitHub's 14-day traffic) |
| `deadline-check` | daily 07:00 | Alert at 14 / 3 / 1 / 0 days and when overdue; follow-ups; calendar |
| `digest` | Fridays 17:00 | What changed, stale pipeline items, next actions |
| `vault-watch` | daily 06:00 | Rule changes (Federal Register, eCFR), the community snapshot library, official sources due; one reminder only when a page changed and no newer copy exists |
| `google` | every 15 min | Gmail threads with your contacts, the Mail view, follow-up drafts (skips until Gmail is connected) |
| `daily-opportunities` | daily 08:30, off | Invitations in your mail to the Inbox, each verified, unconfirmed or suspicious (Settings > Gmail) |
| `mission-opportunity-scout` | Fridays 09:00, off | Agent mission: find opportunities for your weakest criteria (Settings > Missions) |
| `mission-what-changed` | daily 07:00, off | Agent mission: review what changed and write the briefing (Settings > Missions) |

The jobs marked "off" have a schedule but do nothing until you turn them on in Settings. `run` jobs are headless, so cron, launchd or GitHub Actions can call them too, for example `areao1 run sync -w ~/my-case`.

## Environment variables

| Variable | What it does |
|---|---|
| `AREAO1_WORKSPACE` | Workspace to use when `-w` isn't given |
| `AREAO1_HOME` | Where the first run creates your workspace (default `~/AreaO1`) |
| `AREAO1_CONFIG_DIR` | Where Area O1 keeps the file that remembers your last workspace (default `~/.config/areao1`, or `%APPDATA%\areao1` on Windows) |
| `AREAO1_MODEL_HARD`, `AREAO1_MODEL_MID`, `AREAO1_MODEL_MUNDANE` | Override a model tier (also read from the workspace `.env`) |
| `OPENAI_API_KEY` | Your OpenAI key, if none is saved in Settings > Your AI |
| `AREAO1_<REF>` | A secret, overriding the keychain: `notify:slack` becomes `AREAO1_NOTIFY_SLACK` |
