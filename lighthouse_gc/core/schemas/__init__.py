"""Versioned JSON Schemas for workspace files, generated from :mod:`lighthouse_gc.core.models`.

Regenerate after changing a model::

    python -m lighthouse_gc.core.schemas
"""

from __future__ import annotations

import json
from pathlib import Path

from lighthouse_gc.core.models import SCHEMA_VERSION, WORKSPACE_FILE_MODELS

SCHEMA_DIR = Path(__file__).parent
SCHEMA_BASE_URI = "https://lighthouse-gc.dev/schemas"


def build_schemas() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for stem, model in WORKSPACE_FILE_MODELS.items():
        schema = model.model_json_schema(mode="serialization")
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{SCHEMA_BASE_URI}/v{SCHEMA_VERSION}/{stem}.schema.json",
            **schema,
        }
        out[f"{stem}.schema.json"] = schema
    return out


def schema_text(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_schemas(directory: Path = SCHEMA_DIR) -> list[Path]:
    written = []
    for name, schema in build_schemas().items():
        path = directory / name
        path.write_text(schema_text(schema))
        written.append(path)
    return written


def schema_files() -> list[Path]:
    return sorted(SCHEMA_DIR.glob("*.schema.json"))
