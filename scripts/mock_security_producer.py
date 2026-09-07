#!/usr/bin/env python3
"""Emit local JSONL records for security topic and sink testing.

This script deliberately does not connect to Kafka. It validates the fixture's
contract-level fields, then emits a small topic/key/value envelope to stdout or
to --output. Use --no-validate only when generating an invalid-message sample.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOPICS = {
    "luck.security-events": ROOT / "contracts" / "luck.security-events.v1.schema.json",
    "luck.masked-logs": ROOT / "contracts" / "luck.masked-logs.v1.schema.json",
}


def fail(message: str) -> None:
    raise ValueError(message)


@lru_cache(maxsize=None)
def load_schema(topic: str) -> dict[str, Any]:
    with TOPICS[topic].open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        fail(f"only local schema references are supported: {reference}")
    target: Any = root
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        target = target[token]
    if not isinstance(target, dict):
        fail(f"schema reference is not an object: {reference}")
    return target


def matches_type(value: Any, expected: str) -> bool:
    checks = {
        "null": lambda item: item is None,
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    if expected not in checks:
        fail(f"unsupported schema type: {expected}")
    return checks[expected](value)


def validate_datetime(value: str, path: str) -> None:
    if "T" not in value or not value.endswith("Z"):
        fail(f"{path} must be an ISO 8601 UTC date-time ending with Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{path} must be a valid ISO 8601 date-time") from exc
    if parsed.utcoffset() != timedelta(0):
        fail(f"{path} must use UTC")


def validate_value(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> None:
    if "$ref" in schema:
        validate_value(value, resolve_ref(root, schema["$ref"]), root, path)
        return

    if "const" in schema and value != schema["const"]:
        fail(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        fail(f"{path} must be one of {schema['enum']}")

    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(matches_type(value, item) for item in expected_types):
            fail(f"{path} must have type {expected_types}")
    if value is None:
        return

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = [field for field in schema.get("required", []) if field not in value]
        if missing:
            fail(f"{path} is missing required fields: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                fail(f"{path} contains additional fields: {', '.join(extras)}")
        for field, field_value in value.items():
            if field in properties:
                validate_value(field_value, properties[field], root, f"{path}.{field}")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            fail(f"{path} must contain at least {schema['minItems']} items")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                validate_value(item, item_schema, root, f"{path}[{index}]")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            fail(f"{path} is shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            fail(f"{path} is longer than {schema['maxLength']} characters")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            fail(f"{path} does not match {schema['pattern']}")
        if schema.get("format") == "date-time":
            validate_datetime(value, path)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            fail(f"{path} is less than {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            fail(f"{path} is greater than {schema['maximum']}")


def validate(topic: str, record: dict[str, Any]) -> None:
    schema = load_schema(topic)
    validate_value(record, schema, schema, "$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, choices=sorted(TOPICS))
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--repeat", type=int, default=1, help="number of records to emit")
    parser.add_argument("--output", type=Path, help="write JSONL instead of stdout")
    parser.add_argument("--no-validate", action="store_true", help="emit intentionally invalid fixtures")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repeat < 1:
        fail("--repeat must be at least 1")
    fixture = args.fixture if args.fixture.is_absolute() else ROOT / args.fixture
    with fixture.open(encoding="utf-8") as handle:
        record = json.load(handle)
    if not args.no_validate:
        validate(args.topic, record)

    lines = []
    for sequence in range(args.repeat):
        lines.append(json.dumps({
            "topic": args.topic,
            "key": record.get("event_id"),
            "sequence": sequence + 1,
            "value": record,
        }, ensure_ascii=False))
    rendered = "\n".join(lines) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"mock producer error: {exc}", file=sys.stderr)
        raise SystemExit(2)
