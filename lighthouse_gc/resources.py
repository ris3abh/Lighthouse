"""Locate bundled data (profiles, demo workspace, workspace template, web UI).

In a wheel, repo-level folders are force-included under ``lighthouse_gc/_data/``. In a source checkout
(editable install) they are read straight from the repo root.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
_BUNDLED = PACKAGE_DIR / "_data"


def _pick(bundled: str, repo_relative: str) -> Path:
    candidate = _BUNDLED / bundled
    return candidate if candidate.exists() else REPO_DIR / repo_relative


def profiles_dir() -> Path:
    return _pick("profiles", "profiles")


def vault_manifest_path() -> Path:
    return _pick("vault", "vault") / "sources.yaml"


def demo_workspace_dir() -> Path:
    return _pick("demo-workspace", "examples/demo-workspace")


def workspace_template_dir() -> Path:
    return PACKAGE_DIR / "templates" / "workspace"


def web_static_dir() -> Path:
    return PACKAGE_DIR / "server" / "static"
