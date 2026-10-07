"""``areao1`` command line: init, up, import, run <job>, validate."""

from __future__ import annotations

import contextlib
import os
import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from areao1 import __version__
from areao1.core import migrate, names
from areao1.core.workspace import WorkspaceError
from areao1.criteria.case import Case
from areao1.sources.http import SourceError

app = typer.Typer(
    name=names.CLI,
    help="Local-first command center for an O-1A / EB-1A evidence file. Not legal advice.",
    add_completion=False,
)

WorkspaceOpt = Annotated[
    Path | None,
    typer.Option(
        "--workspace",
        "-w",
        help="Workspace directory. Default: $AREAO1_WORKSPACE, the nearest parent of the current "
        "directory containing areao1.yaml, or the workspace you opened last.",
    ),
]


def find_workspace(explicit: Path | None) -> Case:
    if explicit:
        return Case(explicit).require()
    if migrate.env("WORKSPACE"):
        return Case(migrate.env("WORKSPACE") or "").require()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        ws = Case(candidate)
        if ws.exists():
            return ws
    from areao1.home import remembered

    last = remembered()
    if last is not None and Case(last).exists():
        return Case(last)
    raise WorkspaceError(
        "No workspace found. Run `areao1` to start, `areao1 init <dir>`, or pass --workspace."
    )


def _fail(msg: str) -> typer.Exit:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    return typer.Exit(1)


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
) -> None:
    """With no command: open your workspace (creating ~/AreaO1 the first time) in the browser."""
    if version:
        typer.echo(f"areao1 {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _serve(_first_run_workspace(), port=None, scheduler=None, open_browser=True)


def _first_run_workspace() -> Case:
    from areao1.home import default_workspace
    from areao1.scaffold import create_workspace

    try:
        return find_workspace(None)
    except WorkspaceError:
        pass
    target = default_workspace()
    if Case(target).exists():
        return Case(target)
    try:
        ws = create_workspace(target)
    except WorkspaceError as exc:
        raise _fail(f"{exc} Pick another place with `areao1 init <dir>`.") from exc
    typer.secho(f"Created your private workspace at {ws.root}", fg=typer.colors.GREEN)
    typer.echo("It's a folder of plain files and its own git repo. Back it up only to a private remote.")
    return ws


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
    from areao1.scaffold import create_workspace

    try:
        ws = create_workspace(path, name=name, profile=profile, git=git)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    from areao1.home import remember, remembered

    if remembered() is None:
        remember(ws.root)
    typer.secho(f"Workspace created at {ws.root}", fg=typer.colors.GREEN)
    typer.echo(f"Next: areao1 up -w {ws.root}")
    typer.echo("Keep this directory private: push it only to a private remote.")


@app.command("import")
def import_(
    url: Annotated[
        str,
        typer.Argument(
            help="GitHub or Hugging Face URL / handle (github:octo, hf:octo), a scholarly profile (Semantic Scholar, "
            "OpenAlex, arxiv.org/a/<id>, ORCID iD), or a Claude / ChatGPT export (conversations.json or the export .zip)"
        ),
    ],
    private: Annotated[
        bool, typer.Option("--private", help="Prompt for a read-only token (stored in the keychain)")
    ] = False,
    token_env: Annotated[
        str | None, typer.Option(help="Read the token from this environment variable instead")
    ] = None,
    snapshot: Annotated[bool, typer.Option(help="Also take a metrics snapshot now")] = True,
    keep_all: Annotated[
        bool,
        typer.Option("--keep-all", help="Chat exports: also save conversations that produced no suggestions"),
    ] = False,
    workspace: WorkspaceOpt = None,
) -> None:
    """Add a source: auto-detects the connector, discovers items, proposes candidates."""
    from areao1 import sources
    from areao1.jobs.sync import import_source

    path = Path(url).expanduser()
    if path.suffix.lower() in (".json", ".zip") and path.is_file():
        return _import_chats(path, workspace, keep_all)
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
        typer.echo("Review new candidates in the Inbox: areao1 up")


def _import_chats(path: Path, workspace: Path | None, keep_all: bool = False) -> None:
    from areao1.jobs.chats import import_chats
    from areao1.sources.chat_export import ExportError, read_export

    try:
        ws = find_workspace(workspace)
        report = import_chats(ws, read_export(path), path.name, keep_all=keep_all)
    except (WorkspaceError, ExportError) as exc:
        raise _fail(str(exc)) from exc
    typer.secho(report.line(), fg=typer.colors.GREEN)
    if report.candidates_added:
        typer.echo("Review them in the Inbox: areao1 up")


@app.command()
def run(
    job: Annotated[str, typer.Argument(help="Job name (see `areao1 run --list`)")] = "",
    list_jobs: Annotated[bool, typer.Option("--list", help="List available jobs")] = False,
    workspace: WorkspaceOpt = None,
) -> None:
    """Run one job headless (for cron / launchd / GitHub Actions)."""
    from areao1.jobs import JOBS

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
    port: Annotated[int | None, typer.Option(help="Port (default from areao1.yaml, 7777)")] = None,
    scheduler: Annotated[
        bool | None,
        typer.Option(
            "--scheduler/--no-scheduler",
            help="Run scheduled jobs in the background (default: on)",
        ),
    ] = None,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the dashboard in a browser")
    ] = True,
    workspace: WorkspaceOpt = None,
) -> None:
    """Serve the dashboard on http://127.0.0.1 (localhost only)."""
    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    _serve(ws, port=port, scheduler=scheduler, open_browser=open_browser)


def _running(url: str) -> str | None:
    """Who answers at url: an Area O1's workspace id, "other" for anything else on that port, None when free."""
    import httpx

    try:
        r = httpx.get(f"{url}/api/health", timeout=0.5)
    except httpx.HTTPError:
        return None
    try:
        return str(r.json()["workspace_id"]) if r.status_code == 200 else "other"
    except (ValueError, KeyError, TypeError):
        return "other"


def _serve(ws: Case, *, port: int | None, scheduler: bool | None, open_browser: bool) -> None:
    import uvicorn

    from areao1.home import remember
    from areao1.resources import web_static_dir
    from areao1.server.app import create_app

    remember(ws.root)
    if not (web_static_dir() / "index.html").exists():
        typer.secho(
            "Web UI not built — the API works but pages won't. Run `npm --prefix web run build`.",
            fg=typer.colors.YELLOW,
        )
    from areao1.home import workspace_id

    wanted = port or ws.config().server.port
    mine = workspace_id(ws.root)
    for port in range(wanted, wanted + 20):
        url = f"http://127.0.0.1:{port}"
        who = _running(url)
        if who == mine:  # already open (a second launch): just bring it up
            typer.secho(f"Area O1 is already running → {url}", fg=typer.colors.GREEN)
            if open_browser:
                webbrowser.open(url)
            return
        if who is None:
            break
    else:
        raise _fail(f"Ports {wanted}–{wanted + 19} are all taken. Pick one with --port.")
    if port != wanted:  # another case's Area O1 (or another app) has the usual port
        typer.secho(
            f"Port {wanted} is taken by something else, so this one uses {port}.", fg=typer.colors.YELLOW
        )
    typer.secho(f"Area O1 for {ws.root} → {url}", fg=typer.colors.GREEN)
    if open_browser:
        webbrowser.open(url)
    sched = None
    if scheduler if scheduler is not None else True:
        from areao1.jobs.scheduler import start

        sched = start(ws)
        typer.echo(f"Scheduler on: {', '.join(sorted(n for n, e in ws.config().schedules.items() if e))}")
    try:
        uvicorn.run(create_app(ws), host="127.0.0.1", port=port, log_level="warning")
    finally:
        if sched is not None:
            sched.shutdown(wait=False)


notify_app = typer.Typer(help="Notifications (desktop, email, Slack, Discord, ntfy).", no_args_is_help=True)
secret_app = typer.Typer(help="Store or remove a secret (token, webhook URL, SMTP password) in the keychain.",
                         no_args_is_help=True)  # fmt: skip
vault_app = typer.Typer(help="Knowledge vault: official sources, fetched, snapshotted and searchable.",
                        no_args_is_help=True)  # fmt: skip
app.add_typer(notify_app, name="notify")
app.add_typer(vault_app, name="vault")
app.add_typer(secret_app, name="secret")


@notify_app.command("test")
def notify_test(
    channel: Annotated[
        str | None, typer.Option(help="Only this channel (default: every channel routed for `test`)")
    ] = None,
    workspace: WorkspaceOpt = None,
) -> None:
    """Send a test notification."""
    from areao1.notify import Notification, send

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    report = send(ws, Notification("test", "Area O1 test", "Notifications are working.",
                                   minimal_body="Notifications are working."), only=channel)  # fmt: skip
    typer.secho(report.line(), fg=typer.colors.GREEN if report.ok else typer.colors.RED)
    if not report.ok:
        raise typer.Exit(1)


@vault_app.command("sync")
def vault_sync(
    source: Annotated[list[str] | None, typer.Option("--source", "-s", help="Only these source ids")] = None,
    force: Annotated[bool, typer.Option(help="Re-fetch even if still fresh")] = False,
    workspace: WorkspaceOpt = None,
) -> None:
    """Fetch the vault sources that are due (never fetched or past their freshness window)."""
    import anyio

    from areao1.vault import Vault
    from areao1.vault.watch import summarize

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    vault = Vault(ws)
    try:
        results = anyio.run(lambda: vault.sync(source or None, force=force))
    except ValueError as exc:
        raise _fail(str(exc)) from exc
    for r in results:
        color = {"new": typer.colors.GREEN, "changed": typer.colors.YELLOW, "unreadable": typer.colors.RED,
                 "error": typer.colors.RED}.get(r.status)  # fmt: skip
        typer.secho(f"{r.status:>10}  {r.source_id}" + (f"  {r.error}" if r.error else ""), fg=color)
    typer.echo(summarize(results))


@vault_app.command("import")
def vault_import(
    source: Annotated[str, typer.Argument(help="Source id (see `areao1 vault status`)")],
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="A page saved from your browser")],
    workspace: WorkspaceOpt = None,
) -> None:
    """Import a page you saved from your browser, for sources that block automated reading."""
    from areao1.vault import Vault

    try:
        ws = find_workspace(workspace)
        r = Vault(ws).import_file(source, file.read_bytes(), file.name)
    except (WorkspaceError, ValueError) as exc:
        raise _fail(str(exc)) from exc
    typer.secho(
        f"{r.status}  {source}  ({r.chars:,} characters, fresh until it expires)", fg=typer.colors.GREEN
    )


@vault_app.command("search")
def vault_search(
    query: str,
    k: Annotated[int, typer.Option("-k", help="How many results")] = 5,
    workspace: WorkspaceOpt = None,
) -> None:
    """Search the vault (full text + local embeddings)."""
    from areao1.vault import Vault

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    hits = Vault(ws).search(query, k=k)
    if not hits:
        typer.echo("no matches (run `areao1 vault sync` first?)")
    for h in hits:
        fresh = "fresh" if h.fresh else "STALE"
        typer.secho(f"[tier {h.tier} · {fresh}] {h.title}", bold=True)
        typer.echo(f"  {h.url}")
        typer.echo("  " + " ".join(h.text.split())[:400] + "\n")


@vault_app.command("status")
def vault_status(workspace: WorkspaceOpt = None) -> None:
    """Each source: tier, freshness, last check, last change."""
    from areao1.vault import Vault

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    for s in Vault(ws).status():
        state = "fresh" if s["fresh"] else s["status"] if s["status"] != "ok" else "stale"
        typer.echo(f"T{s['tier']}  {state:<15} {s['id']:<28} {s['checked_at'] or '-'}")


@secret_app.command("set")
def secret_set(
    ref: Annotated[
        str, typer.Argument(help="Keychain entry name, e.g. notify:slack (the channel's secret_ref)")
    ],
    workspace: WorkspaceOpt = None,
) -> None:
    """Prompt for a secret (hidden) and store it in the OS keychain."""
    from areao1.core.secrets import set_secret

    ws_root = None
    with contextlib.suppress(WorkspaceError):  # keychain-only is fine outside a workspace
        ws_root = find_workspace(workspace).root
    value = typer.prompt(f"Value for {ref}", hide_input=True)
    where = set_secret(ref, value.strip(), ws_root)
    typer.secho(f"Stored {ref} in the {where}.", fg=typer.colors.GREEN)


@secret_app.command("delete")
def secret_delete(ref: Annotated[str, typer.Argument()], workspace: WorkspaceOpt = None) -> None:
    """Remove a secret from the keychain (and the workspace .env fallback)."""
    from areao1.core.secrets import delete_secret

    try:
        root = find_workspace(workspace).root
    except WorkspaceError:
        root = None
    delete_secret(ref, root)
    typer.echo(f"Removed {ref}.")


@app.command()
def mcp(workspace: WorkspaceOpt = None) -> None:
    """Run a read-only MCP server over stdio (e.g. `claude mcp add areao1 -- areao1 mcp -w <dir>`)."""
    from areao1.mcp.server import serve

    try:
        ws = find_workspace(workspace)
    except WorkspaceError as exc:
        raise _fail(str(exc)) from exc
    serve(ws)  # stdout belongs to the MCP protocol: print nothing else


@app.command()
def validate(workspace: WorkspaceOpt = None) -> None:
    """Check every workspace file against its schema and the evidence naming rules."""
    from areao1.scaffold import validate_workspace

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


def deprecated() -> None:
    """`lighthouse-gc`, the Lighthouse-era command: says the new name, then runs it (ADR 0010)."""
    typer.secho(f"{names.PREVIOUS['cli']} is now {names.CLI}; the old command still works for now.", err=True,
                fg=typer.colors.YELLOW)  # fmt: skip
    app()


if __name__ == "__main__":
    app()
