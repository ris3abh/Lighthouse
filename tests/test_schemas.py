"""JSON Schemas are generated from the pydantic models; examples/ must validate against both."""

from __future__ import annotations

import csv
import json

import jsonschema
import pytest
import yaml

from lighthouse_gc.core.scaffold import validate_workspace
from lighthouse_gc.core.schemas import SCHEMA_DIR, build_schemas, schema_text
from lighthouse_gc.core.workspace import Workspace
from lighthouse_gc.resources import demo_workspace_dir, profiles_dir

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
        f"{name} is stale — run `python -m lighthouse_gc.core.schemas`"
    )


@pytest.mark.parametrize("name", sorted(build_schemas()))
def test_schemas_are_valid_json_schema(name):
    jsonschema.Draft202012Validator.check_schema(load_schema(name.removesuffix(".schema.json")))


@pytest.mark.parametrize(("filename", "stem"), sorted(FILE_SCHEMAS.items()))
def test_demo_workspace_matches_schema(filename, stem):
    data = json.loads((demo_workspace_dir() / "data" / filename).read_text())
    jsonschema.validate(data, load_schema(stem))


def test_demo_config_and_metrics_match_schema():
    root = demo_workspace_dir()
    jsonschema.validate(
        yaml.safe_load((root / "lighthouse.yaml").read_text()), load_schema("lighthouse-config")
    )
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
    assert validate_workspace(Workspace(demo_workspace_dir())) == []
