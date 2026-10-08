# Configuration

Every setting in `areao1.yaml`, the file at the top of your workspace, with its default.

`areao1.yaml` holds settings only. Secrets never go in it: tokens, webhook URLs and passwords live in the OS keychain, and the file only names the keychain entry (`secret_ref`). Many settings also have a control in **Settings** in the dashboard, which writes this same file.

A new workspace gets a complete `areao1.yaml` with every default written out. You can delete any key to go back to its default. Keys are checked when the file loads, so a typo or an unknown key is reported instead of ignored. The JSON Schema is in your workspace at `.areao1/schemas/areao1-config.schema.json`, and the models are in [areao1/core/models.py](https://github.com/ris3abh/areao1/blob/main/areao1/core/models.py).

## Top level

| Key | Default | What it does |
|---|---|---|
| `schema_version` | `1` | File format version. Don't change it. |
| `workspace_name` | the folder name | A name for this case |
| `profile` | `o1a` | Active criteria profile: `o1a` or `eb1a`. The header's profile switch changes it. |
| `engine` | `openai` | The agent engine. OpenAI is the only one. |
| `overrides` | `{}` | Your status overrides per profile: `{profile_id: {criterion_id: dropped \| gap}}` |

## server

| Key | Default | What it does |
|---|---|---|
| `server.host` | `127.0.0.1` | Always `127.0.0.1`; no other value is accepted |
| `server.port` | `7777` | Port for `areao1 up` (1024 to 65535). `--port` overrides it. |

## agent

The agent runs on OpenAI and only when you've added an API key (Settings > Your AI) or set `OPENAI_API_KEY`. See [Add an OpenAI API key](../getting-started/openai-key.md) and [Costs and budget caps](../getting-started/costs.md).

```yaml
agent:
  models:
    hard: gpt-6.1-sol      # chat, tasks you start, letters ($2 / $10 per 1M tokens in / out)
    mid: gpt-6.1-sol       # missions, the rule check, PDFs, cheap-mode chat
    mundane: gpt-6-luna    # chat extraction, long-chat summaries, mail sorting ($0.10 / $0.50)
  effort: medium
  web_search: true
  budget: {per_run_tokens: 300000, per_run_usd: 2.0, monthly_tokens: 10000000, monthly_usd: 50.0}
```

| Key | Default | What it does |
|---|---|---|
| `agent.models.hard` | `gpt-6.1-sol` | Chat, runs you start by hand, letter drafts |
| `agent.models.mid` | `gpt-6.1-sol` | Missions, the rule-check judge, PDFs, cheap-mode chat |
| `agent.models.mundane` | `gpt-6-luna` | Chat extraction, long-chat summaries, mail sorting |
| `agent.effort` | `medium` | Reasoning effort: `low`, `medium`, `high`, `xhigh` or `max` |
| `agent.cheap_mode` | `false` | Run chat on the mid tier instead of the hard one |
| `agent.web_search` | `true` | Let the agent search the web |
| `agent.max_searches` | `8` | Web searches per run (0 to 50). At the cap the run finishes with what it found and says so. |
| `agent.max_turns` | `25` | Most tool-use turns per run (1 to 200) |
| `agent.budget.per_run_tokens` | `300000` | Token cap per run |
| `agent.budget.per_run_usd` | `2.0` | Dollar cap per run (`null` for none) |
| `agent.budget.monthly_tokens` | `10000000` | Token cap per calendar month |
| `agent.budget.monthly_usd` | `50.0` | Dollar cap per calendar month (`null` for none) |
| `agent.missions.opportunity_scout` | `false` | Weekly mission: find opportunities for your weakest criteria |
| `agent.missions.what_changed` | `false` | Daily mission: review what changed and write the briefing |
| `agent.autopilot.tracker_updates` | `false` | Apply pipeline, letter and deadline edits without asking |
| `agent.autopilot.metrics` | `false` | Apply metric values the agent read from a page and quoted |
| `agent.autopilot.tier1_deadlines` | `false` | Apply new deadlines quoted from a Tier 1 source (primary law or agency pages) |

Tokens counted toward the budget are input, output and cache-creation tokens (cache reads are recorded, not counted). Dollar amounts come from Area O1's built-in price table. When the monthly cap is reached, new runs are refused until next month.

Autopilot can never apply anything that could affect a criterion (evidence, exhibits, overrides, the profile), whatever you set here. The environment variables `AREAO1_MODEL_HARD`, `AREAO1_MODEL_MID` and `AREAO1_MODEL_MUNDANE` (or the same names in the workspace `.env`) override the model lines.

## privacy

| Key | Default | What it does |
|---|---|---|
| `privacy.redact_before_llm` | `true` | Remove emails, phone numbers and currency amounts from text sent to the model |

## notifications

Desktop notifications work out of the box. To add email, Slack, Discord or ntfy, add a channel under `notifications.channels` and route events to it:

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

Store the secret in the keychain, never in the file: `areao1 secret set notify:slack`. Then run `areao1 notify test`. Anything sent to Slack, Discord, email or ntfy leaves your computer, so `detail: minimal` sends only counts ("2 deadlines this week"), never titles.

### Channels

Each entry under `notifications.channels` is a named channel:

| Key | Default | Used by | What it does |
|---|---|---|---|
| `kind` | required | all | `desktop`, `email`, `slack`, `discord` or `ntfy` |
| `enabled` | `true` | all | Turn the channel off without deleting it |
| `detail` | `full` | all | `minimal` sends counts only, no titles |
| `secret_ref` | none | email, slack, discord, ntfy | Keychain entry: the webhook URL, SMTP password or ntfy access token |
| `host` | none | email | SMTP server |
| `port` | `587` | email | SMTP port (465 uses SSL) |
| `starttls` | `true` | email | Use STARTTLS (ignored on port 465) |
| `username` | none | email | SMTP login; the password is the `secret_ref` |
| `from_addr`, `to_addr` | none | email | Sender and recipient |
| `server` | `https://ntfy.sh` | ntfy | ntfy server, or your own |
| `topic` | none | ntfy | Topic name; pick an unguessable one |

### Routes

`notifications.routes` maps each event to a list of channel names. Every event goes to `desktop` by default.

| Event | Sent when |
|---|---|
| `deadline` | A deadline is near or overdue |
| `digest` | The weekly digest is ready |
| `new_candidates` | A sync found new items for your Inbox |
| `sync_error` | A source failed to sync |
| `mission` | An agent mission finished |
| `vault` | An official source changed |
| `opportunity` | The daily opportunity check found something |
| `test` | `areao1 notify test` |

| Key | Default | What it does |
|---|---|---|
| `notifications.deadline_alert_days` | `[14, 3, 1, 0]` | Alert when a deadline is this many days away |

## schedules

A cron expression per job. Set a job to `''` to turn it off. Jobs added in later versions get their default schedule until you set one.

```yaml
schedules:
  sync: 0 8 * * *
  metrics-snapshot: 0 9 * * mon     # weekly; skips unless 13+ days since the last snapshot
  deadline-check: 0 7 * * *
  digest: 0 17 * * fri
  mission-opportunity-scout: 0 9 * * fri
  mission-what-changed: 0 7 * * *
  vault-watch: 0 6 * * *
  google: '*/15 * * * *'
  daily-opportunities: 30 8 * * *
```

The missions and `daily-opportunities` do nothing until they're turned on (`agent.missions`, `opportunities.enabled`). See [Scheduled jobs](commands.md#scheduled-jobs).

## vault

| Key | Default | What it does |
|---|---|---|
| `vault.enabled` | `true` | Fetch the public official sources listed in the vault manifest |
| `vault.community` | `true` | Pull hash-verified snapshots of blocked official pages from the community library |
| `vault.community_url` | `https://raw.githubusercontent.com/ris3abh/areao1-community-vault/main` | Where the community library's `manifest.json` lives |
| `vault.share_captures` | `false` | Prepare captures of public government pages for the community library (written to a local outbox; nothing is uploaded) |

## mail

| Key | Default | What it does |
|---|---|---|
| `mail.model_sorting` | `false` | Send mail no rule could sort to the mundane model (sender, subject, first lines, redacted). Off: rules only. |

## outreach

| Key | Default | What it does |
|---|---|---|
| `outreach.daily_limit` | `10` | Most emails sent per day (0 to 100), checked when you approve |
| `outreach.follow_up_days` | `7` | Quiet days after your email before a follow-up draft (2 to 60) |

See [Outreach etiquette](../best-practices/outreach.md).

## opportunities

| Key | Default | What it does |
|---|---|---|
| `opportunities.enabled` | `false` | Run the daily opportunity check every 24 hours (Settings > Gmail) |
| `opportunities.verify_on_web` | `true` | Confirm each event on its official page (or Devpost / MLH); may run one cheap web search per find with no usable link |

See [Daily opportunity check](../how-it-works/opportunities.md).

## connectors

| Key | Default | What it does |
|---|---|---|
| `connectors.include_forks` | `false` | Include forked GitHub repos |
| `connectors.min_stars_for_candidate` | `5` | Star threshold for proposing a GitHub repo as a candidate |
| `connectors.min_downloads_for_candidate` | `100` | Download threshold for proposing a Hugging Face model or dataset as a candidate |

## Calendar subscription

Deadlines and pipeline follow-ups are written to `data/calendar.ics` on every change. There's nothing to configure:

- To subscribe from Apple Calendar, Outlook or Thunderbird on the same computer, use `webcal://127.0.0.1:7777/calendar.ics` while `areao1 up` is running (use your port if you changed it).
- Or import the `data/calendar.ics` file.
- Google Calendar can't reach your laptop's localhost, so import the `.ics` file there.
