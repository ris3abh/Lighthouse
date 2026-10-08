# Troubleshooting

Common problems and how to fix them.

## `areao1` isn't found after installing

The installer puts Area O1 in uv's tool folder. If your shell says `areao1: command not found`, that folder isn't on your `PATH` yet.

1. Open a new terminal window and try again. The installer may have updated your `PATH` for new shells only.
2. If it still isn't found, ask uv where its tools are:

    ```sh
    uv tool dir --bin
    ```

3. Add that folder to your `PATH` with uv's helper, then open a new terminal:

    ```sh
    uv tool update-shell
    ```

Until then you can run it by its full path, for example `"$(uv tool dir --bin)/areao1"`.

## Port 7777 is already in use

You don't need to do anything. If another program has port 7777, `areao1 up` tries the next ports and says so: "Port 7777 is taken by something else, so this one uses 7778." If the same workspace is already running, it opens that one instead of starting a second copy.

To choose a port yourself, use `areao1 up --port 7800`, or set `server.port` in `areao1.yaml`. If you see "Ports 7777–7796 are all taken", pick a port outside that range with `--port`.

If you subscribed to the calendar at `webcal://127.0.0.1:7777/calendar.ics`, update the port in your calendar app too.

## "No workspace found"

Commands look for a workspace in this order: `--workspace`, `AREAO1_WORKSPACE`, the nearest parent folder with an `areao1.yaml`, then the one you opened last. Pass it explicitly:

```sh
areao1 up -w ~/AreaO1
```

Or run `areao1` with no command to create the default workspace.

## The pages don't load after installing from a checkout

If `areao1 up` says "Web UI not built — the API works but pages won't", build the dashboard once:

```sh
npm --prefix web install && npm --prefix web run build
```

## The keychain keeps asking for permission

Area O1 stores secrets in your OS keychain. On macOS the system may ask whether to let Python read the `areao1` entries. Choose **Always Allow** so it doesn't ask on every start. On Linux, a keychain needs a running Secret Service (for example GNOME Keyring). Without one, Area O1 falls back to a `.env` file in your workspace, which is gitignored.

## Gmail won't connect

Area O1 connects with an **app password**, not your normal Google password. The message tells you what went wrong:

| Message says | Fix |
|---|---|
| An app password is 16 letters | Paste the 16-letter app password Google showed you (with or without spaces), not your normal password |
| That's your normal Google password | Create an app password on Google's App passwords page and paste it instead |
| The App passwords setting isn't available | Turn on 2-Step Verification for your Google account first, then create the app password |
| Gmail didn't accept that app password | Check the address, or create a new app password and paste it right away (Google shows each one only once) |
| IMAP is turned off for this Gmail account | In Gmail: Settings > See all settings > Forwarding and POP/IMAP > Enable IMAP, save, and try again |
| Google wants you to sign in once in your browser first | Open gmail.com in your browser, sign in, then try again |
| Couldn't reach Gmail | Check your internet connection |

On a work or school account, your admin may need to allow IMAP or app passwords. Check your employer's policy first. See [Gmail](../connectors/gmail.md).

## An email won't send

Rules are checked when you press **Approve & send**:

- "outreach goes to case contacts only": the address isn't on a contact any more. Add it on the Contacts page.
- "Sending isn't connected": connect Gmail in Settings > Gmail.
- "today's limit of 10 emails is reached": the limit resets tomorrow. You can change `outreach.daily_limit` in `areao1.yaml`.

If Gmail refuses a send, the email stays a draft and appears in the list of sends that didn't go out on Contacts.

## A source fails to sync

Errors show on the Sources page, and as a `sync_error` notification.

- **HTTP 401, "token missing or invalid"**: store a new read-only token with `areao1 import <url> --private`.
- **HTTP 403, "forbidden (token scope?)"**: the token lacks a scope. For GitHub traffic numbers, add *Administration: read*.
- **HTTP 404, "not found (or private)"**: check the URL, or add a token for a private repo.
- **"rate limited for another …s; try again later"**: wait and run `areao1 run sync` again.

## An official page shows "unreadable"

Some official sites (uscis.gov, travel.state.gov) block automated reading, so the Knowledge page marks them **unreadable**. You have three ways to keep them fresh:

1. **The capture extension.** Install it (`areao1 extension` shows where it is), pair it on the Knowledge page, then just visit the page in your browser. See [Capture extension and community vault](../how-it-works/extension.md).
2. **The community library.** With `vault.community` on (the default), the `vault-watch` job pulls hash-verified copies of blocked pages that others captured.
3. **Import it yourself.** Open the link, save the page from your browser (HTML or PDF), and click **Import saved page** on the Knowledge page. Or from the terminal:

    ```sh
    areao1 vault status                       # find the source id
    areao1 vault import <source-id> ~/Downloads/page.html
    ```

## The scoreboard looks out of date

The web scoreboard updates when you accept or reject in the Inbox, or switch profiles. `DASHBOARD.md` is a file, so it changes only when it's regenerated:

```sh
areao1 run dashboard
```

If a criterion you expect to count doesn't:

- Check the exhibit's stage. Invitations don't count; only completed, published or granted do.
- Self-reported items (onboarding answers, chat imports) never count. Upload the document.
- Check the strength signals. A criterion banks only with enough accepted exhibits **and** enough distinct signals.
- Check for an override (`dropped` or `gap`) under `overrides` in `areao1.yaml`.

## My MCP client can't find `areao1`

Desktop apps such as Claude desktop don't read your shell's `PATH`. Use the full path to the command. Find it with:

```sh
which areao1          # macOS / Linux
where areao1          # Windows
```

Put that path in the client's config as `command`, with `["mcp", "-w", "/full/path/to/your-case"]` as `args`, then restart the client. See [Set up your agent](../mcp/setup.md).

## The agent costs more than I expected

Every run is capped, and so is each month. Check the Agent page: it shows this month's spend, tokens against the monthly cap, and the cost of each run.

To spend less:

- Lower the caps under `agent.budget` in `areao1.yaml` (`per_run_usd`, `monthly_usd`, `per_run_tokens`, `monthly_tokens`).
- Turn on `agent.cheap_mode` to run chat on the mid tier.
- Lower `agent.max_searches`, or set `agent.web_search: false`.
- Lower `agent.effort` to `low`.
- Turn off missions you don't need (Settings > Missions) and `mail.model_sorting`.

When a cap is reached, runs stop with "monthly budget reached" or "monthly token budget reached" until next month or until you raise the cap. See [Costs and budget caps](../getting-started/costs.md).

## The agent says "No AI connected"

Add an OpenAI API key in Settings > Your AI, or set `OPENAI_API_KEY` before you start Area O1. Everything else works without one.

## Desktop notifications don't appear on Linux

Area O1 uses `notify-send`. Install libnotify (the package is often called `libnotify-bin`), then run `areao1 notify test`.

## Still stuck

Run `areao1 validate` to check your workspace files, then open an issue on [GitHub](https://github.com/ris3abh/areao1/issues) with the error message. Don't paste personal data, tokens or case documents into the issue.
