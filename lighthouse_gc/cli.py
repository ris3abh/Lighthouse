"""``lighthouse-gc`` command line: init, up, import, run <job>, validate."""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from lighthouse_gc import __version__
from lighthouse_gc.core.workspace import WorkspaceError
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.sources.http import SourceError

app = typer.Typer(
    name="lighthouse-gc",
    help="Local-first command center for an O-1A / EB-1A evidence file. Not legal advice.",
    no_args_is_help=True,
    add_completion=False,
)

WorkspaceOpt = Annotated[
    Path | None,
    typer.Option(
        "--workspace",
        "-w",
        help="Workspace directory. Default: $LIGHTHOUSE_GC_WORKSPACE or the "
        "nearest parent of the current directory containing lighthouse.yaml.",
    ),
]


def find_workspace(explicit: Path | None) -> Case:
    if explicit:
        return Case(explicit).require()
    if os.environ.get("LIGHTHOUSE_GC_WORKSPACE"):
        return Case(os.environ["LIGHTHOUSE_GC_WORKSPACE"]).require()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        ws = Case(candidate)
        if ws.exists():
            return ws
    raise WorkspaceError("No workspace found. Run `lighthouse-gc init <dir>` or pass --workspace.")


def _fail(msg: str) -> typer.Exit:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


@app.callback(invoke_without_command=True)
def _main(
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
) -> None:
    if version:
        typer.echo(f"lighthouse-gc {__version__}")
        raise typer.Exit()


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="Directory to create, e.g. ~/my-case")],
    name: Annotated[str, typer.Option(help="Your name, for data/person.json")] = "",
    profile: Annotated[str, typer.Option(help="Criteria profile: o1a or eb1a")] = "o1a",
    git: Annotated[
        bool, typer.Option(help="git init the workspace and install the gitleaks pre-commit hook")
    ] = True,
) -> None:
    """Create a private case workspace (its own Git repo)."""
    from lighthouse_gc.scaffold import create_workspace

    try:
        ws = create_workspace(path, name=name, profile=profile, git=git)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    typer.secho(f"Workspace created at {ws.root}", fg=typer.colors.GREEN)
    typer.echo("Next steps:")
    typer.echo(f"  cd {ws.root}")
    typer.echo("  lighthouse-gc import https://github.com/<you>")
    typer.echo("  lighthouse-gc up")
    typer.echo("Keep this directory private: push it only to a private remote.")


@app.command("import")
def import_(
    url: Annotated[
        str,
        typer.Argument(
            help="GitHub or Hugging Face URL / handle (github:octo, hf:octo), or a Claude / ChatGPT export "
            "(conversations.json or the export .zip)"
        ),
    ],
    private: Annotated[
        bool, typer.Option("--private", help="Prompt for a read-only token (stored in the keychain)")
    ] = False,
    token_env: Annotated[
        str | None, typer.Option(help="Read the token from this environment variable instead")
    ] = None,
    snapshot: Annotated[bool, typer.Option(help="Also take a metrics snapshot now")] = True,
    workspace: WorkspaceOpt = None,
) -> None:
    """Add a source: auto-detects the connector, discovers items, proposes candidates."""
    from lighthouse_gc import sources
    from lighthouse_gc.jobs.sync import import_source

    path = Path(url).expanduser()
    if path.suffix.lower() in (".json", ".zip") and path.is_file():
        return _import_chats(path, workspace)
    try:
        ws = find_workspace(workspace)
        kind = sources.detect(url)
    except (WorkspaceError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    token = None
    if token_env:
        token = os.environ.get(token_env) or None
        if token is None:
            raise _fail(f"${token_env} is empty")
    elif private:
        help_url = sources.token_help(kind)
        if help_url:
            typer.echo(f"Create a read-only token here: {help_url}")
        token = typer.prompt("Token", hide_input=True)
    typer.echo(f"Detected {kind}. Importing…")
    try:
        report = import_source(ws, url, token=token, snapshot=snapshot)
    except SourceError as exc:
        raise _fail(str(exc)) from exc
    typer.secho(report.line(), fg=typer.colors.GREEN if not report.errors else typer.colors.YELLOW)
    if report.candidates_added:
        typer.echo("Review new candidates in the Inbox: lighthouse-gc up")


def _import_chats(path: Path, workspace: Path | None) -> None:
    from lighthouse_gc.jobs.chats import import_chats
    from lighthouse_gc.sources.chat_export import ExportError, read_export

    try:
        ws = find_workspace(workspace)
        report = import_chats(ws, read_export(path), path.name)
    except (WorkspaceError, ExportError) as exc:
        raise _fail(str(exc)) from exc
    typer.secho(report.line(), fg=typer.colors.GREEN)
    if report.candidates_added:
        typer.echo("Review them in the Inbox: lighthouse-gc up")


@app.command()
def run(
    job: Annotated[str, typer.Argument(help="Job name (see `lighthouse-gc run --list`)")] = "",
    list_jobs: Annotated[bool, typer.Option("--list", help="List available jobs")] = False,
    workspace: WorkspaceOpt = None,
) -> None:
    """Run one job headless (for cron / launchd / GitHub Actions)."""
    from lighthouse_gc.jobs import JOBS

    if list_jobs or not job:
        for name, (desc, _) in JOBS.items():
            typer.echo(f"{name:18} {desc}")
        return
    if job not in JOBS:
        raise _fail(f"unknown job {job!r}; available: {', '.join(JOBS)}")
    try:
        ws = find_workspace(workspace)
        for line in JOBS[job][1](ws, False):
            typer.echo(line)
    except (WorkspaceError, SourceError) as exc:
        raise _fail(str(exc)) from exc


@app.command()
def up(
    port: Annotated[int | None, typer.Option(help="Port (default from lighthouse.yaml, 7777)")] = None,
    demo: Annotated[
        bool, typer.Option("--demo", help="Serve a throwaway copy of the demo workspace")
    ] = False,
    scheduler: Annotated[
        bool | None,
        typer.Option(
            "--scheduler/--no-scheduler",
            help="Run scheduled jobs in the background (default: on; off with --demo)",
        ),
    ] = None,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the dashboard in a browser")
    ] = True,
    workspace: WorkspaceOpt = None,
) -> None:
    """Serve the dashboard on http://127.0.0.1 (localhost only)."""
    import uvicorn

    from lighthouse_gc.resources import demo_workspace_dir, web_static_dir
    from lighthouse_gc.server.app import create_app

    try:
        if demo:
            tmp = Path(tempfile.mkdtemp(prefix="lighthouse-demo-"))
            shutil.copytree(demo_workspace_dir(), tmp / "demo-workspace")
            ws = Case(tmp / "demo-workspace").require()
            typer.echo(f"Demo workspace copied to {ws.root} (changes are thrown away).")
        else:
            ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    if not (web_static_dir() / "index.html").exists():
        typer.secho(
            "Web UI not built — the API works but pages won't. Run `npm --prefix web run build`.",
            fg=typer.colors.YELLOW,
        )
    port = port or ws.config().server.port
    url = f"http://127.0.0.1:{port}"
    typer.secho(f"Lighthouse for {ws.root} → {url}", fg=typer.colors.GREEN)
    if open_browser:
        webbrowser.open(url)
    sched = None
    if scheduler if scheduler is not None else not demo:
        from lighthouse_gc.jobs.scheduler import start

        sched = start(ws)
        typer.echo(f"Scheduler on: {', '.join(sorted(ws.config().schedules))}")
    try:
        uvicorn.run(create_app(ws), host="127.0.0.1", port=port, log_level="warning")
    finally:
        if sched is not None:
            sched.shutdown(wait=False)


notify_app = typer.Typer(help="Notifications (desktop, email, Slack, Discord, ntfy).", no_args_is_help=True)
secret_app = typer.Typer(help="Store or remove a secret (token, webhook URL, SMTP password) in the keychain.",
                         no_args_is_help=True)  # fmt: skip
app.add_typer(notify_app, name="notify")
app.add_typer(secret_app, name="secret")


@notify_app.command("test")
def notify_test(
    channel: Annotated[
        str | None, typer.Option(help="Only this channel (default: every channel routed for `test`)")
    ] = None,
    workspace: WorkspaceOpt = None,
) -> None:
    """Send a test notification."""
    from lighthouse_gc.notify import Notification, send

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    report = send(ws, Notification("test", "Lighthouse test", "Notifications are working.",
                                   minimal_body="Notifications are working."), only=channel)  # fmt: skip
    typer.secho(report.line(), fg=typer.colors.GREEN if report.ok else typer.colors.RED)
    if not report.ok:
        raise typer.Exit(1)


@secret_app.command("set")
def secret_set(
    ref: Annotated[
        str, typer.Argument(help="Keychain entry name, e.g. notify:slack (the channel's secret_ref)")
    ],
    workspace: WorkspaceOpt = None,
) -> None:
    """Prompt for a secret (hidden) and store it in the OS keychain."""
    from lighthouse_gc.core.secrets import set_secret

    ws_root = None
    with contextlib.suppress(WorkspaceError):  # keychain-only is fine outside a workspace
        ws_root = find_workspace(workspace).root
    value = typer.prompt(f"Value for {ref}", hide_input=True)
    where = set_secret(ref, value.strip(), ws_root)
    typer.secho(f"Stored {ref} in the {where}.", fg=typer.colors.GREEN)


@secret_app.command("delete")
def secret_delete(ref: Annotated[str, typer.Argument()], workspace: WorkspaceOpt = None) -> None:
    """Remove a secret from the keychain (and the workspace .env fallback)."""
    from lighthouse_gc.core.secrets import delete_secret

    try:
        root = find_workspace(workspace).root
    except WorkspaceError:
        root = None
    delete_secret(ref, root)
    typer.echo(f"Removed {ref}.")


@app.command()
def mcp(workspace: WorkspaceOpt = None) -> None:
    """Run a read-only MCP server over stdio (e.g. `claude mcp add lighthouse -- lighthouse-gc mcp -w <dir>`)."""
    from lighthouse_gc.mcp.server import serve

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    serve(ws)  # stdout belongs to the MCP protocol: print nothing else


@app.command()
def validate(workspace: WorkspaceOpt = None) -> None:
    """Check every workspace file against its schema and the evidence naming rules."""
    from lighthouse_gc.scaffold import validate_workspace

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    problems = validate_workspace(ws)
    if problems:
        for p in problems:
            typer.secho(f"✗ {p}", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"✓ {ws.root} is valid", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
