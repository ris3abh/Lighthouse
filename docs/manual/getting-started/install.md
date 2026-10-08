# Install

One command installs Area O1 and opens it in your browser.

## macOS and Linux

Open Terminal and run:

```sh
curl -LsSf https://raw.githubusercontent.com/ris3abh/areao1/main/install.sh | sh
```

## Windows

Open PowerShell and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/ris3abh/areao1/main/install.ps1 | iex"
```

## What the installer does

Both scripts are short, and you can read them before you run them:
[install.sh](https://github.com/ris3abh/areao1/blob/main/install.sh) and
[install.ps1](https://github.com/ris3abh/areao1/blob/main/install.ps1). They do the same four things:

1. **Install uv if you don't have it.** [uv](https://docs.astral.sh/uv/) is Astral's Python tool manager. If the
   `uv` command isn't found, the script runs uv's own installer and adds `~/.local/bin` to the path for the rest
   of the script.
2. **Find the latest release.** It asks the GitHub API for the latest release of `ris3abh/areao1` and picks the
   wheel (`.whl`) attached to it. If there's no release, it stops with a message.
3. **Install Area O1 as a uv tool** on Python 3.12: `uv tool install --force --python 3.12 <wheel>`. uv fetches
   Python 3.12 if needed and keeps Area O1 in its own environment. If uv's tool folder isn't on your `PATH`, uv
   tells you.
4. **Start Area O1.** It runs `areao1`, which opens the dashboard in your browser. Press ++ctrl+c++ in the
   terminal to stop it.

It makes no other change to your machine. You don't need Node, a git checkout or a separate Python install.

Two environment variables change what the script does:

| Variable | Effect |
|---|---|
| `AREAO1_SPEC` | Install this wheel file or URL instead of the latest release |
| `AREAO1_NO_RUN=1` | Install only; don't start Area O1 |

For example, to install without starting it:

=== "macOS / Linux"

    ```sh
    curl -LsSf https://raw.githubusercontent.com/ris3abh/areao1/main/install.sh | AREAO1_NO_RUN=1 sh
    ```

=== "Windows"

    ```powershell
    $env:AREAO1_NO_RUN = "1"
    irm https://raw.githubusercontent.com/ris3abh/areao1/main/install.ps1 | iex
    ```

## Start it again later

Run:

```sh
areao1
```

With no command, Area O1 opens the workspace you used last (creating `~/AreaO1` the first time) and serves the
dashboard at `http://127.0.0.1:7777`. If you run it while it's already open, it just brings the page up again.
See [First run and onboarding](first-run.md) for what happens the first time.

## Install from a checkout

To work on Area O1 itself, install it from the source:

```sh
git clone https://github.com/ris3abh/areao1 && cd areao1
pipx install -e .                 # or: uv tool install -e .  /  pip install -e .
npm --prefix web install && npm --prefix web run build   # builds the dashboard into the package
```

The last line needs Node. Without the built dashboard, `areao1 up` warns that the web UI isn't built: the API
works but the pages don't.

!!! warning "Keep your case out of the checkout"
    If you contribute and also use Area O1 for your own case, keep two separate repositories: your fork of the app
    (public) and your case workspace (private). Never create a workspace inside the checkout. See
    [Keep case and code apart](../best-practices/two-repos.md).

For the development setup (tests, linters, the Vite dev server), see
[Contributing](../reference/contributing.md).

## Upgrade

Run the same install command again. It installs the latest release over the old one (`--force`), and your
workspace isn't touched.

If you installed from a checkout, pull and reinstall:

```sh
git pull
npm --prefix web run build
```

An editable install (`-e`) picks up the new Python code by itself; rebuild the dashboard when the web code
changed.

## Uninstall

1. Stop Area O1 (++ctrl+c++ in its terminal).
2. Remove the tool:

    ```sh
    uv tool uninstall areao1
    ```

    If you installed with pipx, use `pipx uninstall areao1`.

What stays behind, on purpose:

| What | Where | To remove it |
|---|---|---|
| Your workspace | `~/AreaO1` (or wherever you ran `areao1 init`) | Delete the folder, after backing up anything you need |
| Saved secrets (OpenAI key, Gmail app password, source tokens) | Your OS keychain, under the service name `areao1` | Before you uninstall: **Forget the key** in Settings > Your AI, **Disconnect** in Settings > Gmail, or `areao1 secret delete <ref>`. Afterwards: your keychain app |
| Which workspace you opened last | `~/.config/areao1/config.json` (`%APPDATA%\areao1` on Windows) | Delete the folder |

Your workspace is your case. Uninstalling the app never deletes it.
