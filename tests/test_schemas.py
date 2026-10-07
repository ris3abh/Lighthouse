"""JSON Schemas are generated from the pydantic models; the fixture workspaces must validate against both."""

from __future__ import annotations

import csv
import json

import jsonschema
import pytest
import yaml
from conftest import ALEX

from areao1.core.schemas import SCHEMA_DIR
from areao1.criteria.case import Case
from areao1.resources import profiles_dir
from areao1.scaffold import validate_workspace
from areao1.schemas import build_schemas, schema_text

FILE_SCHEMAS = {
    "person.json": "person",
    "sources.json": "sources",
    "inbox.json": "inbox",
    "exhibits.json": "exhibits",
    "criteria.json": "criteria",
    "pipeline.json": "pipeline",
    "letters.json": "letters",
    "deadlines.json": "deadlines",
    "opportunities.json": "opportunities",
}


def load_schema(stem: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{stem}.schema.json").read_text())


@pytest.mark.parametrize("name", sorted(build_schemas()))
def test_committed_schemas_match_models(name):
    committed = (SCHEMA_DIR / name).read_text()
    assert committed == schema_text(build_schemas()[name]), (
        f"{name} is stale — run `python -m areao1.schemas`"
    )


@pytest.mark.parametrize("name", sorted(build_schemas()))
def test_schemas_are_valid_json_schema(name):
    jsonschema.Draft202012Validator.check_schema(load_schema(name.removesuffix(".schema.json")))


@pytest.mark.parametrize(("filename", "stem"), sorted(FILE_SCHEMAS.items()))
def test_demo_workspace_matches_schema(filename, stem):
    data = json.loads((ALEX / "data" / filename).read_text())
    jsonschema.validate(data, load_schema(stem))


def test_demo_config_and_metrics_match_schema():
    root = ALEX
    jsonschema.validate(yaml.safe_load((root / "areao1.yaml").read_text()), load_schema("areao1-config"))
    row_schema = load_schema("metric-row")
    with (root / "data" / "metrics.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    for row in rows:
        jsonschema.validate({**row, "value": float(row["value"])}, row_schema)


@pytest.mark.parametrize("path", sorted(profiles_dir().glob("*.yaml")), ids=lambda p: p.name)
def test_profiles_match_schema(path):
    jsonschema.validate(yaml.safe_load(path.read_text()), load_schema("profile"))


def test_demo_workspace_validates():
    assert validate_workspace(Case(ALEX)) == []


@pytest.mark.parametrize(
    ("name", "stem"),
    [("observations", "observation"), ("entities", "entity"), ("claims", "claim"), ("edges", "edge"),
     ("decisions", "decision")],
)  # fmt: skip
def test_demo_memory_lines_match_schema(name, stem):
    path = ALEX / "memory" / f"{name}.jsonl"
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert lines, f"demo memory/{name}.jsonl is empty"
    schema = load_schema(f"memory-{stem}")
    for line in lines:
        jsonschema.validate(line, schema)
