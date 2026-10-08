# Coming from Lighthouse

Lighthouse was this project's previous name; Area O1 is the same project, and your existing setup carries over.

The rename is recorded in [ADR 0010](https://github.com/ris3abh/areao1/blob/main/docs/adr/0010-area-o1.md), which supersedes the earlier naming decision in [ADR 0002](https://github.com/ris3abh/areao1/blob/main/docs/adr/0002-name-lighthouse-gc.md). "Lighthouse" is a common name, crowded on PyPI and GitHub, and it said nothing about O-1 or EB-1 cases. The new name is Area O1, with the letter O, not zero.

## What moves on the first run

The first time you run the new version, Area O1 finds your Lighthouse-era setup and moves what it can, once, with a one-line notice for each thing it moves. A second run moves nothing.

| What | Before | Now | What happens |
|---|---|---|---|
| Command | `lighthouse-gc` | `areao1` | The old command still works for now: it says the new name, then runs |
| Workspace config | `lighthouse.yaml` | `areao1.yaml` | Renamed in place |
| Workspace state folder | `.lighthouse/` | `.areao1/` | Renamed, and the workspace `.gitignore` is updated to match |
| User config folder | `~/.config/lighthouse-gc` | `~/.config/areao1` (`%APPDATA%\areao1` on Windows) | Copied, including the remembered workspace |
| Keychain service | `lighthouse-gc` | `areao1` | A secret not found under `areao1` is read from `lighthouse-gc` and copied over |
| Environment variables | `LIGHTHOUSE_GC_*`, `LIGHTHOUSE_*` | `AREAO1_*` | Old names are still read when the new one isn't set, with a notice naming the new variable |
| Write header | `X-Lighthouse` | `X-AreaO1` | The server accepts both, so a tab left open across the upgrade still saves |

Nothing else in your workspace changes. Your evidence, claims, letters and metrics stay exactly where they are. A workspace you kept at `~/Lighthouse` stays there; only new installs default to `~/AreaO1`.

## What to do

1. Install Area O1 (see [Install](../getting-started/install.md)).
2. Run `areao1` (or `areao1 up -w <your workspace>`) and read the notices it prints.
3. Rename any `LIGHTHOUSE_*` environment variables in your shell profile or cron jobs to `AREAO1_*`, for example `LIGHTHOUSE_MODEL_HARD` to `AREAO1_MODEL_HARD`.
4. Replace `lighthouse-gc` with `areao1` in scripts, cron or launchd jobs, and your MCP client config, for example:

    ```sh
    claude mcp add areao1 -- areao1 mcp -w ~/my-case
    ```

5. If you commit your workspace, commit the renamed `areao1.yaml` and `.gitignore`.

The `lighthouse-gc` alias is deprecated and may be removed in a later release.
