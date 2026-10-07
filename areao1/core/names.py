"""Every name the product uses, from names.json (ADR 0010): the web app imports the same file, and
tests/test_names.py checks the files that can't (installers, workflows, pyproject, landing page) agree with it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_N: dict[str, Any] = json.loads(Path(__file__).with_name("names.json").read_text())

PRODUCT: str = _N["product"]
PACKAGE: str = _N["package"]
CLI: str = _N["cli"]
MCP_SERVER: str = _N["mcp_server"]
ENV_PREFIX: str = _N["env_prefix"]
KEYCHAIN_SERVICE: str = _N["keychain_service"]
CONFIG_DIR: str = _N["config_dir"]
WORKSPACE_CONFIG: str = _N["workspace_config"]
WORKSPACE_STATE: str = _N["workspace_state"]
DEFAULT_HOME: str = _N["default_home"]
WRITE_HEADER: str = _N["write_header"]
REPO: str = _N["repo"]
PREVIOUS: dict[str, Any] = _N["previous"]


def env(name: str) -> str:
    """AREAO1_HOME for "HOME"."""
    return ENV_PREFIX + name
