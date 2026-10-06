"""``lighthouse-gc init``: create a private workspace from the template, plus workspace validation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pydantic import ValidationError

from lighthouse_gc.core.models import Person, WorkspaceConfig
from lighthouse_gc.core.schemas import schema_files
from lighthouse_gc.core.workspace import DATA_FILES, Workspace, WorkspaceError, _atomic_write, dump_model
from lighthouse_gc.resources import workspace_template_dir


def create_workspace(
    path: Path | str,
    *,
    name: str = "",
    profile: str = "o1a",
    git: bool = True,
) -> Workspace:
    ws = Workspace(path)
    if ws.exists():
        raise WorkspaceError(f"{ws.root} is already a Lighthouse workspace.")
    if ws.root.exists() and any(p for p in ws.root.iterdir() if p.name != ".git"):
        raise WorkspaceError(f"{ws.root} exists and is not empty.")
    ws.root.mkdir(parents=True, exist_ok=True)
    ws.profile(profile)  # fail early on an unknown profile

    template = workspace_template_dir()
    shutil.copytree(template / ".claude", ws.root / ".claude", dirs_exist_ok=True)
    shutil.copytree(template / "drafts", ws.root / "drafts", dirs_exist_ok=True)
    shutil.copy(template / "AGENTS.md", ws.root / "AGENTS.md")
    shutil.copy(template / "gitignore.txt", ws.root / ".gitignore")

    schemas = ws.root / ".lighthouse" / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    for schema in schema_files():
        shutil.copy(schema, schemas / schema.name)

    ws.save_config(WorkspaceConfig(workspace_name=ws.root.name, profile=profile))
    for filename, model in DATA_FILES.items():
        value = Person(name=name) if model is Person else model()
        _atomic_write(ws.data_dir / filename, dump_model(value))
    ws.append_metrics([])  # header-only metrics.csv

    criteria = {c.id for p in ws.profiles().values() for c in p.criteria}
    for crit in sorted(criteria):
        (ws.evidence_dir / crit).mkdir(parents=True, exist_ok=True)
        (ws.evidence_dir / crit / ".gitkeep").touch()

    ws.after_change()
    if git:
        _git_init(ws.root, template / "pre-commit.sh")
    return ws


def _git_init(root: Path, hook: Path) -> None:
    if shutil.which("git") is None:
        return
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    target = hooks / "pre-commit"
    shutil.copy(hook, target)
    target.chmod(0o755)


def validate_workspace(ws: Workspace) -> list[str]:
    """Every problem found, as human-readable lines. Empty list = valid."""
    problems: list[str] = []
    try:
        cfg = ws.config()
        if cfg.profile not in ws.profiles():
            problems.append(f"lighthouse.yaml: unknown profile {cfg.profile!r}")
    except (ValidationError, ValueError) as exc:
        problems.append(f"lighthouse.yaml: {exc}")
    for filename, model in DATA_FILES.items():
        path = ws.data_dir / filename
        if not path.exists():
            problems.append(f"data/{filename}: missing")
            continue
        try:
            model.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            problems.append(f"data/{filename}: {exc}")
    try:
        ws.metrics()
    except (ValidationError, ValueError) as exc:
        problems.append(f"data/metrics.csv: {exc}")
    try:
        ws.profiles()
    except (ValidationError, ValueError) as exc:
        problems.append(f"profiles: {exc}")
    for issue in ws.naming_check():
        problems.append(f"{issue['file']}: {issue['problem']} — {issue['detail']}")
    return problems
