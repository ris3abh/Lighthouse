"""Generate the JSON Schemas in ``lighthouse_gc/core/schemas/`` from the core and domain models.

python -m lighthouse_gc.schemas
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from lighthouse_gc.core import models as core
from lighthouse_gc.core.schemas import SCHEMA_DIR
from lighthouse_gc.criteria import models as domain

SCHEMA_BASE_URI = "https://lighthouse-gc.dev/schemas"

# schema file stem -> model. JSONL files get a per-line schema.
MODELS: dict[str, type[BaseModel]] = {
    "person": domain.Person,
    "sources": core.SourcesFile,
    "inbox": core.Inbox,
    "exhibits": core.Exhibits,
    "criteria": domain.Scoreboard,
    "metric-row": core.MetricRow,
    "pipeline": core.Pipeline,
    "letters": domain.Letters,
    "deadlines": core.Deadlines,
    "opportunities": core.Opportunities,
    "lighthouse-config": core.WorkspaceConfig,
    "profile": domain.Profile,
    "memory-observation": core.Observation,
    "memory-entity": core.Entity,
    "memory-claim": core.Claim,
    "memory-edge": core.Edge,
    "memory-decision": core.Decision,
}


def build_schemas() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for stem, model in MODELS.items():
        out[f"{stem}.schema.json"] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{SCHEMA_BASE_URI}/v{core.SCHEMA_VERSION}/{stem}.schema.json",
            **model.model_json_schema(mode="serialization"),
        }
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


if __name__ == "__main__":
    for p in write_schemas():
        print(p)
