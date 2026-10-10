#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Validates a theme.json file against schemas/theme.schema.json.

    python3 deploy/validate_theme.py config/theme.json

Uses `jsonschema` when installed, and otherwise falls back to a standard-library
walk that checks `type`, `pattern`, `enum`, `additionalProperties: false`, and
`required` so validation runs even under a system `python3` without third-party
packages.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "theme.schema.json"
MAX_REF_DEPTH = 10


def _suggest(key: str, properties: dict[str, Any]) -> str:
    """Returns a hint naming schema properties that resemble an unknown key."""
    stem = key.replace("_", " ").split()
    near = [
        name
        for name in properties
        if any(part and part in name for part in stem)
        or any(part and part in key for part in name.replace("_", " ").split())
    ]
    if not near:
        return ""
    return f" (did you mean {' or '.join(sorted(near)[:2])}?)"


def _resolve(spec: Any, root: dict[str, Any]) -> Any:
    """Resolves a local `#/...` `$ref` chain against `root`."""
    seen = 0
    while isinstance(spec, dict) and "$ref" in spec and seen < MAX_REF_DEPTH:
        ref = spec["$ref"]
        if not ref.startswith("#/"):
            return spec
        target: Any = root
        for part in ref[2:].split("/"):
            if not isinstance(target, dict) or part not in target:
                return spec
            target = target[part]
        spec = target
        seen += 1
    return spec


def _matches_type(node: Any, expected: str) -> bool:
    """Returns whether `node` matches the JSON Schema `type` name."""
    if expected == "object":
        return isinstance(node, dict)
    if expected == "array":
        return isinstance(node, list)
    if expected == "string":
        return isinstance(node, str)
    if expected == "integer":
        return (isinstance(node, int) and not isinstance(node, bool)) or (
            isinstance(node, float) and node.is_integer()
        )
    if expected == "number":
        return isinstance(node, (int, float)) and not isinstance(node, bool)
    if expected == "boolean":
        return isinstance(node, bool)
    return True


def _walk(
    node: Any,
    spec: Any,
    where: str,
    problems: list[str],
    root: dict[str, Any],
) -> None:
    """Enforces `type`, `pattern`, `enum`, `additionalProperties`, and
    `required`.
    """
    spec = _resolve(spec, root)
    if not isinstance(spec, dict):
        return

    location = where.rstrip(".") or "(root)"
    expected_type = spec.get("type")
    if isinstance(expected_type, str) and not _matches_type(
        node, expected_type
    ):
        problems.append(f"{location}: expected {expected_type}")
        return

    pattern = spec.get("pattern")
    if (
        isinstance(pattern, str)
        and isinstance(node, str)
        and not re.search(pattern, node)
    ):
        problems.append(f"{location}: does not match {pattern}")

    enum = spec.get("enum")
    if isinstance(enum, list) and node not in enum:
        problems.append(f"{location}: must be one of {enum}")

    if isinstance(node, list):
        items = spec.get("items")
        if items:
            for index, element in enumerate(node):
                _walk(element, items, f"{where}[{index}].", problems, root)
        return

    if not isinstance(node, dict):
        return

    properties: dict[str, Any] = spec.get("properties", {})
    if spec.get("additionalProperties") is False:
        for key in node:
            if key not in properties:
                problems.append(
                    f"{where}{key}: not a property in the schema"
                    f"{_suggest(key, properties)}"
                )
    for key in spec.get("required", []):
        if key not in node:
            problems.append(f"{where}{key}: required, but missing")
    for key, child in properties.items():
        if key in node:
            _walk(node[key], child, f"{where}{key}.", problems, root)


def validate(document: Any, schema: dict[str, Any]) -> list[str]:
    """Validates `document` against `schema` and returns any violation messages.

    Args:
        document: The parsed JSON value from a theme file.
        schema: The parsed JSON Schema object.

    Returns:
        A list of human-readable violation strings, or an empty list if valid.
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        problems: list[str] = []
        _walk(document, schema, "", problems, schema)
        return problems

    return [
        f"{'.'.join(str(p) for p in err.path) or '(root)'}: {err.message}"
        for err in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(document),
            key=lambda e: list(e.path),
        )
    ]


def main(argv: list[str]) -> int:
    """Validates the JSON file at `argv[1]` and prints any errors to stderr.

    Args:
        argv: The command-line arguments (`[script_name, path_to_theme_json]`).

    Returns:
        An exit status code (`0` if valid, `1` on validation or I/O error, and
        `2` on invalid CLI arguments).
    """
    if len(argv) == 2 and argv[1] in ("-h", "--help"):
        print(f"usage: {argv[0]} <path/to/theme.json>")
        return 0
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path/to/theme.json>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"  cannot read {path}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"  {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    problems = validate(document, schema)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
