"""The one-line installers (ADR 0013, S4): short enough to read before running, strict, and they change
nothing on the machine beyond uv and Lighthouse itself. CI runs them for real against a local wheel."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT / "install.sh"
PS1 = ROOT / "install.ps1"

# Anything that reaches past "install uv, install Lighthouse, run it".
FORBIDDEN = [
    r"\bsudo\b", r"\bsu\b", r"\bchmod\b", r"\bchown\b", r"\brm\b", r"Remove-Item",
    r"\.bashrc", r"\.zshrc", r"\.bash_profile", r"(?<![\w-])\.profile", r"\$PROFILE", r"update-shell\s*$",
    r"\bsetx\b", r"SetEnvironmentVariable", r"Set-ExecutionPolicy", r"Add-Content", r"Out-File", r">>",
    r"\bapt(-get)?\b", r"\bbrew\b", r"\bwinget\b", r"\bchoco\b", r"\bpip\b", r"Start-Process.*RunAs",
]  # fmt: skip


def _code(path: Path) -> list[str]:
    return [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


@pytest.mark.parametrize("path", [SH, PS1], ids=["sh", "ps1"])
def test_installer_is_short_and_says_what_it_does(path):
    assert len(path.read_text().splitlines()) <= 50
    assert len(_code(path)) <= 30
    head = path.read_text()[:800]
    assert "uv" in head and "no other change" in head  # the header says what it does before any code


@pytest.mark.parametrize("path", [SH, PS1], ids=["sh", "ps1"])
def test_installer_makes_no_other_machine_changes(path):
    for line in _code(path):
        code = line.split(" # ")[0]
        for pattern in FORBIDDEN:
            assert not re.search(pattern, code), f"{path.name}: {pattern!r} in {line.strip()!r}"
    # Only Astral's official uv installer and this repo's releases ($repo is ris3abh/Lighthouse).
    urls = set(re.findall(r"https://[\w./$-]+", "\n".join(_code(path))))
    official = {
        "https://astral.sh/uv/install.sh",
        "https://astral.sh/uv/install.ps1",
        "https://docs.astral.sh/uv/",
    }
    ours = ("https://api.github.com/repos/$repo/", "https://github.com/$repo/")
    assert all(u in official or u.startswith(ours) for u in urls), urls


@pytest.mark.parametrize("path", [SH, PS1], ids=["sh", "ps1"])
def test_installer_installs_a_uv_tool_on_312_with_ci_overrides(path):
    text = path.read_text()
    assert "uv tool install --force --python 3.12" in text
    assert "LIGHTHOUSE_GC_SPEC" in text and "LIGHTHOUSE_GC_NO_RUN" in text
    assert "releases/latest" in text and "ris3abh/Lighthouse" in text  # default: the latest release wheel
    assert "lighthouse-gc" in text  # and then it runs Lighthouse


def test_sh_is_strict_posix_and_parses():
    lines = SH.read_text().splitlines()
    assert lines[0] == "#!/bin/sh"
    assert _code(SH)[0] == "set -eu"
    assert "[[" not in SH.read_text() and "pipefail" not in SH.read_text()  # POSIX sh, not bash
    subprocess.run(["sh", "-n", str(SH)], check=True)
    if shutil.which("shellcheck"):
        subprocess.run(["shellcheck", "-s", "sh", str(SH)], check=True)


def test_ps1_is_strict():
    code = _code(PS1)
    assert code[0] == "Set-StrictMode -Version Latest"
    assert code[1] == "$ErrorActionPreference = 'Stop'"
    assert re.search(r"\bexit\b", PS1.read_text()) is None  # `exit` would close the window under irm | iex


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh")
def test_sh_installs_the_override_with_uv_and_skips_running(tmp_path):
    """Run install.sh against a stand-in `uv` that records its arguments: no network, nothing installed."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "uv.log"
    fake = bindir / "uv"
    fake.write_text(
        f'#!/bin/sh\necho "$@" >> "{log}"\n[ "$*" = "tool dir --bin" ] && echo "{bindir}"\nexit 0\n'
    )
    fake.chmod(0o755)
    env = {
        "PATH": f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "LIGHTHOUSE_GC_SPEC": "/wheels/lighthouse_gc-1.0.0-py3-none-any.whl",
        "LIGHTHOUSE_GC_NO_RUN": "1",
    }
    out = subprocess.run(["sh", str(SH)], env=env, capture_output=True, text=True, check=True)
    assert log.read_text().splitlines() == [
        "tool install --force --python 3.12 /wheels/lighthouse_gc-1.0.0-py3-none-any.whl"
    ]
    assert "Installing uv" not in out.stdout and "Installed." in out.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bin", "uv.log"]  # nothing written to HOME


def test_ci_runs_both_installers_against_the_local_wheel():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    sh, ps1 = jobs["install-sh"], jobs["install-ps1"]
    assert set(sh["strategy"]["matrix"]["os"]) == {"ubuntu-latest", "macos-latest"}
    assert ps1["runs-on"] == "windows-latest"
    for job in (sh, ps1):
        assert job["needs"] == "wheel"  # the wheel the wheel job built and smoke-tested
        cmds = "\n".join(s.get("run", "") for s in job["steps"])
        for needle in (
            "LIGHTHOUSE_GC_SPEC",
            "dist",
            "LIGHTHOUSE_GC_NO_RUN",
            "--help",
            "scripts/smoke_wheel.py",
        ):
            assert needle in cmds, needle
    assert "sh install.sh" in "\n".join(s.get("run", "") for s in sh["steps"])
    assert "install.ps1 -Raw | Invoke-Expression" in "\n".join(s.get("run", "") for s in ps1["steps"])
