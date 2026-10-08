# First run and onboarding

The first time you start Area O1, it creates your private workspace and walks you through a short setup chat.

## What happens when you run `areao1`

1. Area O1 looks for a workspace: `$AREAO1_WORKSPACE` if you set it, then the current folder and its parents (any
   folder with an `areao1.yaml`), then the workspace you opened last.
2. If it finds none, it creates one at `~/AreaO1` (set `AREAO1_HOME` to use another place). The terminal says:
   `Created your private workspace at ...`.
3. It remembers that workspace (in `~/.config/areao1/config.json`, or `%APPDATA%\areao1` on Windows), so next
   time `areao1` opens it again.
4. It serves the dashboard at `http://127.0.0.1:7777` and opens your browser. A new workspace opens into
   onboarding.

If port 7777 is taken by something else, Area O1 tries the next ports and tells you which one it used. The
dashboard is served only to your own computer (127.0.0.1).

## The workspace

Your workspace is a folder of plain files (JSON, JSONL, CSV and Markdown) and its own git repo, with a gitleaks
pre-commit hook that blocks tokens from being committed.

| Path | What's in it |
|---|---|
| `areao1.yaml` | Your settings: models, budgets, schedules, notifications |
| `data/` | Exhibits, Inbox, deadlines, letters, metrics (`metrics.csv`), the calendar file |
| `evidence/<criterion>/` | One folder per criterion; accepted evidence is filed here |
| `memory/` | Observations and claims: every raw source and every fact quoted from it |
| `drafts/letters/` | Letter drafts |
| `DASHBOARD.md` | Where your case stands, in Markdown |
| `AGENTS.md`, `.claude/skills/areao1/` | Instructions for Codex and Claude Code (see [MCP and agents](../mcp/index.md)) |

!!! warning "Keep it private"
    If you want a backup, push the workspace only to a **private** remote. Never make it public, and never put it
    inside a checkout of the Area O1 code. See [Privacy habits](../best-practices/privacy.md).

## Onboarding, step by step

Onboarding is one conversation with seven steps: **LinkedIn**, **Your profile**, **Your AI**, **Find your work**,
**Chat history**, **Email** and **Tour**. The step bar at the top lets you go back to any step you've reached, and
**Back** returns to your last answer. Every answer is kept.

Want to skip all of it? Press **Skip setup** at the top. You can run onboarding again any time from
**Settings > Setup > Run onboarding again**; what it added before stays in your workspace.

### 1. LinkedIn

Area O1 asks for your LinkedIn profile as a PDF. To get it, open your profile on LinkedIn, then
**More > Save to PDF**.

Drop the PDF on the page, or click to choose it. Here's what happens to it:

- The text is extracted **on your computer** (no network, no model).
- **Emails and phone numbers are removed first**, before anything else sees the text.
- The fields are read from the export's fixed layout: name, headline, location, current role and employer,
  education, awards, publications, judging roles, memberships, certifications and links.
- The PDF itself isn't kept. Only its redacted text is saved, as a self-reported record in your workspace.

The limit is 10 MB. If the PDF isn't a LinkedIn export and you've connected an AI, Area O1 asks the model for the
same fields and keeps only those whose quote really appears in the text.

Don't have it handy? Press **Skip, I don't have it handy**. You'll get just two questions instead.

### 2. Your profile

Area O1 checks what it read, one question at a time, and shows the words from your PDF that each answer came
from. For each one you can answer **Yes**, **No, let me fix it**, or **Skip**. A skipped answer stays blank; nothing is guessed.

It asks, when your PDF has them, about your name, your role and employer, where you're based, your field (from
your headline), education, awards, papers, judging or reviewing, memberships, certifications and links. Then two
more questions, asked even if you skipped the PDF:

- **Which petition are you working toward?** O-1A, EB-1A, or *Not sure yet*. This picks the criteria profile.
- **When do you hope to file?** A rough month is fine.

The panel beside the chat, **Your profile so far**, fills in as you answer.

Each award, judging role, paper and membership you confirm becomes a to-do, such as "Upload proof of your judging".
A to-do is a reminder to find the proof. It never counts as evidence by itself.

### 3. Your AI

Area O1 offers to connect an OpenAI API key. Chat and web lookups need one; everything else works without it.
Paste the key, press **Check and save**, and it's checked with a free request and stored in your OS keychain.
Or press **Later, in Settings**. See [Add an OpenAI API key](openai-key.md).

### 4. Find your work

Area O1 offers lookups, but only for what you confirmed:

| You confirmed | The lookup | Needs AI? |
|---|---|---|
| Papers | Search arXiv for each one, with a check that you're listed as an author | No |
| A GitHub link | Import your public repositories | No |
| An ORCID link | Read your works from your ORCID record | No |
| Another website | Read it for press, talks and awards | No |
| An award, judging role or membership | A web search for the official page that names you | Yes |

Each lookup waits until you press **Yes, look** (or **No thanks**). Anything found goes to your
[Inbox](../tour/inbox.md) for you to check first, and results that may belong to someone with the same name are
marked. A lookup that fails shows why (the site couldn't be reached, or it blocked automated reading) and offers
**Retry**. Press **Continue** whenever you like; searches still running finish in the background.

### 5. Chat history

If you keep notes about your case in Claude or ChatGPT, you can drop a data export here:

- **Claude**: Settings > Privacy > Export data, then drop the `.zip` (or its folder) from the email.
- **ChatGPT**: Settings > Data controls > Export, then drop the `.zip` from the email.

Area O1 sorts it on your computer, shows what looks related to your case and why, and brings in only what you tick.
Or press **Skip for now**. See [Chat-history imports](../connectors/chat-imports.md).

### 6. Email

Optionally, connect Gmail with your address and an app password, so Area O1 can keep up with letter writers and
organizers and draft follow-ups. It sends nothing until you press **Approve & send**. Or press
**Later, in Settings**. See [Gmail](../connectors/gmail.md).

### 7. Tour

A short tour of the main pages, written from your own data. You can skip it.

## More than one case, or a different place

`areao1` with no command always uses one workspace. To keep a case somewhere else, or a second case, create it
with `init` and open it with `up -w`:

```sh
areao1 init ~/my-case                  # an empty, private workspace (a git repo of plain files)
areao1 up -w ~/my-case                 # opens onboarding for it
```

`init` takes `--name "Your Name"` and `--profile o1a` or `--profile eb1a` (the default is `o1a`), and
`--no-git` if you don't want it to be a git repo.

Inside a workspace folder, commands find it on their own:

```sh
cd ~/my-case
areao1 up
```

Each case runs its own server. If one is already on port 7777, the next one picks another port and says so. The
last workspace you opened becomes the one plain `areao1` reopens.
