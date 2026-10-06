"""Repo guard run by the pre-commit hook (.githooks/pre-commit) and by the test suite.

Fails if the spec loses a required section, if the README / CONTRIBUTING lose the "two separate repos"
warning, or if something that looks like a private case workspace appears outside examples/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = {
    "SPEC.md": [
        "## 5a. Knowledge vault",
        "## 5b. Evidence-aware graph memory",
        "## 5c. Evaluation harness",
        "## 11a. Priorities: product first, research second",
        "Two repositories for contributor-users",
        "Core/profile split",
        "Approval records a decision; it does not certify truth or",
    ],
    "README.md": ["Keep two separate repos", "fresh private repo", "not legal advice"],
    "CONTRIBUTING.md": ["keep two separate repos", "fresh private repo"],
}

# A real workspace has a lighthouse.yaml; only the fictional demo may have one in this repo.
ALLOWED_WORKSPACES = {ROOT / "examples" / "demo-workspace"}
SKIP_DIRS = {".git", ".venv", "node_modules", "dist", "build"}


def problems() -> list[str]:
    out = []
    for name, needles in REQUIRED.items():
        path = ROOT / name
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        out += [f"{name}: missing required text {n!r}" for n in needles if n not in text]
    for cfg in ROOT.rglob("lighthouse.yaml"):
        if SKIP_DIRS & set(cfg.relative_to(ROOT).parts):
            continue
        if cfg.parent not in ALLOWED_WORKSPACES:
            out.append(
                f"{cfg.relative_to(ROOT)}: looks like a case workspace inside the app repo — keep it private"
            )
    return out


if __name__ == "__main__":
    found = problems()
    for p in found:
        print(f"✗ {p}", file=sys.stderr)
    sys.exit(1 if found else 0)
