# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6,<7", "jsonschema>=4,<5"]
# ///
"""Validate config/ingestion.yml.

Usage: uv run scripts/validate_ingestion_config.py [path]

Checks the structure against a JSON schema (required fields, types,
expectation levels warn/drop/fail), then rules a schema can't express:
unique source names and target tables, relative paths, and pii_columns that
exist in schema_hints. Exits 1 on any error.
"""

import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

RULES = {"type": "object", "additionalProperties": {"type": "string", "minLength": 1}}

SCHEMA = {
    "type": "object",
    "required": ["version", "sources"],
    "additionalProperties": False,
    "properties": {
        "version": {"const": 1},
        "sources": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name",
                    "source_system",
                    "path",
                    "format",
                    "options",
                    "schema_hints",
                    "target_table",
                    "expectations",
                    "pii_columns",
                    "tags",
                ],
                "properties": {
                    "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                    "source_system": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                    "path": {"type": "string", "minLength": 1},
                    "format": {"enum": ["csv", "json", "parquet", "avro", "orc", "text", "binaryFile"]},
                    "options": {"type": "object", "additionalProperties": {"type": "string"}},
                    "schema_hints": {"type": "string", "minLength": 1},
                    "target_table": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                    "expectations": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"warn": RULES, "drop": RULES, "fail": RULES},
                    },
                    "pii_columns": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "tags": {"type": "object", "additionalProperties": {"type": "string"}},
                },
            },
        },
    },
}


def hint_columns(schema_hints: str) -> list[str]:
    """Column names from a schema hint like "id BIGINT, price DECIMAL(10,2)"."""
    # Split on commas outside parentheses, so DECIMAL(10,2) stays whole.
    parts = re.split(r",(?![^()]*\))", schema_hints)
    return [p.strip().split()[0].strip("`").lower() for p in parts if p.strip()]


def validate(path: Path) -> list[str]:
    config = yaml.safe_load(path.read_text())
    errors = [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in Draft202012Validator(SCHEMA).iter_errors(config)
    ]
    if errors:
        return errors

    seen_names: set[str] = set()
    seen_targets: set[str] = set()
    for source in config["sources"]:
        name = source["name"]
        if name in seen_names:
            errors.append(f"{name}: duplicate source name")
        seen_names.add(name)
        if source["target_table"] in seen_targets:
            errors.append(f"{name}: duplicate target_table {source['target_table']!r}")
        seen_targets.add(source["target_table"])

        if source["path"].startswith("/") or "://" in source["path"]:
            errors.append(f"{name}: path must be relative to the landing root, got {source['path']!r}")

        columns = set(hint_columns(source["schema_hints"]))
        for column in source["pii_columns"]:
            if column.lower() not in columns:
                errors.append(f"{name}: pii column {column!r} is not in schema_hints")

        rule_names = [rule for rules in source["expectations"].values() for rule in rules]
        for rule in {r for r in rule_names if rule_names.count(r) > 1}:
            errors.append(f"{name}: expectation {rule!r} appears in more than one level")
    return errors


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "config/ingestion.yml")
    errors = validate(path)
    for error in errors:
        print(f"ERROR {path}: {error}")
    if errors:
        return 1
    print(f"OK {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
