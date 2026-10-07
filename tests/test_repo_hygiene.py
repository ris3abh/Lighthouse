"""The spec, the two-repo warning and the no-private-data rule must survive every commit."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_repo", Path(__file__).parent.parent / "scripts" / "check_repo.py"
)
check_repo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_repo)


def test_repo_guard_passes():
    assert check_repo.problems() == []


def test_workspace_template_files_are_not_gitignored():
    """The wheel is built from what git doesn't ignore: a broad ignore (".claude/") once dropped the workspace
    template's .claude folder, and `init` failed from the installed wheel."""
    import subprocess

    root = Path(__file__).resolve().parents[1]
    files = subprocess.run(
        ["git", "ls-files", "lighthouse_gc/templates"], cwd=root, capture_output=True, text=True
    ).stdout.split()
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", *files], cwd=root, capture_output=True, text=True
    ).stdout.split()
    assert files and not ignored
