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
