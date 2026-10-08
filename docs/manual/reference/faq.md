# FAQ

Short answers to the questions people ask most.

## Do I need an OpenAI API key?

No. Onboarding, the Inbox, evidence, metrics, the scoreboard, connectors, Gmail, deadlines, letters and the MCP server all work without one. A key adds Area O1's own chat, web lookups, missions, the rule check's model judge, AI-written letter drafts (without a key you get a plain template that lists the facts) and optional model mail sorting. See [Add an OpenAI API key](../getting-started/openai-key.md).

Using Area O1 from Claude Code or Codex through MCP doesn't need an OpenAI key either.

## Does it send my data anywhere?

Only where a feature you turned on needs it: the sources you connect, OpenAI when you use the agent (with `store: false`, and with emails, phone numbers and currency amounts removed), Gmail if you connect it, the official pages and feeds the knowledge vault watches, and your notification channels. There's no telemetry. The complete list is on [Privacy and security](privacy-security.md#every-network-call).

## Is my LinkedIn PDF uploaded?

No. It's read on your computer. Emails and phone numbers are removed before anything else sees the text. Only if the PDF isn't a LinkedIn export, and you've connected an AI, is the redacted text sent to the model to find the same fields.

## Does it tell me whether I qualify?

No. Area O1 organizes evidence; it doesn't judge eligibility. A criterion marked **banked** means your accepted exhibits meet a simple, documented rule in the profile. It doesn't mean USCIS will agree. Ask an immigration attorney. See the [legal disclaimer](disclaimer.md).

## Does it file anything for me?

No. Area O1 never files anything with USCIS or anyone else, and it never signs anything. It helps you and your attorney assemble the file.

## How do I switch between O-1A and EB-1A?

Use the profile switch in the header: **Visitor mode (O-1A)** or **Resident mode (EB-1A)** (on a narrow window it shows just O-1A and EB-1A). Switching re-scores the same evidence against the other profile. EB-1A uses a stricter rubric, so the same file can bank fewer criteria there. You can also set `profile` in `areao1.yaml`.

## Does it work on Windows?

Yes. Install it from PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/ris3abh/areao1/main/install.ps1 | iex"
```

Secrets go to the Windows Credential Manager, desktop notifications show as Windows notifications, and the user config lives in `%APPDATA%\areao1`. See [Install](../getting-started/install.md).

## Where is my data?

In your workspace folder, by default `~/AreaO1`. It's a git repo of plain JSON, CSV and Markdown files. Secrets aren't in it: they're in your OS keychain. See [Architecture](architecture.md#the-workspace-folder).

## Can I have more than one case?

Yes. Each case is its own workspace:

```sh
areao1 init ~/second-case --profile eb1a
areao1 up -w ~/second-case
```

Each running case gets its own port. If 7777 is busy, Area O1 picks the next free one and tells you.

## Can my attorney see it?

Only if you share it. Everything stays on your computer, and the dashboard is served only to your computer. To share, send your attorney the files they need: `DASHBOARD.md`, the documents in `evidence/` and signed letters. A dedicated attorney export is on the [roadmap](roadmap.md).

## Does the agent change my case by itself?

Not your evidence. Anything that could affect a criterion (evidence, exhibits, overrides, the profile) goes to your Inbox and needs your approval. In a chat or task you start, it can update your trackers directly (deadlines, pipeline items, letter writers, contacts, email drafts), and each change is logged and can be undone. Scheduled missions only propose, plus any autopilot rules you turn on (all off by default). Email never goes out without your Approve & send. See [What agents can and can't do](../mcp/limits.md).

## Do my chat imports count as evidence?

No. What you said in a chat is self-reported. It keeps deadlines, pipeline items and letter writers current, but it never counts toward a criterion. Upload the real document for that.

## Does an invitation count?

No. An invitation is not a completion. Only completed, published or granted evidence counts. See [Invited vs completed](../how-it-works/invited-vs-completed.md).

## Does it send email for me?

Only drafts you approve, from your own Gmail, to your case contacts, with 10 seconds to undo and a daily limit. See [Outreach etiquette](../best-practices/outreach.md).

## What does it cost?

Area O1 is free and open source (Apache-2.0). If you add an OpenAI key, you pay OpenAI for what the agent uses, capped per run and per month in `areao1.yaml`. See [Costs and budget caps](../getting-started/costs.md).

## Can I use it from Claude Code or Codex?

Yes, through its read-only MCP server and the skill pack in every workspace. See [Set up your agent](../mcp/setup.md).

## How do I delete everything?

Delete the workspace folder and any private backup, remove secrets with `areao1 secret delete <ref>`, and revoke tokens at their source. The steps are in [Privacy habits](../best-practices/privacy.md#deleting-a-case). To remove the app itself, if you used the installer:

```sh
uv tool uninstall areao1
```

## Is Area O1 affiliated with USCIS or a law firm?

No. Area O1 is not legal advice and is not affiliated with USCIS. Criteria profiles are community-maintained summaries of public regulations.
