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

"""Unit tests for deploy/validate_theme.py."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import validate_theme


@pytest.fixture
def schema() -> dict[str, Any]:
    """Loads schemas/theme.schema.json once per test."""
    loaded: dict[str, Any] = json.loads(
        validate_theme.SCHEMA_PATH.read_text(encoding="utf-8")
    )
    return loaded


def test_validate_accepts_shipped_theme_files_under_both_validators(
    schema: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validates all shipped theme JSON files under jsonschema and stdlib."""
    # Test: Shipped theme files pass both jsonschema and the stdlib fallback.
    # Situation: defaults/theme.json and schemas/theme.*.json are validated with
    #   jsonschema installed and with jsonschema blocked in sys.modules.
    # Expectation: Both code paths return an empty violation list for all files.
    files = [
        validate_theme.REPO_ROOT / "defaults" / "theme.json",
        validate_theme.REPO_ROOT / "schemas" / "theme.example.json",
        validate_theme.REPO_ROOT / "schemas" / "theme.neutral.example.json",
        validate_theme.REPO_ROOT / "schemas" / "theme.base-dc.example.json",
    ]
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert validate_theme.validate(doc, schema) == []

    monkeypatch.setitem(sys.modules, "jsonschema", None)
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert validate_theme.validate(doc, schema) == []


def test_stdlib_fallback_rejects_unknown_key_with_suggestion(
    schema: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports unknown properties and suggests nearby schema keys."""
    # Test: Unknown root and nested keys in the stdlib fallback walker.
    # Situation: jsonschema is unavailable and the document contains
    #   `primary_color` at the root and a completely unrelated key.
    # Expectation: The walker flags both keys and suggests `colors` for
    #   `primary_color`.
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    problems = validate_theme.validate(
        {"primary_color": "#0B57D0", "zzz": 1},
        schema,
    )
    assert sorted(problems) == [
        "primary_color: not a property in the schema (did you mean colors?)",
        "zzz: not a property in the schema",
    ]


def test_stdlib_fallback_checks_type_required_pattern_enum_and_nested_paths(
    schema: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enforces type, required keys through $ref, regex patterns, and enums."""
    # Test: Type mismatch, $ref resolution, required fields, regex pattern, and
    #   enum checks in nested arrays.
    # Situation: jsonschema is unavailable and a document has a list for
    #   `splash_assets`, a navigation item missing `href`, a non-hex
    #   `colors.primary`, and a metrics tile with an invalid `type` enum value.
    # Expectation: Exactly those four violations are reported with their
    #   dotted/indexed paths.
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    doc = {
        "colors": {"primary": "blue"},
        "splash_assets": [],
        "navigation": [{"label": "Overview"}],
        "metrics": {
            "tabs": [
                {
                    "id": "econ",
                    "label": "Economy",
                    "tiles": [
                        {
                            "type": "donut",
                            "title": "GDP",
                            "variable": "Amount_EconomicActivity",
                            "place": "country/USA",
                        }
                    ],
                }
            ]
        },
    }
    problems = validate_theme.validate(doc, schema)
    assert sorted(problems) == [
        "colors.primary: does not match ^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$",
        (
            "metrics.tabs.[0].tiles.[0].type: must be one of "
            "['line', 'bar', 'map', 'ranking', 'highlight', 'scatter', 'pie', "
            "'gauge', 'slider']"
        ),
        "navigation.[0].href: required, but missing",
        "splash_assets: expected object",
    ]


_TAGLINE_SECTION = {"title": "Graph", "body": "Body."}


@pytest.mark.parametrize(
    "link",
    [
        {"text": "Graph", "sections": []},
        {"text": "", "sections": [_TAGLINE_SECTION]},
        {"text": "Graph", "sections": [{"title": "", "body": "Body."}]},
    ],
    ids=["no-sections", "empty-phrase", "empty-title"],
)
@pytest.mark.usefixtures("run_under_each_validator")
def test_tagline_link_rejects_empty_sections_and_strings(
    schema: dict[str, Any], link: dict[str, Any]
) -> None:
    """Enforces `minItems` and `minLength` on `tagline_link`."""
    # Test: The `minItems` and `minLength` keywords on `tagline_link`.
    # Situation: Under jsonschema and under the stdlib fallback, the theme's
    #   `tagline_link` has no sections, an empty phrase, or an empty section
    #   title.
    # Expectation: Validation reports a violation.
    assert validate_theme.validate({"tagline_link": link}, schema) != []


@pytest.mark.usefixtures("run_under_each_validator")
def test_tagline_link_accepts_minimal_link(schema: dict[str, Any]) -> None:
    """Accepts a `tagline_link` with a phrase and one titled section."""
    # Test: The smallest valid `tagline_link`.
    # Situation: Under jsonschema and under the stdlib fallback, the theme's
    #   `tagline_link` has a phrase and one section.
    # Expectation: Validation reports no violation, so the rejections above
    #   come from the empty values alone.
    link = {"text": "Graph", "sections": [_TAGLINE_SECTION]}
    assert validate_theme.validate({"tagline_link": link}, schema) == []


def test_matches_type_covers_all_json_schema_primitives() -> None:
    """Checks each JSON Schema primitive type in _matches_type."""
    # Test: Primitive type predicates in _matches_type.
    # Situation: Values of each Python type (dict, list, str, int, float, bool)
    #   are checked against object, array, string, integer, number, and boolean.
    # Expectation: Booleans are rejected for integer/number, integer-valued
    #   floats (10.0) are accepted for integer, and unknown type names return
    #   False.
    assert validate_theme._matches_type({}, "object") is True
    assert validate_theme._matches_type([], "object") is False
    assert validate_theme._matches_type([], "array") is True
    assert validate_theme._matches_type({}, "array") is False
    assert validate_theme._matches_type("x", "string") is True
    assert validate_theme._matches_type(1, "string") is False
    assert validate_theme._matches_type(10, "integer") is True
    assert validate_theme._matches_type(10.0, "integer") is True
    assert validate_theme._matches_type(10.5, "integer") is False
    assert validate_theme._matches_type(True, "integer") is False
    assert validate_theme._matches_type(10.5, "number") is True
    assert validate_theme._matches_type(False, "number") is False
    assert validate_theme._matches_type(True, "boolean") is True
    assert validate_theme._matches_type(1, "boolean") is False
    assert validate_theme._matches_type("anything", "custom") is False


def test_main_exit_codes(tmp_path: Path) -> None:
    """Verifies CLI exit codes for --help, bad args, I/O errors, and JSON."""
    # Test: CLI entry point exit status codes.
    # Situation: main() is called with --help, wrong arg count, a missing path,
    #   malformed JSON, an invalid theme document, and a valid theme document.
    # Expectation: Returns 0 for --help and valid JSON, 2 for wrong arg count,
    #   and 1 for missing file, malformed JSON, or schema violations.
    assert validate_theme.main(["validate_theme.py", "--help"]) == 0
    assert validate_theme.main(["validate_theme.py"]) == 2

    missing = tmp_path / "missing.json"
    assert validate_theme.main(["validate_theme.py", str(missing)]) == 1

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    assert validate_theme.main(["validate_theme.py", str(bad_json)]) == 1

    invalid_theme = tmp_path / "invalid.json"
    invalid_theme.write_text('{"splash_assets": []}', encoding="utf-8")
    assert validate_theme.main(["validate_theme.py", str(invalid_theme)]) == 1

    valid_theme = tmp_path / "valid.json"
    valid_theme.write_text('{"instance_name": "Acme"}', encoding="utf-8")
    assert validate_theme.main(["validate_theme.py", str(valid_theme)]) == 0


def _build_theme_with_value(field: str, value: str) -> dict[str, Any]:
    """Returns a theme document that sets one URL field to `value`."""
    if field == "navigation":
        return {"navigation": [{"label": "Link", "href": value}]}
    if field == "footer":
        return {"footer": {"links": [{"label": "Link", "href": value}]}}
    if field in ("thinking_indicator", "done_indicator"):
        return {"splash_assets": {field: value}}
    return {field: value}


_LINK_FIELDS = ["navigation", "logo_href", "footer"]
_ASSET_FIELDS = [
    "logo",
    "favicon",
    "thinking_indicator",
    "done_indicator",
]
_URL_FIELDS = [*_LINK_FIELDS, *_ASSET_FIELDS]
_UNSAFE_URLS = [
    "javascript:alert(1)",
    "data:image/svg+xml,<svg/>",
    "vbscript:msgbox(1)",
    "//evil.example/logo.png",
    "assets/logo.png",
    "/theme/logo\\evil.png",
    "https://cdn.example/\x00logo.png",
    "https://cdn.example/\x7flogo.png",
    "https://cdn.example/logo.png\n",
]
_SAFE_URLS = ["https://cdn.example/logo.png", "/theme/logo.png"]


@pytest.fixture(params=["jsonschema", "stdlib"])
def run_under_each_validator(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Parametrizes a test to run under jsonschema and the stdlib fallback."""
    mode: str = request.param
    if mode == "stdlib":
        monkeypatch.setitem(sys.modules, "jsonschema", None)
    return mode


@pytest.mark.parametrize("field", _URL_FIELDS)
@pytest.mark.parametrize("value", _UNSAFE_URLS)
@pytest.mark.usefixtures("run_under_each_validator")
def test_url_fields_reject_unsafe_values(
    schema: dict[str, Any], field: str, value: str
) -> None:
    """Rejects script, data, protocol-relative, and relative URL values."""
    # Test: URL patterns on the theme's link and asset fields.
    # Situation: Under jsonschema and under the stdlib fallback, one link or
    #   asset field holds a `javascript:`, `data:`, or `vbscript:` URL, a
    #   protocol-relative URL, or a relative path.
    # Expectation: Validation reports a violation for the field.
    problems = validate_theme.validate(
        _build_theme_with_value(field, value), schema
    )
    assert problems != []


@pytest.mark.parametrize("field", _URL_FIELDS)
@pytest.mark.parametrize("value", _SAFE_URLS)
@pytest.mark.usefixtures("run_under_each_validator")
def test_url_fields_accept_http_urls_and_root_paths(
    schema: dict[str, Any], field: str, value: str
) -> None:
    """Accepts an https URL and a single-slash path for every URL field."""
    # Test: URL patterns on the theme's link and asset fields.
    # Situation: Under jsonschema and under the stdlib fallback, one link or
    #   asset field holds an https URL or a root-relative path.
    # Expectation: Validation reports no violation.
    problems = validate_theme.validate(
        _build_theme_with_value(field, value), schema
    )
    assert problems == []


@pytest.mark.parametrize("field", _LINK_FIELDS)
@pytest.mark.usefixtures("run_under_each_validator")
def test_link_fields_accept_hash_routes(
    schema: dict[str, Any], field: str
) -> None:
    """Accepts a `#` hash route for the navigation and logo link targets."""
    # Test: Hash routes on link fields.
    # Situation: `navigation[].href` or `logo_href` holds `#/metrics`.
    # Expectation: Validation reports no violation.
    problems = validate_theme.validate(
        _build_theme_with_value(field, "#/metrics"), schema
    )
    assert problems == []


@pytest.mark.parametrize("field", _LINK_FIELDS)
@pytest.mark.parametrize("value", ["#/metrics\\evil", "#/metrics\x00"])
@pytest.mark.usefixtures("run_under_each_validator")
def test_link_fields_reject_malformed_hash_routes(
    schema: dict[str, Any], field: str, value: str
) -> None:
    """Rejects hash routes containing backslashes or control characters."""
    # Test: Malformed hash routes on link fields.
    # Situation: A link field holds a `#` route containing a backslash or an
    #   ASCII control character.
    # Expectation: Validation reports a violation for the field.
    problems = validate_theme.validate(
        _build_theme_with_value(field, value), schema
    )
    assert problems != []


@pytest.mark.parametrize("field", _ASSET_FIELDS)
@pytest.mark.usefixtures("run_under_each_validator")
def test_asset_fields_reject_hash_routes(
    schema: dict[str, Any], field: str
) -> None:
    """Rejects a `#` value in asset URL fields because the UI discards it."""
    # Test: Hash values on asset fields.
    # Situation: An asset field holds `#/metrics`.
    # Expectation: Validation reports a violation for the field.
    problems = validate_theme.validate(
        _build_theme_with_value(field, "#/metrics"), schema
    )
    assert problems != []
