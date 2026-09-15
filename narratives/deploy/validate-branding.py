#!/usr/bin/env python3
"""Validate an instance's branding.json against schemas/branding.schema.json.

    python3 deploy/validate-branding.py config/branding.json

Run by deploy.sh before the config bucket is synced, and usable on its own.

Why this exists
---------------
The schema sets additionalProperties:false so that a typo'd key is an error
rather than a silently ignored one. Nothing enforced that at deploy time, and
the resulting failure is quiet in the worst way: a file carrying
`primary_color` instead of `colors.primary` deploys clean, the agent serves it,
/agent/brand echoes the instance name so branding looks applied -- and only the
colour is missing, from a key nothing ever reads. CI validated
agent-config.json with ajv; branding had no equivalent anywhere.

jsonschema is used when installed. It usually is not: the fallback below walks
the schema with the standard library and enforces the two rules that catch real
mistakes -- unknown keys where the schema forbids them, and missing required
keys. An earlier version simply skipped when jsonschema was absent, which is
the case on the machine this was written on, so it warned and uploaded the
broken file anyway. A check that quietly does nothing is worse than no check;
it reads like coverage.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "branding.schema.json"


def _suggest(key: str, properties: dict) -> str:
    """Point at a real property when the bad key obviously meant one."""
    stem = key.replace("_", " ").split()
    near = [
        name for name in properties
        if any(part and part in name for part in stem)
        or any(part and part in key for part in name.replace("_", " ").split())
    ]
    if not near:
        return ""
    return f" (did you mean {' or '.join(sorted(near)[:2])}?)"


def _resolve(spec, root):
    """Follow a local $ref. This schema keeps its shared shapes in $defs --
    link, metricsTile, metricsTab -- and those are where the required-key rules
    live, so a walk that does not follow $ref checks almost nothing."""
    seen = 0
    while isinstance(spec, dict) and "$ref" in spec and seen < 10:
        ref = spec["$ref"]
        if not ref.startswith("#/"):
            return spec
        target = root
        for part in ref[2:].split("/"):
            if not isinstance(target, dict) or part not in target:
                return spec
            target = target[part]
        spec = target
        seen += 1
    return spec


def _walk(node, spec, where, problems, root):
    """Enforce additionalProperties:false and required, recursively."""
    spec = _resolve(spec, root)
    if not isinstance(spec, dict):
        return

    # Arrays carry their element shape in items; branding's links and metrics
    # tiles are arrays of $ref'd objects, which is exactly where a typo lands.
    if isinstance(node, list):
        items = spec.get("items")
        if items:
            for index, element in enumerate(node):
                _walk(element, items, f"{where}[{index}].", problems, root)
        return

    if not isinstance(node, dict):
        return

    properties = spec.get("properties", {})
    if spec.get("additionalProperties") is False:
        for key in node:
            if key not in properties:
                problems.append(
                    f"{where}{key}: not a property in the schema{_suggest(key, properties)}"
                )
    for key in spec.get("required", []):
        if key not in node:
            problems.append(f"{where}{key}: required, but missing")
    for key, child in properties.items():
        if key in node:
            _walk(node[key], child, f"{where}{key}.", problems, root)


def validate(document, schema) -> list:
    try:
        import jsonschema
    except ImportError:
        problems = []
        _walk(document, schema, "", problems, schema)
        return problems

    return [
        f"{'.'.join(str(p) for p in err.path) or '(root)'}: {err.message}"
        for err in sorted(
            jsonschema.Draft7Validator(schema).iter_errors(document),
            key=lambda e: list(e.path),
        )
    ]


def main(argv) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path/to/branding.json>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    try:
        document = json.loads(path.read_text())
    except OSError as exc:
        print(f"  cannot read {path}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"  {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    schema = json.loads(SCHEMA_PATH.read_text())
    problems = validate(document, schema)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
